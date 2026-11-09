#!/usr/bin/env python3
"""KeremKit audio tool - measure and clean up voice and music with ffmpeg (stdlib only).

  analyze FILE                                   loudness (LUFS), true peak, range, noise floor + advice
  process IN OUT [--chain highpass,denoise,deess,eq,compress,loudnorm] [--target -14] [--tp -1]
                                                 voice clean-up chain; loudnorm is two-pass (exact)
  duck    VOICE MUSIC OUT [--duck-db -12] [--music-db -18]
                                                 music that dips under speech (sidechain), for a music layer

Video inputs keep their picture untouched (stream copy); only the audio is processed.
Every command prints one or two lines.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys

CHAIN = {
    "highpass": "highpass=f=80",
    "denoise": "afftdn=nr=10:nf=-50:tn=1",
    "deess": "deesser=i=0.35:m=0.5:f=0.5",
    "eq": "equalizer=f=300:t=q:w=1.2:g=-2,equalizer=f=4200:t=q:w=1.0:g=2",
    "compress": "acompressor=threshold=-20dB:ratio=3:attack=8:release=160:makeup=2",
}
ORDER = ["highpass", "denoise", "deess", "eq", "compress", "loudnorm"]


def ffmpeg(args):
    if not shutil.which("ffmpeg"):
        sys.exit("ERROR: ffmpeg not found")
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True)


def has_video(path):
    if not shutil.which("ffprobe"):
        return False
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return "video" in r.stdout


def measure(path, pre="", target=-14.0, tp=-1.0):
    af = (pre + "," if pre else "") + f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json"
    r = ffmpeg(["-i", path, "-map", "0:a:0", "-af", af, "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "", re.S)
    if not m:
        sys.exit("ERROR: could not measure loudness: " + (r.stderr or "")[-300:])
    return json.loads(m.group(0))


def noise_floor(path):
    r = ffmpeg(["-i", path, "-map", "0:a:0", "-af", "astats=metadata=0:reset=0", "-f", "null", "-"])
    vals = [float(x) for x in re.findall(r"Noise floor dB:\s*(-?[\d.]+)", r.stderr or "") if x not in ("-inf",)]
    return min(vals) if vals else None


def cmd_analyze(a):
    m = measure(a.file)
    nf = noise_floor(a.file)
    i, tpk, lra = float(m["input_i"]), float(m["input_tp"]), float(m["input_lra"])
    nf_txt = f"{nf:.1f}dB" if nf is not None else "?"
    print(f"LUFS={i:.1f} TRUE_PEAK={tpk:.1f}dBTP LRA={lra:.1f} NOISE_FLOOR={nf_txt}")
    advice = []
    if abs(i - a.target) > 1:
        advice.append(f"loudnorm to {a.target:g} LUFS ({'+' if a.target > i else ''}{a.target - i:.1f} dB)")
    if tpk > -1:
        advice.append("true peak above -1 dBTP (clipping risk) -> loudnorm")
    if nf is not None and nf > -55:
        advice.append("audible noise floor -> denoise")
    if lra > 12:
        advice.append("wide dynamic range -> compress")
    print("ADVICE " + ("; ".join(advice) if advice else "none - within targets"))


def cmd_process(a):
    steps = [s.strip() for s in a.chain.split(",") if s.strip()]
    bad = [s for s in steps if s not in ORDER]
    if bad:
        sys.exit(f"ERROR: unknown step(s) {bad}; use {','.join(ORDER)}")
    steps = [s for s in ORDER if s in steps]          # always in a sensible order
    pre = ",".join(CHAIN[s] for s in steps if s != "loudnorm")
    af = pre
    if "loudnorm" in steps:
        m = measure(a.input, pre, a.target, a.tp)
        ln = (f"loudnorm=I={a.target}:TP={a.tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        af = (pre + "," if pre else "") + ln
    if not af:
        sys.exit("ERROR: empty chain")
    video = has_video(a.input)
    args = ["-y", "-i", a.input, "-map", "0:a:0", "-af", af, "-ar", "48000"]
    if video:
        args = ["-y", "-i", a.input, "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", af,
                "-c:a", "aac", "-b:a", "256k", "-ar", "48000"]
    elif a.output.lower().endswith(".wav"):
        args += ["-c:a", "pcm_s16le"]
    r = ffmpeg(args + [a.output])
    if r.returncode != 0:
        sys.exit("ERROR ffmpeg: " + (r.stderr or "")[-400:])
    after = measure(a.output, "", a.target, a.tp)
    print(f"OK {a.output} chain={','.join(steps)} LUFS={float(after['input_i']):.1f} "
          f"TRUE_PEAK={float(after['input_tp']):.1f}dBTP")


def cmd_duck(a):
    fc = (f"[1:a]volume={a.music_db}dB[m];[0:a]asplit=1[sc];"
          f"[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=25:release=450:makeup=1:"
          f"level_sc=1:knee=4[ducked]")
    r = ffmpeg(["-y", "-i", a.voice, "-i", a.music, "-filter_complex", fc, "-map", "[ducked]",
                "-ar", "48000"] + (["-c:a", "pcm_s16le"] if a.output.lower().endswith(".wav") else []) + [a.output])
    if r.returncode != 0:
        sys.exit("ERROR ffmpeg: " + (r.stderr or "")[-400:])
    print(f"OK {a.output} music at {a.music_db:g} dB, ducks under speech (sidechain)")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    an = sp.add_parser("analyze")
    an.add_argument("file")
    an.add_argument("--target", type=float, default=-14.0)
    pr = sp.add_parser("process")
    pr.add_argument("input")
    pr.add_argument("output")
    pr.add_argument("--chain", default="highpass,compress,loudnorm")
    pr.add_argument("--target", type=float, default=-14.0)
    pr.add_argument("--tp", type=float, default=-1.0)
    du = sp.add_parser("duck")
    du.add_argument("voice")
    du.add_argument("music")
    du.add_argument("output")
    du.add_argument("--duck-db", type=float, default=-12.0, help="kept for reference; depth follows the sidechain")
    du.add_argument("--music-db", type=float, default=-18.0)
    a = ap.parse_args()
    {"analyze": cmd_analyze, "process": cmd_process, "duck": cmd_duck}[a.cmd](a)


if __name__ == "__main__":
    main()
