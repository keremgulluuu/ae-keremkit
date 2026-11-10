"""1.5: library previews (scan / pick / sheet), safe copies, save proof, tool version."""
import json
import os
import re
import shutil
import subprocess

import pytest

from pathlib import Path

from conftest import ROOT as _ROOT, run

ROOT = Path(_ROOT)

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg needed")
TIMES = [0.5 + i for i in range(12)]


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def transparent(path, size="320x180"):
    ff("-f", "lavfi", "-i", f"color=c=black@0.0:s={size},format=rgba", "-frames:v", "1", path)


def box(path, x):
    ff("-f", "lavfi", "-i", "color=c=black@0.0:s=320x180,format=rgba", "-f", "lavfi", "-i", "color=c=white:s=80x80",
       "-filter_complex", f"[0][1]overlay=x={x}:y=40,format=rgba", "-frames:v", "1", path)


def frames(tmp_path, kind):
    out = []
    if kind == "continuous":
        ff("-f", "lavfi", "-i", "testsrc=s=320x180:r=10", "-frames:v", 12, "-start_number", 0, tmp_path / "c_%02d.png")
        return [tmp_path / f"c_{i:02d}.png" for i in range(12)]
    for i in range(12):
        p = tmp_path / f"{kind}_{i:02d}.png"
        if kind == "static":
            box(p, 100)
        elif kind == "blank":
            transparent(p)
        else:                       # animated: empty, moves for 3 probes, then holds
            transparent(p) if i < 4 else box(p, 30 * min(i, 6))
        out.append(p)
    return out


@pytest.mark.parametrize("kind", ["static", "continuous", "animated", "blank"])
def test_pick_classifies_motion(tmp_path, kind):
    out = run("previews.py", "pick", *frames(tmp_path, kind), "--times", *TIMES, "--fps", 30).stdout
    assert f"KIND\t{kind}" in out
    times = [float(t) for t in re.search(r"TIMES\t(.*)", out).group(1).split()] if kind != "blank" else []
    if kind == "static":
        assert len(times) == 1 and "FRAMES" in out
    if kind == "continuous":
        assert len(times) == 6 and "FRAMES" in out
    if kind == "animated":
        assert len(times) == 6 and "render these times" in out
        assert all(3.5 < t <= 6.5 for t in times) and times[-1] == 6.5   # inside the motion, ends settled


def test_probe_times_spread_and_snap():
    t = [float(x) for x in run("previews.py", "probe-times", 10.01, "--fps", 29.97).stdout.split()]
    assert 8 <= len(t) <= 16 and t[0] > 0 and t[-1] < 10.01
    assert all(abs(x * 29.97 - round(x * 29.97)) < 0.01 for x in t)


def test_sheet_layout_and_meta(tmp_path):
    ff("-f", "lavfi", "-i", "testsrc=s=1080x1920", "-frames:v", 6, "-start_number", 0, tmp_path / "v_%d.png")
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"id": "UI-001"}), encoding="utf-8")
    out = run("previews.py", "sheet", *[tmp_path / f"v_{i}.png" for i in range(6)], "-o", tmp_path / "item" / "preview.png",
              "--kind", "animated", "--times", 1, 2, 3, 4, 5, 6, "--meta", meta).stdout
    assert out.startswith("OK") and "6 frame(s)" in out
    w, h = map(int, re.search(r"(\d+)x(\d+)", out).groups())
    assert w > 3 * h                                        # vertical items: one row of 6
    m = json.loads(meta.read_text(encoding="utf-8"))
    assert m["preview_kind"] == "animated" and m["preview_times"] == [1, 2, 3, 4, 5, 6]


def test_sheet_refuses_blank_result(tmp_path):
    transparent(tmp_path / "b.png")
    r = run("previews.py", "sheet", tmp_path / "b.png", "-o", tmp_path / "p.png", check=False)
    assert r.returncode == 1 and "BLANK" in r.stdout


def test_scan_finds_blank_missing_and_duplicates(tmp_path):
    lib = tmp_path / "KeremKit" / "library" / "items" / "ui"
    for i, kind in enumerate(["good", "blank", "missing", "dup", "dup"]):
        d = lib / f"UI-00{i}_x"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": f"UI-00{i}", "comp": f"LIB_UI-00{i}", "duration": 3}), encoding="utf-8")
        if kind == "good":
            ff("-f", "lavfi", "-i", "testsrc=s=1280x720", "-frames:v", 1, d / "preview.png")
        elif kind == "blank":
            transparent(d / "preview.png", "1080x1920")
        elif kind == "dup":
            box(d / "preview.png", 100)
    rep = tmp_path / "repair.json"
    out = run("previews.py", "scan", "--home", tmp_path / "KeremKit", "--json", rep).stdout
    assert "items=5 ok=1 blank=1 missing=1 suspect=2" in out
    ids = {r["id"]: r["status"] for r in json.loads(rep.read_text(encoding="utf-8"))}
    assert ids == {"UI-001": "blank", "UI-002": "missing", "UI-003": "suspect", "UI-004": "suspect"}
    brief = run("previews.py", "scan", "--home", tmp_path / "KeremKit", "--brief").stdout
    assert brief.count("\n") == 1 and brief.startswith("SUMMARY")


def test_safe_copy_and_stat(tmp_path):
    src = tmp_path / "Apple Design.aep"
    src.write_bytes(b"x" * 1000)
    dst = tmp_path / "_work" / "Apple Design_work.aep"
    assert "source untouched" in run("keremkit.py", "safe-copy", src, dst).stdout
    assert dst.read_bytes() == src.read_bytes()
    again = run("keremkit.py", "safe-copy", src, dst, check=False)
    assert again.returncode != 0 and "exists" in again.stderr
    same = run("keremkit.py", "safe-copy", src, src, "--overwrite", check=False)
    assert same.returncode != 0 and "same file" in same.stderr
    st = run("keremkit.py", "stat", dst, tmp_path / "nope.aep", check=False)
    assert st.returncode == 1 and "1000 B" in st.stdout and "MISSING" in st.stdout


def test_version_matches_plugin():
    v = json.loads((ROOT / "plugins" / "ae-keremkit" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert run("keremkit.py", "version").stdout.strip() == f"KeremKit {v}"
    skill = (ROOT / "plugins" / "ae-keremkit" / "skills" / "ae-keremkit" / "SKILL.md").read_text(encoding="utf-8")
    assert f"KeremKit {v}" in skill


def test_new_prefs_and_known_issue(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    run("keremkit.py", "init", tmp_path / "KK", env=env)
    assert run("keremkit.py", "--home", tmp_path / "KK", "pref", "get", "library.preview_repair").stdout.strip() == "null"
    ki = (tmp_path / "KK" / "learning" / "known-issues.md").read_text(encoding="utf-8")
    assert "Never reduce the user's project" in ki
    assert (tmp_path / "KK" / "tools" / "previews.py").exists()
