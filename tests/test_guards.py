"""Guards: clean errors for bad input, map kind/header checks, removals and subtitle output guards."""
import json
import os
import pathlib

import pytest

from conftest import SCRIPTS, run


@pytest.fixture
def kk(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    home = tmp_path / "KK"
    run("keremkit.py", "init", home, env=env)
    return home


def k(home, *args, check=True):
    return run("keremkit.py", "--home", home, *args, check=check)


def test_add_many_missing_file(kk, tmp_path):
    before = (kk / "library" / "CATALOG.tsv").read_bytes()
    r = k(kk, "add-many", tmp_path / "nope.tsv", check=False)
    assert r.returncode != 0 and "ERROR: file not found:" in r.stderr
    assert (kk / "library" / "CATALOG.tsv").read_bytes() == before


def test_add_many_empty_file(kk, tmp_path):
    f = tmp_path / "items.tsv"
    f.write_text("# only a comment\n\n", encoding="utf-8")
    before = (kk / "library" / "CATALOG.tsv").read_bytes()
    r = k(kk, "add-many", f, check=False)
    assert r.returncode != 0
    assert "has no rows - first line must be a header with: id category name" in r.stderr
    assert (kk / "library" / "CATALOG.tsv").read_bytes() == before


def test_digest_missing_file(tmp_path):
    r = run("digest.py", tmp_path / "nope.json", check=False)
    assert r.returncode != 0 and "ERROR: file not found:" in r.stderr


def test_digest_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    r = run("digest.py", p, check=False)
    assert r.returncode != 0 and "is not valid JSON:" in r.stderr


def test_map_add_rejects_unknown_kind(kk, tmp_path):
    proj = tmp_path / "Proj" / "Eco.aep"
    proj.parent.mkdir()
    proj.write_bytes(b"x")
    k(kk, "map", "init", proj)
    mp = tmp_path / "Proj" / "_keremkit" / "map.tsv"
    before = mp.read_bytes()
    r = k(kk, "map", "add", proj, "--kind", "bogus", "--name", "X", check=False)
    assert r.returncode != 0
    assert "ERROR: --kind must be one of comp, layer, element, asset, open, decision (got 'bogus')" in r.stderr
    assert mp.read_bytes() == before


def test_map_bad_header_is_refused(kk, tmp_path):
    proj = tmp_path / "Proj" / "Eco.aep"
    proj.parent.mkdir()
    proj.write_bytes(b"x")
    k(kk, "map", "init", proj)
    mp = tmp_path / "Proj" / "_keremkit" / "map.tsv"
    mp.write_text("kind\tname\tcomp\n", encoding="utf-8")
    before = mp.read_bytes()
    bad = "header must contain kind name comp time purpose status updated - found: kind name comp"
    show = k(kk, "map", "show", proj, check=False)
    add = k(kk, "map", "add", proj, "--kind", "comp", "--name", "SCN_Main", check=False)
    assert show.returncode != 0 and bad in show.stderr
    assert add.returncode != 0 and bad in add.stderr
    assert mp.read_bytes() == before


def test_transcript_remove_refuses_foreign_into(tmp_path, words_file):
    path, _ = words_file
    into = tmp_path / "rem.json"
    into.write_text(json.dumps({"words_file": str(path), "removals": [{"id": 1, "start": 1.0}]}), encoding="utf-8")
    before = into.read_bytes()
    r = run("transcript.py", "remove", path, "--index", "2-4", "--into", into, check=False)
    assert r.returncode != 0
    assert "is not a removals file this tool wrote - fix or remove it, nothing was changed" in r.stderr
    assert into.read_bytes() == before


def test_transcript_remove_refuses_a_words_file_as_into(tmp_path, words_file):
    path, _ = words_file
    before = path.read_bytes()
    r = run("transcript.py", "remove", path, "--index", "2-4", "--into", path, check=False)
    assert r.returncode != 0 and "is not a removals file this tool wrote" in r.stderr
    assert path.read_bytes() == before


def test_transcript_remove_refuses_non_json_into(tmp_path, words_file):
    path, _ = words_file
    into = tmp_path / "rem.txt"
    into.write_text("my own notes, not JSON\n", encoding="utf-8")
    before = into.read_bytes()
    r = run("transcript.py", "remove", path, "--index", "2-4", "--into", into, check=False)
    assert r.returncode != 0 and "is not a removals file this tool wrote" in r.stderr
    assert into.read_bytes() == before


def test_subtitles_build_refuses_output_over_input(tmp_path):
    p = tmp_path / "cam.json"
    p.write_text(json.dumps({"language": "en", "segments": [{"words": [{"word": " hi", "start": 0.0, "end": 0.5}]}]}),
                 encoding="utf-8")
    before = p.read_bytes()
    r = run("subtitles.py", "build", "--words", p, "-o", tmp_path / "cam", check=False)
    assert r.returncode != 0 and f"would overwrite the input file {p}" in r.stderr
    assert p.read_bytes() == before


def test_design_plan_uses_techniques_list():
    text = (pathlib.Path(SCRIPTS).parent / "references" / "design-plan.md").read_text(encoding="utf-8")
    assert "techniques.py search" not in text
    assert "`techniques.py list`" in text
