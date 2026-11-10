"""1.10.0: Premiere export (xmeml, frame-exact EDL), .prproj reading, wordless-audio guard,
partially kept subtitle words, and download.py (format choice, Premiere check, repair)."""
import gzip
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from conftest import SCRIPTS, run

sys.path.insert(0, SCRIPTS)
import download  # noqa: E402

TICKS = 254016000000


def make_cut(tmp_path, segs, fps=60, duration=20.0):
    out, t = [], 0.0
    for a, b in segs:
        out.append({"src_in": a, "src_out": b, "out_in": round(t, 4), "out_out": round(t + b - a, 4)})
        t += b - a
    cut = {"kk": "cutlist", "version": 2, "media": str(tmp_path / "cam.mp4"), "duration": duration, "fps": fps,
           "has_video": True, "has_audio": True, "segments": out, "out_duration": round(t, 4)}
    p = tmp_path / "cut.json"
    p.write_text(json.dumps(cut), encoding="utf-8")
    return p


# ---------------------------------------------------------------- export
def test_edl_is_frame_exact_and_uses_one_audio_track(tmp_path):
    # times that rounded separately gave source length != record length
    cut = make_cut(tmp_path, [(0.008, 1.508), (2.0083, 3.4917), (5.0084, 6.0)])
    edl = tmp_path / "cut.edl"
    run("cutlist.py", "export", cut, "--format", "edl", "-o", edl)
    events = [l.split() for l in edl.read_text(encoding="utf-8").splitlines() if l[:3].isdigit()]
    assert len(events) == 3

    def frames(tc):
        h, m, s, f = map(int, tc.split(":"))
        return ((h * 60 + m) * 60 + s) * 60 + f
    prev_end = 0
    for e in events:
        assert e[2] == "B" and e[1] == "CAM"
        src_in, src_out, rec_in, rec_out = map(frames, e[-4:])
        assert src_out - src_in == rec_out - rec_in
        assert rec_in == prev_end
        prev_end = rec_out


def test_xmeml_defines_the_file_once_and_is_contiguous(tmp_path):
    cut = make_cut(tmp_path, [(0.0, 1.0), (2.5, 4.0), (6.0, 7.25)])
    out = tmp_path / "cut.xml"
    res = run("cutlist.py", "export", cut, "-o", out).stdout   # xmeml is the default
    assert "OK xmeml clips=3" in res
    root = ET.parse(out).getroot()
    assert root.tag == "xmeml"
    assert len([f for f in root.iter("file") if f.find("pathurl") is not None]) == 1
    for kind in ("video", "audio"):
        items = root.findall(f".//{kind}/track/clipitem")
        assert len(items) == 3
        end = 0
        for c in items:
            s, e, i, o = (int(c.findtext(k)) for k in ("start", "end", "in", "out"))
            assert s == end and e - s == o - i
            end = e
    assert root.find(".//pathurl").text.startswith("file://localhost/")


# ---------------------------------------------------------------- subtitles
def test_word_starting_in_a_removed_pause_is_kept(tmp_path):
    words = [{"word": " Hello", "start": 0.0, "end": 0.5},
             {"word": " world", "start": 0.6, "end": 2.0},     # Whisper start drifted into the pause
             {"word": " gone", "start": 3.0, "end": 3.4}]      # really removed
    wp = tmp_path / "w.json"
    wp.write_text(json.dumps({"language": "en", "segments": [{"words": words}]}), encoding="utf-8")
    cut = make_cut(tmp_path, [(0.0, 0.55), (1.45, 2.1)], fps=30, duration=4.0)
    base = tmp_path / "subs"
    run("subtitles.py", "build", "--words", wp, "--cutlist", cut, "-o", base, "--set", "min_words=1")
    text = " ".join(c["t"] for c in json.loads((tmp_path / "subs.json").read_text(encoding="utf-8"))["cues"])
    assert "world" in text and "gone" not in text


# ---------------------------------------------------------------- wordless audio
def test_loud_wordless_audio_is_kept_and_reported(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    media = tmp_path / "talk.wav"
    # 0-2 s tone (speech, has words), 2-3 s silence, 3-5 s tone (no words: an unheard line), 5-6 s silence, 6-8 s tone
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=f=300:d=8,volume='if(between(t,2,3)+between(t,5,6),0,1)':eval=frame",
                    "-ar", "16000", str(media)], check=True)
    words = [{"word": " a", "start": 0.1, "end": 1.9}, {"word": " b", "start": 6.1, "end": 7.9}]
    wp = tmp_path / "w.json"
    wp.write_text(json.dumps({"segments": [{"words": words}]}), encoding="utf-8")
    out = run("cutlist.py", "build", "--words", wp, "--media", media, "-o", tmp_path / "c.json").stdout
    assert "WARN loud audio without words 3.0" in out and "KEPT" in out
    cl = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert any(s["src_in"] <= 3.5 <= s["src_out"] for s in cl["segments"])
    run("cutlist.py", "build", "--words", wp, "--media", media, "--drop-wordless", "-o", tmp_path / "d.json")
    cl = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert not any(s["src_in"] <= 4.0 <= s["src_out"] for s in cl["segments"])


# ---------------------------------------------------------------- prproj
def obj(tag, oid=None, uid=None):
    e = ET.Element(tag)
    if oid:
        e.set("ObjectID", str(oid))
    if uid:
        e.set("ObjectUID", uid)
    return e


def sub(parent, path, text=None, **attrs):
    el = parent
    for part in path.split("/"):
        el = ET.SubElement(el, part)
    for k, v in attrs.items():
        el.set(k, v)
    if text is not None:
        el.text = str(text)
    return el


def tiny_prproj(path):
    root = ET.Element("PremiereData")
    seq = obj("Sequence", uid="seq-1")
    sub(seq, "Name", "Main")
    sub(seq, "TrackGroups/TrackGroup/Second", ObjectRef="1")
    vg = obj("VideoTrackGroup", 1)
    sub(vg, "TrackGroup/FrameRate", 8467200000)
    sub(vg, "FrameRect", "0,0,1080,1920")
    sub(vg.find("TrackGroup"), "Tracks/Track", ObjectRef="2")
    track = obj("VideoClipTrack", 2)
    items = sub(track, "ClipTrack/ClipItems/TrackItems")
    for oid in (3, 4):
        sub(items, "TrackItem", ObjectRef=str(oid))
    elems = [seq, vg, track]
    for oid, start, end, muted in ((3, 0, 2, False), (4, 2, 5, True)):
        it = obj("VideoClipTrackItem", oid)
        sub(it, "ClipTrackItem/TrackItem/Start", start * TICKS)
        sub(it.find("ClipTrackItem/TrackItem"), "End", end * TICKS)
        sub(it.find("ClipTrackItem"), "SubClip", ObjectRef=str(oid * 10))
        sub(it.find("ClipTrackItem"), "IsMuted", "true" if muted else "false")
        sc = obj("SubClip", oid * 10)
        sub(sc, "Name", f"clip{oid}.mp4")
        sub(sc, "Clip", ObjectRef=str(oid * 10 + 1))
        clip = obj("VideoClip", oid * 10 + 1)
        sub(clip, "Clip/InPoint", 1 * TICKS)
        sub(clip.find("Clip"), "OutPoint", 3 * TICKS)
        sub(clip.find("Clip"), "Source", ObjectRef=str(oid * 10 + 2))
        src = obj("VideoMediaSource", oid * 10 + 2)
        sub(src, "MediaSource/Media", ObjectURef=f"m{oid}")
        media = obj("Media", uid=f"m{oid}")
        sub(media, "ActualMediaFilePath", f"D:/footage/clip{oid}.mp4")
        elems += [it, sc, clip, src, media]
    root.extend(elems)
    path.write_bytes(gzip.compress(ET.tostring(root)))


def test_prproj_reads_sequences_clips_and_disabled_flag(tmp_path):
    p = tmp_path / "copy.prproj"
    tiny_prproj(p)
    assert "Main\t[1080, 1920]\t30.0\t5.0s\t2 items" in run("prproj.py", "sequences", p).stdout
    out = tmp_path / "analysis.json"
    run("prproj.py", "analyze", p, "--out", out)
    data = json.loads(out.read_text(encoding="utf-8"))
    items = data["video"][0]["items"]
    assert [i["dur"] for i in items] == [2.0, 3.0]
    assert items[0]["src"] == "D:/footage/clip3.mp4" and items[0]["in"] == 1.0
    assert [i["disabled"] for i in items] == [False, True]
    assert data["summary"]["sequence"]["fps"] == 30.0
    bad = run("prproj.py", "analyze", p, "--out", out, "--seq", "Nope", check=False)
    assert bad.returncode != 0 and "no sequence named" in bad.stderr


# ---------------------------------------------------------------- download
def test_premiere_fix_asks_for_h264_and_aac():
    f = download.format_string("premiere_fix", "1080p", None)
    assert f.startswith("bestvideo[vcodec^=avc1][height<=1080]+bestaudio[acodec^=mp4a]")
    assert f.endswith("/best")
    assert download.format_string("best", "2160p", None) == "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best"
    assert download.format_string("best_repair", "best", None) == "bestvideo+bestaudio/best/best"
    assert download.format_string("premiere_fix", "best", "mp3") == "bestaudio/best"
    assert download.platform_of("https://vm.tiktok.com/x") == "tiktok"
    assert download.platform_of("https://youtu.be/abc") == "youtube"
    assert download.platform_of("https://www.instagram.com/reel/x") == "instagram"


def test_check_flags_vp9_and_repair_makes_it_premiere_safe(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "libvpx-vp9" not in enc or "libopus" not in enc:
        pytest.skip("ffmpeg without libvpx-vp9 / libopus")
    src = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:d=2",
                    "-f", "lavfi", "-i", "sine=d=2", "-c:v", "libvpx-vp9", "-deadline", "realtime",
                    "-c:a", "libopus", "-shortest", str(src)], check=True)
    out = run("download.py", "check", src).stdout
    assert "premiere=NO" in out and "vp9" in out and "opus" in out
    res = run("download.py", "repair", src, "--encoder", "libx264").stdout
    assert "OK repaired strategy=standard encoder=libx264" in res
    assert "video=h264 640x360 30.0fps audio=aac" in res and "premiere=ok" in res
    assert (tmp_path / "clip_premiere.mp4").exists() and src.exists()   # the original is never touched
