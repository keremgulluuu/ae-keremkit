import json
import subprocess

import pytest

from conftest import run


def build(tmp_path, words, duration, preset="tight"):
    media = tmp_path / "missing.mp4"  # no ffprobe needed when --duration and --fps are given
    out = tmp_path / "cam.cut.json"
    run("cutlist.py", "build", "--words", words, "--media", media, "--preset", preset,
        "--duration", duration, "--fps", 30, "-o", out)
    return out, json.loads(out.read_text(encoding="utf-8"))


def test_build_removes_long_pauses(tmp_path, words_file):
    words, dur = words_file
    _, cl = build(tmp_path, words, dur)
    assert cl["out_duration"] < dur * 0.8
    segs = cl["segments"]
    for a, b in zip(segs, segs[1:]):
        assert b["src_in"] > a["src_out"]                      # sorted, no overlap
        assert abs(b["out_in"] - a["out_out"]) < 1e-3          # output is continuous
    for s in segs:                                             # snapped to 30 fps
        assert abs(s["src_in"] * 30 - round(s["src_in"] * 30)) < 0.01


def test_presets_are_ordered(tmp_path, words_file):
    words, dur = words_file
    _, tight = build(tmp_path, words, dur, "tight")
    _, relaxed = build(tmp_path, words, dur, "relaxed")
    assert tight["out_duration"] < relaxed["out_duration"]


def test_add_never_exceeds_removed_pause(tmp_path, words_file):
    words, dur = words_file
    path, before = build(tmp_path, words, dur)
    out = run("cutlist.py", "add", path, "--from", 4, "--to", 6, "--sec", 1).stdout
    after = json.loads(path.read_text(encoding="utf-8"))
    added = after["out_duration"] - before["out_duration"]
    assert 0 < added <= 1.0 + 1e-3
    assert "added=" in out


def test_strict_add_stays_inside_range(tmp_path, words_file):
    words, dur = words_file
    path, before = build(tmp_path, words, dur)
    run("cutlist.py", "add", path, "--from", 4, "--to", 6, "--sec", 5, "--strict")
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["out_duration"] - before["out_duration"] < 5


def test_cut_restore_undo_roundtrip(tmp_path, words_file):
    words, dur = words_file
    path, original = build(tmp_path, words, dur)
    run("cutlist.py", "cut", path, "--from", 1, "--to", 1.5)
    cut = json.loads(path.read_text(encoding="utf-8"))
    assert cut["out_duration"] == pytest.approx(original["out_duration"] - 0.5, abs=0.04)
    run("cutlist.py", "undo", path)
    back = json.loads(path.read_text(encoding="utf-8"))
    assert back["out_duration"] == pytest.approx(original["out_duration"], abs=1e-3)
    run("cutlist.py", "restore", path, "--src-from", 0, "--src-to", 0.6)
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored["segments"][0]["src_in"] == 0


def test_map_both_directions(tmp_path, words_file):
    words, dur = words_file
    path, cl = build(tmp_path, words, dur)
    seg = cl["segments"][2]
    mid_src = (seg["src_in"] + seg["src_out"]) / 2
    out = run("cutlist.py", "map", path, "--src", mid_src).stdout
    assert "-> out" in out
    gap = (cl["segments"][0]["src_out"] + cl["segments"][1]["src_in"]) / 2
    assert "REMOVED" in run("cutlist.py", "map", path, "--src", gap).stdout


def test_render_matches_cut_list(tmp_path, words_file, has_ffmpeg):
    if not has_ffmpeg:
        pytest.skip("ffmpeg not installed")
    words, dur = words_file
    media = tmp_path / "cam.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", str(dur),
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(media)], check=True)
    cut = tmp_path / "cam.cut.json"
    run("cutlist.py", "build", "--words", words, "--media", media, "--preset", "tight", "-o", cut)
    out = tmp_path / "cam_cut.mp4"
    run("cutlist.py", "render", cut, "-o", out, "--run")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=duration", "-of", "csv=p=0", str(out)], capture_output=True, text=True)
    expected = json.loads(cut.read_text(encoding="utf-8"))["out_duration"]
    assert float(probe.stdout.strip()) == pytest.approx(expected, abs=0.1)
