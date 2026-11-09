import json
import os

import pytest

from conftest import run


@pytest.fixture
def home(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "KeremKit"
    run("keremkit.py", "init", kk, env=env)
    return kk, env


def make_presets(tmp_path):
    root = tmp_path / "User Presets"
    (root / "Text" / "Animate In").mkdir(parents=True)
    (root / "Glows").mkdir()
    for p in (root / "Glows" / "Soft Glow Pop.ffx", root / "Glows" / "Neon Deep Glow.ffx",
              root / "Text" / "Animate In" / "Typewriter Fast.ffx", root / "Broken Plugin.ffx"):
        p.write_bytes(b"RIFX fake preset")
    return root


def lab_export(scan):
    by_name = {it["name"]: it["lab_layer"] for it in scan["items"]}
    layers = [
        # schema A: flat "effects" list, keyframes under properties
        {"name": by_name["Soft Glow Pop"], "effects": [
            {"name": "Glow", "matchName": "ADBE Glo2", "properties": [
                {"name": "Glow Intensity", "matchName": "ADBE Glo2-0004",
                 "keyframes": [{"time": 0, "value": 0, "inInterpolationType": "bezier"},
                               {"time": 0.4, "value": 2.5, "inInterpolationType": "bezier"}]}]}],
         "transform": {"Scale": {"name": "Scale", "keyframes": [{"time": 0, "value": [80, 80]}, {"time": 0.4, "value": [100, 100]}]}}},
        # schema B: AE-like property tree, third-party effect, expression
        {"name": by_name["Neon Deep Glow"], "properties": [
            {"matchName": "ADBE Effect Parade", "properties": [
                {"name": "Deep Glow", "matchName": "PEDG", "properties": [
                    {"name": "Radius", "expression": "wiggle(3, 20)", "expressionEnabled": True}]}]},
            {"matchName": "ADBE Transform Group", "properties": [
                {"name": "Opacity", "keys": [{"t": 0, "v": 0}, {"t": 0.5, "v": 100}]}]}]},
        {"name": by_name["Typewriter Fast"], "properties": [
            {"matchName": "ADBE Text Properties", "properties": [
                {"matchName": "ADBE Text Animators", "properties": [
                    {"name": "Typewriter", "matchName": "ADBE Text Animator"}]}]}]},
        {"name": by_name["Broken Plugin"]},
    ]
    return {"project": {"items": [{"name": "Other", "layers": []}, {"name": "KK_PRESET_LAB", "layers": layers}]}}


def test_scan_plan_learn_show(tmp_path, home):
    kk, env = home
    root = make_presets(tmp_path)
    scan_p = tmp_path / "scan.json"
    out = run("presets.py", "scan", root, "-o", scan_p, env=env).stdout
    assert "presets=4" in out and "text_presets=1" in out
    scan = json.loads(scan_p.read_text(encoding="utf-8"))
    assert next(i for i in scan["items"] if i["name"] == "Typewriter Fast")["kind"] == "text"

    batch_p = tmp_path / "batch.json"
    run("presets.py", "plan", scan_p, "--batch", 10, "-o", batch_p, env=env)
    ops = json.loads(batch_p.read_text(encoding="utf-8"))["ops"]
    assert ops[0]["operation"] == "comp.create"
    assert sum(o["operation"] == "layer.apply_preset" for o in ops) == 4
    assert any(o["operation"] == "layer.create_text" for o in ops)

    export_p = tmp_path / "export.json"
    export_p.write_text(json.dumps(lab_export(scan)), encoding="utf-8")
    broken = next(i["lab_layer"] for i in scan["items"] if i["name"] == "Broken Plugin")
    err_p = tmp_path / "errors.json"
    err_p.write_text(json.dumps({broken: "Effect 'Saber' is missing (plug-in not installed)"}), encoding="utf-8")
    out = run("presets.py", "learn", scan_p, "--export", export_p, "--errors", err_p, env=env).stdout
    assert "learned=4" in out and "failed=1" in out
    assert "Deep Glow (Plugin Everything)" in out

    glow = run("presets.py", "show", "soft glow pop", env=env).stdout
    assert "EFFECT\tGlow\tADBE Glo2" in glow and "REQUIRES" not in glow
    assert "Glow Intensity" in glow and "2 keys 0.0-0.4s" in glow
    assert "Scale" in glow

    neon = run("presets.py", "show", "Neon Deep Glow", env=env).stdout
    assert "REQUIRES\tDeep Glow (Plugin Everything)" in neon
    assert "EXPR\tRadius\twiggle(3, 20)" in neon
    assert "Opacity" in neon

    assert "TEXT_ANIMATORS\tTypewriter" in run("presets.py", "show", "typewriter", env=env).stdout

    # catalog: plugin presets are labelled and searchable by effect or vendor
    hits = run("keremkit.py", "search", "deep", "glow", env=env).stdout
    assert "[requires plugin]" in hits
    assert "FXP-" in run("keremkit.py", "search", "glow", "intensity", env=env).stdout

    # relearning updates instead of duplicating
    out = run("presets.py", "learn", scan_p, "--export", export_p, "--errors", err_p, env=env).stdout
    assert "learned=0" in out and "updated=4" in out

    ins = run("presets.py", "insights", env=env).stdout
    assert "Glow (1)" in ins
    assert (kk / "learning" / "presets-insights.md").exists()
