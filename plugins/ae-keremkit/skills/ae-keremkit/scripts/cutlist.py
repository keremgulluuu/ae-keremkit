#!/usr/bin/env python3
"""KeremKit cut list tool - tight, editable, token-cheap cutting (Python stdlib + ffmpeg).

A cut list (cut.json) records which parts of ONE source recording are kept. Every
segment knows its source time and its output time, so a request like "output 10-12 s is
cut too fast, add 1 s of breathing room" becomes one command instead of a re-edit.

Commands
  build   --words W.json --media FILE [--preset tight|normal|relaxed]
          [--pad-before S] [--pad-after S] [--max-pause S] [--duration S] [--fps N]
          [--silence auto|on|off] [--noise-db DB] [--remove repeats.json] -o cut.json
          Pauses are found in the real audio (ffmpeg silencedetect) and confirmed with the words;
          --remove drops repeats/false starts found by transcript.py.
  show    cut.json [--from A --to B]          compact summary (+ boundaries in range)
  map     cut.json (--out T | --src T)        convert a time between output and source
  add     cut.json --from A --to B --sec X    give back X s of removed pause inside output range
          cut.json --at T --sec X             ...at the boundary nearest to output time T
          (if the range has too little removed pause, nearby cuts within --window s are used;
           --strict forbids that)
  cut     cut.json --from A --to B            remove an output range
  restore cut.json --src-from A --src-to B    put a source range back
  undo    cut.json                            revert the last edit
  zoom    cut.json [--levels 100 110] [--emphasis subs.json] -o zoom.json
                                              jump-cut zoom framing per segment + the AE Scale expression
  export  cut.json --format xmeml|edl|fcpxml -o FILE
                                              xmeml = Premiere (FCP7 XML, linked); fcpxml = Final Cut / Resolve
  render  cut.json -o OUT [--crf N] [--x264-preset P] [--run]
                                              build (and with --run, execute) the ffmpeg render

Times are seconds. Every edit prints one short line; nothing large is printed.
"""
import argparse
import json
import os
import re
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
def audio_db(media, hop=0.01):
    """Loudness envelope (dBFS every 10 ms) of the first audio stream, via ffmpeg. None if unavailable."""
    if not shutil.which("ffmpeg"):
        return None
    sr = 8000
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", media, "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None
    import array
    import math
    a = array.array("h")
    a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    n = int(sr * hop)
    out = []
    for k in range(0, len(a) - n + 1, n):
        acc = 0
        for v in a[k:k + n]:
            acc += v * v
        out.append(10 * math.log10(acc / n / 1073741824.0 + 1e-12))
    return out


def detect_silences(media, max_pause, noise_db=None, words=None, rel_db=-10.0):
    """Silent stretches from the actual audio.

    Whisper's word ends often run into the following pause, so cutting on words alone leaves part of
    every pause in. The threshold is relative to the speech itself: the median level of the frames
    inside Whisper's words, minus rel_db (default 10 dB). An explicit noise_db overrides it.
    Returns ([(start, end)], threshold_db) or (None, None) when ffmpeg/audio is unavailable.
    The envelope and the speech median are kept in LAST for the wordless-audio check."""
    LAST.clear()
    env = audio_db(media)
    if env is None:
        return None, None
    hop = 0.01
    speech = []
    for s, e in (words or []):
        speech.extend(env[int(s / hop):int(e / hop) + 1])
    if not speech:
        speech = list(env)
    speech.sort()
    median = speech[len(speech) // 2]
    LAST.update(env=env, median=median, hop=hop)
    if noise_db is None:
        noise_db = max(-60.0, min(-20.0, median + rel_db))
    out, start = [], None
    min_len = max(0.05, max_pause)
    for k, v in enumerate(env + [0.0]):
        if v < noise_db and k < len(env):
            if start is None:
                start = k
        elif start is not None:
            if (k - start) * hop >= min_len:
                out.append((start * hop, k * hop))
            start = None
    return out, noise_db


LAST = {}


def loud_wordless(regions, min_len=1.0, below_median_db=6.0):
    """Non-silent regions with no words that are as loud as speech (music, a laugh, an unheard line).
    Whisper sometimes misses whole sentences; dropping these silently loses real audio."""
    env, median, hop = LAST.get("env"), LAST.get("median"), LAST.get("hop", 0.01)
    if not env:
        return []
    out = []
    for x, y in regions:
        if y - x < min_len:
            continue
        seg = sorted(env[int(x / hop):int(y / hop)])
        if seg and seg[len(seg) // 2] >= median - below_median_db:
            out.append((round(x, 2), round(y, 2), round(seg[len(seg) // 2], 1)))
    return out


def subtract(intervals, holes):
    out = []
    for x, y in intervals:
        parts = [[x, y]]
        for hx, hy in holes:
            nxt = []
            for px, py in parts:
                if hy <= px or hx >= py:
                    nxt.append([px, py])
                else:
                    if hx > px:
                        nxt.append([px, hx])
                    if hy < py:
                        nxt.append([hy, py])
            parts = nxt
        out.extend(parts)
    return out


def load_removals(path, include_uncertain=False):
    """Ranges to drop (repeats, false starts, fillers) from transcript.py repeats."""
    if not path:
        return [], 0
    data = json.load(open(path, encoding="utf-8"))
    items = data.get("removals", data) if isinstance(data, dict) else data
    keep = [(float(r["src_in"]), float(r["src_out"])) for r in items
            if r.get("apply", r.get("confidence") == "high") or (include_uncertain and r.get("confidence") == "low")]
    return keep, len(keep)


def cmd_build(a):
    words = load_words(a.words)
    p = dict(PRESETS[a.preset])
    for k in ("pad_before", "pad_after", "max_pause"):
        if getattr(a, k) is not None:
            p[k] = getattr(a, k)
    dur, fps, has_v, has_a = probe(a.media)
    dur = a.duration or dur or (words[-1][1] + p["pad_after"])
    fps = a.fps or fps
    word_iv = [[s, e] for s, e, _ in words]

    silences, noise = (None, None)
    if a.silence != "off" and has_a is not False:
        silences, noise = detect_silences(a.media, p["max_pause"], a.noise_db, word_iv, a.rel_db)
        if silences is None and a.silence == "on":
            sys.exit("ERROR: silence detection needs ffmpeg with an audio stream")
    mode = "words only"
    if silences == []:
        mode = "words only (audio has no pauses below the threshold)"
        silences = None
    loud, inside = [], 0
    if silences:
        # never cut a silence inside a normal-length word: stop consonants ("sattı", "tt") are silent for ~0.1 s.
        # Very long words are left alone here - they can hide retakes (transcript.py bursts).
        normal = [(s, e) for s, e in word_iv if e - s <= 1.2]
        # Whisper's word edges are loose, so a short silence (< 0.25 s) that reaches into a word's inside counts too
        kept_sil = [(x, y) for x, y in silences
                    if not any((s + 0.02 < x and y < e - 0.02) or (y - x < 0.25 and x < e - 0.05 and y > s + 0.05)
                               for s, e in normal)]
        inside = len(silences) - len(kept_sil)
        silences = kept_sil
    if silences:
        # speech = audio that is not silent, kept only where Whisper heard words (drops coughs, clicks, noise)
        sounding = subtract([[0.0, dur]], [(x, min(y, dur)) for x, y in silences])
        speech = [iv for iv in sounding if any(w[0] < iv[1] and w[1] > iv[0] for w in word_iv)]
        # wordless audio as loud as the speaker for > 1 s is kept (not dropped as noise) unless asked
        loud = loud_wordless([iv for iv in sounding if iv not in speech])
        if loud and not a.drop_wordless:
            speech = sorted(speech + [[x, y] for x, y, _ in loud])
        raw = [[x - p["pad_before"], y + p["pad_after"]] for x, y in speech]
        mode = f"audio+words (silence < {noise:.0f} dB)"
    else:
        raw = [[s - p["pad_before"], e + p["pad_after"]] for s, e in word_iv]
    merged = []
    for iv in sorted(raw):
        if merged and iv[0] - merged[-1][1] <= p["max_pause"]:
            merged[-1][1] = max(merged[-1][1], iv[1])
        else:
            merged.append(iv)
    removals, n_rem = load_removals(a.remove, a.include_uncertain)
    if removals:
        merged = subtract(merged, removals)
    segs = normalize(merged, fps, dur)
    cl = {"kk": "cutlist", "version": 2, "media": os.path.abspath(a.media), "duration": round(dur, 4),
          "fps": fps, "has_video": has_v, "has_audio": has_a,
          "params": dict(p, preset=a.preset, silence=mode, noise_db=noise),
          "words_file": os.path.abspath(a.words), "removals": [list(r) for r in removals],
          "segments": [{"src_in": x, "src_out": y} for x, y in segs]}
    save(a.output, cl)
    cl = load(a.output)
    removed = dur - cl["out_duration"]
    rep_s = sum(y - x for x, y in removals)
    print(f"OK segments={len(cl['segments'])} source={fmt(dur)}s output={fmt(cl['out_duration'])}s "
          f"removed={fmt(removed)}s ({removed / dur * 100:.0f}%) preset={a.preset} mode={mode}"
          + (f" repeats_removed={n_rem} ({rep_s:.1f}s)" if n_rem else "")
          + (f" in_word_gaps_kept={inside}" if inside else ""))
    for x, y, lv in loud:
        print(f"WARN loud audio without words {fmt(x)}-{fmt(y)}s ({lv} dB) "
              + ("REMOVED (--drop-wordless)" if a.drop_wordless else "KEPT - ask the user; --drop-wordless removes it"))


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


def need(cond, msg):
    if not cond:
        sys.exit("ERROR: " + msg)


def cmd_add(a):
    need(a.sec > 0, f"--sec must be positive (got {a.sec})")
    if a.at is None:
        need(a.to > a.frm, f"--to must be after --from (got {a.frm} -> {a.to})")
    need(min(x for x in (a.at, a.frm, a.to) if x is not None) >= 0, "times must not be negative")
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
    need(a.to > a.frm, f"--to must be after --from (got {a.frm} -> {a.to})")
    need(a.frm >= 0, "times must not be negative")
    cl = load(a.cutlist)
    need(a.frm < cl["out_duration"], f"--from {a.frm} is past the end of the output ({cl['out_duration']} s)")
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
    need(a.src_to > a.src_from, f"--src-to must be after --src-from (got {a.src_from} -> {a.src_to})")
    need(a.src_from >= 0, "times must not be negative")
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
    fade = 0.008  # tiny audio fades stop clicks at every cut
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
        compressed = has_v or a.output.lower().endswith((".m4a", ".mp4", ".aac", ".mov"))
        cmd += ["-map", "[a]"] + (["-c:a", "aac", "-b:a", "256k"] if compressed else ["-c:a", "pcm_s16le", "-ar", "48000"])
    cmd.append(a.output)
    if not a.run:
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and "fps_mode" in (r.stderr or ""):
        i = cmd.index("-fps_mode")
        cmd[i:i + 2] = ["-vsync", "cfr"]           # ffmpeg before 5.1
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and "filter_complex_script" in (r.stderr or ""):
        cmd[cmd.index("-filter_complex_script")] = "-/filter_complex"  # ffmpeg 7.1+ spelling
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ERROR ffmpeg: " + (r.stderr or "").strip()[-600:])
    print(f"OK rendered {a.output} ({fmt(cl['out_duration'])}s, {n} segments)")


def tc(seconds, fps):
    f = int(round(seconds * fps))
    r = int(round(fps))
    return f"{f // (3600 * r):02d}:{f // (60 * r) % 60:02d}:{f // r % 60:02d}:{f % r:02d}"


def cmd_zoom(a):
    """Framing per output segment for jump-cut zoom (+ optional emphasis punch-ins), as data for AE."""
    cl = load(a.cutlist)
    lv = a.levels
    entries = []
    for i, s in enumerate(cl["segments"]):
        z = lv[i % len(lv)] if a.mode == "alternate" else (lv[0] if i == 0 else lv[1] if s["src_in"] - cl["segments"][i - 1]["src_out"] > a.min_gap else lv[0])
        entries.append({"s": round(s["out_in"] + a.at, 3), "e": round(s["out_out"] + a.at, 3), "z": z})
    punches = 0
    if a.emphasis:
        subs = json.load(open(a.emphasis, encoding="utf-8"))
        for c in subs.get("cues", []):
            if not c.get("h"):
                continue
            t = c["s"]
            for e in entries:
                if e["s"] <= t < e["e"] and t - e["s"] > 0.2:
                    # split the segment: punch in from the highlighted cue to the next cut
                    entries.append({"s": round(t, 3), "e": e["e"], "z": a.emphasis_scale})
                    e["e"] = round(t, 3)
                    punches += 1
                    break
        entries.sort(key=lambda x: x["s"])
    for prev, cur in zip(entries, entries[1:]):
        if abs(prev["e"] - cur["s"]) < 1e-3 and prev["z"] != cur["z"]:
            cur["p"] = prev["z"]               # previous framing, for an optional eased change
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "cuts": entries}, f, separators=(",", ":"))
    name = os.path.basename(a.output)
    expr = (f'var d=footage("{name}").sourceData.cuts;var lo=0,hi=d.length-1,c=null;'
            'while(lo<=hi){var m=(lo+hi)>>1;if(time<d[m].s)hi=m-1;else if(time>=d[m].e)lo=m+1;else{c=d[m];break;}}')
    if a.ease_frames > 0:
        expr += (f'if(c){{var z=c.z,f={a.ease_frames}*thisComp.frameDuration;'
                 'if(c.p!==undefined&&time<c.s+f){z=ease(time,c.s,c.s+f,c.p,c.z);}[z,z];}else value;')
    else:
        expr += 'c?[c.z,c.z]:value;'
    print(f"OK segments={len(entries)} punch_ins={punches} levels={lv} -> {a.output}")
    print("SCALE_EXPRESSION " + expr)


def frame_segments(cl, fps, start=0.0):
    """Source frames per segment and contiguous record frames: every event's source length equals its
    record length (rounding source and record times separately gave 1-frame mismatches)."""
    rec = int(round(start * fps))
    rows = []
    for s in cl["segments"]:
        a0, b0 = int(round(s["src_in"] * fps)), int(round(s["src_out"] * fps))
        if b0 <= a0:
            continue
        rows.append((a0, b0, rec, rec + b0 - a0))
        rec += b0 - a0
    return rows


def tcf(f, fps):
    r = int(round(fps))
    return f"{f // (3600 * r):02d}:{f // (60 * r) % 60:02d}:{f // r % 60:02d}:{f % r:02d}"


def probe_av(media):
    """(width, height, sample_rate, channels) via ffprobe; defaults when unavailable."""
    w, h, sr, ch = 1920, 1080, 48000, 2
    if shutil.which("ffprobe") and os.path.exists(media):
        try:
            info = json.loads(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,sample_rate,channels",
                 "-of", "json", media], capture_output=True, text=True, check=True).stdout)
            for st in info.get("streams", []):
                if st.get("codec_type") == "video" and st.get("width"):
                    w, h = int(st["width"]), int(st["height"])
                elif st.get("codec_type") == "audio" and st.get("sample_rate"):
                    sr, ch = int(st["sample_rate"]), int(st.get("channels") or 2)
        except Exception:
            pass
    return w, h, sr, ch


def xmeml(cl, fps, title):
    """FCP7 XML (xmeml v4) that Premiere imports linked: one master clip (file defined once, the rest
    reference file-1), V1 + one audio track, contiguous integer frames."""
    from urllib.parse import quote
    from xml.sax.saxutils import escape
    media = cl["media"]
    clip = escape(os.path.basename(media))
    W, H, SR, CH = probe_av(media)
    tb = int(round(fps))
    ntsc = "TRUE" if abs(fps - round(fps)) > 0.001 else "FALSE"
    rate = f"<rate><timebase>{tb}</timebase><ntsc>{ntsc}</ntsc></rate>"
    url = escape("file://localhost/" + quote(media.replace("\\", "/").lstrip("/"), safe="/:"))
    dur = int(round(cl["duration"] * fps))
    tcode = f"<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
    has_v = cl.get("has_video", True) is not False
    has_a = cl.get("has_audio", True) is not False
    vchar = (f"<samplecharacteristics>{rate}<width>{W}</width><height>{H}</height>"
             "<pixelaspectratio>square</pixelaspectratio></samplecharacteristics>")
    achar = f"<samplecharacteristics><depth>16</depth><samplerate>{SR}</samplerate></samplecharacteristics>"
    file_full = (f'<file id="file-1"><name>{clip}</name><pathurl>{url}</pathurl>{rate}<duration>{dur}</duration>{tcode}'
                 "<media>" + (f"<video>{vchar}</video>" if has_v else "")
                 + (f"<audio>{achar}<channelcount>{CH}</channelcount></audio>" if has_a else "") + "</media></file>")
    rows = frame_segments(cl, fps)
    V, A = [], []
    for i, (a0, b0, r0, r1) in enumerate(rows, 1):
        links = ""
        if has_v and has_a:
            links = (f"<link><linkclipref>v{i}</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex>"
                     f"<clipindex>{i}</clipindex></link><link><linkclipref>a{i}</linkclipref><mediatype>audio</mediatype>"
                     f"<trackindex>1</trackindex><clipindex>{i}</clipindex><groupindex>1</groupindex></link>")
        base = (f"<name>{clip}</name><enabled>TRUE</enabled><duration>{dur}</duration>{rate}"
                f"<start>{r0}</start><end>{r1}</end><in>{a0}</in><out>{b0}</out>")
        first = file_full if i == 1 else '<file id="file-1"/>'
        if has_v:
            V.append(f'<clipitem id="v{i}">{base}{first}{links}</clipitem>')
        if has_a:
            f = first if not has_v else '<file id="file-1"/>'
            A.append(f'<clipitem id="a{i}">{base}{f}<sourcetrack><mediatype>audio</mediatype>'
                     f"<trackindex>1</trackindex></sourcetrack>{links}</clipitem>")
    total = rows[-1][3] if rows else 0
    media_xml = ""
    if has_v:
        media_xml += f"<video><format>{vchar}</format><track>{''.join(V)}</track></video>"
    if has_a:
        media_xml += (f"<audio><numOutputChannels>2</numOutputChannels><format>{achar}</format>"
                      f"<track>{''.join(A)}</track></audio>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4"><sequence id="seq-1">'
            f"<name>{escape(title)}</name><duration>{total}</duration>{rate}{tcode}<media>{media_xml}</media>"
            "</sequence></xmeml>"), len(rows), total


def cmd_export(a):
    cl = load(a.cutlist)
    fps = a.fps or cl.get("fps") or 30
    media = cl["media"]
    clip = os.path.basename(media)
    out = []
    if a.format == "xmeml":
        text, n, frames = xmeml(cl, fps, a.title or os.path.splitext(clip)[0] + "_cut")
        with open(a.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
        print(f"OK xmeml clips={n} frames={frames} fps={fps:g} -> {a.output} "
              "(Premiere: File > Import; HDR source -> set Color Setup after import, see premiere.md)")
        return
    if a.format == "edl":
        # one source, one stereo/mono audio track -> track B (V + A1); reel = clip name
        reel = re.sub(r"[^A-Z0-9_]", "", os.path.splitext(clip)[0].upper())[:8] or "AX"
        out += [f"TITLE: {a.title or os.path.splitext(clip)[0]}", "FCM: NON-DROP FRAME", ""]
        for i, (a0, b0, r0, r1) in enumerate(frame_segments(cl, fps, a.start), 1):
            out.append(f"{i:03d}  {reel:<8} B     C        {tcf(a0, fps)} {tcf(b0, fps)} {tcf(r0, fps)} {tcf(r1, fps)}")
            out.append(f"* FROM CLIP NAME: {clip}")
            out.append(f"* SOURCE FILE: {media}")
            out.append("")
    else:
        num, den = (1001, int(round(fps * 1001))) if abs(fps - round(fps)) > 0.001 else (1, int(round(fps)))
        def r(t):
            return f"{int(round(t * fps)) * num}/{den}s"
        total = cl["out_duration"]
        uri = "file://" + (media if media.startswith("/") else "/" + media.replace("\\", "/"))
        out += ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.9">', "  <resources>",
                f'    <format id="r1" frameDuration="{num}/{den}s"/>',
                f'    <asset id="r2" name="{clip}" start="0s" duration="{r(cl["duration"])}" hasVideo="1" hasAudio="1" format="r1">',
                f'      <media-rep kind="original-media" src="{uri}"/>', "    </asset>", "  </resources>",
                f'  <library><event name="KeremKit"><project name="{a.title or "KeremKit cut"}">',
                f'    <sequence format="r1" duration="{r(total)}" tcStart="0s"><spine>']
        for s in cl["segments"]:
            out.append(f'      <asset-clip ref="r2" name="{clip}" offset="{r(s["out_in"])}" start="{r(s["src_in"])}" '
                       f'duration="{r(s["src_out"] - s["src_in"])}" format="r1"/>')
        out += ["    </spine></sequence>", "  </project></event></library>", "</fcpxml>"]
    with open(a.output, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"OK {a.format} events={len(cl['segments'])} fps={fps:g} -> {a.output}")


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
    b.add_argument("--silence", choices=["auto", "on", "off"], default="auto",
                   help="cut on the real audio silence too (needs ffmpeg); auto = when available")
    b.add_argument("--noise-db", type=float, help="absolute silence threshold in dBFS (overrides --rel-db)")
    b.add_argument("--rel-db", type=float, default=-10.0,
                   help="silence = quieter than the speech median by this much (default -10 dB)")
    b.add_argument("--remove", help="removals JSON from transcript.py repeats (repeats, false starts, fillers)")
    b.add_argument("--include-uncertain", action="store_true", help="also remove low-confidence repeats")
    b.add_argument("--drop-wordless", action="store_true",
                   help="also remove wordless audio as loud as speech (default: keep it and warn)")
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
    z = sp.add_parser("zoom")
    z.add_argument("cutlist")
    z.add_argument("--levels", type=float, nargs="+", default=[100, 110])
    z.add_argument("--mode", choices=["alternate", "gaps"], default="alternate",
                   help="alternate every cut, or only change framing at cuts that removed > --min-gap")
    z.add_argument("--min-gap", type=float, default=0.5)
    z.add_argument("--emphasis", help="subs.json: punch in at highlighted cues")
    z.add_argument("--emphasis-scale", type=float, default=118)
    z.add_argument("--ease-frames", type=int, default=0, help="0 = hard cut between framings")
    z.add_argument("--at", type=float, default=0.0, help="where the cut file starts on the timeline (s)")
    z.add_argument("-o", "--output", required=True)
    ex = sp.add_parser("export")
    ex.add_argument("cutlist")
    ex.add_argument("--format", choices=["xmeml", "edl", "fcpxml"], default="xmeml",
                    help="xmeml = FCP7 XML for Premiere (linked media, preferred); edl = CMX3600 (Premiere links "
                         "media by hand); fcpxml = Final Cut Pro / Resolve")
    ex.add_argument("--fps", type=float)
    ex.add_argument("--start", type=float, default=0.0, help="record timecode offset (s)")
    ex.add_argument("--title")
    ex.add_argument("-o", "--output", required=True)
    a = ap.parse_args()
    if a.cmd == "add" and a.at is None and (a.frm is None or a.to is None):
        ap.error("add needs --at T or --from A --to B")
    {"build": cmd_build, "show": cmd_show, "map": cmd_map, "add": cmd_add, "cut": cmd_cut,
     "restore": cmd_restore, "undo": cmd_undo, "render": cmd_render, "zoom": cmd_zoom,
     "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    main()
