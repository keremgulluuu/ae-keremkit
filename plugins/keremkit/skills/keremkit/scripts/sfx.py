#!/usr/bin/env python3
"""KeremKit SFX - synthesise basic edit sound effects with ffmpeg (no samples, no licences).

  list                             the sounds this tool makes
  make  [NAME ...] -o DIR [--variants 3]
                                   write WAV files (48 kHz mono), e.g. whoosh_1.wav, impact_1.wav
                                   NAME defaults to all; variants differ slightly in pitch/length

Use them when the user has no SFX folder, or as placeholders; real libraries sound richer.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

PEAK_DB = -3.0   # every sound peaks here; set the level in the edit (see sound-effects.md)

SOUNDS = {
    # name: (duration, filter graph building the sound from lavfi sources; {d} and {v} are filled in)
    "whoosh": (0.55, "anoisesrc=d={d}:c=pink:a=0.9,highpass=f=300,lowpass=f=6000,"
                     "volume='if(lt(t,{d}*0.6),t/({d}*0.6),({d}-t)/({d}*0.4))':eval=frame,"
                     "bandpass=f=1200*{v}:w=1.2"),
    "impact": (0.9, "sine=f=55*{v}:d={d},volume='exp(-6*t)':eval=frame[a];"
                    "anoisesrc=d=0.08:c=brown:a=0.8,lowpass=f=900[b];[a][b]amix=inputs=2:normalize=0"),
    "pop": (0.12, "sine=f=900*{v}:d={d},volume='exp(-35*t)':eval=frame"),
    "tick": (0.05, "anoisesrc=d={d}:c=white:a=0.6,highpass=f=2500,volume='exp(-90*t)':eval=frame"),
    "click": (0.04, "sine=f=2200*{v}:d={d},volume='exp(-120*t)':eval=frame"),
    "glitch": (0.25, "anoisesrc=d={d}:c=white:a=0.7,acrusher=bits=4:samples=12*{v}:mix=1,"
                     "volume='if(lt(mod(t,0.05),0.025),1,0.15)':eval=frame,highpass=f=200"),
    "flash": (0.35, "anoisesrc=d={d}:c=white:a=0.5,highpass=f=4000,volume='exp(-9*t)':eval=frame"),
    "riser": (2.0, "sine=f=200*{v}:d={d},vibrato=f=6:d=0.3,volume='t/{d}':eval=frame[a];"
                   "anoisesrc=d={d}:c=pink:a=0.3,highpass=f=800,volume='(t/{d})^2':eval=frame[b];"
                   "[a][b]amix=inputs=2:normalize=0"),
    "typing": (1.2, "anoisesrc=d={d}:c=white:a=0.6,highpass=f=1800,"
                    "volume='if(lt(mod(t,0.085*{v}),0.012),1,0)':eval=frame"),
}


def render(name, out, variant):
    d, graph = SOUNDS[name]
    v = 1 + 0.08 * (variant - 1) * (1 if variant % 2 else -1)
    d = round(d * (1 + 0.1 * (variant - 1)), 3)
    g = graph.format(d=d, v=round(v, 3))
    fc = g
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=0.01",
           "-filter_complex", fc + ",aformat=sample_rates=48000:channel_layouts=mono,afade=t=out:st=" +
           f"{max(0, d - 0.01)}:d=0.01", "-t", str(d), "-ac", "1", "-ar", "48000", out]
    tmp = out + ".tmp.wav"
    cmd[-1] = tmp
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip()[-300:])
    # normalise every sound to the same peak so levels in the edit are predictable
    m = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", tmp, "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", m or "")
    gain = PEAK_DB - float(peak.group(1)) if peak else 0.0
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af", f"volume={gain:.2f}dB", "-c:a", "pcm_s16le", out],
                       capture_output=True, text=True)
    os.remove(tmp)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip()[-300:])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list")
    m = sp.add_parser("make")
    m.add_argument("names", nargs="*")
    m.add_argument("-o", "--output", required=True)
    m.add_argument("--variants", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "list":
        for n, (d, _) in SOUNDS.items():
            print(f"{n}\t{d}s")
        return
    if not shutil.which("ffmpeg"):
        sys.exit("ERROR: ffmpeg not found")
    names = a.names or list(SOUNDS)
    bad = [n for n in names if n not in SOUNDS]
    if bad:
        sys.exit(f"ERROR: unknown sound(s) {bad}; use: {', '.join(SOUNDS)}")
    os.makedirs(a.output, exist_ok=True)
    made, failed = 0, []
    for n in names:
        for k in range(1, a.variants + 1):
            try:
                render(n, os.path.join(a.output, f"{n}_{k}.wav"), k)
                made += 1
            except RuntimeError as e:
                failed.append(f"{n}: {e}")
    for f in failed:
        print("FAILED " + f)
    print(f"OK made={made} -> {a.output}")
    if failed and not made:
        sys.exit(1)


if __name__ == "__main__":
    main()
