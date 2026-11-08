import json

from conftest import run


def test_digest_summarises_unknown_schema(tmp_path):
    project = {"items": [{"type": "comp", "name": "SCN_01_Intro", "width": 1080, "height": 1920,
                          "frameRate": 30, "duration": 42.5, "layers": [
                              {"name": "SUB_Captions", "text": {"sourceText": "Hello there", "font": "Inter-Black",
                                                                "fontSize": 72, "fillColor": [1, 0.8, 0]}},
                              {"name": "UI_Counter", "effects": [{"matchName": "ADBE Glo2"}]},
                              {"name": "Shape Layer 1", "fillColor": [0.1, 0.1, 0.1]}]}]}
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project), encoding="utf-8")
    out = run("digest.py", path).stdout
    assert "SCN_01_Intro\t1080x1920" in out
    assert "Inter-Black" in out
    assert "#FFCC00" in out
    assert "ADBE Glo2" in out
    assert "SUB(1)" in out and "(none)(1)" in out
