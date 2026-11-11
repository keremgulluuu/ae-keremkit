#!/usr/bin/env python3
"""KeremKit transcript tool - review, correct and de-duplicate a Whisper transcript (stdlib only).

  review   W.json [--min-prob 0.6] [--from S] [--to S] [--cutlist C.json [--at S]]
           compact transcript, one utterance per line ("mm:ss.s | text"), doubtful words
           marked as word(?0.42). This is what Claude reads to spot mis-heard words.
  words    W.json [--cutlist C.json [--at S]]
           every word with its index ("12:Claude"), one utterance per line - anchors for fixes and edit plans
  fix      W.json --corrections C.json -o W.fixed.json
           apply word corrections, anchored by time and the old text, keeping timestamps.
           C.json: [{"time": 12.4, "old": "Kılavd", "new": "Claude"}, {"index": 28, "new": "Grok"}, ...]
           old/new may be several words ("after a fax" -> "After Effects").
  repeats  W.json [--window 15] [--pause 0.45] -o repeats.json
           find retakes and false starts (a phrase said again shortly after), stutters
           and filler sounds; high-confidence ones are marked apply=true, the rest are
           listed for the user. Feed the file to `cutlist.py build --remove`.
  accept   repeats.json --ids 3,5 [--reject 4]   change which removals apply
  bursts   W.json --media FILE --wav-dir DIR -o bursts.json
           hidden retakes: Whisper can write several takes ONCE and stretch a word over them. Finds words
           longer than 1.2 s (or very slow utterances) that cover 2+ speech bursts, and cuts each burst of
           those spots into its own wav. Transcribe every wav alone, fill "text"/"words", then:
  retakes  bursts.json [--into repeats.json]
           a burst whose end repeats the start of the next burst is a retake (the later take is kept)

Times are source seconds of the recording the JSON belongs to.
"""
import argparse
import difflib
import json
import os
import re
import sys
import unicodedata

FILLERS = {"ııı", "ıı", "ı", "eee", "ee", "eh", "ehm", "hmm", "hm", "mmm", "mm", "um", "uh", "uhm", "erm", "ah", "aa", "aaa",
           "ımm", "şey şey"}
SENT_END = re.compile(r"[.!?…]+[\"')\]]*$")
_TR = str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})
_ASCII = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(w):
    w = unicodedata.normalize("NFC", w).translate(_TR).lower()
    return re.sub(r"[^\w]", "", w.translate(_ASCII))


def mmss(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m):02d}:{s:04.1f}"


# ---------------------------------------------------------------- whisper json
def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data


def words_of(data):
    """Flat list of word dicts (references into data, so edits write through)."""
    if isinstance(data, list):
        return data
    if data.get("segments"):
        out = []
        for seg in data["segments"]:
            out.extend(seg.get("words") or [])
        return out
    return data.get("word_segments") or data.get("words") or []


def text_of(w):
    return (w.get("word") or w.get("text") or "").strip()


def utterances(ws, pause):
    groups, cur = [], []
    for i, w in enumerate(ws):
        if not text_of(w):
            continue
        cur.append(i)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        gap = (nxt.get("start", 0) - w.get("end", 0)) if nxt else 99
        if nxt is None or gap >= pause or SENT_END.search(text_of(w)):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


# ---------------------------------------------------------------- review
def to_out(cut, t):
    for seg in cut["segments"]:
        if seg["src_in"] - 1e-6 <= t <= seg["src_out"] + 1e-6:
            return seg["out_in"] + (t - seg["src_in"])
    return None


def cmd_words(a):
    """Every word with its index - cheap anchors for corrections and edit plans."""
    data = load(a.words)
    ws = words_of(data)
    cut = load(a.cutlist) if a.cutlist else None
    shown = 0
    for g in utterances(ws, a.pause):
        items, t0 = [], None
        for i in g:
            w = ws[i]
            if cut:
                o = to_out(cut, (w.get("start", 0) + w.get("end", 0)) / 2)
                if o is None:
                    continue
                t = o + a.at
            else:
                t = w.get("start", 0)
            t0 = t if t0 is None else t0
            items.append(f"{i}:{text_of(w)}")
        if items:
            print(f"{mmss(t0)} | {' '.join(items)}")
            shown += len(items)
    print(f"-- words={len(ws)} shown={shown}" + (" (cut parts hidden, timeline times)" if cut else ""))


def cmd_review(a):
    data = load(a.words)
    ws = words_of(data)
    cut = load(a.cutlist) if a.cutlist else None
    flagged = 0
    for g in utterances(ws, a.pause):
        s, e = ws[g[0]].get("start", 0), ws[g[-1]].get("end", 0)
        if cut:
            # show output (timeline) times; utterances that were cut out are skipped
            mids = [to_out(cut, (ws[i].get("start", 0) + ws[i].get("end", 0)) / 2) for i in g]
            kept = [i for i, o in zip(g, mids) if o is not None]
            if not kept:
                continue
            g = kept
            # sentence start = start of its first kept word, end = end of its last kept word (timeline time)
            first, last = ws[g[0]], ws[g[-1]]
            s = to_out(cut, first.get("start", 0))
            s = (s if s is not None else to_out(cut, (first.get("start", 0) + first.get("end", 0)) / 2)) + a.at
            e = to_out(cut, last.get("end", 0))
            e = (e if e is not None else to_out(cut, (last.get("start", 0) + last.get("end", 0)) / 2)) + a.at
        if (a.frm is not None and e < a.frm) or (a.to is not None and s > a.to):
            continue
        parts = []
        for i in g:
            t = text_of(ws[i])
            p = ws[i].get("probability", ws[i].get("score"))
            if p is not None and p < a.min_prob:
                parts.append(f"{t}(?{p:.2f})")
                flagged += 1
            else:
                parts.append(t)
        print(f"{mmss(s)} | {' '.join(parts)}")
    lang = data.get("language") if isinstance(data, dict) else None
    print(f"-- words={len(ws)} doubtful={flagged} language={lang or '?'}")


# ---------------------------------------------------------------- fix
def cmd_fix(a):
    data = load(a.words)
    ws = words_of(data)
    corr = load(a.corrections)
    corr = corr.get("corrections", corr) if isinstance(corr, dict) else corr
    applied, missed = [], []
    # index-based fixes first, from the end so earlier indices stay valid
    by_index = sorted((c for c in corr if "index" in c), key=lambda c: -int(c["index"]))
    if by_index and isinstance(data, dict) and data.get("_kk_index_changed") and not a.force_index:
        sys.exit("ERROR: an earlier fix added or deleted words in this file, so word indices no longer match "
                 "`transcript.py words` of the raw file. Anchor these fixes by time + old text, or apply every index "
                 "fix in ONE pass on the raw file (--force-index only if the indices were taken from THIS file).")
    for c in by_index:
        i = int(c["index"])
        if not 0 <= i < len(ws):
            missed.append({"time": 0, "old": f"#{i}"})
            continue
        w = ws[i]
        lead = " " if (w.get("word") or "").startswith(" ") else ""
        tail = re.search(r"[.,!?;:…]+$", text_of(w))
        new = str(c["new"]).split()
        s0, e0 = w.get("start", 0), w.get("end", 0)
        items = []
        for k, nw in enumerate(new):
            txt = nw + (tail.group(0) if tail and k == len(new) - 1 and not re.search(r"[.,!?;:…]$", nw) else "")
            item = {"word": (lead if k == 0 else " ") + txt, "start": round(s0 + (e0 - s0) * k / len(new), 3),
                    "end": round(s0 + (e0 - s0) * (k + 1) / len(new), 3), "probability": 1.0}
            if k == 0:
                item["corrected_from"] = text_of(w)
            items.append(item)
        old_text = text_of(w)
        if len(items) != 1 and isinstance(data, dict):
            data["_kk_index_changed"] = True
        replace_span(data, [w], items)
        ws = words_of(data)
        applied.append((s0, f"#{i} {old_text}", " ".join(new)))
    for c in corr:
        if "index" in c:
            continue
        old = [fold(x) for x in str(c["old"]).split()]
        new = str(c["new"]).split()
        t = float(c["time"])
        best, best_d = None, None
        for i in range(len(ws) - len(old) + 1):
            cand = [fold(text_of(ws[i + k])) for k in range(len(old))]
            ratio = difflib.SequenceMatcher(None, " ".join(cand), " ".join(old)).ratio()
            if ratio < 0.8:
                continue
            d = abs(ws[i].get("start", 0) - t)
            if d <= a.tolerance and (best_d is None or d < best_d):
                best, best_d = i, d
        if best is None:
            missed.append(c)
            continue
        span = ws[best:best + len(old)]
        s, e = span[0].get("start", t), span[-1].get("end", t)
        lead = " " if (span[0].get("word") or "").startswith(" ") else ""
        # keep trailing punctuation of the last old word
        tail = re.search(r"[.,!?;:…]+$", text_of(span[-1]))
        new_words = []
        for k, nw in enumerate(new):
            ns = s + (e - s) * k / len(new)
            ne = s + (e - s) * (k + 1) / len(new)
            txt = nw + (tail.group(0) if tail and k == len(new) - 1 and not re.search(r"[.,!?;:…]$", nw) else "")
            item = {"word": (lead if k == 0 else " ") + txt, "start": round(ns, 3), "end": round(ne, 3),
                    "probability": 1.0, "corrected_from": " ".join(text_of(x) for x in span) if k == 0 else None}
            new_words.append({k2: v for k2, v in item.items() if v is not None})
        # write back into the owning segment list
        if len(new_words) != len(span) and isinstance(data, dict):
            data["_kk_index_changed"] = True
        replace_span(data, span, new_words)
        ws = words_of(data)
        applied.append((s, " ".join(text_of(x) for x in span), " ".join(new)))
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    for s, o, n in applied:
        print(f"{mmss(s)} - {o} - {n}")
    for c in missed:
        print(f"NOT_FOUND {mmss(float(c['time']))} - {c['old']}")
    print(f"OK applied={len(applied)} not_found={len(missed)} -> {a.output}")


def replace_span(data, span, new_words):
    lists = [seg["words"] for seg in data.get("segments", []) if seg.get("words")] if isinstance(data, dict) else [data]
    if isinstance(data, dict) and not lists:
        lists = [data.get("word_segments") or data.get("words")]
    ids = {id(x) for x in span}
    for lst in lists:
        idx = [i for i, w in enumerate(lst) if id(w) in ids]
        if idx:
            first = idx[0]
            for i in reversed(idx):
                del lst[i]
            for k, nw in enumerate(new_words):
                lst.insert(first + k, nw)
            return
    raise RuntimeError("span not found")


# ---------------------------------------------------------------- repeats
TAG = re.compile(r"^\[[^\]]*\]$")          # verbatim models write sounds as [laughter], [UH], [sniff]
TAG_FILLERS = {"[uh]", "[um]", "[uhm]", "[eh]", "[ah]", "[hmm]"}


def cmd_repeats(a):
    ws = []
    for w in words_of(load(a.words)):
        t = text_of(w)
        if not t:
            continue
        if TAG.match(t) and t.lower() not in TAG_FILLERS:
            continue                          # laughter, sniff, breath: not words, the silence cut handles them
        ws.append(w)
    toks = [fold(text_of(w)) for w in ws]
    found = []

    def add(i0, i1, kind, conf, kept_from, kept_to):
        if i1 < i0:
            return
        s = ws[i0].get("start", 0)
        # cut up to the start of the kept take so no gap is left in between
        e = ws[kept_from]["start"] if kept_from is not None else ws[i1].get("end", s)
        found.append({"src_in": round(s, 3), "src_out": round(e, 3), "kind": kind, "confidence": conf,
                      "apply": conf == "high", "removed": " ".join(text_of(ws[k]) for k in range(i0, i1 + 1)),
                      "kept": " ".join(text_of(ws[k]) for k in range(kept_from, kept_to + 1)) if kept_from is not None else "",
                      "word_range": [i0, i1]})

    # 1) filler sounds
    for i, t in enumerate(toks):
        if t in {fold(f) for f in FILLERS} or text_of(ws[i]).lower() in TAG_FILLERS:
            add(i, i, "filler", "high", None, None)

    # 1b) restarts at a cut-off word: verbatim transcripts mark a broken word with "-" ("ürete-"). The words
    #     before it are said again right after -> everything from the first repeated word to the cut-off goes.
    prev_cut = -1
    for c, w in enumerate(ws):
        if not text_of(w).rstrip().endswith("-") or c + 1 >= len(ws):
            continue
        after = toks[c + 1:c + 12]
        best = None
        lo = max(prev_cut + 1, c - 10)
        for j in range(c - 1, lo - 1, -1):         # never reach back over a sentence end
            if SENT_END.search(text_of(ws[j])):
                lo = j + 1
                break
        for k in range(lo, c):
            before = toks[k:c]
            head = after[:len(before) + 1]
            m = sum(b.size for b in difflib.SequenceMatcher(None, before, head).get_matching_blocks())
            # the new take may drop a leading particle ("ya bunu..." -> "bunu...")
            starts_alike = before and (before[0] in head[:2] or (len(before) > 1 and before[1] == head[0]))
            if starts_alike and m >= max(0.6 * len(before), min(2, len(before))):
                best = k
                break                          # earliest start = the longest repeated stretch
        if best is None:
            nxt = toks[c + 1] if c + 1 < len(toks) else ""
            stem = fold(text_of(w).rstrip("-"))
            if stem and nxt.startswith(stem):    # "anla- anlaştığınız": only the broken word
                best = c
        if best is not None:
            add(best, c, "restart", "high", c + 1, min(c + 6, len(ws) - 1))
            prev_cut = c

    # 2) restarted sentences: an utterance that is (nearly) the beginning of a later one
    groups = utterances(ws, a.pause)
    for gi, g in enumerate(groups):
        if len(g) < 2:
            continue
        u = [toks[i] for i in g]
        for gj in range(gi + 1, min(gi + 4, len(groups))):
            h = groups[gj]
            if ws[h[0]].get("start", 0) - ws[g[-1]].get("end", 0) > a.window:
                break
            v = [toks[i] for i in h]
            head = v[:len(u)]
            # compare as text so a slightly different word ending still counts ("Kılavd" / "Kılavd'u")
            ratio = difflib.SequenceMatcher(None, " ".join(u), " ".join(head)).ratio()
            if len(v) >= len(u) and ratio >= 0.75:
                add(g[0], g[-1], "retake", "high" if ratio >= 0.85 and len(u) >= 3 else "low", h[0], h[-1])
                break

    # 3) repeated phrase inside the flow: "bugün size bugün size şunu"
    covered = set()
    for r in found:
        covered.update(range(r["word_range"][0], r["word_range"][1] + 1))
    i = 0
    while i < len(toks):
        hit = False
        for n in range(min(6, (len(toks) - i) // 2), 0, -1):
            a_, b_ = toks[i:i + n], toks[i + n:i + 2 * n]
            if a_ == b_ and all(a_) and not covered.intersection(range(i, i + 2 * n)):
                gap = ws[i + n].get("start", 0) - ws[i + n - 1].get("end", 0)
                if n == 1:
                    # single-word doubles are often meant ("çok çok", "yavaş yavaş") - ask, unless a clear stutter
                    conf = "high" if gap >= 0.25 and len(a_[0]) <= 3 else "low"
                    kind = "stutter"
                else:
                    conf, kind = "high", "repeat"
                add(i, i + n - 1, kind, conf, i + n, i + 2 * n - 1)
                covered.update(range(i, i + 2 * n))
                i += n
                hit = True
                break
        if not hit:
            i += 1

    found.sort(key=lambda r: r["src_in"])
    for k, r in enumerate(found, 1):
        r["id"] = k
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump({"words_file": os.path.abspath(a.words), "removals": found}, f, ensure_ascii=False, indent=1)
    for r in found:
        mark = "AUTO" if r["apply"] else "ASK "
        kept = f" -> keeps \"{r['kept']}\"" if r["kept"] else ""
        print(f"{r['id']}\t{mark}\t{mmss(r['src_in'])}-{mmss(r['src_out'])}\t{r['kind']}\t\"{r['removed']}\"{kept}")
    auto = sum(r["apply"] for r in found)
    print(f"OK found={len(found)} auto={auto} ask={len(found) - auto} -> {a.output}")


# ---------------------------------------------------------------- hidden retakes
HALLUCINATIONS = {"altyazi mk", "altyazi m k", "abone olmayi unutmayin", "izlediginiz icin tesekkurler",
                  "thanks for watching", "subtitles by the amaraorg community", "thank you"}


def speech_bursts(media, words, rel_db=-10.0, min_silence=0.15):
    """Sounding stretches of the recording, split by silences >= min_silence (threshold relative to the speaker)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import cutlist  # noqa: E402  (sibling kit tool: audio envelope + silence detection)
    sil, thr = cutlist.detect_silences(media, min_silence, None, [[s, e] for s, e in words], rel_db)
    if sil is None:
        sys.exit("ERROR: needs ffmpeg and an audio stream")
    dur = len(cutlist.LAST["env"]) * cutlist.LAST["hop"]
    out, t = [], 0.0
    for x, y in sil:
        if x - t > 0.08:
            out.append([round(t, 3), round(x, 3)])
        t = y
    if dur - t > 0.08:
        out.append([round(t, 3), round(dur, 3)])
    return out, thr


def cmd_bursts(a):
    ws = [w for w in words_of(load(a.words)) if text_of(w) and w.get("start") is not None]
    spans = [(w["start"], w.get("end", w["start"])) for w in ws]
    bursts, thr = speech_bursts(a.media, spans, a.rel_db)

    def idx(t):
        return next((k for k, (x, y) in enumerate(bursts) if x - 0.02 <= t <= y + 0.02),
                    next((k for k, (x, y) in enumerate(bursts) if x > t), len(bursts) - 1))
    reasons, ranges = [], []
    for w in ws:
        s, e = w["start"], w.get("end", w["start"])
        i0, i1 = idx(s), idx(e)
        if e - s > a.max_word and i1 > i0:
            reasons.append(f"{mmss(s)} \"{text_of(w)}\" {e - s:.2f}s over {i1 - i0 + 1} bursts")
            ranges.append([i0, min(i1 + 1, len(bursts) - 1)])
    for g in utterances(ws, 0.45):
        s, e = ws[g[0]]["start"], ws[g[-1]].get("end", ws[g[-1]]["start"])
        i0, i1 = idx(s), idx(e)
        if len(g) >= 3 and (e - s) / len(g) > a.per_word and i1 > i0:
            reasons.append(f"{mmss(s)} utterance {len(g)} words in {e - s:.1f}s over {i1 - i0 + 1} bursts")
            ranges.append([i0, min(i1 + 1, len(bursts) - 1)])
    ranges.sort()
    groups = []
    for r in ranges:
        if groups and r[0] <= groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], r[1])
        else:
            groups.append(list(r))
    os.makedirs(a.wav_dir, exist_ok=True)
    manifest = {"media": os.path.abspath(a.media), "words_file": os.path.abspath(a.words), "threshold_db": round(thr, 1),
                "groups": []}
    import subprocess
    for gi, (i0, i1) in enumerate(groups, 1):
        items = []
        for k in range(i0, i1 + 1):
            x, y = bursts[k]
            wav = os.path.join(os.path.abspath(a.wav_dir), f"g{gi:02d}_b{k:04d}.wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, x - 0.1):.3f}", "-to", f"{y + 0.1:.3f}",
                            "-i", a.media, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
            items.append({"start": x, "end": y, "offset": round(max(0, x - 0.1), 3), "wav": wav, "text": None, "words": None})
        manifest["groups"].append({"id": gi, "bursts": items})
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    for r in reasons:
        print("SUSPECT " + r)
    print(f"OK groups={len(groups)} bursts={sum(len(g['bursts']) for g in manifest['groups'])} -> {a.output}"
          + ("" if groups else " (no hidden retakes suspected)"))
    if groups:
        print("NEXT transcribe each burst wav ON ITS OWN (condition_on_previous_text=False, word timestamps), fill "
              "'text' and 'words' [{w,s,e} in source seconds = offset + time], then: transcript.py retakes")


def _toks(text):
    return [t for t in (fold(x) for x in (text or "").split()) if t]


def cmd_retakes(a):
    m = load(a.manifest)
    found = []
    for g in m["groups"]:
        bs = [b for b in g["bursts"] if b.get("text") is not None]
        if len(bs) != len(g["bursts"]):
            sys.exit(f"ERROR: group {g['id']} has bursts without text - transcribe them first")
        live = [b for b in bs if b["end"] - b["start"] >= 0.25 and " ".join(_toks(b["text"])) not in HALLUCINATIONS
                and _toks(b["text"])]
        done_until = -1.0
        for n, b in enumerate(live):
            if b["start"] < done_until:
                continue
            ti = _toks(b["text"])
            best, nxt = 0, None
            # the next take may come one burst later (a number or a word said alone in between)
            for cand in live[n + 1:n + 3]:
                tj = _toks(cand["text"])
                cut_off = b["text"].rstrip().endswith(("...", "…", "-")) or (
                    tj and any(t.startswith(ti[-1]) and t != ti[-1] for t in tj[:len(ti) + 2]))
                core = ti[:-1] if cut_off and len(ti) > 1 else ti
                for L in range(1, len(core) + 1):
                    suf = core[-L:]
                    head = tj[:L + 1]
                    matched = sum(blk.size for blk in difflib.SequenceMatcher(None, suf, head).get_matching_blocks())
                    if matched >= max(0.6 * L, min(2, L)) and (L > 1 or len(suf[0]) >= 4) and L > best:
                        best, nxt, best_core = L, cand, core
                if nxt is not None:
                    break
            if not best:
                continue
            core = best_core
            # remove from the first repeated word of this burst to the start of the next take
            start = b["start"]
            words = b.get("words") or []
            if best < len(core) and len(words) >= len(ti):
                start = words[len(core) - best]["s"]
            done_until = nxt["start"]
            found.append({"src_in": round(start, 3), "src_out": round(nxt["start"], 3), "kind": "hidden-retake",
                          "confidence": "high", "apply": True, "removed": b["text"].strip(),
                          "kept": nxt["text"].strip()})
    if a.into:
        data = load(a.into)
        rem = [r for r in data["removals"] if r.get("kind") != "hidden-retake"] + found
        rem.sort(key=lambda r: r["src_in"])
        for k, r in enumerate(rem, 1):
            r["id"] = k
        data["removals"] = rem
        out = a.into
    else:
        for k, r in enumerate(found, 1):
            r["id"] = k
        data = {"words_file": m.get("words_file"), "removals": found}
        out = a.output or os.path.splitext(a.manifest)[0] + ".retakes.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for r in found:
        print(f"RETAKE\t{mmss(r['src_in'])}-{mmss(r['src_out'])}\t\"{r['removed']}\" -> keeps \"{r['kept'][:60]}\"")
    print(f"OK hidden_retakes={len(found)} -> {out}")


def cmd_accept(a):
    data = load(a.file)
    ids = {int(x) for x in (a.ids or "").split(",") if x.strip()}
    rej = {int(x) for x in (a.reject or "").split(",") if x.strip()}
    for r in data["removals"]:
        if r["id"] in ids:
            r["apply"] = True
        if r["id"] in rej:
            r["apply"] = False
    with open(a.file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"OK apply={sum(r['apply'] for r in data['removals'])} of {len(data['removals'])}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("review")
    r.add_argument("words")
    r.add_argument("--min-prob", type=float, default=0.6)
    r.add_argument("--pause", type=float, default=0.6)
    r.add_argument("--from", dest="frm", type=float)
    r.add_argument("--to", type=float)
    r.add_argument("--cutlist", help="print timeline (output) times and skip what was cut - for chapters")
    r.add_argument("--at", type=float, default=0.0, help="where the cut file starts on the timeline (s)")
    w = sp.add_parser("words")
    w.add_argument("words")
    w.add_argument("--cutlist")
    w.add_argument("--at", type=float, default=0.0)
    w.add_argument("--pause", type=float, default=0.6)
    f = sp.add_parser("fix")
    f.add_argument("words")
    f.add_argument("--corrections", required=True)
    f.add_argument("--tolerance", type=float, default=1.5, help="max distance (s) between given time and the word")
    f.add_argument("-o", "--output", required=True)
    f.add_argument("--force-index", action="store_true",
                   help="allow index fixes on a file whose word count was changed by an earlier fix")
    p = sp.add_parser("repeats")
    p.add_argument("words")
    p.add_argument("--window", type=float, default=15.0, help="how far apart a retake can be (s)")
    p.add_argument("--pause", type=float, default=0.45, help="pause that separates utterances (s)")
    p.add_argument("-o", "--output", required=True)
    c = sp.add_parser("accept")
    c.add_argument("file")
    c.add_argument("--ids")
    c.add_argument("--reject")
    b = sp.add_parser("bursts")
    b.add_argument("words")
    b.add_argument("--media", required=True)
    b.add_argument("--max-word", type=float, default=1.2, help="a word longer than this over 2+ bursts is suspect (s)")
    b.add_argument("--per-word", type=float, default=0.6, help="an utterance slower than this per word is suspect (s)")
    b.add_argument("--rel-db", type=float, default=-10.0)
    b.add_argument("--wav-dir", required=True, help="where the burst wav pieces go")
    b.add_argument("-o", "--output", required=True)
    rt = sp.add_parser("retakes")
    rt.add_argument("manifest")
    rt.add_argument("--into", help="add the hidden retakes to this repeats.json (for cutlist.py build --remove)")
    rt.add_argument("-o", "--output")
    a = ap.parse_args()
    {"words": cmd_words, "review": cmd_review, "fix": cmd_fix, "repeats": cmd_repeats, "accept": cmd_accept,
     "bursts": cmd_bursts, "retakes": cmd_retakes}[a.cmd](a)


if __name__ == "__main__":
    main()
