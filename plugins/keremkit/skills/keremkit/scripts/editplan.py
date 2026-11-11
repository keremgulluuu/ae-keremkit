#!/usr/bin/env python3
"""KeremKit edit plan - write the edit as data against word indices, check it, get exact times.

An edit plan (edit.json) lists shots that start on a spoken word (its index from
`transcript.py words`). This tool turns it into frame-exact timeline times and checks it
against editing rules, so the edit can be fixed in a few characters and rebuilt.

  check  edit.json [-o edit.times.json]     validate + print the shot table (ERROR / WARN lines)

edit.json:
  {"words": "cam.fixed.json", "cutlist": "cam.cut.json", "at": 0, "fps": 30,
   "rules": {...optional, see DEFAULT_RULES...},
   "keys": [6, 15],                                   word indices shown as emphasised captions
   "shots": [{"at": 0, "kind": "type", "text": "WHAT IF..."},
             {"at": 5, "kind": "host"},
             {"at": 14, "kind": "clip", "file": "clips/c01.mp4", "in": 0.5}, ...]}

A cut lands `lead_frames` (default 1) before its word. A shot runs until the next shot starts;
the last one runs to the end of the last word plus `tail`.
"""
import argparse
import json
import os
import re
import sys

DEFAULT_RULES = {
    "lead_frames": 1,          # the cut lands this many frames before the word
    "tail": 0.4,               # last shot runs this long past the last word (s)
    "min_shot": 1.2,           # shorter shots are flagged (s)
    "max_shot": 3.5,           # longer shots are flagged (s)...
    "long_kinds": {"host": 6.0, "type": 5.0, "giant": 5.0},   # ...except these kinds, with their own limits
    "short_ok": ["flash"],     # kinds allowed under min_shot
    "no_consecutive": ["host"],  # never two of these in a row
    "no_repeat_seconds": True,   # never show the same seconds of a file twice
    "max_keys_per_sentence": 1,
    "first_at": 0,
}
SENT_END = re.compile(r"[.!?…]+[\"')\]]*$")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def words_of(data):
    if isinstance(data, list):
        return data
    if data.get("segments"):
        out = []
        for seg in data["segments"]:
            out.extend(seg.get("words") or [])
        return out
    return data.get("word_segments") or data.get("words") or []


def to_out(cut, t):
    if not cut:
        return t
    for s in cut["segments"]:
        if s["src_in"] - 1e-6 <= t <= s["src_out"] + 1e-6:
            return s["out_in"] + (t - s["src_in"])
    return None


def snap(t, fps):
    return round(round(t * fps) / fps, 4)


def mmss(t):
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m):02d}:{s:05.2f}"


def cmd_check(a):
    plan = load(a.plan)
    base = os.path.dirname(os.path.abspath(a.plan))
    rules = dict(DEFAULT_RULES)
    rules.update(plan.get("rules") or {})
    ws = [w for w in words_of(load(os.path.join(base, plan["words"])))
          if (w.get("word") or w.get("text") or "").strip()]
    cut = load(os.path.join(base, plan["cutlist"])) if plan.get("cutlist") else None
    fps = float(plan.get("fps") or (cut or {}).get("fps") or 30)
    at = float(plan.get("at") or 0)
    errors, warns = [], []

    def word_time(i):
        w = ws[i]
        o = to_out(cut, w.get("start", 0))
        if o is None:
            o = to_out(cut, (w.get("start", 0) + w.get("end", 0)) / 2)
        return None if o is None else o + at

    shots = plan.get("shots") or []
    if not shots:
        sys.exit("ERROR: the plan has no shots")
    if shots[0].get("at") != rules["first_at"]:
        errors.append(f"first shot must start at word {rules['first_at']} (starts at {shots[0].get('at')})")
    starts = []
    prev = -1
    for k, sh in enumerate(shots):
        i = sh.get("at")
        if not isinstance(i, int) or not 0 <= i < len(ws):
            errors.append(f"shot {k + 1}: word index {i} does not exist (0-{len(ws) - 1})")
            starts.append(None)
            continue
        if i <= prev:
            errors.append(f"shot {k + 1}: word indices must rise ({prev} -> {i})")
        prev = i
        t = word_time(i)
        if t is None:
            errors.append(f"shot {k + 1}: word {i} \"{ws[i].get('word', '').strip()}\" was cut out of the recording")
            starts.append(None)
            continue
        lead = rules["lead_frames"] / fps
        starts.append(max(0.0, snap(t - lead, fps)) if k else snap(at, fps))
    last_end = None
    for w in reversed(ws):
        o = to_out(cut, w.get("end", 0))
        if o is None:
            o = to_out(cut, (w.get("start", 0) + w.get("end", 0)) / 2)
        if o is not None:
            last_end = snap(o + at + rules["tail"], fps)
            break
    if cut:
        last_end = min(last_end, snap(cut["out_duration"] + at, fps))

    rows, used = [], {}
    for k, sh in enumerate(shots):
        s = starts[k]
        nxt = next((x for x in starts[k + 1:] if x is not None), last_end)
        if s is None or nxt is None:
            continue
        d = round(nxt - s, 3)
        kind = sh.get("kind", "?")
        txt = " ".join((ws[j].get("word") or "").strip() for j in range(sh["at"], min(len(ws), sh["at"] + 4)))
        rows.append({"n": k + 1, "kind": kind, "word": sh["at"], "start": s, "end": nxt, "dur": d, "first_words": txt,
                     **{x: sh[x] for x in ("file", "in", "text", "word_text") if x in sh}})
        lim = rules["long_kinds"].get(kind, rules["max_shot"])
        if d < rules["min_shot"] and kind not in rules["short_ok"]:
            warns.append(f"shot {k + 1} ({kind}) is {d:.2f}s - shorter than {rules['min_shot']}s")
        if d > lim:
            warns.append(f"shot {k + 1} ({kind}) is {d:.2f}s - longer than {lim}s")
        if d <= 0:
            errors.append(f"shot {k + 1} has no duration")
        if k and kind in rules["no_consecutive"] and shots[k - 1].get("kind") == kind:
            warns.append(f"shots {k} and {k + 1} are both '{kind}' - put something between them")
        f = sh.get("file")
        if f:
            if not os.path.exists(os.path.join(base, f)):
                errors.append(f"shot {k + 1}: file not found: {f}")
            if rules["no_repeat_seconds"] and "in" in sh:
                a0, a1 = float(sh["in"]), float(sh["in"]) + d
                for (b0, b1, n) in used.get(f, []):
                    if a0 < b1 - 0.05 and b0 < a1 - 0.05:
                        warns.append(f"shot {k + 1} repeats seconds {max(a0, b0):.1f}-{min(a1, b1):.1f} of {f} "
                                     f"already shown in shot {n}")
                used.setdefault(f, []).append((a0, a1, k + 1))
        for sub in sh.get("items") or []:
            if sub.get("file") and not os.path.exists(os.path.join(base, sub["file"])):
                errors.append(f"shot {k + 1}: file not found: {sub['file']}")

    keys = plan.get("keys") or []
    if keys:
        sent, per = 0, {}
        bounds = []
        for j, w in enumerate(ws):
            bounds.append(sent)
            if SENT_END.search((w.get("word") or "").strip()):
                sent += 1
        for kidx in keys:
            if 0 <= kidx < len(ws):
                per.setdefault(bounds[kidx], []).append(kidx)
            else:
                errors.append(f"key word {kidx} does not exist")
        for sidx, ks in per.items():
            if len(ks) > rules["max_keys_per_sentence"]:
                warns.append(f"sentence with words {ks} has {len(ks)} keys (max {rules['max_keys_per_sentence']})")

    print("n\tstart\tend\tdur\tkind\tword\tfirst words")
    for r in rows:
        print(f"{r['n']}\t{mmss(r['start'])}\t{mmss(r['end'])}\t{r['dur']:.2f}\t{r['kind']}\t{r['word']}\t{r['first_words']}")
    for e in errors:
        print("ERROR " + e)
    for w in warns:
        print("WARN " + w)
    total = rows[-1]["end"] - rows[0]["start"] if rows else 0
    print(f"{'FAILED' if errors else 'OK'} shots={len(rows)} length={total:.2f}s errors={len(errors)} warnings={len(warns)}")
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            json.dump({"fps": fps, "at": at, "shots": rows, "errors": errors, "warnings": warns}, f, ensure_ascii=False, indent=1)
    if errors:
        sys.exit(1)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check")
    c.add_argument("plan")
    c.add_argument("-o", "--output")
    a = ap.parse_args()
    {"check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
