#!/usr/bin/env python3
"""KeremKit subtitle tool - flexible cue building from Whisper word timestamps (Python stdlib).

Builds subtitle cues with configurable rules (words per line, lines, min/max words per cue,
sentence-aware splitting, orphan handling, highlights), maps them through cut lists onto the
final timeline, and writes:
  - <out>.json : compact data file for After Effects (one text layer reads it by expression)
  - <out>.srt  : standard subtitles

Commands
  build    (--words W.json [--cutlist C.json] [--at S] [--zone NAME] | --plan P.json)
           [--rules R.json] [--set key=value ...] -o OUT     (OUT without extension)
  preview  OUT.json [--from N] [--n 20]           cue list as compact text (index, time, text, highlights)
  highlight OUT.json --cue N --words 0,2 [--clear] set manual highlights for one cue
  ae-expr  OUT.json --footage NAME [--positions P.json]
                                                   print the AE expressions for source text,
                                                   highlight selector and zone-based position
  rules                                            print the default rules (all keys)

plan.json (several sources on one timeline, e.g. camera part 1 -> voice -> camera part 2):
  {"placements": [
     {"words": "cam.json",   "cutlist": "cam_cut.json",   "from": 0,    "to": 41.2, "at": 0,    "zone": "camera"},
     {"words": "voice.json", "cutlist": "voice_cut.json", "from": 0,    "to": null, "at": 41.2, "zone": "voice"},
     {"words": "cam.json",   "cutlist": "cam_cut.json",   "from": 41.2, "to": null, "at": 63.0, "zone": "camera"}]}
  from/to are times in that source's CUT output (null = to the end); at = start on the final timeline.
"""
import argparse
import json
import itertools
import math
import os
import re
import sys

DEFAULT_RULES = {
    "max_words_per_line": 4,      # words on one line
    "max_lines": 2,               # lines in one cue
    "min_words": 2,               # fewer than this -> merge into a neighbour
    "max_words": None,            # None = max_words_per_line * max_lines
    "max_chars_per_line": None,   # optional hard character limit per line
    "split_mode": "hybrid",       # words | sentence | hybrid
    "orphan": "rebalance",        # rebalance | extra_line | allow
    "orphan_max_words": 1,        # a leftover this small counts as an orphan
    "break_on_pause": 0.6,        # a pause this long always starts a new cue (s)
    "min_duration": 0.5,          # shortest cue on screen (s)
    "max_duration": 4.0,          # longest cue before it is split (s)
    "close_gaps": 0.25,           # gaps shorter than this are closed (no flicker)
    "language": None,             # None = taken from the Whisper output; "tr"/"az" enable dotted/dotless i casing
    "no_break_after": None,       # None = built-in list for the language; or your own list of words
                                  # avoid ending a line with these words (or with a number)
    "case": "as_is",              # as_is | upper | lower | sentence
    "strip_punctuation": "trailing",  # none | trailing | all
    "keep_punctuation": "?!",     # always kept even when stripping
    "highlight": {
        "modes": ["keywords", "numbers"],  # keywords | numbers | longest | manual
        "keywords": [],                    # words/stems to highlight (case/accent-insensitive)
        "max_per_cue": 1,
        "min_chars": 3,
    },
}
# words a line should not end on, per language (articles, conjunctions, short glue words)
GLUE_WORDS = {
    "en": ["a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "my", "your", "this", "that"],
    "tr": ["ve", "ile", "bir", "bu", "şu", "o", "çok", "en", "daha", "her", "hiç"],
    "de": ["der", "die", "das", "ein", "eine", "und", "oder", "zu", "mit", "im", "am"],
    "es": ["el", "la", "los", "las", "un", "una", "y", "o", "de", "en", "con", "por", "para"],
    "fr": ["le", "la", "les", "un", "une", "et", "ou", "de", "du", "des", "en", "à", "pour", "avec"],
    "pt": ["o", "a", "os", "as", "um", "uma", "e", "ou", "de", "do", "da", "em", "com", "para"],
    "it": ["il", "lo", "la", "gli", "le", "un", "una", "e", "o", "di", "in", "con", "per"],
}
DOTTED_I = ("tr", "az")
SENT_END = re.compile(r"[.!?…]+[\"')\]]*$")
SOFT = re.compile(r"[,;:–—-]+[\"')\]]*$")
_TR = str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})
_ASCII = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(w):
    return re.sub(r"[^\w]", "", w.translate(_TR).lower().translate(_ASCII))


def to_upper(s, lang):
    return s.replace("i", "İ").replace("ı", "I").upper() if (lang or "")[:2] in DOTTED_I else s.upper()


def to_lower(s, lang):
    return s.translate(_TR).lower() if (lang or "")[:2] in DOTTED_I else s.lower()


# ---------------------------------------------------------------- input
def detect_language(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("language") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def load_words(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = []
    if isinstance(data, list):
        raw = data
    elif data.get("segments"):
        for seg in data["segments"]:
            raw.extend(seg.get("words") or [])
    elif data.get("word_segments"):
        raw = data["word_segments"]
    elif data.get("words"):
        raw = data["words"]
    if not raw and isinstance(data, dict) and data.get("segments"):
        # no word timestamps: spread each segment's words evenly over the segment (coarse, but usable)
        for seg in data["segments"]:
            toks = (seg.get("text") or "").split()
            s0, e0 = seg.get("start"), seg.get("end")
            if not toks or s0 is None or e0 is None:
                continue
            step = (float(e0) - float(s0)) / len(toks)
            raw.extend({"word": tk, "start": float(s0) + k * step, "end": float(s0) + (k + 1) * step}
                       for k, tk in enumerate(toks))
        if raw:
            print(f"WARN {os.path.basename(path)} has no word timestamps; word times were spread over each segment. "
                  "Re-run Whisper with word timestamps for exact timing.", file=sys.stderr)
    out = []
    for w in raw:
        t = (w.get("word") or w.get("text") or "").strip()
        if t and not (t.startswith("[") and t.endswith("]")):   # verbatim sound tags: [laughter], [UH]
            out.append([w.get("start"), w.get("end"), t])
    if not out:
        sys.exit(f"ERROR: {path} contains no words (was Whisper run with word timestamps?)")
    for i, w in enumerate(out):
        if w[0] is None:
            w[0] = out[i - 1][1] if i and out[i - 1][1] is not None else 0.0
        if w[1] is None:
            w[1] = w[0] + 0.25
    return [(float(s), float(e), t) for s, e, t in out]


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def src_to_out(cut, t):
    for s in cut["segments"]:
        if s["src_in"] - 1e-6 <= t <= s["src_out"] + 1e-6:
            return s["out_in"] + (t - s["src_in"])
    return None


def kept_part(cut, s, e):
    """Largest overlap of the word [s, e] with a kept segment -> (out_start, out_end, overlap_s)."""
    best = None
    for seg in cut["segments"]:
        x, y = max(s, seg["src_in"]), min(e, seg["src_out"])
        if y - x > 1e-6 and (best is None or y - x > best[2]):
            best = (seg["out_in"] + x - seg["src_in"], seg["out_in"] + y - seg["src_in"], y - x)
    return best


def place(words, cut, frm, to, at, zone):
    """Map words (source time) -> cut output time -> final timeline; drop removed words.

    Whisper often starts a word inside the pause before it. When that pause was cut, the word's
    middle can fall in the removed part although its sound is kept - such a word is kept on its
    kept part (>= 60 % of the word or >= 0.25 s inside one kept segment). Only words that are
    really gone (retakes, repeats) are dropped."""
    res = []
    for s, e, t in words:
        if cut:
            mid = (s + e) / 2
            if src_to_out(cut, mid) is None:
                part = kept_part(cut, s, e)
                if part is None or (part[2] < 0.25 and part[2] < 0.6 * (e - s)):
                    continue
                s2, e2 = part[0], part[1]
            else:
                os_ = src_to_out(cut, s)
                oe = src_to_out(cut, e)
                om = src_to_out(cut, mid)
                s2 = os_ if os_ is not None else om
                e2 = oe if oe is not None else om
        else:
            s2, e2 = s, e
        if s2 < frm - 1e-6 or (to is not None and s2 >= to - 1e-6):
            continue
        res.append({"s": at + s2 - frm, "e": at + e2 - frm, "w": t, "z": zone})
    return res


# ---------------------------------------------------------------- rules
def merge_rules(base, extra):
    out = json.loads(json.dumps(base))
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def parse_set(pairs):
    extra = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        try:
            val = json.loads(v)
        except json.JSONDecodeError:
            val = v
        node = extra
        parts = k.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = val
    return extra


# ---------------------------------------------------------------- segmentation
def phrases(words, r):
    """Split the word stream at hard boundaries (pauses, zone changes, sentence ends)."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        hard = nxt is None or nxt["z"] != w["z"] or (nxt["s"] - w["e"]) >= r["break_on_pause"]
        if r["split_mode"] in ("sentence", "hybrid") and SENT_END.search(w["w"]):
            hard = True
        if hard:
            groups.append(cur)
            cur = []
    return groups


def chunk(group, r):
    mx = r["max_words"] or r["max_words_per_line"] * r["max_lines"]
    n = len(group)
    if n <= mx:
        return [group]
    if r["split_mode"] == "words":  # greedy fill, then fix the orphan
        parts = [group[i:i + mx] for i in range(0, n, mx)]
        last = parts[-1]
        if len(parts) > 1 and len(last) <= r["orphan_max_words"]:
            if r["orphan"] == "rebalance":
                both = parts[-2] + last
                h = math.ceil(len(both) / 2)
                parts[-2:] = [both[:h], both[h:]]
            elif r["orphan"] == "extra_line":
                parts[-2] = parts[-2] + last
                parts.pop()
        return parts
    # sentence / hybrid: balanced split, prefer breaking after soft punctuation
    k = math.ceil(n / mx)
    if r["orphan"] == "extra_line" and n - (k - 1) * mx <= r["orphan_max_words"] and k > 1:
        k -= 1  # allow one cue to grow by an extra line instead of leaving an orphan
    size = n / k
    cuts, pos = [], 0
    for j in range(1, k):
        ideal = round(j * size)
        best = ideal
        if r["split_mode"] == "hybrid":
            for d in (0, -1, 1):
                c = ideal + d
                if pos < c < n and SOFT.search(group[c - 1]["w"]) and c - pos <= mx + (1 if r["orphan"] == "extra_line" else 0):
                    best = c
                    break
        cuts.append(best)
        pos = best
    bounds = [0] + cuts + [n]
    return [group[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]


def fix_small(cues, r):
    """Merge cues shorter than min_words into the closer neighbour (same zone, small gap)."""
    mx = (r["max_words"] or r["max_words_per_line"] * r["max_lines"]) + r["max_words_per_line"]
    changed = True
    while changed:
        changed = False
        for i, c in enumerate(cues):
            if len(c) >= r["min_words"]:
                continue
            cands = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(cues) and cues[j][0]["z"] == c[0]["z"] and len(cues[j]) + len(c) <= mx:
                    first = cues[j] if j < i else c
                    if r["split_mode"] != "words" and SENT_END.search(first[-1]["w"]):
                        continue  # never glue two sentences together to satisfy min_words
                    gap = (c[0]["s"] - cues[j][-1]["e"]) if j < i else (cues[j][0]["s"] - c[-1]["e"])
                    if gap < r["break_on_pause"]:
                        cands.append((gap, j))
            if cands:
                _, j = min(cands)
                a, b = (j, i) if j < i else (i, j)
                cues[a] = cues[a] + cues[b]
                del cues[b]
                changed = True
                break
    return cues


def glue(word, r):
    f = fold(word)
    if any(ch.isdigit() for ch in f) and not re.search(r"[.,!?;:]$", word):
        return True
    words = r.get("no_break_after")
    if words is None:
        words = GLUE_WORDS.get((r.get("language") or "en")[:2], GLUE_WORDS["en"])
    return f in {fold(x) for x in words}


def lines_for(words, r):
    """Split a cue into lines: fewest lines that respect the limits, then the most even
    line lengths in characters (so 'Bu ses / kaydinda size anlatacagim' becomes
    'Bu ses kaydinda / size anlatacagim')."""
    n = len(words)
    wpl = r["max_words_per_line"]
    mc = r.get("max_chars_per_line")
    lens = [len(w["w"]) for w in words]
    k = max(1, math.ceil(n / wpl))
    while k <= n:
        best = None
        for cut in itertools.combinations(range(1, n), k - 1):
            b = (0,) + cut + (n,)
            if any(b[i + 1] - b[i] > wpl for i in range(k)):
                continue
            chars = [sum(lens[b[i]:b[i + 1]]) + (b[i + 1] - b[i] - 1) for i in range(k)]
            if mc and max(chars) > mc:
                continue
            # avoid ending a line on a glue word or a number ("3 / adimdan"), then most even
            # lengths; ties -> slightly longer first line (reads naturally)
            bad = sum(1 for i in range(k - 1) if glue(words[b[i + 1] - 1]["w"], r))
            sizes = [b[i + 1] - b[i] for i in range(k)]
            lonely = sum(1 for x in sizes if x == 1) if k > 1 and n > k else 0
            score = (bad * 8 + lonely * 15 + max(chars) - min(chars), -chars[0])
            if best is None or score < best[0]:
                best = (score, b)
        if best:
            b = best[1]
            return [words[b[i]:b[i + 1]] for i in range(k)]
        k += 1
    return [[w] for w in words]


def fmt_word(w, r):
    keep = r.get("keep_punctuation", "")
    mode = r.get("strip_punctuation", "none")
    if mode == "all":
        w = "".join(ch for ch in w if ch.isalnum() or ch in keep or ch in "'’%-")
    elif mode == "trailing":
        m = re.search(r"[^\w%’']+$", w)
        if m:
            tail = "".join(ch for ch in m.group(0) if ch in keep)
            w = w[:m.start()] + tail
    if r["case"] == "upper":
        w = to_upper(w, r.get("language"))
    elif r["case"] == "lower":
        w = to_lower(w, r.get("language"))
    return w


def pick_highlights(words, r):
    h = r.get("highlight") or {}
    modes = h.get("modes") or []
    if "manual" in modes and len(modes) == 1:
        return []
    kws = {fold(k) for k in h.get("keywords", []) if k}
    scored = []
    for i, w in enumerate(words):
        f = fold(w["w"])
        if len(f) < h.get("min_chars", 0) and not any(ch.isdigit() for ch in f):
            continue
        score = 0
        if "keywords" in modes and kws and any(f == k or (len(k) >= 4 and f.startswith(k)) for k in kws):
            score = 3
        elif "numbers" in modes and any(ch.isdigit() for ch in f):
            score = 2
        elif "longest" in modes:
            score = 1 + len(f) / 100
        if score:
            scored.append((-score, i))
    return sorted(i for _, i in sorted(scored)[: h.get("max_per_cue", 1)])


def build_cues(words, r, zone_end=None):
    cues = []
    for g in phrases(words, r):
        cues.extend(chunk(g, r))
    cues = fix_small(cues, r)
    allowed = r["max_lines"] + (1 if r["orphan"] == "extra_line" else 0)
    queue, sized = list(cues), []
    while queue:
        c = queue.pop(0)
        if len(c) > 1 and len(lines_for(c, r)) > allowed:
            h = math.ceil(len(c) / 2)
            queue[:0] = [c[:h], c[h:]]
        else:
            sized.append(c)
    cues = sized
    out = []
    for c in cues:
        lines = lines_for(c, r)
        flat = [w for ln in lines for w in ln]
        texts = [[fmt_word(w["w"], r) for w in ln] for ln in lines]
        if r["case"] == "sentence" and texts and texts[0]:
            texts[0][0] = texts[0][0][:1].upper() + texts[0][0][1:]
        out.append({"s": c[0]["s"], "e": c[-1]["e"], "lines": texts, "h": pick_highlights(flat, r), "z": c[0]["z"]})
    # timing polish: close tiny gaps, enforce min duration, split very long cues
    for i, c in enumerate(out):
        nxt = out[i + 1]["s"] if i + 1 < len(out) else None
        if nxt is not None and 0 < nxt - c["e"] < r["close_gaps"]:
            c["e"] = nxt
        if c["e"] - c["s"] < r["min_duration"]:
            c["e"] = min(c["s"] + r["min_duration"], nxt if nxt is not None else c["s"] + r["min_duration"])
    final = []
    for c in out:
        if zone_end and c["z"] in zone_end:
            ze = max(e for s0, e in zone_end[c["z"]] if s0 <= c["s"] + 1e-6) if any(s0 <= c["s"] + 1e-6 for s0, _ in zone_end[c["z"]]) else None
            if ze is not None and c["e"] > ze:
                c["e"] = max(ze, c["s"] + 0.05)
        words_n = sum(len(x) for x in c["lines"])
        if c["e"] - c["s"] > r["max_duration"] and words_n > 1 and len(c["lines"]) > 1:
            mid = c["s"] + (c["e"] - c["s"]) / 2
            half = math.ceil(len(c["lines"]) / 2)
            first_n = sum(len(x) for x in c["lines"][:half])
            final.append(dict(c, e=mid, lines=c["lines"][:half], h=[i for i in c["h"] if i < first_n]))
            final.append(dict(c, s=mid, lines=c["lines"][half:], h=[i - first_n for i in c["h"] if i >= first_n]))
        else:
            final.append(c)
    return final


# ---------------------------------------------------------------- output
def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_outputs(base, cues, zones, rules):
    data = {"v": 1, "cues": [{"s": round(c["s"], 3), "e": round(c["e"], 3),
                              "t": "\r".join(" ".join(ln) for ln in c["lines"]),
                              "h": c["h"], "z": c["z"]} for c in cues],
            "zones": zones, "rules": rules}
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(base + ".srt", "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{srt_time(c['s'])} --> {srt_time(c['e'])}\n" + "\n".join(" ".join(ln) for ln in c["lines"]) + "\n\n")
    return data


def cmd_build(a):
    rules = merge_rules(DEFAULT_RULES, load_json(a.rules) if a.rules else {})
    rules = merge_rules(rules, parse_set(a.set))
    words, zones = [], []
    if a.plan:
        plan = load_json(a.plan)
        base = os.path.dirname(os.path.abspath(a.plan))
        for p in plan["placements"]:
            wp = os.path.join(base, p["words"])
            if not rules.get("language"):
                rules["language"] = detect_language(wp)
            cut = load_json(os.path.join(base, p["cutlist"])) if p.get("cutlist") else None
            placed = place(load_words(wp), cut, p.get("from") or 0, p.get("to"), p.get("at") or 0, p.get("zone") or "main")
            words.extend(placed)
            # end in the placement's own time base (cut output, or source when there is no cut list)
            if p.get("to") is not None:
                end_src = p["to"]
            elif cut:
                end_src = cut["out_duration"]
            else:
                end_src = max((w[1] for w in load_words(wp)), default=p.get("from") or 0)
            zones.append({"s": round(p.get("at") or 0, 3), "e": round((p.get("at") or 0) + end_src - (p.get("from") or 0), 3),
                          "z": p.get("zone") or "main"})
    else:
        cut = load_json(a.cutlist) if a.cutlist else None
        if not rules.get("language"):
            rules["language"] = detect_language(a.words)
        words = place(load_words(a.words), cut, 0, None, a.at, a.zone)
        if words:
            zones = [{"s": round(a.at, 3), "e": round(words[-1]["e"], 3), "z": a.zone}]
    zs = sorted(zones, key=lambda z: z["s"])
    for x, y in zip(zs, zs[1:]):
        if y["s"] < x["e"] - 0.01:
            sys.exit(f"ERROR: placements overlap on the timeline: '{x['z']}' ends at {x['e']}s "
                     f"but '{y['z']}' starts at {y['s']}s. Fix 'at' values in the plan.")
    words.sort(key=lambda w: w["s"])
    if not words:
        sys.exit("ERROR: no words left after mapping (check cut list / plan ranges).")
    zone_end = {}
    for z in zones:
        zone_end.setdefault(z["z"], []).append((z["s"], z["e"]))
    cues = build_cues(words, rules, zone_end)
    write_outputs(a.output, cues, zones, rules)
    counts = [sum(len(x) for x in c["lines"]) for c in cues]
    short = sum(1 for n in counts if n < rules["min_words"])
    hl = sum(1 for c in cues if c["h"])
    print(f"OK cues={len(cues)} words={sum(counts)} avg_words={sum(counts) / len(cues):.1f} "
          f"max_words={max(counts)} below_min={short} highlighted_cues={hl} zones={len(zones)} "
          f"-> {a.output}.json, {a.output}.srt")


def cmd_preview(a):
    d = load_json(a.file)
    for i, c in enumerate(d["cues"][a.frm:a.frm + a.n], a.frm):
        words = c["t"].replace("\r", " / ").split(" ")
        flat = [w for w in words if w != "/"]
        hw = ",".join(flat[j] for j in c["h"] if j < len(flat))
        print(f"{i}\t{c['s']:.2f}-{c['e']:.2f}\t{c['z']}\t{c['t'].replace(chr(13), ' / ')}\t[{hw}]")


def cmd_highlight(a):
    d = load_json(a.file)
    c = d["cues"][a.cue]
    c["h"] = [] if a.clear else sorted({int(x) for x in a.words.split(",") if x.strip() != ""})
    with open(a.file, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK cue {a.cue} highlights={c['h']}")


def cmd_ae_expr(a):
    name = a.footage
    pos = load_json(a.positions) if a.positions else {}
    find = ("function kkFind(arr,t){var lo=0,hi=arr.length-1;while(lo<=hi){var m=(lo+hi)>>1;"
            "if(t<arr[m].s)hi=m-1;else if(t>=arr[m].e)lo=m+1;else return arr[m];}return null;}\n")
    src = (f'var d=footage("{name}").sourceData;\n' + find +
           'var c=kkFind(d.cues,time);\nc?c.t:"";')
    sel = (f'var d=footage("{name}").sourceData;\n' + find +
           'var c=kkFind(d.cues,time);\n(c&&c.h.indexOf(textIndex-1)>-1)?100:0;')
    print("=== Source Text (text layer) ===")
    print(src)
    print("\n=== Highlight: Animator > Expression Selector (Based On: Words) > Amount ===")
    print(sel)
    if pos:
        p = json.dumps(pos, separators=(",", ":"))
        print("\n=== Position (zone-based placement) ===")
        print(f'var d=footage("{name}").sourceData;\nvar P={p};\n' + find +
              'var z=kkFind(d.zones,time);\n(z&&P[z.z])?P[z.z]:value;')


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--words")
    b.add_argument("--cutlist")
    b.add_argument("--at", type=float, default=0.0)
    b.add_argument("--zone", default="main")
    b.add_argument("--plan")
    b.add_argument("--rules")
    b.add_argument("--set", nargs="*", help="override a rule: key=value (JSON values), e.g. max_lines=1 highlight.max_per_cue=2")
    b.add_argument("-o", "--output", required=True)
    p = sp.add_parser("preview")
    p.add_argument("file")
    p.add_argument("--from", dest="frm", type=int, default=0)
    p.add_argument("--n", type=int, default=20)
    h = sp.add_parser("highlight")
    h.add_argument("file")
    h.add_argument("--cue", type=int, required=True)
    h.add_argument("--words", default="")
    h.add_argument("--clear", action="store_true")
    e = sp.add_parser("ae-expr")
    e.add_argument("file")
    e.add_argument("--footage", required=True, help="name of the imported JSON item in AE, e.g. subs.json")
    e.add_argument("--positions", help='JSON file {"camera":[960,900],"voice":[960,540]}')
    sp.add_parser("rules")
    a = ap.parse_args()
    if a.cmd == "build" and not a.plan and not a.words:
        ap.error("build needs --words or --plan")
    if a.cmd == "rules":
        print(json.dumps(DEFAULT_RULES, indent=1, ensure_ascii=False))
        return
    {"build": cmd_build, "preview": cmd_preview, "highlight": cmd_highlight, "ae-expr": cmd_ae_expr}[a.cmd](a)


if __name__ == "__main__":
    main()
