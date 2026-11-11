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
  queue  ID [ID ...] [--home H] [--ae-home PATH] [--map m.json]
                                             one ae_render_frame call per item: ~12 probe times (alpha kept)
  auto   RUN                                 read the rendered frames: static / continuous -> preview done;
                                             animated -> a 2nd call per item with 6 times in the motion; run again
  compare ID [ID ...] -o OUT.png [--home H] [--width W]
                                             several items' previews in one sharp image, numbered 1, 2, 3...
                                             with their ids - to show the user options in the chat

Nothing here opens an image for Claude to look at: frames are measured as numbers.
Pixel checks need ffmpeg; without it, scan falls back to file size only.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys

SMALL = 20000          # previews under this many bytes are pixel-checked (old blank ones are 0.7-8 KB)
BLANK_STD = 1.5        # luminance spread (0-255) below this = one flat colour or fully transparent
MOVE = 0.4             # mean frame difference (0-255) above this = something moved
CONTINUOUS = 0.6       # share of probe intervals with movement that makes an item "continuous"
BACKDROP = "0x262626"  # shown behind transparent items
LIGHT_BACKDROP = "0xc8c8c8"  # ... when their content is dark (black icons, dark text)
POINTER = os.path.join(os.path.expanduser("~"), ".keremkit.json")
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "Documents", "KeremKit")


# ---------------------------------------------------------------- pixels
def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", head[16:24])


def image_size(path):
    """Width, height of a PNG (header) or any image ffprobe can read (TIFF from the render queue)."""
    try:
        return png_size(path)
    except ValueError:
        pass
    probe = shutil.which("ffprobe")
    if probe:
        r = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", path], capture_output=True, text=True)
        try:
            w, h = r.stdout.strip().split(",")[:2]
            return int(w), int(h)
        except ValueError:
            pass
    raise ValueError(f"cannot read the size of {path}")


def content_level(paths, width=48):
    """Mean brightness (0-255) of the visible content (alpha-weighted) - None when fully opaque or unreadable."""
    ff = ffmpeg()
    tot = wsum = 0.0
    opaque = True
    for path in paths[:6]:
        r = subprocess.run([ff, "-v", "error", "-i", path, "-vf", f"scale={width}:-2:flags=area,format=rgba",
                            "-frames:v", "1", "-f", "rawvideo", "-"], capture_output=True) if ff else None
        if not r or r.returncode or not r.stdout:
            continue
        b = r.stdout
        for i in range(0, len(b) - 3, 4):
            a = b[i + 3] / 255.0
            if a < 0.99:
                opaque = False
            tot += a * (0.299 * b[i] + 0.587 * b[i + 1] + 0.114 * b[i + 2])
            wsum += a
    if opaque or wsum < 1:
        return None
    return tot / wsum


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
def build_sheet(frames, out, thumb=None):
    """Tile frames into one image over a backdrop that suits the content. -> (W, H, blank)."""
    ff = ffmpeg()
    if not ff:
        sys.exit("ERROR: ffmpeg not found")
    for p in frames:
        if not os.path.isfile(p):
            sys.exit(f"ERROR: frame not found: {p}")
    w, h = image_size(frames[0])
    level = content_level(frames)
    backdrop = LIGHT_BACKDROP if level is not None and level < 90 else BACKDROP   # dark content -> light grey
    n = len(frames)
    portrait = h > w
    if n == 1:
        cols, tw = 1, thumb or min(w, 1280)
    else:
        cols = n if (portrait and n <= 6) else math.ceil(math.sqrt(n))
        tw = thumb or (360 if portrait else 640)
    tw -= tw % 2
    th = max(2, round(h * tw / w / 2) * 2)
    gap = 0 if n == 1 else 4
    rows = math.ceil(n / cols)
    parts, tiles = [], []
    for i in range(rows * cols):
        if i < n:
            parts.append(f"color=c={backdrop}:s={tw}x{th}:d=1[b{i}];"
                         f"[{i}:v]scale={tw}:{th}:flags=lanczos,format=rgba[s{i}];"
                         f"[b{i}][s{i}]overlay=shortest=1:format=auto,format=rgb24,"
                         f"pad={tw + 2 * gap}:{th + 2 * gap}:{gap}:{gap}:color=0x111111[t{i}]")
        else:
            parts.append(f"color=c=0x111111:s={tw + 2 * gap}x{th + 2 * gap}:d=1,format=rgb24[t{i}]")
        tiles.append(f"[t{i}]")
    row_labels = []
    for r_ in range(rows):
        row = tiles[r_ * cols:(r_ + 1) * cols]
        if cols == 1:
            row_labels.append(row[0])
        else:
            parts.append("".join(row) + f"hstack=inputs={cols}[r{r_}]")
            row_labels.append(f"[r{r_}]")
    if rows == 1:
        label = row_labels[0]
    else:
        parts.append("".join(row_labels) + f"vstack=inputs={rows}[out]")
        label = "[out]"
    cmd = [ff, "-y", "-v", "error"]
    for p in frames:
        cmd += ["-i", p]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cmd += ["-filter_complex", ";".join(parts), "-map", label, "-frames:v", "1", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.isfile(out):
        sys.exit("ERROR: ffmpeg failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    W, H = png_size(out)
    return W, H, bool(is_blank(out))


def update_meta(path, preview, times=None, kind=None):
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["preview"] = preview
        if times:
            meta["preview_times"] = times
        if kind:
            meta["preview_kind"] = kind
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    except (OSError, ValueError) as e:
        print(f"WARN\tmeta.json not updated: {e}")


def cmd_sheet(a):
    W, H, blank = build_sheet(a.frames, a.out, a.thumb)
    if a.meta:
        update_meta(a.meta, os.path.basename(a.out), a.times, a.kind)
    print(f"{'BLANK' if blank else 'OK'}\t{a.out}\t{W}x{H}\t{len(a.frames)} frame(s)\t{os.path.getsize(a.out)} B")
    if blank:
        sys.exit(1)


# ---------------------------------------------------------------- render-queue flow: any number of items, 2-4 AE calls
PROBES = 12


def motion(lumas, times):
    """-> kind, reusable probe indices (static/continuous), window (start, end) for animated."""
    blanks = [spread(v) < BLANK_STD for v in lumas]
    if all(blanks):
        return "blank", [], None
    if len(lumas) == 1:
        return "static", [0], None
    d = [diff(lumas[i - 1], lumas[i]) for i in range(1, len(lumas))]
    moving = [x > MOVE for x in d]
    if not any(moving):
        return "static", [max(range(len(lumas)), key=lambda i: spread(lumas[i]))], None
    if sum(moving) / len(moving) >= CONTINUOUS:
        pool = [i for i in range(len(lumas)) if not blanks[i]] or list(range(len(lumas)))
        k = min(6, len(pool))
        return "continuous", sorted({pool[round(j * (len(pool) - 1) / max(1, k - 1))] for j in range(k)}), None
    segs, i = [], 0
    while i < len(moving):
        if moving[i]:
            j = i
            while j + 1 < len(moving) and moving[j + 1]:
                j += 1
            segs.append((i, j + 1, sum(d[i:j + 1])))
            i = j + 1
        else:
            i += 1
    a, b = segs[0][0], segs[-1][1]
    active = sum(times[s_[1]] - times[s_[0]] for s_ in segs)
    if len(segs) > 1 and active / max(1e-6, times[b] - times[a]) < 0.4:      # long hold between: keep the main move
        a, b, _ = max(segs, key=lambda s_: s_[2])
    end = times[b]
    if blanks[b]:                                                            # moves out to nothing: stop before
        end = (times[b] + times[b - 1]) / 2
    return "animated", [], (times[a], end)


def frames_in(folder):
    """Rendered frames in order: <stem>_<index>.png from ae_render_frame (index unpadded) or any numbered files."""
    if not os.path.isdir(folder):
        return []
    files = [f for f in os.listdir(folder) if f.lower().endswith((".tif", ".tiff", ".png"))]
    num = lambda f: int((re.findall(r"(\d+)\.[A-Za-z]+$", f) or ["0"])[0])
    return [os.path.join(folder, f) for f in sorted(files, key=lambda f: (num(f), f))]


def render_calls(state, which):
    """One ae_render_frame call per item - exact times, alpha kept, colour managed."""
    out = []
    for iid, it in state["items"].items():
        p = it.get(which)
        if not p or it.get("done"):
            continue
        out.append({"compNameOrId": it["comp"], "outPath": state["ae_root"].rstrip("/") + f"/{iid}/{which}/{which}.png",
                    "times": p["times"]})
    return out


def print_calls(calls):
    print(f"RENDER\t{len(calls)} ae_render_frame call(s), one at a time (no contactSheet, no analyze):")
    for c in calls:
        print(json.dumps(c, separators=(",", ":")))


def cmd_queue(a):
    import time
    home = home_dir(a.home)
    found = {m.get("id", "").upper(): (f, m) for f, m in items(home)}
    comp_map = {}
    if a.map:
        with open(a.map, encoding="utf-8") as f:
            comp_map = {k.upper(): v for k, v in json.load(f).items()}
    run = time.strftime("%Y%m%d-%H%M%S")
    root = os.path.abspath(os.path.join(home, "library", "_work", "previews", run))
    ae_home = (a.ae_home or home).replace("\\", "/")
    state = {"root": root, "ae_root": f"{ae_home.rstrip('/')}/library/_work/previews/{run}", "items": {}}
    for iid in a.ids:
        hit = found.get(iid.upper())
        if not hit:
            sys.exit(f"ERROR: item not found: {iid}")
        folder, meta = hit
        fps, dur = meta.get("fps"), meta.get("duration")
        if not fps or not dur:
            sys.exit(f"ERROR: {iid}: meta.json needs fps and duration (read them with comp.info)")
        n = max(2, min(a.probes, 32))
        times = sorted({snap(min((k + 0.5) * dur / n, dur - 1.0 / fps), fps) for k in range(n)})
        state["items"][meta["id"]] = {"comp": comp_map.get(iid.upper()) or meta.get("comp"), "fps": fps, "duration": dur,
                                      "folder": folder, "p": {"times": times}}
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print(f"RUN\t{root}")
    print_calls(render_calls(state, "p"))
    print(f"NEXT\tafter the render: previews.py auto \"{root}\"")


def cmd_auto(a):
    path = os.path.join(a.run, "state.json")
    with open(path, encoding="utf-8") as f:
        state = json.load(f)
    pending, report = 0, {"ok": 0, "blank": 0, "missing": 0}
    for iid, it in state["items"].items():
        if it.get("done"):
            continue
        which = "a" if it.get("a") else "p"
        files = frames_in(os.path.join(state["root"], iid, which))
        if not files:
            print(f"MISSING\t{iid}\tno frames in {which}/ - render failed or still running (render.status)")
            report["missing"] += 1
            continue
        fps = it["fps"]
        times = it[which]["times"][:len(files)]
        if len(files) < len(it[which]["times"]):
            print(f"WARN\t{iid}\t{len(files)} of {len(it[which]['times'])} frames found")
        prev = os.path.join(it["folder"], "preview.png")
        meta = os.path.join(it["folder"], "meta.json")
        if which == "p":
            lumas = []
            for f_ in files:
                v = luma(f_)
                if v is None:
                    sys.exit(f"ERROR: cannot read {f_}")
                lumas.append(v)
            kind, idx, window = motion(lumas, times)
            if kind == "blank":
                print(f"BLANK\t{iid}\tevery frame empty - check the comp (glass/adjustment items need content under them)")
                it.update(done=True, kind="blank")
                report["blank"] += 1
                continue
            if kind == "animated":
                ta, tb = window
                step = max(1.0 / fps, (tb - ta) / 6)
                at = sorted({snap(max(0.0, tb - k * step), fps) for k in range(6)})
                it.update(kind="animated", a={"times": at})
                pending += 1
                continue
            use, use_times = [files[i] for i in idx], [times[i] for i in idx]
        else:
            kind, use, use_times = "animated", files[:6], times[:6]
        W, H, blank = build_sheet(use, prev)
        update_meta(meta, "preview.png", use_times, kind)
        it.update(done=True, kind=kind)
        report["blank" if blank else "ok"] += 1
        print(f"{'BLANK' if blank else 'OK'}\t{iid}\t{kind}\t{len(use)} frame(s)\t{W}x{H}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    print("SUMMARY\tok=%d blank=%d missing=%d animated_pending=%d" % (report["ok"], report["blank"], report["missing"], pending))
    if pending:
        print_calls(render_calls(state, "a"))
        print(f"NEXT\tafter the render: previews.py auto \"{a.run}\" again")


# 5x7 bitmap font: labels without depending on system fonts
FONT = {
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11110 00001 00001 01110 00001 00001 11110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01110 10001 10000 10000 10000 10001 01110", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01110 10001 10000 10111 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "01110 00100 00100 00100 00100 00100 01110", "J": "00111 00010 00010 00010 00010 10010 01100",
    "K": "10001 10010 10100 11000 10100 10010 10001", "L": "10000 10000 10000 10000 10000 10000 11111",
    "M": "10001 11011 10101 10101 10001 10001 10001", "N": "10001 11001 10101 10011 10001 10001 10001",
    "O": "01110 10001 10001 10001 10001 10001 01110", "P": "11110 10001 10001 11110 10000 10000 10000",
    "Q": "01110 10001 10001 10001 10101 10010 01101", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "V": "10001 10001 10001 10001 10001 01010 00100",
    "W": "10001 10001 10001 10101 10101 10101 01010", "X": "10001 10001 01010 00100 01010 10001 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "Z": "11111 00001 00010 00100 01000 10000 11111",
    "-": "00000 00000 00000 11111 00000 00000 00000", " ": "00000 00000 00000 00000 00000 00000 00000",
}


def text_boxes(text, x, y, px, color):
    """drawbox filters that write text with the bitmap font (one box per horizontal run of pixels)."""
    out = []
    for ch in text.upper():
        rows = FONT.get(ch, FONT[" "]).split()
        for ry, row in enumerate(rows):
            cx = 0
            while cx < 5:
                if row[cx] == "1":
                    run = 1
                    while cx + run < 5 and row[cx + run] == "1":
                        run += 1
                    out.append(f"drawbox=x={x + cx * px}:y={y + ry * px}:w={run * px}:h={px}:color={color}:t=fill")
                    cx += run
                else:
                    cx += 1
        x += 6 * px
    return out


def cmd_compare(a):
    ff = ffmpeg()
    if not ff:
        sys.exit("ERROR: ffmpeg not found")
    home = home_dir(a.home)
    found = {}
    for folder, meta in items(home):
        if meta.get("id"):
            found[meta["id"].upper()] = (folder, meta)
    paths, labels = [], []
    for n, item_id in enumerate(a.ids, 1):
        hit = found.get(item_id.upper())
        if not hit:
            sys.exit(f"ERROR: item not found: {item_id}")
        p = os.path.join(hit[0], hit[1].get("preview") or "preview.png")
        if not os.path.isfile(p):
            sys.exit(f"ERROR: {item_id} has no preview - make one first (library-save.md 4b)")
        if is_blank(p):
            print(f"WARN\t{item_id}\tpreview is empty - repair it before showing it")
        paths.append(p)
        name = "".join(c for c in str(hit[1].get("name") or "").upper() if c in FONT)[:36].strip()
        labels.append(f"{n}  {hit[1]['id']}" + (f"  {name}" if name else ""))
    W = a.width
    strip, px = 64, 6
    parts = []
    for i, (p, label) in enumerate(zip(paths, labels)):
        w, h = png_size(p)
        th = max(2, round(h * W / w / 2) * 2)
        draw = ",".join(text_boxes(label, 24, (strip - 7 * px) // 2, px, "white"))
        parts.append(f"[{i}:v]scale={W}:{th}:flags=lanczos,format=rgba[s{i}];"
                     f"color=c={BACKDROP}:s={W}x{th}:d=1[b{i}];[b{i}][s{i}]overlay=shortest=1:format=auto,format=rgb24[p{i}];"
                     f"color=c=0x111111:s={W}x{strip}:d=1,format=rgb24,{draw}[l{i}];[l{i}][p{i}]vstack=inputs=2[r{i}]")
    rows = "".join(f"[r{i}]" for i in range(len(paths)))
    out = "[r0]" if len(paths) == 1 else "[out]"
    if len(paths) > 1:
        parts.append(f"{rows}vstack=inputs={len(paths)}[out]")
    cmd = [ff, "-y", "-v", "error"]
    for p in paths:
        cmd += ["-i", p]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    cmd += ["-filter_complex", ";".join(parts), "-map", out, "-frames:v", "1", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode or not os.path.isfile(a.out):
        sys.exit("ERROR: ffmpeg failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    W2, H2 = png_size(a.out)
    print(f"OK\t{a.out}\t{W2}x{H2}\t{len(paths)} item(s)\t{os.path.getsize(a.out)} B")


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
    q = sp.add_parser("queue")
    q.add_argument("ids", nargs="+")
    q.add_argument("--home")
    q.add_argument("--ae-home", help="the KeremKit folder as After Effects sees it, when the tools run elsewhere (e.g. C:/Users/me/Documents/KeremKit)")
    q.add_argument("--map", help='JSON {"ID": comp name or id} - e.g. a TMP_ comp with content under a glass item')
    q.add_argument("--probes", type=int, default=PROBES)
    au = sp.add_parser("auto")
    au.add_argument("run", help="the RUN folder printed by queue")
    m = sp.add_parser("compare")
    m.add_argument("ids", nargs="+")
    m.add_argument("-o", "--out", required=True)
    m.add_argument("--home")
    m.add_argument("--width", type=int, default=1920, help="width of each item's row (default 1920)")
    c = sp.add_parser("check")
    c.add_argument("image")
    a = ap.parse_args(argv)
    {"scan": cmd_scan, "probe-times": cmd_probe_times, "pick": cmd_pick, "sheet": cmd_sheet, "check": cmd_check, "compare": cmd_compare, "queue": cmd_queue, "auto": cmd_auto}[a.cmd](a)


if __name__ == "__main__":
    main()
