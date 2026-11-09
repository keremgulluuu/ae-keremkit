#!/usr/bin/env python3
"""KeremKit render QC - check a finished video and pick thumbnail frames (ffmpeg, stdlib only).

  check  RENDER [--target -14] [--black 0.5] [--freeze 1.0] [--silence 2.0]
         black frames, frozen picture, long silences, loudness, true peak, duration
         -> one line per issue with its time, then a verdict
  thumbs RENDER [-n 6] -o DIR
         sharp, representative frames spread over the video, saved as JPG for the user
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys


def run(args):
    if not shutil.which("ffmpeg"):
        sys.exit("ERROR: ffmpeg not found")
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True)


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def mmss(t):
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m):02d}:{s:04.1f}"


def cmd_check(a):
    issues = []
    dur = duration(a.render)
    r = run(["-i", a.render, "-vf", f"blackdetect=d={a.black}:pix_th=0.10,freezedetect=n=0.003:d={a.freeze}",
             "-af", f"silencedetect=noise=-50dB:d={a.silence},loudnorm=I={a.target}:TP=-1:LRA=11:print_format=json",
             "-f", "null", "-"])
    err = r.stderr or ""
    for s, e in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", err):
        issues.append(f"BLACK {mmss(s)}-{mmss(e)}")
    fs = re.findall(r"freeze_start:\s*([\d.]+)", err)
    fe = re.findall(r"freeze_end:\s*([\d.]+)", err)
    for i, s in enumerate(fs):
        issues.append(f"FROZEN {mmss(s)}-{mmss(fe[i]) if i < len(fe) else 'end'}")
    ss = re.findall(r"silence_start:\s*([\d.]+)", err)
    se = re.findall(r"silence_end:\s*([\d.]+)", err)
    for i, s in enumerate(ss):
        issues.append(f"SILENCE {mmss(s)}-{mmss(se[i]) if i < len(se) else 'end'}")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    if m:
        ld = json.loads(m.group(0))
        i, tp = float(ld["input_i"]), float(ld["input_tp"])
        if abs(i - a.target) > 1:
            issues.append(f"LOUDNESS {i:.1f} LUFS (target {a.target:g})")
        if tp > -1:
            issues.append(f"TRUE_PEAK {tp:.1f} dBTP (above -1, may clip)")
        loud = f"LUFS={i:.1f} TP={tp:.1f}"
    else:
        loud = "LUFS=? (no audio)"
    for x in issues:
        print(x)
    print(f"{'OK' if not issues else 'ISSUES=' + str(len(issues))} duration={dur and round(dur, 2)}s {loud}")


def cmd_thumbs(a):
    dur = duration(a.render)
    if not dur:
        sys.exit("ERROR: cannot read duration")
    os.makedirs(a.output, exist_ok=True)
    paths = []
    for k in range(a.n):
        t = dur * (k + 0.5) / a.n
        out = os.path.join(a.output, f"thumb_{k + 1:02d}_{mmss(t).replace(':', 'm')}.jpg")
        # thumbnail filter picks the most representative frame of the next ~60 frames
        r = run(["-y", "-ss", f"{max(0.0, t - 1):.2f}", "-i", a.render, "-vf", "thumbnail=60", "-frames:v", "1",
                 "-q:v", "2", out])
        if r.returncode == 0 and os.path.exists(out):
            paths.append(out)
    print(f"OK thumbs={len(paths)} -> {a.output}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check")
    c.add_argument("render")
    c.add_argument("--target", type=float, default=-14.0)
    c.add_argument("--black", type=float, default=0.5)
    c.add_argument("--freeze", type=float, default=1.0)
    c.add_argument("--silence", type=float, default=2.0)
    t = sp.add_parser("thumbs")
    t.add_argument("render")
    t.add_argument("-n", type=int, default=6)
    t.add_argument("-o", "--output", required=True)
    a = ap.parse_args()
    {"check": cmd_check, "thumbs": cmd_thumbs}[a.cmd](a)


if __name__ == "__main__":
    main()
