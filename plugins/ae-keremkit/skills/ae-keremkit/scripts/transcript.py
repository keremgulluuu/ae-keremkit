#!/usr/bin/env python3
"""KeremKit transcript tool - review, correct and de-duplicate a Whisper transcript (stdlib only).

  review   W.json [--min-prob 0.6] [--from S] [--to S] [--cutlist C.json [--at S]]
           compact transcript, one utterance per line ("mm:ss.s | text"), doubtful words
           marked as word(?0.42). This is what Claude reads to spot mis-heard words.
  fix      W.json --corrections C.json -o W.fixed.json
           apply word corrections, anchored by time and the old text, keeping timestamps.
           C.json: [{"time": 12.4, "old": "Kılavd", "new": "Claude"}, ...]
           old/new may be several words ("after a fax" -> "After Effects").
  repeats  W.json [--window 15] [--pause 0.45] -o repeats.json
           find retakes and false starts (a phrase said again shortly after), stutters
           and filler sounds; high-confidence ones are marked apply=true, the rest are
           listed for the user. Feed the file to `cutlist.py build --remove`.
  accept   repeats.json --ids 3,5 [--reject 4]   change which removals apply

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


def cmd_review(a):
    data = load(a.words)
    ws = words_of(data)
    cut = load(a.cutlist) if a.cutlist else None
    flagged = 0
    for g in utterances(ws, a.pause):
        s, e = ws[g[0]].get("start", 0), ws[g[-1]].get("end", 0)
        if cut:
            # show output (timeline) times; utterances that were cut out are skipped
            outs = [to_out(cut, (ws[i].get("start", 0) + ws[i].get("end", 0)) / 2) for i in g]
            kept = [i for i, o in zip(g, outs) if o is not None]
            if not kept:
                continue
            g = kept
            s = next(o for o in outs if o is not None) + a.at
            e = s
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
    for c in corr:
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
def cmd_repeats(a):
    ws = [w for w in words_of(load(a.words)) if text_of(w)]
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
        if t in {fold(f) for f in FILLERS}:
            add(i, i, "filler", "high", None, None)

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
    f = sp.add_parser("fix")
    f.add_argument("words")
    f.add_argument("--corrections", required=True)
    f.add_argument("--tolerance", type=float, default=1.5, help="max distance (s) between given time and the word")
    f.add_argument("-o", "--output", required=True)
    p = sp.add_parser("repeats")
    p.add_argument("words")
    p.add_argument("--window", type=float, default=15.0, help="how far apart a retake can be (s)")
    p.add_argument("--pause", type=float, default=0.45, help="pause that separates utterances (s)")
    p.add_argument("-o", "--output", required=True)
    c = sp.add_parser("accept")
    c.add_argument("file")
    c.add_argument("--ids")
    c.add_argument("--reject")
    a = ap.parse_args()
    {"review": cmd_review, "fix": cmd_fix, "repeats": cmd_repeats, "accept": cmd_accept}[a.cmd](a)


if __name__ == "__main__":
    main()
