#!/usr/bin/env python3
"""KeremKit video reference - turn a reference video into a small, token-cheap package.

  python videoref.py VIDEO -o OUTDIR [--thumb 216] [--per-sheet 8] [--cut 28] [--move 2.5]

Measures with code (ffmpeg + standard library) and writes:
  OUTDIR/README.md      how to read the package + shots, motion windows, colours, audio onsets
  OUTDIR/data.json      the same as data (plus the frame-by-frame motion curve)
  OUTDIR/sheets/*.jpg   contact sheets: start/middle/end of each shot, and every frame where
                        something moves (sparse where the picture holds, dense where it changes)

Claude reads README.md first, then only the sheets it needs. Words and their timing come from
Whisper (`transcript.py`), run separately on the same video.
"""
import argparse
import array
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile


def run(args, **kw):
    return subprocess.run(args, capture_output=True, **kw)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,avg_frame_rate",
             "-of", "json", path], text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: cannot read {path}: {r.stderr.strip()[-200:]}")
    info = json.loads(r.stdout)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not v:
        sys.exit("ERROR: no video stream")
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1) if float(num) else 30.0
    audio = any(s["codec_type"] == "audio" for s in info["streams"])
    return float(info["format"]["duration"]), v["width"], v["height"], fps, audio


def gray_frames(path, w, h):
    raw = run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"]).stdout
    size = w * h
    return [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]


def frame_rgb(path, index, fps, w, h):
    raw = run(["ffmpeg", "-v", "error", "-ss", f"{index / fps:.4f}", "-i", path, "-frames:v", "1",
               "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]).stdout
    return raw[: w * h * 3]


def palette(rgb, n=5):
    """Main colours: 4-bit buckets, most common first, near-duplicates merged."""
    counts = {}
    for i in range(0, len(rgb) - 2, 3):
        key = (rgb[i] >> 4, rgb[i + 1] >> 4, rgb[i + 2] >> 4)
        c = counts.setdefault(key, [0, 0, 0, 0])
        c[0] += 1
        c[1] += rgb[i]
        c[2] += rgb[i + 1]
        c[3] += rgb[i + 2]
    total = sum(c[0] for c in counts.values()) or 1
    picked = []
    for c in sorted(counts.values(), key=lambda c: -c[0]):
        col = (c[1] // c[0], c[2] // c[0], c[3] // c[0])
        near = next((p for p in picked if sum((a - b) ** 2 for a, b in zip(p["rgb"], col)) < 900), None)
        if near:
            near["n"] += c[0]
        elif len(picked) < n:
            picked.append({"rgb": col, "n": c[0]})
    picked.sort(key=lambda p: -p["n"])
    return [{"hex": "#%02X%02X%02X" % p["rgb"], "share": round(p["n"] / total, 3)} for p in picked]


def audio_onsets(path):
    r = run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"])
    if r.returncode != 0 or not r.stdout:
        return [], None
    a = array.array("h")
    a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    hop = 80
    db = []
    for k in range(0, len(a) - hop + 1, hop):
        acc = 0
        for v in a[k:k + hop]:
            acc += v * v
        db.append(10 * math.log10(acc / hop / 1073741824.0 + 1e-12))
    flux = [0.0] + [max(0.0, db[i] - db[i - 1]) for i in range(1, len(db))]
    hits, last = [], -1.0
    for i in range(1, len(db) - 1):
        win = sorted(flux[max(0, i - 25):i + 25])
        med = win[len(win) // 2]
        if flux[i] > max(6.0, med * 4) and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1] and db[i] > -45:
            t = i * hop / 8000
            if t - last > 0.12:
                hits.append(round(t, 2))
                last = t
    lr = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "loudnorm=print_format=json",
              "-f", "null", "-"], text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", lr or "", re.S)
    lufs = float(json.loads(m.group(0))["input_i"]) if m else None
    return hits, lufs


def tc(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def extract_thumbs(path, picks, fps, tw, th, tmp):
    """One decode pass: every picked frame as a labelled JPG."""
    sel = "+".join(f"eq(n\\,{f})" for f in picks)
    label = ("drawtext=text='%{pts\\:hms}':x=4:y=4:fontsize=13:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=3")
    base = f"select='{sel}',scale={tw}:{th}"
    for vf in (f"{base},{label}", base):
        r = run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", vf, "-fps_mode", "passthrough", "-q:v", "3",
                 os.path.join(tmp, "f%05d.jpg")], text=True)
        if r.returncode != 0 and "fps_mode" in (r.stderr or ""):
            r = run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", vf, "-vsync", "passthrough", "-q:v", "3",
                     os.path.join(tmp, "f%05d.jpg")], text=True)
        files = sorted(x for x in os.listdir(tmp) if x.startswith("f") and x.endswith(".jpg"))
        if r.returncode == 0 and len(files) >= len(picks):
            return {f: os.path.join(tmp, files[i]) for i, f in enumerate(picks)}
        for x in files:
            os.remove(os.path.join(tmp, x))
    sys.exit("ERROR: could not extract frames: " + (r.stderr or "")[-300:])


def tile(files, out, tmp):
    cols = min(4, len(files))
    rows = (len(files) + cols - 1) // cols
    files = files + [files[-1]] * (cols * rows - len(files))
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in files:
            f.write(f"file '{p}'\n")
    r = run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
             "-vf", f"tile={cols}x{rows}:padding=4:margin=4:color=0x141414", "-frames:v", "1", "-q:v", "3", out], text=True)
    if r.returncode != 0:
        sys.exit("ERROR: could not build contact sheet: " + (r.stderr or "")[-300:])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--thumb", type=int, default=216, help="thumbnail width in px")
    ap.add_argument("--per-sheet", type=int, default=8)
    ap.add_argument("--cut", type=float, default=28.0, help="frame difference (0-255) that counts as a cut")
    ap.add_argument("--move", type=float, default=2.5, help="frame difference that counts as motion")
    ap.add_argument("--max-motion-frames", type=int, default=12, help="frames kept per motion window")
    a = ap.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("ERROR: ffmpeg/ffprobe not found")

    dur, W, H, fps, has_audio = probe(a.video)
    aw = 64
    ah = max(2, int(round(aw * H / W / 2)) * 2)
    frames = gray_frames(a.video, aw, ah)
    n = len(frames)
    if n < 2:
        sys.exit("ERROR: video has fewer than 2 frames")
    px = aw * ah
    diff = [0.0] + [sum(abs(x - y) for x, y in zip(frames[i], frames[i - 1])) / px for i in range(1, n)]
    cuts = [i for i in range(1, n) if diff[i] > a.cut and diff[i] >= diff[i - 1] and diff[i] >= diff[min(n - 1, i + 1)]]

    bounds = [0] + cuts + [n]
    shots = []
    pw = 48
    ph = max(2, int(round(pw * H / W)))
    for k in range(len(bounds) - 1):
        s, e = bounds[k], bounds[k + 1]
        windows = []
        for f in range(s + 1, e):
            if diff[f] > a.move:
                if windows and f - windows[-1][1] <= 2:
                    windows[-1][1] = f
                else:
                    windows.append([f, f])
        mid = (s + e - 1) // 2
        shots.append({"id": len(shots) + 1, "start_f": s, "end_f": e - 1, "start": round(s / fps, 3),
                      "end": round(e / fps, 3), "dur": round((e - s) / fps, 3),
                      "motion": [{"from": round(x / fps, 2), "to": round((y + 1) / fps, 2), "frames": y - x + 1,
                                  "peak": round(max(diff[x:y + 1]), 1)} for x, y in windows],
                      "palette": palette(frame_rgb(a.video, mid, fps, pw, ph))})

    plan = [("00_overview.jpg", [(s["start_f"] + s["end_f"]) // 2 for s in shots][:16],
             f"overview: middle frame of each shot ({len(shots)} shots)")]
    for s in shots:
        picks = {s["start_f"], s["end_f"], (s["start_f"] + s["end_f"]) // 2}
        for m in s["motion"]:
            f0 = max(s["start_f"], int(round(m["from"] * fps)) - 1)
            f1 = min(s["end_f"], int(round(m["to"] * fps)))
            span = list(range(f0, f1 + 1))
            if len(span) > a.max_motion_frames:
                step = len(span) / a.max_motion_frames
                span = [span[int(i * step)] for i in range(a.max_motion_frames)]
            picks.update(span)
        picks = sorted(picks)
        parts = [picks[i:i + a.per_sheet] for i in range(0, len(picks), a.per_sheet)]
        for j, chunk in enumerate(parts):
            name = f"shot{s['id']:02d}" + (f"_{j + 1}" if len(parts) > 1 else "") + ".jpg"
            plan.append((name, chunk, f"shot {s['id']} {tc(s['start'])}-{tc(s['end'])}" +
                         (f" part {j + 1}/{len(parts)}" if len(parts) > 1 else "")))

    tw = a.thumb
    th = int(round(tw * H / W / 2)) * 2
    os.makedirs(os.path.join(a.out, "sheets"), exist_ok=True)
    all_picks = sorted({f for _, fs, _ in plan for f in fs})
    sheets = []
    with tempfile.TemporaryDirectory() as tmp:
        thumbs = extract_thumbs(a.video, all_picks, fps, tw, th, tmp)
        for name, fs, title in plan:
            out = os.path.join(a.out, "sheets", name)
            tile([thumbs[f] for f in fs], out, tmp)
            cols = min(4, len(fs))
            rows = (len(fs) + cols - 1) // cols
            wpx, hpx = cols * tw + (cols + 1) * 4, rows * th + (rows + 1) * 4
            sheets.append({"file": f"sheets/{name}", "title": title, "frames": fs,
                           "times": [round(f / fps, 3) for f in fs], "approx_tokens": int(wpx * hpx / 750)})

    hits, lufs = audio_onsets(a.video) if has_audio else ([], None)
    cut_t = [round(c / fps, 2) for c in cuts]
    data = {"source": os.path.basename(a.video), "duration": round(dur, 3), "size": [W, H], "fps": fps, "frames": n,
            "cuts": cut_t, "shots": shots, "audio": {"lufs": lufs, "onsets": hits}, "sheets": sheets,
            "motion_curve": [round(x, 1) for x in diff]}
    with open(os.path.join(a.out, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    near = sum(1 for h in hits if any(abs(h - c) <= 0.1 for c in cut_t))
    tok = sum(s["approx_tokens"] for s in sheets)
    L = [f"# Reference video: {data['source']}", "",
         f"{W}x{H}, {fps:g} fps, {dur:.2f} s, {n} frames. Audio: {'none' if not has_audio else f'{lufs} LUFS'}.", "",
         "## How to read this package", "",
         "- The numbers were measured from the pixels and the audio by code. Trust them over impressions from the images.",
         "- `sheets/00_overview.jpg` shows one frame per shot. `sheets/shotNN*.jpg` show the start, middle and end of each shot "
         "plus the frames where something moves, left to right, top to bottom; each thumbnail is stamped with its time.",
         "- Read the overview first, then only the shot sheets you need.",
         "- Motion windows are where the picture changes inside a shot: animations, camera moves, text pops.",
         "- Audio onsets are sudden loudness jumps: speech syllables, SFX and beats together. Onsets right on a cut "
         "usually mean an SFX cut to picture.", "",
         f"## Shots ({len(shots)}; cuts at {', '.join(map(str, cut_t)) or 'none'} s)", "",
         "| # | start | end | dur | motion inside | main colours |", "|---|---|---|---|---|---|"]
    for s in shots:
        mo = "; ".join(f"{m['from']}-{m['to']}s ({m['frames']}f)" for m in s["motion"]) or "still"
        pal = " ".join(f"{p['hex']} {int(p['share'] * 100)}%" for p in s["palette"][:4])
        L.append(f"| {s['id']} | {s['start']} | {s['end']} | {s['dur']} | {mo} | {pal} |")
    L += ["", "## Audio", ""]
    if has_audio:
        L += [f"- Loudness: {lufs} LUFS integrated.", f"- Onsets ({len(hits)}): {', '.join(map(str, hits)) or 'none'} s.",
              f"- {near} of {len(hits)} onsets are within 0.1 s of a cut.",
              "- Words: not included. Run Whisper with word timestamps and put the transcript next to this file."]
    else:
        L.append("- No audio.")
    L += ["", "## Sheets", "", "| file | frames | ~tokens |", "|---|---|---|"]
    L += [f"| {s['file']} | {len(s['frames'])} | {s['approx_tokens']} |" for s in sheets]
    L += ["", f"All sheets together: ~{tok} tokens."]
    with open(os.path.join(a.out, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"OK shots={len(shots)} cuts={len(cuts)} sheets={len(sheets)} onsets={len(hits)} tokens~{tok} -> {a.out}")


if __name__ == "__main__":
    main()
