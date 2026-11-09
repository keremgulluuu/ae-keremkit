import json
import os
import subprocess
import zipfile

import pytest

from conftest import run


@pytest.fixture
def home(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "KeremKit"
    run("keremkit.py", "init", kk, env=env)
    return kk, env


# ---------------------------------------------------------------- techniques
def test_techniques_list_show_add(home):
    kk, env = home
    groups = run("techniques.py", "groups", env=env).stdout
    assert "cuts" in groups and "audio" in groups
    cuts = run("techniques.py", "list", "--group", "cuts", env=env).stdout
    assert "j-cut\tJ-cut" in cuts and "l-cut\tL-cut" in cuts and "jump-cut-zoom" in cuts
    audio = run("techniques.py", "list", "--group", "audio", env=env).stdout
    assert "loudness-normalize" in audio and "ducking" in audio
    assert "what\t" in run("techniques.py", "show", "l-cut", env=env).stdout
    run("techniques.py", "add", "--id", "glitch-cut", "--group", "cuts", "--name", "Glitch cut",
        "--what", "RGB split on the cut frame", "--auto", env=env)
    assert "glitch-cut\tGlitch cut\t[auto, user]" in run("techniques.py", "list", "--group", "cuts", env=env).stdout
    # the copy inside KeremKit/tools works too (techniques.json copied by init)
    import sys
    out = subprocess.run([sys.executable, "-I", str(kk / "tools" / "techniques.py"), "list",
                          "--group", "qc"], capture_output=True, text=True, env=env).stdout
    assert "pre-render-qc" in out


# ---------------------------------------------------------------- cut extras
def build_cut(tmp_path, words_file):
    words, dur = words_file
    cut = tmp_path / "cut.json"
    run("cutlist.py", "build", "--words", words, "--media", tmp_path / "x.mp4", "--duration", dur, "--fps", 30,
        "--silence", "off", "-o", cut)
    return cut


def test_zoom_alternates_and_punches_in(tmp_path, words_file):
    cut = build_cut(tmp_path, words_file)
    subs = tmp_path / "subs"
    run("subtitles.py", "build", "--words", words_file[0], "--cutlist", cut, "-o", subs)
    z = tmp_path / "zoom.json"
    out = run("cutlist.py", "zoom", cut, "--emphasis", f"{subs}.json", "--ease-frames", 2, "-o", z).stdout
    data = json.loads(z.read_text(encoding="utf-8"))["cuts"]
    levels = [c["z"] for c in data if c["z"] != 118]
    assert levels[:4] == [100, 110, 100, 110]
    assert any(c["z"] == 118 for c in data) and "punch_ins=" in out
    assert all(a["e"] <= b["s"] + 1e-6 for a, b in zip(data, data[1:]))
    assert 'footage("zoom.json")' in out and "ease(time" in out


def test_edl_and_fcpxml_export(tmp_path, words_file):
    cut = build_cut(tmp_path, words_file)
    cl = json.loads(cut.read_text(encoding="utf-8"))
    edl = tmp_path / "cut.edl"
    run("cutlist.py", "export", cut, "--format", "edl", "-o", edl)
    lines = edl.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("TITLE:") and lines[1] == "FCM: NON-DROP FRAME"
    events = [l for l in lines if l[:3].isdigit()]
    assert len(events) == len(cl["segments"])
    assert events[0].split()[-2] == "00:00:00:00"
    xml = tmp_path / "cut.fcpxml"
    run("cutlist.py", "export", cut, "--format", "fcpxml", "-o", xml)
    import xml.etree.ElementTree as ET
    root = ET.parse(xml).getroot()
    assert root.tag == "fcpxml" and len(root.findall(".//asset-clip")) == len(cl["segments"])


def test_review_in_timeline_time(tmp_path, words_file):
    cut = build_cut(tmp_path, words_file)
    out = run("transcript.py", "review", words_file[0], "--cutlist", cut).stdout.splitlines()
    first = out[0].split(" | ")[0]
    assert first == "00:00.0" or first.startswith("00:00")
    times = [l.split(" | ")[0] for l in out if " | " in l]
    assert times == sorted(times)


# ---------------------------------------------------------------- audio / qc
@pytest.fixture
def voice(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    p = tmp_path / "voice.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "aevalsrc='0.08*sin(2*PI*220*t)*between(mod(t,3),0,2)':s=48000:d=9", str(p)], check=True)
    return p


def test_audio_analyze_and_process(tmp_path, voice):
    out = run("audio.py", "analyze", voice).stdout
    assert out.startswith("LUFS=") and "ADVICE" in out and "loudnorm" in out
    clean = tmp_path / "clean.wav"
    out = run("audio.py", "process", voice, clean, "--chain", "loudnorm,highpass,compress").stdout
    assert "chain=highpass,compress,loudnorm" in out                  # always a sensible order
    lufs = float(out.split("LUFS=")[1].split()[0])
    assert lufs == pytest.approx(-14, abs=1.0)


def test_audio_duck(tmp_path, voice):
    music = tmp_path / "music.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=110:d=9",
                    "-af", "volume=0.4", str(music)], check=True)
    out_p = tmp_path / "ducked.wav"
    assert "OK" in run("audio.py", "duck", voice, music, out_p).stdout and out_p.exists()


def test_qc_finds_black_and_thumbs(tmp_path, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    r = tmp_path / "render.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=1.5",
                    "-f", "lavfi", "-i", "testsrc=s=320x180:r=30:d=6", "-f", "lavfi", "-i", "sine=f=440:d=7.5",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(r)], check=True)
    out = run("qc.py", "check", r).stdout
    assert "BLACK 00:00.0" in out and "ISSUES=" in out
    out = run("qc.py", "thumbs", r, "-n", 3, "-o", tmp_path / "th").stdout
    assert "thumbs=3" in out and len(list((tmp_path / "th").glob("*.jpg"))) == 3


# ---------------------------------------------------------------- doctor / pack / unpack
def test_doctor(home):
    _, env = home
    out = run("keremkit.py", "doctor", env=env).stdout
    assert "OK\tpython" in out and "home" in out and "preferences" in out


def test_pack_unpack_roundtrip(tmp_path, home):
    kk, env = home
    item = kk / "library" / "items" / "ui" / "UI-001_gold-counter"
    item.mkdir(parents=True)
    (item / "item.aep").write_bytes(b"aep")
    (item / "meta.json").write_text(json.dumps({"id": "UI-001", "name": "Gold Counter", "category": "ui",
        "tags": ["counter"], "summary": "s", "file": "item.aep", "deps": {"fonts": ["Inter-Black"], "plugins": []}}), encoding="utf-8")
    run("keremkit.py", "add", item / "meta.json", env=env)
    pkg = tmp_path / "share.zip"
    assert "items=1" in run("keremkit.py", "pack", "--items", "UI-001", "-o", pkg, env=env).stdout
    assert "manifest.json" in zipfile.ZipFile(pkg).namelist()

    other = tmp_path / "friend"
    env2 = dict(os.environ, HOME=str(other), USERPROFILE=str(other))
    run("keremkit.py", "init", other / "KeremKit", env=env2)
    clash = other / "KeremKit" / "library" / "items" / "ui" / "UI-001_card"
    clash.mkdir(parents=True)
    (clash / "meta.json").write_text(json.dumps({"id": "UI-001", "name": "Card", "category": "ui", "tags": ["c"],
                                                 "summary": "s"}), encoding="utf-8")
    run("keremkit.py", "add", clash / "meta.json", env=env2)
    out = run("keremkit.py", "unpack", pkg, env=env2).stdout
    assert "imported=1 renamed_ids=1" in out and "FONTS_NEEDED\tInter-Black" in out
    hits = run("keremkit.py", "search", "gold", "counter", env=env2).stdout
    assert "UI-002" in hits
    assert run("keremkit.py", "validate", env=env2).stdout.strip() == "OK"
