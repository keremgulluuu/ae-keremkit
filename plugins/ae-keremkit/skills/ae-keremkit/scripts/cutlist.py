#!/usr/bin/env python3
"""KeremKit cut list tool - tight, editable, token-cheap cutting (Python stdlib + ffmpeg).

A cut list (cut.json) records which parts of ONE source recording are kept. Every
segment knows its source time and its output time, so a request like "output 10-12 s is
cut too fast, add 1 s of breathing room" becomes one command instead of a re-edit.

Commands
  build   --words W.json --media FILE [--preset tight|normal|relaxed]
          [--pad-before S] [--pad-after S] [--max-pause S] [--duration S] [--fps N] -o cut.json
  show    cut.json [--from A --to B]          compact summary (+ boundaries in range)
  map     cut.json (--out T | --src T)        convert a time between output and source
  add     cut.json --from A --to B --sec X    give back X s of removed pause inside output range
          cut.json --at T --sec X             ...at the boundary nearest to output time T
          (if the range has too little removed pause, nearby cuts within --window s are used;
           --strict forbids that)
  cut     cut.json --from A --to B            remove an output range
  restore cut.json --src-from A --src-to B    put a source range back
  undo    cut.json                            revert the last edit
  render  cut.json -o OUT [--crf N] [--x264-preset P] [--run]
                                              build (and with --run, execute) the ffmpeg render

Times are seconds. Every edit prints one short line; nothing large is printed.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

PRESETS = {
    #            pad before word, pad after word, longest pause kept as-is
    "tight":   {"pad_before": 0.05, "pad_after": 0.08, "max_pause": 0.15},
    "normal":  {"pad_before": 0.10, "pad_after": 0.15, "max_pause": 0.35},
    "relaxed": {"pad_before": 0.15, "pad_after": 0.25, "max_pause": 0.70},
}
HISTORY_LIMIT = 20
EPS = 1e-6


# ---------------------------------------------------------------- helpers
def load_words(path):
    """Return [(start, end, word)] from openai-whisper / faster-whisper / whisperx JSON
    or a plain list of {word,start,end}. Missing word times are interpolated."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = []
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        if data.get("segments"):
            for seg in data["segments"]:
                if seg.get("words"):
                    raw.extend(seg["words"])
                elif "start" in seg and "end" in seg:  # no word timestamps: use segment
                    raw.append({"word": seg.get("text", ""), "start": seg["start"], "end": seg["end"]})
        elif data.get("word_segments"):
            raw = data["word_segments"]
        elif data.get("words"):
            raw = data["words"]
    words = []
    for w in raw:
        text = (w.get("word") or w.get("text") or "").strip()
        if not text:
            continue
        words.append([w.get("start"), w.get("end"), text])
    # interpolate missing times (whisperx leaves numbers untimed)
    for i, w in enumerate(words):
        if w[0] is None:
            prev_end = next((words[j][1] for j in range(i - 1, -1, -1) if words[j][1] is not None), 0.0)
            w[0] = prev_end
        if w[1] is None:
            nxt = next((words[j][0] for j in range(i + 1, len(words)) if words[j][0] is not None), w[0] + 0.3)
            w[1] = max(w[0], nxt)
    words = [(float(s), float(e), t) for s, e, t in words]
    words.sort(key=lambda x: x[0])
    if not words:
        sys.exit("ERROR: no words found. Was Whisper run with word timestamps?")
    return words


def probe(media):
    """Return (duration, fps, has_video, has_audio) via ffprobe; None values if unavailable."""
    if not shutil.which("ffprobe"):
        return None, None, None, None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,avg_frame_rate", "-of", "json", media],
            capture_output=True, text=True, check=True).stdout
        info = json.loads(out)
    except Exception:
        return None, None, None, None
    dur = float(info.get("format", {}).get("duration") or 0) or None
    fps, has_v, has_a = None, False, False
    for st in info.get("streams", []):
        if st.get("codec_type") == "video":
            has_v = True
            num, _, den = (st.get("avg_frame_rate") or "0/1").partition("/")
            try:
                if float(den or 1) and float(num):
                    fps = round(float(num) / float(den or 1), 3)
            except ValueError:
                pass
        elif st.get("codec_type") == "audio":
            has_a = True
    return dur, fps, has_v, has_a


def snap(t, fps):
    return round(round(t * fps) / fps, 4) if fps else round(t, 4)


def normalize(intervals, fps, duration):
    """Sort, clamp, snap to frames and merge overlapping intervals."""
    out = []
    for a, b in sorted(intervals):
        a, b = max(0.0, a), min(duration, b) if duration else b
        a, b = snap(a, fps), snap(b, fps)
        if b - a <= EPS:
            continue
        if out and a <= out[-1][1] + EPS:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def with_out_times(segs):
    t, rows = 0.0, []
    for a, b in segs:
        d = b - a
        rows.append({"src_in": round(a, 4), "src_out": round(b, 4),
                     "out_in": round(t, 4), "out_out": round(t + d, 4)})
        t += d
    return rows


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, cl, note=None, previous=None):
    if previous is not None:
        hist = cl.setdefault("history", [])
        hist.append({"note": note, "segments": previous})
        del hist[:-HISTORY_LIMIT]
    cl["segments"] = with_out_times([(s["src_in"], s["src_out"]) for s in cl["segments"]])
    cl["out_duration"] = cl["segments"][-1]["out_out"] if cl["segments"] else 0
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cl, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def intervals(cl):
    return [[s["src_in"], s["src_out"]] for s in cl["segments"]]


def out_to_src(cl, t):
    for s in cl["segments"]:
        if s["out_in"] - EPS <= t <= s["out_out"] + EPS:
            return s["src_in"] + (t - s["out_in"])
    return None


def src_to_out(cl, t):
    for s in cl["segments"]:
        if s["src_in"] - EPS <= t <= s["src_out"] + EPS:
            return s["out_in"] + (t - s["src_in"])
    return None  # inside a removed part


def fmt(t):
    return f"{t:.2f}"


# ---------------------------------------------------------------- commands
def cmd_build(a):
    words = load_words(a.words)
    p = dict(PRESETS[a.preset])
    for k in ("pad_before", "pad_after", "max_pause"):
        if getattr(a, k) is not None:
            p[k] = getattr(a, k)
    dur, fps, has_v, has_a = probe(a.media)
    dur = a.duration or dur or (words[-1][1] + p["pad_after"])
    fps = a.fps or fps
    raw = [[s - p["pad_before"], e + p["pad_after"]] for s, e, _ in words]
    merged = []
    for iv in sorted(raw):
        if merged and iv[0] - merged[-1][1] <= p["max_pause"]:
            merged[-1][1] = max(merged[-1][1], iv[1])
        else:
            merged.append(iv)
    segs = normalize(merged, fps, dur)
    cl = {"kk": "cutlist", "version": 1, "media": os.path.abspath(a.media), "duration": round(dur, 4),
          "fps": fps, "has_video": has_v, "has_audio": has_a, "params": dict(p, preset=a.preset),
          "words_file": os.path.abspath(a.words), "segments": [{"src_in": x, "src_out": y} for x, y in segs]}
    save(a.output, cl)
    cl = load(a.output)
    removed = dur - cl["out_duration"]
    print(f"OK segments={len(cl['segments'])} source={fmt(dur)}s output={fmt(cl['out_duration'])}s "
          f"removed={fmt(removed)}s ({removed / dur * 100:.0f}%) preset={a.preset}")


def cmd_show(a):
    cl = load(a.cutlist)
    segs = cl["segments"]
    print(f"media={os.path.basename(cl['media'])} segments={len(segs)} source={fmt(cl['duration'])}s "
          f"output={fmt(cl['out_duration'])}s edits={len(cl.get('history', []))}")
    if a.frm is None:
        return
    to = a.to if a.to is not None else a.frm
    print("boundary_out_time\tremoved_pause_s\tsrc_cut")
    for i in range(len(segs) - 1):
        t = segs[i]["out_out"]
        if a.frm - 0.5 <= t <= to + 0.5:
            gap = segs[i + 1]["src_in"] - segs[i]["src_out"]
            print(f"{fmt(t)}\t{gap:.2f}\t{fmt(segs[i]['src_out'])}-{fmt(segs[i + 1]['src_in'])}")


def cmd_map(a):
    cl = load(a.cutlist)
    if a.out is not None:
        s = out_to_src(cl, a.out)
        print(f"out {fmt(a.out)} -> src {fmt(s)}" if s is not None else "OUT_OF_RANGE")
    else:
        o = src_to_out(cl, a.src)
        print(f"src {fmt(a.src)} -> out {fmt(o)}" if o is not None else f"src {fmt(a.src)} is in a REMOVED part")


def cmd_add(a):
    cl = load(a.cutlist)
    segs = cl["segments"]
    prev = intervals(cl)
    if len(segs) < 2:
        sys.exit("ERROR: no cuts to loosen.")
    lo, hi = (a.at, a.at) if a.at is not None else (a.frm, a.to)
    idx = [i for i in range(len(segs) - 1) if lo - EPS <= segs[i]["out_out"] <= hi + EPS]
    if not idx:  # nearest boundary to the middle of the range
        mid = (lo + hi) / 2
        idx = [min(range(len(segs) - 1), key=lambda i: abs(segs[i]["out_out"] - mid))]
    cap = {i: segs[i + 1]["src_in"] - segs[i]["src_out"] for i in range(len(segs) - 1)}
    give = {i: 0.0 for i in idx}
    left = a.sec

    def fill(group):
        nonlocal left
        open_ = [i for i in group if cap[i] - give.get(i, 0) > EPS]
        while left > EPS and open_:  # water-filling: share evenly, respect each pause's size
            share = left / len(open_)
            for i in list(open_):
                g = min(share, cap[i] - give.get(i, 0))
                give[i] = give.get(i, 0) + g
                left -= g
                if cap[i] - give[i] <= EPS:
                    open_.remove(i)

    fill(idx)
    # not enough removed pause inside the range: borrow from the nearest cuts just outside it
    if left > EPS and not a.strict:
        outside = sorted((i for i in range(len(segs) - 1) if i not in idx
                          and min(abs(segs[i]["out_out"] - lo), abs(segs[i]["out_out"] - hi)) <= a.window),
                         key=lambda i: min(abs(segs[i]["out_out"] - lo), abs(segs[i]["out_out"] - hi)))
        for i in outside:
            if left <= EPS:
                break
            idx.append(i)
            fill([i])
    idx = [i for i in idx if give.get(i, 0) > EPS] or idx
    for i in idx:
        segs[i]["src_out"] += give.get(i, 0)
    merged = normalize(intervals(cl), cl.get("fps"), cl.get("duration"))
    cl["segments"] = [{"src_in": x, "src_out": y} for x, y in merged]
    save(a.cutlist, cl, f"add {a.sec}s at out {fmt(lo)}-{fmt(hi)}", prev)
    added = a.sec - left
    msg = f"OK added={added:.2f}s over {len(idx)} cut(s) output={fmt(load(a.cutlist)['out_duration'])}s"
    if left > 0.01:
        msg += f" NOTE: only {added:.2f}s of removed pause existed here; {left:.2f}s could not be added"
    print(msg)


def cmd_cut(a):
    cl = load(a.cutlist)
    prev = intervals(cl)
    remove = []
    for s in cl["segments"]:
        x, y = max(a.frm, s["out_in"]), min(a.to, s["out_out"])
        if y - x > EPS:
            remove.append((s["src_in"] + x - s["out_in"], s["src_in"] + y - s["out_in"]))
    keep = []
    for x, y in prev:
        parts = [[x, y]]
        for rx, ry in remove:
            nxt = []
            for px, py in parts:
                if ry <= px or rx >= py:
                    nxt.append([px, py])
                else:
                    if rx > px:
                        nxt.append([px, rx])
                    if ry < py:
                        nxt.append([ry, py])
            parts = nxt
        keep.extend(parts)
    merged = normalize(keep, cl.get("fps"), cl.get("duration"))
    cl["segments"] = [{"src_in": x, "src_out": y} for x, y in merged]
    save(a.cutlist, cl, f"cut out {fmt(a.frm)}-{fmt(a.to)}", prev)
    print(f"OK removed={sum(y - x for x, y in remove):.2f}s output={fmt(load(a.cutlist)['out_duration'])}s")


def cmd_restore(a):
    cl = load(a.cutlist)
    prev = intervals(cl)
    merged = normalize(prev + [[a.src_from, a.src_to]], cl.get("fps"), cl.get("duration"))
    cl["segments"] = [{"src_in": x, "src_out": y} for x, y in merged]
    save(a.cutlist, cl, f"restore src {fmt(a.src_from)}-{fmt(a.src_to)}", prev)
    o = src_to_out(load(a.cutlist), a.src_from)
    print(f"OK restored src {fmt(a.src_from)}-{fmt(a.src_to)} now at out {fmt(o)} "
          f"output={fmt(load(a.cutlist)['out_duration'])}s")


def cmd_undo(a):
    cl = load(a.cutlist)
    hist = cl.get("history", [])
    if not hist:
        sys.exit("ERROR: nothing to undo.")
    last = hist.pop()
    cl["segments"] = [{"src_in": x, "src_out": y} for x, y in last["segments"]]
    save(a.cutlist, cl)
    print(f"OK undone: {last['note']} output={fmt(load(a.cutlist)['out_duration'])}s")


def cmd_render(a):
    cl = load(a.cutlist)
    segs = cl["segments"]
    has_v = cl.get("has_video", True) is not False
    has_a = cl.get("has_audio", True) is not False
    fade = 0.005  # tiny audio fades stop clicks at every cut
    lines, vl, al = [], [], []
    for i, s in enumerate(segs):
        a0, b0 = s["src_in"], s["src_out"]
        d = b0 - a0
        if has_v:
            lines.append(f"[0:v]trim=start={a0}:end={b0},setpts=PTS-STARTPTS[v{i}];")
            vl.append(f"[v{i}]")
        if has_a:
            f = min(fade, d / 4)
            lines.append(f"[0:a]atrim=start={a0}:end={b0},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:st=0:d={f},afade=t=out:st={max(0, d - f):.4f}:d={f}[a{i}];")
            al.append(f"[a{i}]")
    n = len(segs)
    pairs = "".join((vl[i] if has_v else "") + (al[i] if has_a else "") for i in range(n))
    lines.append(f"{pairs}concat=n={n}:v={1 if has_v else 0}:a={1 if has_a else 0}"
                 + ("[v]" if has_v else "") + ("[a]" if has_a else ""))
    script = os.path.splitext(a.output)[0] + ".filter.txt"
    with open(script, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", cl["media"],
           "-filter_complex_script", script]
    if has_v:
        cmd += ["-map", "[v]", "-c:v", "libx264", "-preset", a.x264_preset, "-crf", str(a.crf),
                "-pix_fmt", "yuv420p"]
        if cl.get("fps"):
            cmd += ["-r", str(cl["fps"]), "-fps_mode", "cfr"]
    if has_a:
        cmd += ["-map", "[a]"] + (["-c:a", "aac", "-b:a", "256k"] if has_v else ["-c:a", "pcm_s16le", "-ar", "48000"])
    cmd.append(a.output)
    if not a.run:
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and "filter_complex_script" in (r.stderr or ""):
        cmd[cmd.index("-filter_complex_script")] = "-/filter_complex"  # ffmpeg 7.1+ spelling
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ERROR ffmpeg: " + (r.stderr or "").strip()[-600:])
    print(f"OK rendered {a.output} ({fmt(cl['out_duration'])}s, {n} segments)")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--words", required=True)
    b.add_argument("--media", required=True)
    b.add_argument("--preset", choices=list(PRESETS), default="normal")
    for k in ("pad-before", "pad-after", "max-pause", "duration", "fps"):
        b.add_argument("--" + k, type=float, dest=k.replace("-", "_"))
    b.add_argument("-o", "--output", required=True)
    s = sp.add_parser("show")
    s.add_argument("cutlist")
    s.add_argument("--from", dest="frm", type=float)
    s.add_argument("--to", type=float)
    m = sp.add_parser("map")
    m.add_argument("cutlist")
    g = m.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", type=float)
    g.add_argument("--src", type=float)
    ad = sp.add_parser("add")
    ad.add_argument("cutlist")
    ad.add_argument("--from", dest="frm", type=float)
    ad.add_argument("--to", type=float)
    ad.add_argument("--at", type=float)
    ad.add_argument("--sec", type=float, required=True)
    ad.add_argument("--strict", action="store_true", help="only use cuts inside the range")
    ad.add_argument("--window", type=float, default=1.5, help="how far outside the range to borrow (s)")
    c = sp.add_parser("cut")
    c.add_argument("cutlist")
    c.add_argument("--from", dest="frm", type=float, required=True)
    c.add_argument("--to", type=float, required=True)
    r = sp.add_parser("restore")
    r.add_argument("cutlist")
    r.add_argument("--src-from", type=float, required=True)
    r.add_argument("--src-to", type=float, required=True)
    u = sp.add_parser("undo")
    u.add_argument("cutlist")
    rd = sp.add_parser("render")
    rd.add_argument("cutlist")
    rd.add_argument("-o", "--output", required=True)
    rd.add_argument("--crf", type=int, default=18)
    rd.add_argument("--x264-preset", default="veryfast")
    rd.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "add" and a.at is None and (a.frm is None or a.to is None):
        ap.error("add needs --at T or --from A --to B")
    {"build": cmd_build, "show": cmd_show, "map": cmd_map, "add": cmd_add, "cut": cmd_cut,
     "restore": cmd_restore, "undo": cmd_undo, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    main()
