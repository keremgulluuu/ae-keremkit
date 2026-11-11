"""2.0.0: new free sources, the assets folder and index, prbatch.py, the transcript index guard."""
import json
import os
import sys
import textwrap

import pytest

from conftest import SCRIPTS, run

sys.path.insert(0, SCRIPTS)
import assets  # noqa: E402

SHAPES = {
    "undraw.co/api/search": {"results": [{"_id": "1", "title": "Maker launch", "newSlug": "maker-launch_x",
                                          "media": "https://cdn.undraw.co/illustration/maker-launch_x.svg"}]},
    "api.unsplash.com/search": {"results": [{"id": "u1", "width": 6000, "height": 4000, "alt_description": "marble texture",
                                             "urls": {"full": "https://images.unsplash.com/u1?full", "small": "https://s/u1"},
                                             "links": {"html": "https://unsplash.com/photos/u1",
                                                       "download_location": "https://api.unsplash.com/photos/u1/download"},
                                             "user": {"name": "Ann Lee"}}]},
    "stocksnap.io/api": {"results": [{"img_id": "ABC123", "img_width": 3000, "img_height": 2000,
                                      "keywords": ["white", "marble", "texture"]}]},
    "graphql.lottiefiles.com": {"data": {"searchPublicAnimations": {"edges": [{"node": {
        "id": 5, "name": "confetti", "jsonUrl": "https://lf/c.json", "imageUrl": "https://lf/c.png",
        "url": "https://lottiefiles.com/animations/c", "createdBy": {"username": "/bob"}}}]}}},
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    calls = []

    def fake(url, headers=None, timeout=20, raw=False, body=None):
        calls.append((url, headers, body))
        if raw:
            return b"<svg/>"
        for k, v in SHAPES.items():
            if k in url:
                return v
        raise assets.Skip("no connection (test)")
    monkeypatch.setattr(assets, "fetch", fake)
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "keys.json").write_text(json.dumps({"unsplash": "k"}))
    return str(tmp_path), calls


def test_new_providers_parse_recorded_shapes(home):
    h, calls = home
    u = assets.p_undraw(h, "launch", 3, "vector", False)[0]
    assert u["url"].endswith(".svg") and u["kind"] == "vector" and "no credit" in u["license"]
    sp = assets.p_unsplash(h, "marble", 3, "photo", False)[0]
    assert sp["w"] == 6000 and sp["extra"]["ping"].endswith("/download") and "Ann Lee" in sp["extra"]["credit_line"]
    assert any(c[1] and c[1].get("Authorization") == "Client-ID k" for c in calls)
    ss = assets.p_stocksnap(h, "marble", 3, "photo", False)[0]
    assert ss["license"] == "CC0" and ss["extra"]["preview_only"] and ss["page"].endswith("ABC123")
    lf = assets.p_lottiefiles(h, "confetti", 3, "lottie", False)[0]
    assert lf["url"] == "https://lf/c.json" and lf["author"] == "bob"
    assert any(c[2] and b"searchPublicAnimations" in c[2] for c in calls)
    assert set(assets.TYPES["vector"]) == {"undraw", "wikimedia", "openverse"} and "unsplash" in assets.TYPES["photo"]


def test_unsplash_without_key_is_skipped(tmp_path, monkeypatch):
    (tmp_path / "settings").mkdir()
    with pytest.raises(assets.Skip, match="Access Key"):
        assets.p_unsplash(str(tmp_path), "x", 1, "photo", False)


def test_download_goes_to_assets_folder_and_index(home):
    h, calls = home
    r = assets.p_undraw(h, "launch", 1, "vector", False)[0]
    dest = assets.default_dest(h, "vector", r["src"])
    saved = assets.download(h, r, dest)
    assets.index_add(h, saved, r, "vector", "launch")
    assert os.path.normpath(saved[0]).startswith(os.path.normpath(os.path.join(h, "assets", "vector", "undraw")))
    rows = assets.index_find(h, "launch", "vector")
    assert rows and rows[0][2] == "undraw" and rows[0][4].startswith("assets/vector/undraw/")
    sp = assets.p_unsplash(h, "marble", 1, "photo", False)[0]
    assets.download(h, sp, assets.default_dest(h, "photo", "unsplash"))
    assert any("photos/u1/download" in c[0] for c in calls)              # Unsplash download ping
    with pytest.raises(assets.Skip, match="960 px"):
        assets.download(h, assets.p_stocksnap(h, "m", 1, "photo", False)[0], dest)


def test_sources_table_and_have_command(tmp_path):
    out = run("assets.py", "--home", tmp_path, "sources", "ai").stdout
    assert "Public Domain Vectors" in out and "token cost" in out and "orta" in out
    full = run("assets.py", "--home", tmp_path, "sources", "--full").stdout
    assert "everything each site offers" in full and "Unsplash" in full and "LottieFiles" in full
    f = tmp_path / "x.ai"
    f.write_text("%!PS-Adobe")
    run("assets.py", "--home", tmp_path, "import", f, "--type", "ai", "--source", "publicdomainvectors",
        "--license", "Public domain")
    assert (tmp_path / "assets" / "ai" / "publicdomainvectors" / "x.ai").exists()
    have = run("assets.py", "--home", tmp_path, "have", "x").stdout
    assert "HAVE\tai\tpublicdomainvectors" in have
    for site in assets.SITES:
        assert len(site) == 8 and site[7] in ("az", "orta", "cok")


FAKE_SERVER = textwrap.dedent('''
    import json, sys
    for line in sys.stdin:
        m = json.loads(line)
        if "id" not in m:
            continue
        if m["method"] == "initialize":
            res = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake", "version": "1"}}
        elif m["method"] == "tools/list":
            res = {"tools": [{"name": "import_mogrt", "description": "Import a MOGRT", "inputSchema": {}}]}
        else:
            a = m["params"]["arguments"]
            name = m["params"]["name"]
            if name == "boom":
                res = {"isError": True, "content": [{"type": "text", "text": "{\\"ok\\": false, \\"error\\": {\\"code\\": \\"HOST_RECOVERY_REQUIRED\\"}}"}]}
            elif a.get("dry_run"):
                res = {"structuredContent": {"ok": True, "data": {"confirmationToken": "tok-1"}}}
            else:
                res = {"structuredContent": {"ok": True, "data": {"verified": True, "got": a}}}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": res}) + "\\n")
        sys.stdout.flush()
''')


def test_prbatch_runs_a_plan_in_one_process(tmp_path):
    server = tmp_path / "fake_server.py"
    server.write_text(FAKE_SERVER, encoding="utf-8")
    kk = tmp_path / "KeremKit"
    (kk / "settings").mkdir(parents=True)
    (kk / "settings" / "preferences.json").write_text(json.dumps(
        {"tools": {"premiere_mcp": {"command": [sys.executable, str(server)]}}}))
    (tmp_path / ".keremkit.json").write_text(json.dumps({"home": str(kk)}))
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"expected_project_path": "C:/work.prproj", "steps": [
        {"tool": "ripple_remove_timeline_ranges", "args": {"dry_run": True}, "save_as": "cut"},
        {"tool": "ripple_remove_timeline_ranges", "args": {}, "token_from": "cut", "pick": ["data.verified", "data.got.confirmation_token"]},
        {"tool": "boom", "args": {}},
        {"tool": "never_reached", "args": {}}]}), encoding="utf-8")
    res = run("prbatch.py", "run", plan, env=env, check=False)
    out = res.stdout
    assert "#2 ripple_remove_timeline_ranges OK verified=true confirmation_token=tok-1" in out
    assert "#3 boom ERR" in out and "STOP recovery lock" in out and "never_reached" not in out
    assert "DONE steps=3/4 errors=1" in out and res.returncode == 1
    results = json.loads((tmp_path / "plan.results.json").read_text(encoding="utf-8"))
    assert results[1]["result"]["data"]["got"]["expected_project_path"] == "C:/work.prproj"
    listed = run("prbatch.py", "list", "mogrt", env=env).stdout
    assert listed.startswith("import_mogrt")


def test_fix_refuses_stale_indices(tmp_path):
    words = {"segments": [{"words": [{"word": " a", "start": 0, "end": 0.2}, {"word": " b", "start": 0.2, "end": 0.4},
                                     {"word": " c", "start": 0.4, "end": 0.6}]}]}
    wp = tmp_path / "w.json"
    wp.write_text(json.dumps(words), encoding="utf-8")
    c1 = tmp_path / "c1.json"
    c1.write_text(json.dumps([{"index": 0, "new": ""}]), encoding="utf-8")
    run("transcript.py", "fix", wp, "--corrections", c1, "-o", tmp_path / "w2.json")
    c2 = tmp_path / "c2.json"
    c2.write_text(json.dumps([{"index": 1, "new": "B"}]), encoding="utf-8")
    bad = run("transcript.py", "fix", tmp_path / "w2.json", "--corrections", c2, "-o", tmp_path / "w3.json", check=False)
    assert bad.returncode != 0 and "indices no longer match" in bad.stderr
    ok = run("transcript.py", "fix", tmp_path / "w2.json", "--corrections", c2, "-o", tmp_path / "w3.json", "--force-index")
    assert "applied=1" in ok.stdout


def test_init_creates_new_folders(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    kk = tmp_path / "KeremKit"
    run("keremkit.py", "init", kk, env=env)
    for d in ("assets", "library/mogrt", "learning/sessions"):
        assert (kk / d).is_dir()
    assert "Token notes" in (kk / "learning" / "token-notes.md").read_text(encoding="utf-8")
    prefs = json.loads((kk / "settings" / "preferences.json").read_text(encoding="utf-8"))
    assert prefs["premiere"] == {"project_folder": None, "project_naming": None, "sequence_naming": None}
