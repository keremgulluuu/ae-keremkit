"""2.1.0: project map, find, style-get, learning-archive, LOGIC.md check, pref set guard, prbatch re-run guard,
digest --deep, transcript remove."""
import json
import os
import sys

import pytest

from conftest import SCRIPTS, run

sys.path.insert(0, SCRIPTS)
import prbatch  # noqa: E402


@pytest.fixture
def kk(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    home = tmp_path / "KK"
    run("keremkit.py", "init", home, env=env)
    return home


def k(home, *args, check=True):
    return run("keremkit.py", "--home", home, *args, check=check)


def test_pref_set_needs_key_value_in_one_argument(kk):
    k(kk, "pref", "set", 'custom_rules=[{"rule": "a"}]')
    bad = k(kk, "pref", "set", "custom_rules", '[{"rule": "b"}]', check=False)
    assert bad.returncode != 0 and "KEY=VALUE" in bad.stderr
    assert json.loads(k(kk, "pref", "get", "custom_rules").stdout) == [{"rule": "a"}]   # unchanged


def test_new_preferences_start_unanswered(kk):
    missing = k(kk, "pref", "missing").stdout
    for key in ("motion.transform_rig", "motion.blur", "organize.precomp_elements"):
        assert key in missing


def test_init_writes_change_request_template(kk):
    text = (kk / "learning" / "skill-change-requests.md").read_text(encoding="utf-8")
    assert "Status: open" in text


def test_map_flow(tmp_path, kk):
    proj = tmp_path / "Proj" / "Eco.aep"
    proj.parent.mkdir()
    proj.write_bytes(b"x")
    out = k(kk, "map", "init", proj).stdout
    assert "map.tsv" in out and (tmp_path / "Proj" / "_keremkit" / "brandkit.md").exists()
    (tmp_path / "Proj" / "_keremkit" / "log.md").write_text("mine\n", encoding="utf-8")
    k(kk, "map", "init", proj)                                   # never overwrites
    assert (tmp_path / "Proj" / "_keremkit" / "log.md").read_text(encoding="utf-8") == "mine\n"
    k(kk, "map", "add", proj, "--kind", "element", "--name", "PRE_Supply", "--comp", "SCN_Main",
      "--time", "52:00-54:15", "--purpose", "tedarik çizgileri", "--status", "open")
    k(kk, "map", "add", proj, "--kind", "element", "--name", "PRE_Supply", "--comp", "SCN_Main", "--status", "done")
    rows = (tmp_path / "Proj" / "_keremkit" / "map.tsv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2 and "\tdone\t" in rows[1] and "52:00-54:15" in rows[1]   # updated, not duplicated
    assert "PRE_Supply" in k(kk, "map", "find", proj, "tedarik").stdout
    assert "ROWS 0" in k(kk, "map", "show", proj, "--open").stdout
    assert "NONE" in k(kk, "map", "name", proj, "iphone", "mockup").stdout
    k(kk, "map", "name", proj, "iphone", "mockup", "--canon", "UI_IPhone17ProMax")
    assert "UI_IPhone17ProMax" in k(kk, "map", "name", proj, "iphone", "mockup").stdout
    clash = k(kk, "map", "name", proj, "iphone", "mockup", "--canon", "UIApple", check=False)
    assert clash.returncode != 0


def test_map_without_init_is_refused(tmp_path, kk):
    r = k(kk, "map", "show", tmp_path / "Nope", check=False)
    assert r.returncode != 0 and "map init" in r.stderr


def test_find_searches_everything(kk):
    (kk / "learning" / "sessions" / "2026-11-12-liquid-glass-card.md").write_text("glass card build", encoding="utf-8")
    ext = kk / "extensions" / "liquid-glass-2d"
    ext.mkdir(parents=True)
    (ext / "README.md").write_text("Liquid glass recipe", encoding="utf-8")
    (kk / "assets" / "INDEX.tsv").write_text("date\ttype\tsource\ttitle\n2026\ttexture\tambientCG\tGlass frosted\n",
                                             encoding="utf-8")
    out = k(kk, "find", "glass").stdout
    assert "EXTENSION\tliquid-glass-2d" in out and "SESSION" in out and "ASSET" in out
    assert "NO_MATCH" in k(kk, "find", "zzzqqq").stdout


def test_style_get(kk):
    d = kk / "styles" / "eco"
    d.mkdir(parents=True)
    (d / "style.json").write_text(json.dumps({"id": "STY-001", "cutting": {"pad": 0.05}}), encoding="utf-8")
    out = k(kk, "style-get", "eco", "cutting.pad", "nope").stdout
    assert "cutting.pad\t0.05" in out and "nope\tMISSING" in out


def test_learning_archive(kk):
    p = kk / "learning" / "skill-change-requests.md"
    p.write_text("# Requests\n\nintro\n\n## A (2026-11-12)\nStatus: done 2.1.0\n- x\n\n## B\nStatus: open\n- y\n",
                 encoding="utf-8")
    assert "WOULD MOVE\tA" in k(kk, "learning-archive", "--dry-run").stdout
    assert "Status: done" in p.read_text(encoding="utf-8")       # dry run changed nothing
    k(kk, "learning-archive")
    left = p.read_text(encoding="utf-8")
    assert "## B" in left and "## A" not in left and left.startswith("# Requests")
    arch = (kk / "learning" / "skill-change-requests.archive.md").read_text(encoding="utf-8")
    assert "## A (2026-11-12)" in arch
    assert (kk / "learning" / "skill-change-requests.md.bak").exists()


def test_save_check_reminds_logic(tmp_path, kk):
    proj = tmp_path / "P.aep"
    proj.write_bytes(b"aep")
    item = tmp_path / "item" / "item.aep"
    k(kk, "save-prep", proj, tmp_path / "work.aep", "--items", item.parent)
    item.write_bytes(b"saved")
    out = k(kk, "save-check", tmp_path / "work.aep", "--items", item).stdout
    assert "TODO\tLOGIC.md missing" in out
    (item.parent / "LOGIC.md").write_text("# logic", encoding="utf-8")
    assert "TODO" not in k(kk, "save-check", tmp_path / "work.aep", "--items", item).stdout


def test_prbatch_refuses_rerun_and_cleans_keys(tmp_path):
    plan = tmp_path / "p.json"
    plan.write_text(json.dumps({"steps": [{"tool": "x"}]}), encoding="utf-8")
    (tmp_path / "p.results.json").write_text(json.dumps([{"step": 1, "tool": "x", "ok": True}]), encoding="utf-8")
    r = run("prbatch.py", "run", plan, check=False)
    assert r.returncode != 0 and "ALREADY_RUN" in (r.stdout + r.stderr) and "--from 2" in (r.stdout + r.stderr)
    assert prbatch.clean_keys({"idempotency_key": "tint (Film Burn) 07"})["idempotency_key"] == "tint_Film_Burn_07"


def test_digest_deep(tmp_path):
    export = {"items": [{"id": 1, "name": "SCN_Main", "width": 1080, "height": 1920, "frameRate": 30, "duration": 5,
                         "motionBlur": True, "shutterAngle": 180, "layers": [
        {"index": 1, "name": "TXT_Title", "type": "TextLayer", "inPoint": 1.0, "outPoint": 4.0, "startTime": 0,
         "text": "Hello", "font": "Inter-Bold", "fontSize": 90,
         "transformGroup": {"properties": [
             {"name": "Opacity", "value": 100, "keyframes": [
                 {"time": 1.0, "value": 0, "inEase": [{"speed": 0, "influence": 33}], "outEase": [{"speed": 0, "influence": 10}],
                  "inInterpName": "bezier", "outInterpName": "bezier"},
                 {"time": 1.5, "value": 100, "inEase": [{"speed": 0, "influence": 90}], "outEase": [{"speed": 0, "influence": 33}],
                  "inInterpName": "bezier", "outInterpName": "bezier"}]},
             {"name": "Position", "value": [540, 960], "expression": "wiggle(2,5)"}]},
         "effectsGroup": {"groups": [{"name": "Glow", "matchName": "ADBE Glo2",
                                      "properties": [{"name": "Glow Radius", "value": 25}]}]}},
        {"index": 2, "name": "SFX_Pop", "type": "AVLayer", "inPoint": 2.0, "outPoint": 2.5, "hasAudio": True,
         "hasVideo": False, "sourceName": "pop.wav"}]}]}
    f = tmp_path / "e.json"
    f.write_text(json.dumps(export), encoding="utf-8")
    out = run("digest.py", f, "--comp", "SCN_Main", "--deep", "--noaudio").stdout
    assert "K T/Opacity: +0.000=0[i0/33 o0/10] +0.500=100[i0/90 o0/33]" in out
    assert "E T/Position: wiggle(2,5)" in out and "FX Glow (ADBE Glo2)" in out
    assert "Glow Radius" not in out and "AUDIO LAYERS 1" in out and out.rstrip().splitlines()[-1].startswith("GAPS")
    assert "Glow Radius=25" in run("digest.py", f, "--comp", "SCN_Main", "--deep", "--params", "TXT_").stdout
    assert run("digest.py", f, "--deep", check=False).returncode != 0


def test_transcript_remove(tmp_path, words_file):
    path, _ = words_file
    into = tmp_path / "rem.json"
    out = run("transcript.py", "remove", path, "--index", "2-4", "--reason", "chatter", "--into", into).stdout
    data = json.loads(into.read_text(encoding="utf-8"))
    r = data["removals"][0]
    assert r["kind"] == "manual" and r["apply"] is True and r["removed"] == "today I want" and "OK manual=1" in out
    assert run("transcript.py", "remove", path, "--index", "9999-10000", "--into", into, check=False).returncode != 0
