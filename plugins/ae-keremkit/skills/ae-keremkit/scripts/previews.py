#!/usr/bin/env python3
"""Library previews - find broken ones, choose the frames that show an item, build the image.

  scan   [--home H] [--brief] [--json OUT]   every library item's preview: ok / blank / missing / suspect
  probe-times DURATION [--fps F] [--n N]     evenly spaced probe times for a first, coarse render
  pick   FRAME.png ... --times T ... [--fps F] [--n 6]
                                             read the probe frames: static / animated / continuous / blank,
                                             and the times the preview should show
  sheet  FRAME.png ... -o preview.png [--times T ...] [--kind K] [--meta meta.json] [--thumb W]
                                             tile the frames over a dark backdrop into one preview, then check it
  check  IMAGE.png                           ok / blank for one image

Nothing here opens an image for Claude to look at: frames are measured as numbers.
Pixel checks need ffmpeg; without it, scan falls back to file size only.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys

SMALL = 20000          # previews under this many bytes are pixel-checked (old blank ones are 0.7-8 KB)
BLANK_STD = 1.5        # luminance spread (0-255) below this = one flat colour or fully transparent
MOVE = 0.4             # mean frame difference (0-255) above this = something moved
CONTINUOUS = 0.6       # share of probe intervals with movement that makes an item "continuous"
BACKDROP = "0x262626"  # shown behind transparent items
POINTER = os.path.join(os.path.expanduser("~"), ".keremkit.json")
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "Documents", "KeremKit")


# ---------------------------------------------------------------- pixels
def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", head[16:24])


def ffmpeg():
    return shutil.which("ffmpeg")


def luma(path, width=48):
    """Downscaled luminance, transparent parts shown over mid grey. None when ffmpeg can't read it."""
    ff = ffmpeg()
    if not ff:
        return None
    r = subprocess.run([ff, "-v", "error", "-i", path, "-vf", f"scale={width}:-2:flags=area,format=rgba",
                        "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True)
    if r.returncode or not r.stdout:
        return None
    b = r.stdout
    out = []
    for i in range(0, len(b) - 3, 4):
        a = b[i + 3] / 255.0
        y = 0.299 * b[i] + 0.587 * b[i + 1] + 0.114 * b[i + 2]
        out.append(y * a + 128.0 * (1.0 - a))
    return out


def spread(v):
    if not v:
        return 0.0
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / len(v))


def diff(a, b):
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(n)) / n if n else 0.0


def is_blank(path):
    v = luma(path)
    if v is None:
        return None
    return spread(v) < BLANK_STD


# ---------------------------------------------------------------- scan
def home_dir(h):
    if h:
        return h
    try:
        with open(POINTER, encoding="utf-8") as f:
            return json.load(f)["home"]
    except (OSError, ValueError, KeyError):
        return DEFAULT_HOME


def items(home):
    base = os.path.join(home, "library", "items")
    for cat in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        cdir = os.path.join(base, cat)
        if not os.path.isdir(cdir) or cat.startswith((".", "_")):
            continue
        for it in sorted(os.listdir(cdir)):
            mp = os.path.join(cdir, it, "meta.json")
            if os.path.isfile(mp):
                try:
                    with open(mp, encoding="utf-8") as f:
                        meta = json.load(f)
                except (OSError, ValueError):
                    meta = {}
                yield os.path.join(cdir, it), meta


def cmd_scan(a):
    home = home_dir(a.home)
    if not os.path.isdir(os.path.join(home, "library")):
        sys.exit(f"ERROR: no library in {home}")
    rows, hashes = [], {}
    have_ff = bool(ffmpeg())
    for folder, meta in items(home):
        p = os.path.join(folder, meta.get("preview") or "preview.png")
        row = {"id": meta.get("id", os.path.basename(folder)), "folder": os.path.relpath(folder, home).replace("\\", "/"),
               "comp": meta.get("comp"), "duration": meta.get("duration"), "fps": meta.get("fps"),
               "size": meta.get("size"), "pack": (meta.get("source") or {}).get("pack"),
               "original_comp": (meta.get("source") or {}).get("original_comp"), "bytes": 0}
        if not os.path.isfile(p):
            row["status"] = "missing"
        else:
            row["bytes"] = os.path.getsize(p)
            with open(p, "rb") as f:
                hashes.setdefault(hashlib.md5(f.read()).hexdigest(), []).append(row)
            if row["bytes"] >= SMALL:
                row["status"] = "ok"
            elif have_ff:
                blank = is_blank(p)
                row["status"] = "suspect" if blank is None else ("blank" if blank else "ok")
            else:
                row["status"] = "suspect"
        rows.append(row)
    for group in hashes.values():           # the same image saved for several items
        if len(group) > 1:
            for r in group:
                if r["status"] == "ok":
                    r["status"] = "suspect"
                r["same_as"] = len(group) - 1
    bad = [r for r in rows if r["status"] != "ok"]
    if not a.brief:
        for r in bad:
            extra = f"\tsame image as {r['same_as']} other(s)" if r.get("same_as") else ""
            print(f"{r['status'].upper()}\t{r['id']}\t{r['bytes']} B\t{r['folder']}{extra}")
    count = {s: sum(1 for r in rows if r["status"] == s) for s in ("ok", "blank", "missing", "suspect")}
    print("SUMMARY\titems=%d ok=%d blank=%d missing=%d suspect=%d%s" % (
        len(rows), count["ok"], count["blank"], count["missing"], count["suspect"],
        "" if have_ff else "\t(no ffmpeg: size check only)"))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(bad, f, ensure_ascii=False, indent=1)
        print(f"WROTE\t{a.json}\t{len(bad)} to repair")


# ---------------------------------------------------------------- probe / pick
def snap(t, fps):
    return round(round(t * fps) / fps, 4) if fps else round(t, 4)


def cmd_probe_times(a):
    d = a.duration
    n = a.n or max(8, min(16, round(d * 1.6)))
    times = []
    for k in range(n):
        t = snap((k + 0.5) * d / n, a.fps)
        if a.fps:
            t = min(t, snap(d - 1.0 / a.fps, a.fps))
        if t not in times:
            times.append(t)
    print(" ".join(f"{t:g}" for t in times))


def classify(lumas, times, n=6, fps=None):
    """-> (kind, preview times, indices of probe frames that can be reused or None)."""
    blanks = [spread(v) < BLANK_STD for v in lumas]
    if all(blanks):
        return "blank", [], None
    if len(lumas) == 1:
        return "static", [times[0]], [0]
    d = [diff(lumas[i - 1], lumas[i]) for i in range(1, len(lumas))]
    moving = [x > MOVE for x in d]
    if not any(moving):
        best = max(range(len(lumas)), key=lambda i: spread(lumas[i]))
        return "static", [times[best]], [best]
    if sum(moving) / len(moving) >= CONTINUOUS:
        pool = [i for i in range(len(lumas)) if not blanks[i]] or list(range(len(lumas)))
        k = min(n, len(pool))
        idx = sorted({pool[round(j * (len(pool) - 1) / max(1, k - 1))] for j in range(k)})
        return "continuous", [times[i] for i in idx], idx
    # animated: movement in some windows only - spread the frames over those windows
    segs, i = [], 0
    while i < len(moving):
        if moving[i]:
            j = i
            while j + 1 < len(moving) and moving[j + 1]:
                j += 1
            segs.append({"a": i, "b": j + 1, "score": sum(d[i:j + 1])})
            i = j + 1
        else:
            i += 1
    if len(segs) > n:
        segs = sorted(sorted(segs, key=lambda s: -s["score"])[:n], key=lambda s: s["a"])
    left = n - len(segs)
    total = sum(times[s["b"]] - times[s["a"]] for s in segs) or 1.0
    for s in segs:
        q = left * (times[s["b"]] - times[s["a"]]) / total
        s["m"], s["frac"] = 1 + int(q), q - int(q)
    rest = n - sum(s["m"] for s in segs)
    for s in sorted(segs, key=lambda s: -s["frac"])[:max(0, rest)]:
        s["m"] += 1
    out = []
    for s in segs:
        ta, tb, m = times[s["a"]], times[s["b"]], s["m"]
        settles = not blanks[s["b"]] and (s["b"] >= len(moving) or not moving[s["b"]])
        for k in range(m):
            f = (k + 1) / m if settles else (k + 0.5) / m
            t = snap(ta + (tb - ta) * f, fps)
            if t not in out:
                out.append(t)
    return "animated", sorted(out), None


def cmd_pick(a):
    if len(a.frames) != len(a.times):
        sys.exit(f"ERROR: {len(a.frames)} frames but {len(a.times)} times")
    if not ffmpeg():
        sys.exit("ERROR: ffmpeg not found (needed to read the frames)")
    lumas = []
    for p in a.frames:
        v = luma(p)
        if v is None:
            sys.exit(f"ERROR: cannot read {p}")
        lumas.append(v)
    kind, times, idx = classify(lumas, a.times, a.n, a.fps)
    print(f"KIND\t{kind}")
    if kind == "blank":
        print("NOTE\tevery probe frame is empty - check the comp (hidden layers, missing footage, wrong comp) before saving a preview")
        return
    print("TIMES\t" + " ".join(f"{t:g}" for t in times))
    if idx is None:
        print("NEXT\trender these times, then: previews.py sheet <new frames> -o <item>/preview.png --kind animated")
    else:
        print("FRAMES\t" + " ".join(a.frames[i] for i in idx))
        print("NEXT\tno new render needed: previews.py sheet <FRAMES> -o <item>/preview.png --kind " + kind)


# ---------------------------------------------------------------- sheet
def cmd_sheet(a):
    ff = ffmpeg()
    if not ff:
        sys.exit("ERROR: ffmpeg not found")
    for p in a.frames:
        if not os.path.isfile(p):
            sys.exit(f"ERROR: frame not found: {p}")
    w, h = png_size(a.frames[0])
    n = len(a.frames)
    portrait = h > w
    if n == 1:
        cols, tw = 1, a.thumb or min(w, 1280)
    else:
        cols = n if (portrait and n <= 6) else math.ceil(math.sqrt(n))
        tw = a.thumb or (240 if portrait else 480)
    tw -= tw % 2
    th = max(2, round(h * tw / w / 2) * 2)
    gap = 0 if n == 1 else 4
    rows = math.ceil(n / cols)
    parts, tiles = [], []
    for i in range(rows * cols):
        if i < n:
            parts.append(f"color=c={BACKDROP}:s={tw}x{th}:d=1[b{i}];"
                         f"[{i}:v]scale={tw}:{th}:flags=lanczos,format=rgba[s{i}];"
                         f"[b{i}][s{i}]overlay=shortest=1:format=auto,format=rgb24,"
                         f"pad={tw + 2 * gap}:{th + 2 * gap}:{gap}:{gap}:color=0x111111[t{i}]")
        else:
            parts.append(f"color=c=0x111111:s={tw + 2 * gap}x{th + 2 * gap}:d=1,format=rgb24[t{i}]")
        tiles.append(f"[t{i}]")
    row_labels = []
    for r in range(rows):
        row = tiles[r * cols:(r + 1) * cols]
        if cols == 1:
            row_labels.append(row[0])
        else:
            parts.append("".join(row) + f"hstack=inputs={cols}[r{r}]")
            row_labels.append(f"[r{r}]")
    if rows == 1:
        out = row_labels[0]
    else:
        parts.append("".join(row_labels) + f"vstack=inputs={rows}[out]")
        out = "[out]"
    cmd = [ff, "-y", "-v", "error"]
    for p in a.frames:
        cmd += ["-i", p]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cmd += ["-filter_complex", ";".join(parts), "-map", out, "-frames:v", "1", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.isfile(a.out):
        sys.exit("ERROR: ffmpeg failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    blank = is_blank(a.out)
    W, H = png_size(a.out)
    if a.meta:
        try:
            with open(a.meta, encoding="utf-8") as f:
                meta = json.load(f)
            meta["preview"] = os.path.basename(a.out)
            if a.times:
                meta["preview_times"] = a.times
            if a.kind:
                meta["preview_kind"] = a.kind
            with open(a.meta, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
        except (OSError, ValueError) as e:
            print(f"WARN\tmeta.json not updated: {e}")
    state = "BLANK" if blank else "OK"
    print(f"{state}\t{a.out}\t{W}x{H}\t{n} frame(s)\t{os.path.getsize(a.out)} B")
    if blank:
        sys.exit(1)


def cmd_check(a):
    if not os.path.isfile(a.image):
        sys.exit(f"MISSING\t{a.image}")
    blank = is_blank(a.image)
    size = os.path.getsize(a.image)
    if blank is None:
        print(f"{'SUSPECT' if size < SMALL else 'OK'}\t{a.image}\t{size} B\t(no pixel check: ffmpeg missing or unreadable)")
    else:
        print(f"{'BLANK' if blank else 'OK'}\t{a.image}\t{size} B")
        if blank:
            sys.exit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(description="KeremKit library previews")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("scan")
    s.add_argument("--home")
    s.add_argument("--brief", action="store_true", help="one summary line")
    s.add_argument("--json", help="write the items that need a new preview")
    t = sp.add_parser("probe-times")
    t.add_argument("duration", type=float)
    t.add_argument("--fps", type=float)
    t.add_argument("--n", type=int)
    p = sp.add_parser("pick")
    p.add_argument("frames", nargs="+")
    p.add_argument("--times", type=float, nargs="+", required=True)
    p.add_argument("--fps", type=float)
    p.add_argument("--n", type=int, default=6)
    h = sp.add_parser("sheet")
    h.add_argument("frames", nargs="+")
    h.add_argument("-o", "--out", required=True)
    h.add_argument("--times", type=float, nargs="+")
    h.add_argument("--kind")
    h.add_argument("--meta")
    h.add_argument("--thumb", type=int)
    c = sp.add_parser("check")
    c.add_argument("image")
    a = ap.parse_args(argv)
    {"scan": cmd_scan, "probe-times": cmd_probe_times, "pick": cmd_pick, "sheet": cmd_sheet, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
