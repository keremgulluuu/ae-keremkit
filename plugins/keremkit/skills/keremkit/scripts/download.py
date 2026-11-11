#!/usr/bin/env python3
"""KeremKit video downloads (yt-dlp + ffmpeg) with a Premiere-safe mode and a repair chain. Stdlib only.

Commands
  setup   [--update]                       install yt-dlp into KeremKit/tools/bin (GitHub release), check
                                           ffmpeg / deno; --update runs yt-dlp -U
  info    URL [cookies]                    title, length, best quality, best H.264 quality -> what each mode gives
  get     URL --out DIR [--mode premiere_fix|best|best_repair] [--quality best|2160p|1440p|1080p|720p|480p|360p]
          [--audio mp3|m4a|wav] [--subs LANGS] [--playlist] [--keep-raw] [cookies]
  check   FILE [--scan]                    will Premiere import it? (codec / bit depth / VFR); --scan = decode scan
  repair  FILE [-o OUT] [--strategy auto|standard|container|conceal|aggressive|segmented] [--encoder auto|...]
          re-encode to H.264 + AAC MP4 (resolution and fps kept); damaged files go down a fallback chain
  cookies: --cookies-from-browser NAME | --cookies FILE

Why two ways to get a Premiere-safe file (learned from the user's VideoGrab Pro):
  * Premiere Pro cannot import VP9 / AV1 video or Opus audio ("vp09" errors). YouTube serves 1440p and
    2160p ONLY as VP9/AV1, and H.264 (avc1) up to 1080p.
  * premiere_fix asks yt-dlp for H.264 + AAC streams, skips thumbnail/metadata embedding (they can break the
    MP4 atoms) and writes +faststart. Imports everywhere, but YouTube 4K is not available as H.264, so the
    result is <= 1080p there.
  * best_repair downloads the best streams (4K/60, VP9/AV1) and re-encodes them to H.264 + AAC at the same
    resolution and frame rate. Slower, but 4K stays 4K and Premiere imports it.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

POINTER = os.path.join(os.path.expanduser("~"), ".keremkit.json")
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "Documents", "KeremKit")
EXE = ".exe" if os.name == "nt" else ""
RELEASE = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
HEIGHTS = {"2160p": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
SAFE_VIDEO = {"h264", "hevc", "prores", "dnxhd", "mpeg2video", "mpeg4", "mjpeg"}
SAFE_AUDIO = {"aac", "mp3", "ac3", "eac3", "alac", "flac", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"}
CHAIN = ["container", "standard", "conceal", "aggressive", "segmented"]
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


# ---------------------------------------------------------------- locations
def home():
    try:
        with open(POINTER, encoding="utf-8") as f:
            return json.load(f).get("home") or DEFAULT_HOME
    except (OSError, ValueError):
        return DEFAULT_HOME


def bin_dir():
    return os.path.join(home(), "tools", "bin")


def find(name):
    local = os.path.join(bin_dir(), name + EXE)
    if os.path.exists(local):
        return local
    return shutil.which(name)


def need(name, hint):
    p = find(name)
    if not p:
        sys.exit(f"ERROR: {name} not found. {hint}")
    return p


def run(cmd, timeout=None):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=ENV, timeout=timeout)


def save_last_folder(folder):
    p = os.path.join(home(), "settings", "preferences.json")
    try:
        with open(p, encoding="utf-8") as f:
            prefs = json.load(f)
        prefs.setdefault("download", {})["last_folder"] = os.path.abspath(folder)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=1)
        os.replace(p + ".tmp", p)
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------- setup
def asset_name():
    s = platform.system()
    if s == "Windows":
        return "yt-dlp.exe"
    if s == "Darwin":
        return "yt-dlp_macos"
    return "yt-dlp_linux" + ("_aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "")


def cmd_setup(a):
    os.makedirs(bin_dir(), exist_ok=True)
    target = os.path.join(bin_dir(), "yt-dlp" + EXE)
    if not os.path.exists(target) and not shutil.which("yt-dlp"):
        url = RELEASE + asset_name()
        tmp = target + ".part"
        try:
            urllib.request.urlretrieve(url, tmp)
        except Exception as e:  # noqa: BLE001
            sys.exit(f"ERROR: could not download {url}: {e}")
        os.replace(tmp, target)
        if os.name != "nt":
            os.chmod(target, 0o755)
        print(f"INSTALLED yt-dlp -> {target}")
    y = find("yt-dlp")
    if a.update:
        r = run([y, "-U"], timeout=300)
        print("UPDATE " + (r.stdout.strip().splitlines() or ["?"])[-1])
    v = run([y, "--version"], timeout=60).stdout.strip()
    print(f"OK yt-dlp {v} at {y}")
    ff = find("ffmpeg")
    print(f"OK ffmpeg at {ff}" if ff else "MISSING ffmpeg - needed to merge video+audio and to repair "
          "(install it, or put ffmpeg/ffprobe into " + bin_dir() + ")")
    dn = find("deno")
    print(f"OK deno at {dn}" if dn else "OPTIONAL deno (>= 2.3) not found - YouTube still works through fallback "
          "clients; with deno yt-dlp can use every YouTube client (put deno into " + bin_dir() + ")")


# ---------------------------------------------------------------- yt-dlp args
def platform_of(url):
    u = url.lower()
    for key, name in (("youtu", "youtube"), ("tiktok", "tiktok"), ("instagram", "instagram"),
                      ("twitter.com", "x"), ("x.com", "x"), ("facebook", "facebook"), ("fb.watch", "facebook"),
                      ("vimeo", "vimeo"), ("twitch", "twitch"), ("reddit", "reddit")):
        if key in u:
            return name
    return "other"


def format_string(mode, quality, audio):
    if audio:
        return "bestaudio/best"
    h = HEIGHTS.get(quality)
    cap = f"[height<={h}]" if h else ""
    if mode == "premiere_fix":
        return (f"bestvideo[vcodec^=avc1]{cap}+bestaudio[acodec^=mp4a]/"
                f"bestvideo[vcodec^=avc]{cap}+bestaudio[acodec^=mp4a]/"
                f"bestvideo{cap}[ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo{cap}+bestaudio/best{cap}/best")
    return f"bestvideo{cap}+bestaudio/best{cap}/best"


def base_args(url, a):
    args = ["--no-warnings", "--socket-timeout", "30", "--retries", "3", "--fragment-retries", "5",
            "--concurrent-fragments", "4"]
    args.append("--yes-playlist" if getattr(a, "playlist", False) else "--no-playlist")
    if platform_of(url) == "tiktok":
        args += ["--impersonate", "chrome", "--sleep-requests", "1"]
    if getattr(a, "cookies_from_browser", None):
        args += ["--cookies-from-browser", a.cookies_from_browser]
    if getattr(a, "cookies", None):
        args += ["--cookies", os.path.abspath(a.cookies)]
    ff = find("ffmpeg")
    if ff and os.path.dirname(ff) != os.path.dirname(shutil.which("ffmpeg") or ""):
        args += ["--ffmpeg-location", os.path.dirname(ff)]
    dn = find("deno")
    if dn and platform_of(url) == "youtube":
        args += ["--js-runtimes", "deno:" + dn]
    return args


RETRY_CLIENTS = ["--extractor-args", "youtube:player_client=default,web_embedded"]


def ytdlp(args, url, timeout=None):
    """Run yt-dlp; on YouTube's 'page needs to be reloaded' error retry once with other player clients."""
    y = need("yt-dlp", "Run: download.py setup")
    r = run([y] + args + [url], timeout=timeout)
    if r.returncode != 0 and "needs to be reloaded" in (r.stderr or "") and platform_of(url) == "youtube":
        r = run([y] + args + RETRY_CLIENTS + [url], timeout=timeout)
    return r


def last_error(stderr):
    lines = [l.strip() for l in (stderr or "").splitlines() if l.strip()]
    for l in reversed(lines):
        if l.startswith("ERROR:"):
            msg = l[6:].strip()
            break
    else:
        msg = lines[-1] if lines else "unknown error"
    hint = ""
    if re.search(r"login|sign in|cookies|private|rate-limit|age", msg, re.I):
        hint = " | HINT: this needs a signed-in session -> ask the user about cookies (download.cookies)"
    return msg[:300] + hint


# ---------------------------------------------------------------- info
def cmd_info(a):
    r = ytdlp(base_args(a.url, a) + ["--dump-single-json", "--skip-download"], a.url, timeout=180)
    if r.returncode != 0:
        sys.exit("ERROR " + last_error(r.stderr))
    d = json.loads(r.stdout)
    if d.get("_type") == "playlist":
        entries = d.get("entries") or []
        print(f"PLAYLIST {d.get('title')} items={len(entries)} (use get --playlist to download all)")
        return
    vids = [f for f in d.get("formats") or [] if f.get("vcodec") not in (None, "none") and f.get("height")]
    best = max(vids, key=lambda f: (f["height"], f.get("fps") or 0), default=None)
    avc = [f for f in vids if str(f.get("vcodec", "")).startswith("avc")]
    best_avc = max(avc, key=lambda f: (f["height"], f.get("fps") or 0), default=None)
    def desc(f):
        return f"{f['height']}p{int(f.get('fps') or 0) or ''} {str(f.get('vcodec')).split('.')[0]}" if f else "none"
    print(f"TITLE {d.get('title')}")
    print(f"FROM {platform_of(a.url)} uploader={d.get('uploader') or d.get('channel')} "
          f"length={d.get('duration') or '?'}s")
    print(f"BEST {desc(best)} | BEST_H264 {desc(best_avc)}")
    if best and best_avc and best["height"] > best_avc["height"]:
        print(f"NOTE premiere_fix gives {best_avc['height']}p; best_repair keeps {best['height']}p (slower: re-encode)")
    elif best and not best_avc:
        print("NOTE no H.264 stream: premiere_fix falls back to the best stream and repairs it")
    else:
        print("NOTE premiere_fix already gives the best quality")


# ---------------------------------------------------------------- probe / check
def probe(path):
    fp = need("ffprobe", "Install ffmpeg (ffprobe comes with it).")
    r = run([fp, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], timeout=60)
    try:
        return json.loads(r.stdout or "{}"), r.stderr or ""
    except ValueError:
        return {}, r.stderr or ""


def rate(s):
    n, _, d = (s or "0/1").partition("/")
    try:
        return float(n) / float(d or 1) if float(d or 1) else 0.0
    except ValueError:
        return 0.0


def summarize(path):
    data, err = probe(path)
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video" and
              not (s.get("disposition") or {}).get("attached_pic")), None)
    au = next((s for s in streams if s.get("codec_type") == "audio"), None)
    info = {"file": path, "duration": float((data.get("format") or {}).get("duration") or 0),
            "size": os.path.getsize(path) if os.path.exists(path) else 0,
            "video": v.get("codec_name") if v else None, "audio": au.get("codec_name") if au else None,
            "width": v.get("width") if v else None, "height": v.get("height") if v else None,
            "pix_fmt": v.get("pix_fmt") if v else None,
            "fps": round(rate(v.get("avg_frame_rate")), 3) if v else None,
            "vfr": bool(v) and abs(rate(v.get("r_frame_rate")) - rate(v.get("avg_frame_rate"))) > 0.05,
            "hdr": bool(v) and v.get("color_transfer") in ("smpte2084", "arib-std-b67"),
            "probe_error": err.strip()[:200]}
    reasons = []
    if not streams:
        reasons.append("no readable streams")
    if v and info["video"] not in SAFE_VIDEO:
        reasons.append(f"video {info['video']} (Premiere cannot import it)")
    if v and info["video"] == "h264" and "10" in (info["pix_fmt"] or ""):
        reasons.append("10-bit H.264")
    if au and info["audio"] not in SAFE_AUDIO:
        reasons.append(f"audio {info['audio']}")
    if info["vfr"]:
        reasons.append("variable frame rate (audio drifts in Premiere)")
    info["premiere_ok"] = not reasons
    info["reasons"] = reasons
    return info


PATTERNS = [  # (regex, weight) - ffmpeg decode errors, from VideoGrab Pro's corruption analyser
    (r"moov atom not found", 40), (r"header damaged", 30), (r"could not find codec parameters", 25),
    (r"invalid data found when processing input", 35), (r"invalid NAL unit size", 10),
    (r"corrupt(?:ed)? decoded frame", 15), (r"missing picture in access unit", 10),
    (r"decode_slice_header error", 10), (r"no frame!", 8), (r"concealing \d+ DC", 5),
    (r"error while decoding MB", 10), (r"(?:left|top) block unavailable", 8), (r"reference.*out of.*range", 12),
    (r"non.existing [PS]PS.*referenced", 20), (r"[sp]ps_id.*out of range", 20),
    (r"invalid timestamp", 8), (r"DTS.*out of order", 10), (r"pts.*< dts", 10),
    (r"non monotonically increasing dts", 10), (r"error decoding.*audio", 8), (r"invalid audio frame size", 10),
    (r"(?:moov|mdat).*truncated", 30), (r"discarding.*corrupted", 15), (r"invalid NAL unit.*truncated", 20),
]


def scan(path, timeout=900):
    """Decode the whole file and score the errors: 0 none, <=20 mild, <=60 moderate, <=150 severe, else catastrophic."""
    ff = need("ffmpeg", "Install ffmpeg.")
    try:
        err = run([ff, "-v", "error", "-i", path, "-f", "null", "-"], timeout=timeout).stderr or ""
    except subprocess.TimeoutExpired:
        return {"severity": "unknown", "score": None, "errors": ["scan timed out"]}
    score = sum(w * min(len(re.findall(p, err, re.I)), 10) for p, w in PATTERNS)
    sev = ("none" if score == 0 else "mild" if score <= 20 else "moderate" if score <= 60
           else "severe" if score <= 150 else "catastrophic")
    lines = [l for l in err.splitlines() if l.strip()]
    return {"severity": sev, "score": score, "errors": lines[:5], "error_lines": len(lines)}


def line(info, extra=""):
    v = f"{info['video']} {info['width']}x{info['height']} {info['fps']}fps" if info["video"] else "no video"
    ok = "ok" if info["premiere_ok"] else "NO (" + "; ".join(info["reasons"]) + ")"
    hdr = " HDR" if info["hdr"] else ""
    return (f"file={info['file']} video={v}{hdr} audio={info['audio']} length={info['duration']:.1f}s "
            f"size={info['size'] / 1e6:.1f}MB premiere={ok}{extra}")


def cmd_check(a):
    info = summarize(a.file)
    print("OK " + line(info))
    if a.scan:
        s = scan(a.file)
        print(f"SCAN severity={s['severity']} score={s['score']} error_lines={s.get('error_lines', 0)}")
        for e in s["errors"]:
            print("  " + e[:160])


# ---------------------------------------------------------------- repair
def test_encoder(ff, enc):
    r = run([ff, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:r=1", "-frames:v", "1",
             "-c:v", enc, "-f", "null", "-"], timeout=20)
    return r.returncode == 0


def pick_encoder(choice, ff):
    if choice and choice != "auto":
        return choice
    listed = run([ff, "-hide_banner", "-encoders"], timeout=20).stdout
    for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
        if enc in listed and test_encoder(ff, enc):
            return enc
    return "libx264"


def quality_args(enc, crf, strong=False):
    if enc == "libx264":
        return ["-crf", str(crf), "-preset", "slow" if strong else "medium"]
    if enc == "h264_nvenc":
        return ["-preset", "p5", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0"]
    if enc == "h264_qsv":
        return ["-global_quality", str(crf + 2)]
    if enc == "h264_amf":
        return ["-quality", "quality", "-rc", "cqp", "-qp_i", str(crf), "-qp_p", str(crf + 2)]
    return []


def video_args(info, enc, crf, strong=False, extra_vf=None):
    vf = list(extra_vf or [])
    out = ["-c:v", enc] + quality_args(enc, crf, strong) + ["-pix_fmt", "yuv420p"]
    if info.get("vfr") and info.get("fps"):
        out += ["-r", f"{info['fps']:.3f}".rstrip("0").rstrip("."), "-fps_mode", "cfr"]
    if vf:
        out += ["-vf", ",".join(vf)]
    return out


AUDIO = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]


def ffmpeg_ok(cmd, timeout):
    r = run(cmd, timeout=timeout)
    if r.returncode != 0 and "fps_mode" in (r.stderr or ""):
        i = cmd.index("-fps_mode")
        cmd[i:i + 2] = ["-vsync", "cfr"]
        r = run(cmd, timeout=timeout)
    return r.returncode == 0, (r.stderr or "").strip()[-400:]


def strategy_cmd(name, src, dst, info, enc, crf):
    ff = find("ffmpeg")
    has_v = bool(info["video"])
    v = video_args(info, enc, crf) if has_v else ["-vn"]
    if name == "container":
        return [ff, "-y", "-v", "error", "-i", src, "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy",
                "-movflags", "+faststart", dst]
    if name == "standard":
        return [ff, "-y", "-v", "error", "-i", src, "-map", "0:v:0?", "-map", "0:a:0?"] + v + AUDIO + \
               ["-movflags", "+faststart", dst]
    if name == "conceal":
        v = video_args(info, enc, max(crf - 2, 14), strong=True) if has_v else ["-vn"]
        return [ff, "-y", "-v", "error", "-err_detect", "ignore_err", "-i", src, "-map", "0:v:0?", "-map", "0:a:0?"] \
            + v + AUDIO + ["-movflags", "+faststart", dst]
    if name == "aggressive":
        v = video_args(info, enc, crf, extra_vf=["hqdn3d"] if enc == "libx264" else None) if has_v else ["-vn"]
        return [ff, "-y", "-v", "error", "-probesize", "100M", "-analyzeduration", "100M",
                "-fflags", "+genpts+igndts", "-err_detect", "ignore_err", "-i", src,
                "-map", "0:v:0?", "-map", "0:a:0?"] + v + AUDIO + ["-movflags", "+faststart", dst]
    raise ValueError(name)


def segmented(src, dst, info, enc, crf, timeout):
    ff = find("ffmpeg")
    work = tempfile.mkdtemp(prefix="kk_seg_")
    try:
        ext = os.path.splitext(src)[1] or ".mp4"
        ok, err = ffmpeg_ok([ff, "-y", "-v", "error", "-fflags", "+genpts+igndts", "-err_detect", "ignore_err",
                             "-i", src, "-c", "copy", "-f", "segment", "-segment_time", "10", "-reset_timestamps", "1",
                             os.path.join(work, "seg%04d" + ext)], timeout)
        segs = sorted(f for f in os.listdir(work) if f.startswith("seg"))
        if not segs:
            return False, err or "no segments"
        fixed = []
        for s in segs:
            out = os.path.join(work, "fix_" + os.path.splitext(s)[0] + ".mp4")
            okk, _ = ffmpeg_ok(strategy_cmd("conceal", os.path.join(work, s), out, info, enc, crf), timeout)
            if okk and os.path.exists(out) and os.path.getsize(out) > 0:
                fixed.append(out)
        if not fixed:
            return False, "no segment could be repaired"
        lst = os.path.join(work, "list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for p in fixed:
                f.write("file '" + p.replace("\\", "/").replace("'", "'\\''") + "'\n")
        ok, err = ffmpeg_ok([ff, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                             "-movflags", "+faststart", dst], timeout)
        return ok, err + f" (segments {len(fixed)}/{len(segs)})"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def validate(dst, src_info):
    """Playability score as in VideoGrab Pro: errors 40 + duration 20 + size 15 + metadata 15 + decodable 10."""
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        return 0.0, None
    out = summarize(dst)
    errs = scan(dst)
    n = errs.get("error_lines", 0) if errs["score"] is not None else 99
    score = 0.4 if n == 0 else 0.3 if n <= 3 else 0.15 if n <= 10 else 0
    d0 = src_info["duration"]
    if not d0 or abs(out["duration"] - d0) <= d0 * 0.05:
        score += 0.2
    ratio = out["size"] / src_info["size"] if src_info["size"] else 1
    if 0.05 <= ratio <= 6:
        score += 0.15
    if out["video"] or out["audio"]:
        score += 0.15
    if n == 0:
        score += 0.1
    return round(score, 2), out


def repair(src, dst, strategy="auto", encoder="auto", crf=18, timeout=7200):
    ff = need("ffmpeg", "Install ffmpeg.")
    info = summarize(src)
    if strategy == "auto":
        s = scan(src)
        start = {"none": "standard", "mild": "container", "moderate": "conceal", "severe": "aggressive",
                 "catastrophic": "segmented", "unknown": "standard"}[s["severity"]]
        # a clean file in a codec Premiere cannot read still needs a re-encode, never just a remux
        if start == "container" and not info["premiere_ok"]:
            start = "standard"
        order = CHAIN[CHAIN.index(start):]
    else:
        order = [strategy]
    enc = pick_encoder(encoder, ff)
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    tmp = os.path.splitext(dst)[0] + "_KKTEMP.mp4"
    tried = []
    for name in order:
        t0 = time.time()
        if name == "segmented":
            ok, err = segmented(src, tmp, info, enc, crf, timeout)
        else:
            ok, err = ffmpeg_ok(strategy_cmd(name, src, tmp, info, enc, crf), timeout)
            if not ok and enc != "libx264" and name != "container":   # GPU encoder failed (e.g. too big) -> CPU
                enc = "libx264"
                ok, err = ffmpeg_ok(strategy_cmd(name, src, tmp, info, enc, crf), timeout)
        score, out = validate(tmp, info) if ok else (0.0, None)
        tried.append(f"{name}:{score}")
        if ok and score >= 0.75 and out and out["premiere_ok"]:
            os.replace(tmp, dst)
            out["file"] = dst
            return out, name, enc, tried, round(time.time() - t0)
        if os.path.exists(tmp):
            os.remove(tmp)
    return None, None, enc, tried, 0


def unique(path):
    if not os.path.exists(path):
        return path
    b, e = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{b}_{i}{e}"):
        i += 1
    return f"{b}_{i}{e}"


def cmd_repair(a):
    src = os.path.abspath(a.file)
    dst = os.path.abspath(a.output) if a.output else unique(os.path.splitext(src)[0] + "_premiere.mp4")
    out, name, enc, tried, secs = repair(src, dst, a.strategy, a.encoder, a.crf)
    if not out:
        sys.exit(f"ERROR repair failed (tried {', '.join(tried)}; encoder {enc}). The original is unchanged.")
    print(f"OK repaired strategy={name} encoder={enc} took={secs}s " + line(out))


# ---------------------------------------------------------------- get
def cmd_get(a):
    if a.mode == "ask":
        sys.exit("ERROR: --mode ask is a preference; ask the user, then pass premiere_fix, best or best_repair")
    out_dir = os.path.abspath(a.out)
    os.makedirs(out_dir, exist_ok=True)
    raw_dir = out_dir if a.mode == "premiere_fix" or a.audio else os.path.join(out_dir, "_kk_raw")
    os.makedirs(raw_dir, exist_ok=True)
    args = base_args(a.url, a) + ["-f", format_string(a.mode, a.quality, a.audio),
                                  "-o", os.path.join(raw_dir, a.name),
                                  "--print", "after_move:KKFILE %(filepath)s", "--no-simulate", "--quiet",
                                  "--no-progress"]
    if a.audio:
        args += ["-x", "--audio-format", a.audio, "--audio-quality", "0"]
    else:
        args += ["--merge-output-format", "mp4"]
        if a.mode == "premiere_fix":
            args += ["--postprocessor-args", "ffmpeg:-movflags +faststart"]
        else:
            args += ["-S", "res,fps,hdr:sdr"]   # 4K60 beats 4K30; SDR over HDR (HDR looks washed out)
    if a.subs:
        args += ["--write-subs", "--write-auto-subs", "--sub-langs", a.subs, "--convert-subs", "srt"]
    r = ytdlp(args, a.url)
    files = [l[7:].strip() for l in (r.stdout or "").splitlines() if l.startswith("KKFILE ")]
    if r.returncode != 0 and not files:
        sys.exit("ERROR " + last_error(r.stderr))
    save_last_folder(out_dir)
    for f in files:
        if a.audio:
            print("OK audio " + f)
            continue
        info = summarize(f)
        need_fix = a.mode == "best_repair" or (a.mode == "premiere_fix" and not info["premiere_ok"])
        if not need_fix:
            print(f"OK mode={a.mode} " + line(info))
            continue
        dst = unique(os.path.join(out_dir, os.path.splitext(os.path.basename(f))[0] + ".mp4"))
        if info["premiere_ok"] and a.mode == "best_repair":
            # already H.264/AAC (e.g. TikTok, Instagram): nothing to re-encode, just move it out of _kk_raw
            os.replace(f, dst)
            info["file"] = dst
            print(f"OK mode=best_repair repaired=no (already Premiere-safe) " + line(info))
            continue
        out, name, enc, tried, secs = repair(f, dst, "auto", a.encoder, a.crf)
        if not out:
            print(f"WARN repair failed (tried {', '.join(tried)}); raw file kept: " + line(info))
            continue
        if not a.keep_raw and os.path.abspath(f) != os.path.abspath(dst):
            os.remove(f)
        print(f"OK mode={a.mode} repaired={name} encoder={enc} took={secs}s " + line(out))
    if os.path.isdir(os.path.join(out_dir, "_kk_raw")) and not os.listdir(os.path.join(out_dir, "_kk_raw")):
        os.rmdir(os.path.join(out_dir, "_kk_raw"))
    if r.returncode != 0:
        print("WARN yt-dlp: " + last_error(r.stderr))


# ---------------------------------------------------------------- main
def add_cookies(p):
    p.add_argument("--cookies-from-browser", help="firefox, chrome, edge, brave... (ask the user first)")
    p.add_argument("--cookies", help="cookies.txt exported by the user")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("setup")
    s.add_argument("--update", action="store_true")
    i = sp.add_parser("info")
    i.add_argument("url")
    add_cookies(i)
    g = sp.add_parser("get")
    g.add_argument("url")
    g.add_argument("--out", required=True, help="download folder (ask the user)")
    g.add_argument("--mode", choices=["premiere_fix", "best", "best_repair", "ask"], default="premiere_fix")
    g.add_argument("--quality", default="best", choices=["best"] + list(HEIGHTS))
    g.add_argument("--audio", choices=["mp3", "m4a", "wav"], help="audio only")
    g.add_argument("--subs", help="also download subtitles, e.g. 'tr,en' (as .srt)")
    g.add_argument("--playlist", action="store_true", help="download the whole playlist / profile list")
    g.add_argument("--name", default="%(title).120B [%(id)s].%(ext)s", help="yt-dlp output template")
    g.add_argument("--keep-raw", action="store_true", help="keep the original VP9/AV1 file after a repair")
    g.add_argument("--encoder", default="auto")
    g.add_argument("--crf", type=int, default=18)
    add_cookies(g)
    c = sp.add_parser("check")
    c.add_argument("file")
    c.add_argument("--scan", action="store_true", help="decode the whole file and score errors (slow on 4K)")
    rp = sp.add_parser("repair")
    rp.add_argument("file")
    rp.add_argument("-o", "--output")
    rp.add_argument("--strategy", default="auto", choices=["auto"] + CHAIN)
    rp.add_argument("--encoder", default="auto", help="auto (NVENC -> QSV -> AMF -> libx264) or an ffmpeg encoder")
    rp.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()
    {"setup": cmd_setup, "info": cmd_info, "get": cmd_get, "check": cmd_check, "repair": cmd_repair}[a.cmd](a)


if __name__ == "__main__":
    main()
