import json
import os

import pytest

from conftest import run


@pytest.fixture
def home(tmp_path):
    """A fake user home so the pointer file never touches the real one."""
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "My Edits" / "KeremKit"
    run("keremkit.py", "init", kk, env=env)
    return kk, env


def kk(env, *args, check=True):
    return run("keremkit.py", *args, env=env, check=check)


def test_init_creates_layout_and_pointer(home, tmp_path):
    path, env = home
    for d in ("settings", "library/items/ui", "styles/_archive", "learning", "tools"):
        assert (path / d).is_dir()
    assert json.loads((tmp_path / ".keremkit.json").read_text(encoding="utf-8"))["home"] == str(path)
    assert kk(env, "where").stdout.startswith("READY")
    assert (path / "tools" / "cutlist.py").exists()


def test_init_never_overwrites_preferences(home):
    path, env = home
    kk(env, "pref", "set", 'cutting.preset="tight"')
    run("keremkit.py", "init", path, env=env)
    assert kk(env, "pref", "get", "cutting.preset").stdout.strip() == '"tight"'


def test_pref_missing_lists_unanswered(home):
    _, env = home
    out = kk(env, "pref", "missing", "render").stdout.split()
    assert "render.mode" in out
    kk(env, "pref", "set", 'render.mode="ask"')
    assert "render.mode" not in kk(env, "pref", "missing", "render").stdout.split()


def test_categories_can_grow(home):
    _, env = home
    kk(env, "cat", "add", "--key", "3d objects", "--prefix", "3DO", "--name", "3D Objects", "--local", "tr=3D Objeler")
    assert "3DO" in kk(env, "cat", "list").stdout
    dup = kk(env, "cat", "add", "--key", "x", "--prefix", "UI", "--name", "X", check=False)
    assert dup.returncode != 0
    assert kk(env, "new-id", "3DO").stdout.strip() == "3DO-001"


def test_items_and_styles_found_in_any_language(home):
    path, env = home
    item = path / "library" / "items" / "ui" / "UI-001_gold-counter"
    item.mkdir(parents=True)
    (item / "item.aep").write_bytes(b"")
    (item / "meta.json").write_text(json.dumps({
        "id": "UI-001", "name": "Gold Counter", "names": {"tr": "Altın Sayaç"}, "category": "ui",
        "tags": ["counter", "sayaç"], "summary": "Gold count-up", "file": "item.aep"}), encoding="utf-8")
    kk(env, "add", item / "meta.json")
    style = path / "styles" / "talk"
    style.mkdir()
    (style / "style.json").write_text(json.dumps({
        "id": "STY-001", "kind": "edit-style", "name": "Talk Style", "names": {"tr": "Konuşma Stili"},
        "version": 1}), encoding="utf-8")
    kk(env, "add", style / "style.json")

    assert "UI-001" in kk(env, "search", "ALTIN", "sayac").stdout.splitlines()[0]
    assert "UI-001" in kk(env, "search", "gold", "counter").stdout.splitlines()[0]
    assert "STY-001" in kk(env, "search", "konusma", "--type", "style").stdout
    assert kk(env, "search", "gold", "--type", "style").stdout.strip() == "NO_MATCH"
    assert kk(env, "new-id", "UI").stdout.strip() == "UI-002"
    assert kk(env, "validate").stdout.strip() == "OK"


def test_old_field_names_still_accepted(home):
    path, env = home
    item = path / "library" / "items" / "ui" / "UI-005_old"
    item.mkdir(parents=True)
    (item / "meta.json").write_text(json.dumps({
        "id": "UI-005", "name_en": "Old Card", "name_tr": "Eski Kart", "category": "ui",
        "tags": ["card"], "summary": "legacy fields"}), encoding="utf-8")
    assert "Old Card / Eski Kart" in kk(env, "add", item / "meta.json").stdout


def test_style_archive_keeps_reason(home):
    path, env = home
    style = path / "styles" / "talk"
    style.mkdir()
    (style / "style.json").write_text(json.dumps({"id": "STY-001", "name": "Talk", "version": 1}), encoding="utf-8")
    kk(env, "style-archive", "talk", "--reason", "captions turned yellow")
    archived = path / "styles" / "_archive" / "talk" / "v001"
    assert "captions turned yellow" in (archived / "CHANGE.txt").read_text(encoding="utf-8")
    assert json.loads((style / "style.json").read_text(encoding="utf-8"))["version"] == 2
