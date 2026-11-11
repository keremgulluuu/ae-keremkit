"""assets.py: providers parsed from recorded API shapes (no network), licence filter, last-search flow."""
import json
import os
import sys

import pytest

from conftest import SCRIPTS, run

sys.path.insert(0, SCRIPTS)
import assets  # noqa: E402

FIXTURES = {
    "api.pexels.com/videos": {"videos": [{"url": "https://www.pexels.com/video/green-screen-smoke-123/", "duration": 12,
                                          "image": "https://x/t.jpg", "user": {"name": "Ann"},
                                          "video_files": [{"link": "https://x/4k.mp4", "width": 3840, "height": 2160},
                                                          {"link": "https://x/hd.mp4", "width": 1920, "height": 1080}]}]},
    "pixabay.com/api/videos": {"hits": [{"tags": "light leak", "pageURL": "https://pixabay.com/v/1", "user": "bo", "duration": 8,
                                         "videos": {"large": {"url": "https://x/l.mp4", "width": 1920, "height": 1080},
                                                    "medium": {"url": "https://x/m.mp4", "thumbnail": "https://x/m.jpg"}}}]},
    "api.openverse.org/v1/audio": {"results": [
        {"title": "Whoosh", "url": "https://x/w.mp3", "license": "cc0", "duration": 1200, "creator": "c", "filetype": "mp3",
         "foreign_landing_url": "https://f/1"},
        {"title": "Swish", "url": "https://x/s.mp3", "license": "by", "license_version": "4.0", "duration": 900}]},
    "commons.wikimedia.org": {"query": {"pages": {
        "1": {"title": "File:Confetti.jpg", "imageinfo": [{"url": "https://x/c.jpg", "width": 800, "height": 600,
              "thumburl": "https://x/c_t.jpg", "descriptionurl": "https://c/1",
              "extmetadata": {"LicenseShortName": {"value": "Public domain"}, "License": {"value": "pd"}}}]},
        "2": {"title": "File:Other.jpg", "imageinfo": [{"url": "https://x/o.jpg",
              "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "License": {"value": "cc-by-sa-4.0"}}}]}}}},
    "freesound.org": {"results": [{"id": 1, "name": "boom", "duration": 2.5, "username": "u", "url": "https://fs/1",
                                   "license": "http://creativecommons.org/publicdomain/zero/1.0/",
                                   "previews": {"preview-hq-mp3": "https://fs/1.mp3"}}]},
    "api.iconify.design/search": {"icons": ["mdi:heart", "solar:heart-bold"],
                                  "collections": {"mdi": {"name": "Material Design Icons", "license": {"title": "Apache 2.0", "spdx": "Apache-2.0"}},
                                                  "solar": {"name": "Solar", "license": {"title": "CC BY 4.0", "spdx": "CC-BY-4.0"}}}},
    "api.polyhaven.com/assets": {"wood_floor": {"name": "Wood Floor", "tags": ["wood", "floor"], "categories": ["wood"],
                                                "authors": {"Rob": "All"}, "dimensions": [2000, 2000], "download_count": 5},
                                 "rock": {"name": "Rock", "tags": ["stone"], "categories": [], "download_count": 9}},
    "api.fontsource.org/v1/fonts": [{"id": "poppins", "family": "Poppins", "license": "OFL-1.1", "weights": [400, 700]},
                                    {"id": "closed", "family": "Poppins Pro", "license": "Commercial"}],
    "dashboard-icons/main/tree.json": {"svg": ["instagram.svg", "youtube.svg"], "png": ["instagram.png", "youtube.png", "tiktok.png"]},
    "simple-icons/develop/data/simple-icons.json": [{"title": "Instagram", "hex": "FF0069"}, {"title": "Dot.js"}],
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    calls = []

    def fake(url, headers=None, timeout=20, raw=False):
        calls.append(url)
        for k, v in FIXTURES.items():
            if k in url:
                return v
        raise assets.Skip("no connection (test)")
    monkeypatch.setattr(assets, "fetch", fake)
    (tmp_path / "settings").mkdir()
    (tmp_path / "settings" / "keys.json").write_text(json.dumps({"pexels": "k", "pixabay": "k", "freesound": "k"}))
    return str(tmp_path), calls


def test_video_sources(home):
    h, _ = home
    r = assets.p_pexels(h, "smoke green screen", 3, "video")[0]
    assert r["url"] == "https://x/hd.mp4" and r["w"] == 1920 and r["license"] == "Pexels License"
    p = assets.p_pixabay(h, "light leak", 3, "video")[0]
    assert p["url"] == "https://x/l.mp4" and p["thumb"] == "https://x/m.jpg"


def test_licence_filter(home):
    h, _ = home
    au = assets.p_openverse(h, "whoosh", 5, "sfx", False)
    assert [a["license"] for a in au][0] == "CC0" and au[1]["credit"] is True        # API filter is the guard for 'by'
    wm = assets.p_wikimedia(h, "confetti", 5, "photo", False)
    assert [w["title"] for w in wm] == ["Confetti"]
    assert len(assets.p_wikimedia(h, "confetti", 5, "photo", True)) == 2
    ic = assets.p_iconify(h, "heart", 5, "icon", False)
    assert [i["title"] for i in ic] == ["mdi:heart"]
    assert assets.p_freesound(h, "boom", 3, "sfx", False)[0]["license"] == "CC0"
    fonts = assets.p_fontsource(h, "poppins", 5, "font", False)
    assert [f["title"] for f in fonts] == ["Poppins"]


def test_logos_and_textures(home):
    h, _ = home
    d = assets.p_dashboard(h, "instagram", 3, "logo", False)[0]
    assert d["url"].endswith("/svg/instagram.svg") and d["extra"]["trademark"]
    t = assets.p_dashboard(h, "tiktok", 3, "logo", False)[0]
    assert t["url"].endswith("/png/tiktok.png")
    s = assets.p_simpleicons(h, "dot.js", 3, "logo", False)[0]
    assert s["url"].endswith("/icons/dotdotjs.svg") or s["url"].endswith("/icons/dotjs.svg")
    ph = assets.p_polyhaven(h, "wood", 3, "texture", False)
    assert [p["url"] for p in ph] == ["wood_floor"]


def test_search_writes_last_and_reports_skips(home, capsys):
    h, _ = home
    assets.main(["--home", h, "search", "sfx", "whoosh"])
    out = capsys.readouterr().out
    assert " 1  freesound" in out and "openverse" in out
    last = json.load(open(os.path.join(h, "cache", "assets", "last.json"), encoding="utf-8"))
    assert last["type"] == "sfx" and len(last["rows"]) >= 2
    assets.main(["--home", h, "search", "texture", "lava"])
    assert "NO_RESULTS" in capsys.readouterr().out


def test_cache_avoids_second_request(home, capsys):
    h, calls = home
    assets.main(["--home", h, "search", "icon", "heart"])
    n = len(calls)
    assets.main(["--home", h, "search", "icon", "heart"])
    assert len(calls) == n


def test_links_keys_import(tmp_path):
    out = run("assets.py", "links", "mogrt").stdout
    assert "mixkit.co" in out and "assets.py import" in out
    out = run("assets.py", "--home", tmp_path, "keys", "set", "pexels=SECRET123").stdout
    assert "SECRET123" not in out
    shown = run("assets.py", "--home", tmp_path, "keys").stdout
    assert "pexels\tset" in shown and "SECRET123" not in shown
    bad = run("assets.py", "--home", tmp_path, "keys", "set", "evil=1", check=False)
    assert bad.returncode != 0
    f = tmp_path / "lower-third.mogrt"
    f.write_bytes(b"x")
    run("assets.py", "import", f, "-o", tmp_path / "assets", "--source", "Mixkit", "--license", "Mixkit Free License")
    assert "Mixkit Free License" in (tmp_path / "assets" / "SOURCES.md").read_text(encoding="utf-8")


def test_prefs_defaults(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    run("keremkit.py", "init", tmp_path / "KK", env=env)
    get = lambda k: run("keremkit.py", "--home", tmp_path / "KK", "pref", "get", k).stdout.strip().strip('"')
    assert get("logos.confirm") == "ask" and get("assets.allow_attribution") == "false"
    assert (tmp_path / "KK" / "tools" / "assets.py").exists()


# ---------------------------------------------------------------- 3D sources (recorded API shapes, 2026-11-11)
FIXTURES_3D = {
    "ambientcg.com/api/v2": {"foundAssets": [
        {"assetId": "Wood096", "dataType": "Material", "displayName": "Wood 096", "shortLink": "https://ambientcg.com/a/Wood096",
         "downloadCount": 9, "previewImage": {"256-PNG": "https://acg/t.png"},
         "downloadFolders": {"default": {"downloadFiletypeCategories": {"zip": {"downloads": [
             {"downloadLink": "https://ambientcg.com/get?file=Wood096_1K-JPG.zip", "fileName": "Wood096_1K-JPG.zip", "attribute": "1K-JPG", "size": 1},
             {"downloadLink": "https://ambientcg.com/get?file=Wood096_2K-JPG.zip", "fileName": "Wood096_2K-JPG.zip", "attribute": "2K-JPG", "size": 2}]}}}}},
        {"assetId": "DaySky", "dataType": "HDRI", "displayName": "Day Sky", "downloadFolders": {}}]},
    "api.sketchfab.com/v3/search": {"results": [
        {"uid": "abc", "name": "Side Chair", "viewerUrl": "https://sketchfab.com/3d-models/x-abc", "user": {"username": "Smithsonian"},
         "faceCount": 100, "likeCount": 3, "thumbnails": {"images": [{"url": "https://sf/1024.jpg", "width": 1024},
                                                                     {"url": "https://sf/256.jpg", "width": 256}]}}]},
    "nasa/NASA-3D-Resources/git/trees": {"tree": [
        {"path": "3D Models/Hubble/Hubble.glb", "type": "blob"}, {"path": "3D Models/Hubble/Hubble.jpg", "type": "blob"},
        {"path": "3D Models/Mars/Mars.stl", "type": "blob"}, {"path": "3D Models/Hubble", "type": "tree"}]},
    "api.poly.pizza": {"results": [
        {"ID": "p1", "Title": "Low Poly Tree", "Download": "https://pp/tree.glb", "Licence": "CC0 1.0", "Creator": {"Username": "Quaternius"}},
        {"ID": "p2", "Title": "Tree Pack", "Download": "https://pp/pack.glb", "Licence": "CC-BY 3.0"}]},
}


def test_3d_sources(home, monkeypatch):
    h, _ = home

    def fake(url, headers=None, timeout=20, raw=False):
        for k, v in FIXTURES_3D.items():
            if k in url:
                return v
        raise assets.Skip("no connection (test)")
    monkeypatch.setattr(assets, "fetch", fake)
    acg = assets.p_ambientcg(h, "wood", 5, "texture", False)
    assert [a["title"] for a in acg] == ["Wood 096"] and acg[0]["url"].endswith("2K-JPG.zip") and acg[0]["license"] == "CC0"
    assert assets.p_ambientcg(h, "sky", 5, "hdri", False) == []          # an asset without downloads is skipped
    sf = assets.p_sketchfab(h, "chair", 3, "model", False)[0]
    assert sf["license"] == "CC0" and sf["url"] == "abc" and sf["thumb"] == "https://sf/256.jpg" and not sf["credit"]
    nasa = assets.p_nasa(h, "hubble", 3, "model", False)
    assert len(nasa) == 1 and nasa[0]["url"].endswith("Hubble/Hubble.glb") and nasa[0]["thumb"].endswith("Hubble.jpg")
    with pytest.raises(assets.Skip):
        assets.p_polypizza(h, "tree", 3, "model", False)                 # no key
    keys = json.loads(open(os.path.join(h, "settings", "keys.json")).read())
    keys["polypizza"] = "k"
    open(os.path.join(h, "settings", "keys.json"), "w").write(json.dumps(keys))
    pp = assets.p_polypizza(h, "tree", 3, "model", False)
    assert [p["title"] for p in pp] == ["Low Poly Tree"]
    assert len(assets.p_polypizza(h, "tree", 3, "model", True)) == 2
    with pytest.raises(assets.Skip, match="API token"):
        assets.download(h, sf, os.path.join(h, "dl"))                    # Sketchfab download needs the user's token
    assert set(assets.TYPES["model"]) >= {"polyhaven", "sketchfab", "nasa", "ambientcg", "polypizza"}
