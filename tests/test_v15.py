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


def test_compare_builds_one_numbered_image(tmp_path):
    lib = tmp_path / "KK" / "library" / "items" / "text"
    for i, size in enumerate(["1920x1080", "1080x1920"]):
        d = lib / f"TXT-00{i + 1}_x"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": f"TXT-00{i + 1}", "name": "Rise Blur – Reveal"}), encoding="utf-8")
        ff("-f", "lavfi", "-i", f"testsrc=s={size}", "-frames:v", 1, d / "preview.png")
    out = run("previews.py", "compare", "TXT-001", "txt-002", "-o", tmp_path / "c.png", "--home", tmp_path / "KK").stdout
    assert out.startswith("OK") and "2 item(s)" in out
    w, h = map(int, re.search(r"(\d+)x(\d+)", out).groups())
    assert w == 1920 and h > 1080 + 3400
    missing = run("previews.py", "compare", "NOPE-001", "-o", tmp_path / "d.png", "--home", tmp_path / "KK", check=False)
    assert missing.returncode != 0 and "not found" in missing.stderr


def test_plan_searches_every_part(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "KK"
    run("keremkit.py", "init", kk, env=env)
    d = kk / "library" / "items" / "text" / "TXT-001_rise-reveal"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": "TXT-001", "name": "Rise Reveal", "category": "text",
                                             "tags": ["animated", "title", "reveal"], "summary": "Animated title"}), encoding="utf-8")
    run("keremkit.py", "--home", kk, "add", d / "meta.json")
    out = run("keremkit.py", "--home", kk, "plan", "intro: animated title", "outro: confetti explosion").stdout
    assert "PART 1\tintro\t1 hit(s)" in out and "good\t" in out and "TXT-001" in out and "preview: check" in out
    assert "PART 2\toutro\t0 hit(s)" in out
    assert run("keremkit.py", "--home", kk, "pref", "get", "design.plan").stdout.strip() in ('"big"', "big")


def test_queue_and_auto_two_passes(tmp_path):
    kk = tmp_path / "KK"
    for iid in ("UI-001", "UI-002"):
        d = kk / "library" / "items" / "ui" / f"{iid}_x"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"id": iid, "comp": f"LIB_{iid}", "fps": 10, "duration": 12}), encoding="utf-8")
    out = run("previews.py", "queue", "UI-001", "UI-002", "--home", kk, "--ae-home", "C:/Users/me/Documents/KeremKit").stdout
    root = re.search(r"RUN\t(.*)", out).group(1)
    ops = json.loads(out.split("\n")[2])
    assert ops[0]["operation"] == "render.clear_queue" and ops[-1]["operation"] == "render.start" and len(ops) == 8
    assert ops[3]["args"]["outputPath"].startswith("C:/Users/me/Documents/KeremKit/library/_work/previews/")
    assert ops[2]["args"]["skipFrames"] == 9
    for k in range(12):                                   # UI-001 black icon (static), UI-002 moves at probes 4-6
        p1 = os.path.join(root, "UI-001", "p")
        p2 = os.path.join(root, "UI-002", "p")
        os.makedirs(p1, exist_ok=True)
        os.makedirs(p2, exist_ok=True)
        ff("-f", "lavfi", "-i", "color=c=black@0.0:s=320x180,format=rgba", "-f", "lavfi", "-i", "color=c=black:s=60x60",
           "-filter_complex", "[0][1]overlay=x=100:y=50,format=rgba", "-frames:v", 1, os.path.join(p1, f"p_{k * 10:05d}.tif"))
        x = -200 if k < 4 else (180 if k > 6 else k * 30)
        ff("-f", "lavfi", "-i", "color=c=black@0.0:s=320x180,format=rgba", "-f", "lavfi", "-i", "color=c=white:s=80x80",
           "-filter_complex", f"[0][1]overlay=x={x}:y=40,format=rgba", "-frames:v", 1, os.path.join(p2, f"p_{k * 10:05d}.tif"))
    out = run("previews.py", "auto", root).stdout
    assert "OK\tUI-001\tstatic" in out and "animated_pending=1" in out
    ops2 = json.loads(out.strip().split("\n")[-2])
    span = ops2[2]["args"]
    assert 3.0 <= span["timeSpanStart"] and span["timeSpanStart"] + span["timeSpanDuration"] <= 6.2
    a = os.path.join(root, "UI-002", "a")
    os.makedirs(a)
    for k in range(6):
        box(os.path.join(a, f"a_{k:05d}.png"), 100 + 16 * k)
    out = run("previews.py", "auto", root).stdout
    assert "OK\tUI-002\tanimated\t6 frame(s)" in out
    m = json.loads((kk / "library" / "items" / "ui" / "UI-002_x" / "meta.json").read_text(encoding="utf-8"))
    assert m["preview_kind"] == "animated" and len(m["preview_times"]) == 6
    # dark content got the light backdrop
    px = subprocess.run(["ffmpeg", "-v", "error", "-i", kk / "library" / "items" / "ui" / "UI-001_x" / "preview.png",
                         "-vf", "crop=1:1:0:0", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    assert px[0] > 150


def test_save_prep_and_check(tmp_path):
    proj = tmp_path / "Apple Design.aep"
    proj.write_bytes(b"A" * 500)
    work = tmp_path / "KK" / "library" / "_work" / "Apple_work.aep"
    item = tmp_path / "KK" / "library" / "items" / "ui" / "UI-009_x"
    out = run("keremkit.py", "save-prep", proj, work, "--items", item).stdout
    assert out.startswith("OK") and work.read_bytes() == proj.read_bytes() and item.is_dir()
    bad = run("keremkit.py", "save-check", work, "--items", item / "item.aep", check=False)
    assert bad.returncode == 1 and "NOT WRITTEN" in bad.stdout
    (item / "item.aep").write_bytes(b"x")
    assert run("keremkit.py", "save-check", work, "--items", item / "item.aep").stdout.startswith("OK")
    proj.write_bytes(b"reduced")
    changed = run("keremkit.py", "save-check", work, check=False)
    assert changed.returncode == 1 and "PROJECT CHANGED" in changed.stdout


def test_add_many(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "KK"
    run("keremkit.py", "init", kk, env=env)
    tsv = tmp_path / "items.tsv"
    tsv.write_text("id\tcategory\tname\tlocal\ttags\tsummary\tcomp\tsize\tfps\tduration\tpack\toriginal_comp\tfonts\n"
                   "UI-050\tui\tRed Lock\tKırmızı Kilit\tlock, red, kilit\tA red padlock pops in.\tLIB_UI-050_RedLock\t1080x1920\t29.97\t10\tME v2\tRed Lock\tMontserrat\n"
                   "UI-051\tui\tSwitch\t\ttoggle\t\tLIB_UI-051\t1080x1920\t30\t5\n", encoding="utf-8")
    out = run("keremkit.py", "--home", kk, "add-many", tsv).stdout
    assert "SKIP\tline 3\tmissing summary" in out and "OK\t1 item(s)" in out
    m = json.loads((kk / "library" / "items" / "ui" / "UI-050_red-lock" / "meta.json").read_text(encoding="utf-8"))
    assert m["size"] == [1080, 1920] and m["names"]["tr"] == "Kırmızı Kilit" and m["deps"]["fonts"] == ["Montserrat"]
    assert m["source"]["pack"] == "ME v2"
    assert "UI-050" in run("keremkit.py", "--home", kk, "search", "kirmizi", "kilit").stdout


def test_skill_forbids_self_update_and_doctor_flags_user_tools(tmp_path):
    skill = (ROOT / "plugins" / "ae-keremkit" / "skills" / "ae-keremkit" / "SKILL.md").read_text(encoding="utf-8")
    assert "The skill is read-only" in skill and "only when the user asks" in skill
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "KK"
    run("keremkit.py", "init", kk, env=env)
    assert (kk / "extensions").is_dir()
    (kk / "tools" / "texturelock.py").write_text("print(1)\n")
    (kk / "extensions" / "texture-lock").mkdir()
    out = run("keremkit.py", "--home", kk, "doctor", env=env).stdout
    assert "not kit files: texturelock.py" in out and "texture-lock" in out
