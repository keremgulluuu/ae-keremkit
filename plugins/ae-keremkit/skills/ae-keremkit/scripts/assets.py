#!/usr/bin/env python3
"""Free stock elements - search many sources at once, show them, download the picks with their licence.

  search TYPE "QUERY" [--source a,b] [--n 6] [--allow-attribution]
         TYPE: photo video greenscreen overlay background sfx music icon logo texture hdri model font
         -> numbered compact lines (source, size/length, licence, title); results cached 24 h
  sheet  [-o OUT.png]                        the last search's thumbnails in one numbered image (for the user)
  get    N [N ...] -o DIR                    download picks from the last search + a line each in DIR/SOURCES.md
  logo   NAME [NAME ...] -o DIR [--mono]     a brand logo straight away (colour SVG/PNG, else one-colour SVG)
  links  TYPE "QUERY"                        search pages of free sites without an API (templates, MOGRT, music...)
  import FILE [FILE ...] -o DIR --source S --license L [--url U]   record a file the user downloaded by hand
  keys   [set NAME=VALUE]                    which API keys are set (values never printed); pexels, pixabay, freesound,
                                             sketchfab (token, for model downloads), polypizza
  3D: model = Poly Haven, Sketchfab (CC0, incl. Smithsonian scans), NASA, ambientCG, Poly Pizza; texture / hdri also ambientCG

Only licences that need no credit are listed by default: CC0, public domain, the Pexels and Pixabay licences,
MIT / Apache / ISC / BSD / OFL (icons, fonts). Standard library only; images are never shown to Claude.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = "KeremKit/1.11 (+https://github.com/keremgulluuu/ae-keremkit)"
TTL = 24 * 3600
POINTER = os.path.join(os.path.expanduser("~"), ".keremkit.json")
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "Documents", "KeremKit")
FREE_SPDX = {"MIT", "APACHE-2.0", "ISC", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "CC0-1.0", "OFL-1.1", "UNLICENSE", "0BSD"}
GH_DASH = "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main"
GH_SIMPLE = "https://raw.githubusercontent.com/simple-icons/simple-icons/develop"

TYPES = {
    "photo": ["pexels", "pixabay", "openverse", "wikimedia"],
    "video": ["pexels-video", "pixabay-video", "wikimedia-video"],
    "greenscreen": ["pexels-video", "pixabay-video"],
    "overlay": ["pexels-video", "pixabay-video"],
    "background": ["pexels-video", "pixabay-video"],
    "sfx": ["freesound", "openverse-audio"],
    "music": ["openverse-audio", "freesound"],
    "icon": ["iconify"],
    "logo": ["dashboard", "simpleicons"],
    "texture": ["polyhaven", "ambientcg"],
    "hdri": ["polyhaven", "ambientcg"],
    "model": ["polyhaven", "sketchfab", "nasa", "ambientcg", "polypizza"],
    "font": ["fontsource"],
}
QUERY_ADD = {"greenscreen": "green screen", "overlay": "overlay", "background": "background"}
KEYS = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY", "freesound": "FREESOUND_API_KEY",
        "sketchfab": "SKETCHFAB_API_TOKEN", "polypizza": "POLYPIZZA_API_KEY"}

LINKS = {
    "template": [("Mixkit After Effects templates (Mixkit Free License - check each item)", "https://mixkit.co/free-after-effects-templates/"),
                 ("Mixkit Premiere Pro templates / MOGRT", "https://mixkit.co/free-premiere-pro-templates/mogrt/"),
                 ("Mixkit DaVinci Resolve templates", "https://mixkit.co/free-davinci-resolve-templates/")],
    "mogrt": [("Mixkit MOGRT templates", "https://mixkit.co/free-premiere-pro-templates/mogrt/")],
    "music": [("Pixabay music", "https://pixabay.com/music/search/{q}/"),
              ("Mixkit music", "https://mixkit.co/free-stock-music/"),
              ("YouTube Audio Library (YouTube Studio > Audio Library; pick 'No attribution required')", "https://studio.youtube.com/")],
    "sfx": [("Pixabay sound effects", "https://pixabay.com/sound-effects/search/{q}/"),
            ("Mixkit sound effects", "https://mixkit.co/free-sound-effects/"),
            ("Freesound, CC0 only", "https://freesound.org/search/?q={q}&f=license:%22Creative+Commons+0%22")],
    "video": [("Mixkit stock video", "https://mixkit.co/free-stock-video/"),
              ("Pexels videos", "https://www.pexels.com/search/videos/{q}/"),
              ("Pixabay videos", "https://pixabay.com/videos/search/{q}/")],
    "game": [("Kenney - CC0 game and UI assets", "https://kenney.nl/assets")],
    "model": [("Quaternius - CC0 low-poly packs (characters, nature, vehicles; glTF/FBX)", "https://quaternius.com/"),
              ("Kenney 3D - CC0 kits", "https://kenney.nl/assets/category:3D"),
              ("Smithsonian 3D - CC0 museum scans", "https://3d.si.edu/explore"),
              ("NASA 3D Resources", "https://science.nasa.gov/3d-resources/"),
              ("Sketchfab, CC0 + downloadable", "https://sketchfab.com/search?features=downloadable&licenses=7c23a1ba438d4306920229c12afcb5f9&q={q}&type=models"),
              ("Poly Pizza (CC0 filter)", "https://poly.pizza/search/{q}")],
    "preset": [("Presets (.ffx / .prfpset) have no trustworthy free API: download by hand, then `assets.py import` and `presets.py learn`", "")],
}
LINKS["greenscreen"] = LINKS["overlay"] = LINKS["background"] = LINKS["video"]
LINKS["aep"] = LINKS["project"] = LINKS["template"]
LINKS["prfpset"] = LINKS["ffx"] = LINKS["preset"]
LINKS["3d"] = LINKS["model"]


# ---------------------------------------------------------------- basics
def home_dir(h=None):
    if h:
        return h
    try:
        with open(POINTER, encoding="utf-8") as f:
            return json.load(f)["home"]
    except (OSError, ValueError, KeyError):
        return DEFAULT_HOME


def cache_dir(home):
    d = os.path.join(home, "cache", "assets")
    os.makedirs(d, exist_ok=True)
    return d


def keys(home):
    try:
        with open(os.path.join(home, "settings", "keys.json"), encoding="utf-8") as f:
            k = json.load(f)
    except (OSError, ValueError):
        k = {}
    for name, env in KEYS.items():
        if os.environ.get(env):
            k[name] = os.environ[env]
    return k


class Skip(Exception):
    pass


def fetch(url, headers=None, timeout=20, raw=False):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise Skip(f"HTTP {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise Skip(f"no connection ({getattr(e, 'reason', e)})")
    return data if raw else json.loads(data.decode("utf-8"))


def cached(home, key, ttl, fn):
    p = os.path.join(cache_dir(home), hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")
    if os.path.isfile(p) and time.time() - os.path.getmtime(p) < ttl:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    data = fn()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def slug(text, n=40):
    t = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return t[:n].strip("-") or "item"


def words(q):
    return [w for w in re.split(r"\W+", q.lower()) if w]


def hit(text, q):
    t = (text or "").lower()
    return all(w in t for w in words(q))


def item(src, kind, title, url, lic, page="", author="", w=None, h=None, dur=None, thumb="", ext="", credit=False, extra=None):
    return {"src": src, "kind": kind, "title": (title or "").strip()[:60], "url": url, "license": lic, "page": page,
            "author": author, "w": w, "h": h, "dur": dur, "thumb": thumb, "ext": ext, "credit": credit,
            "extra": extra or {}}


# ---------------------------------------------------------------- providers
def p_pexels(home, q, n, kind):
    k = keys(home).get("pexels")
    if not k:
        raise Skip("no key (keys set pexels=...)")
    video = kind != "photo"
    url = ("https://api.pexels.com/videos/search?" if video else "https://api.pexels.com/v1/search?") + \
        urllib.parse.urlencode({"query": q, "per_page": n})
    data = fetch(url, {"Authorization": k})
    out = []
    if video:
        for v in data.get("videos", []):
            files = sorted([f for f in v.get("video_files", []) if f.get("link") and (f.get("width") or 0) <= 1920],
                           key=lambda f: -(f.get("width") or 0)) or v.get("video_files", [])
            if not files:
                continue
            f = files[0]
            out.append(item("pexels", "video", (v.get("url") or "").rstrip("/").split("/")[-1].replace("-", " "),
                            f["link"], "Pexels License", v.get("url", ""), (v.get("user") or {}).get("name", ""),
                            f.get("width"), f.get("height"), v.get("duration"), v.get("image", ""), "mp4"))
    else:
        for p in data.get("photos", []):
            out.append(item("pexels", "photo", p.get("alt") or "photo", p["src"].get("original") or p["src"].get("large2x"),
                            "Pexels License", p.get("url", ""), p.get("photographer", ""), p.get("width"), p.get("height"),
                            thumb=p["src"].get("medium", ""), ext="jpg"))
    return out


def p_pixabay(home, q, n, kind):
    k = keys(home).get("pixabay")
    if not k:
        raise Skip("no key (keys set pixabay=...)")
    video = kind != "photo"
    base = "https://pixabay.com/api/videos/?" if video else "https://pixabay.com/api/?"
    data = cached(home, f"pixabay|{video}|{q}|{n}", TTL,
                  lambda: fetch(base + urllib.parse.urlencode({"key": k, "q": q, "per_page": max(3, n), "safesearch": "true"})))
    out = []
    for hh in data.get("hits", []):
        if video:
            vs = hh.get("videos", {})
            v = vs.get("large") if (vs.get("large") or {}).get("url") else vs.get("medium", {})
            thumb = (vs.get("medium") or {}).get("thumbnail") or (vs.get("tiny") or {}).get("thumbnail", "")
            out.append(item("pixabay", "video", hh.get("tags", ""), v.get("url", ""), "Pixabay Content License",
                            hh.get("pageURL", ""), hh.get("user", ""), v.get("width"), v.get("height"), hh.get("duration"),
                            thumb, "mp4"))
        else:
            out.append(item("pixabay", "photo", hh.get("tags", ""), hh.get("largeImageURL", ""), "Pixabay Content License",
                            hh.get("pageURL", ""), hh.get("user", ""), hh.get("imageWidth"), hh.get("imageHeight"),
                            thumb=hh.get("webformatURL", ""), ext="jpg"))
    return out


def p_openverse(home, q, n, kind, allow):
    audio = kind in ("sfx", "music")
    lic = "cc0,pdm" + (",by,by-sa" if allow else "")
    params = {"q": q, "page_size": n, "license": lic}
    if audio:
        params["category"] = "music" if kind == "music" else "sound_effect"
    url = f"https://api.openverse.org/v1/{'audio' if audio else 'images'}/?"
    try:
        data = fetch(url + urllib.parse.urlencode(params))
    except Skip as e:
        if "400" not in str(e) or "category" not in params:
            raise
        params.pop("category")
        data = fetch(url + urllib.parse.urlencode(params))
    out = []
    for r in data.get("results", []):
        code = (r.get("license") or "").lower()
        credit = code not in ("cc0", "pdm")
        lic = "CC0" if code == "cc0" else ("Public Domain" if code == "pdm" else f"CC {code.upper()} {r.get('license_version', '')}".strip())
        dur = (r.get("duration") or 0) / 1000 if audio and r.get("duration") else None
        out.append(item("openverse", "audio" if audio else "photo", r.get("title", ""), r.get("url", ""), lic,
                        r.get("foreign_landing_url", ""), r.get("creator", ""), r.get("width"), r.get("height"), dur,
                        r.get("thumbnail", ""), (r.get("filetype") or "").lower(), credit))
    return out


def p_wikimedia(home, q, n, kind, allow):
    ft = "video" if kind == "video" else ("audio" if kind in ("sfx", "music") else "bitmap")
    params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": n * 3,
              "gsrsearch": f"{q} filetype:{ft}", "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
              "iiurlwidth": 320}
    data = fetch("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
    out = []
    for pg in (data.get("query", {}).get("pages") or {}).values():
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        short = re.sub("<[^>]+>", "", (md.get("LicenseShortName") or {}).get("value", ""))
        code = (md.get("License") or {}).get("value", "").lower()
        free = code.startswith(("pd", "cc0")) or short.lower().startswith(("public domain", "cc0", "pd"))
        if not free and not allow:
            continue
        artist = re.sub("<[^>]+>", "", (md.get("Artist") or {}).get("value", ""))[:40]
        title = pg.get("title", "").replace("File:", "")
        out.append(item("wikimedia", kind if kind == "video" else "photo", os.path.splitext(title)[0], ii.get("url", ""),
                        short or code, ii.get("descriptionurl", ""), artist, ii.get("width"), ii.get("height"),
                        ii.get("duration"), ii.get("thumburl", ""), os.path.splitext(title)[1].lstrip(".").lower(), not free))
        if len(out) >= n:
            break
    return out


def p_freesound(home, q, n, kind, allow):
    k = keys(home).get("freesound")
    if not k:
        raise Skip("no key (keys set freesound=...)")
    flt = 'license:"Creative Commons 0"' if not allow else ""
    if kind == "music":
        flt = (flt + " tag:music").strip()
    params = {"query": q, "page_size": n, "fields": "id,name,duration,license,previews,username,url", "token": k}
    if flt:
        params["filter"] = flt
    data = fetch("https://freesound.org/apiv2/search/text/?" + urllib.parse.urlencode(params))
    out = []
    for r in data.get("results", []):
        lic = r.get("license", "")
        cc0 = "publicdomain/zero" in lic
        out.append(item("freesound", "audio", r.get("name", ""), (r.get("previews") or {}).get("preview-hq-mp3", ""),
                        "CC0" if cc0 else lic, r.get("url", ""), r.get("username", ""), dur=r.get("duration"),
                        ext="mp3", credit=not cc0))
    return out


def p_iconify(home, q, n, kind, allow):
    data = fetch("https://api.iconify.design/search?" + urllib.parse.urlencode({"query": q, "limit": max(32, n * 4)}))
    cols = data.get("collections", {})
    out = []
    for ic in data.get("icons", []):
        prefix, _, name = ic.partition(":")
        lic = (cols.get(prefix) or {}).get("license") or {}
        spdx = (lic.get("spdx") or "").upper()
        free = spdx in FREE_SPDX
        if not free and not allow:
            continue
        out.append(item("iconify", "icon", f"{prefix}:{name}", f"https://api.iconify.design/{prefix}/{name}.svg?height=512",
                        lic.get("title") or spdx, f"https://icon-sets.iconify.design/{prefix}/{name}/",
                        (cols.get(prefix) or {}).get("name", ""), ext="svg", credit=not free))
        if len(out) >= n:
            break
    return out


def dash_tree(home):
    return cached(home, "dashboard-tree", TTL, lambda: fetch(GH_DASH + "/tree.json"))


def p_dashboard(home, q, n, kind, allow):
    tree = dash_tree(home)
    names = sorted({os.path.splitext(f)[0] for f in tree.get("svg", []) + tree.get("png", [])})
    exact = [x for x in names if x == slug(q)]
    rest = [x for x in names if x not in exact and hit(x.replace("-", " "), q)]
    out = []
    for name in (exact + sorted(rest, key=len))[:n]:
        has_svg = f"{name}.svg" in tree.get("svg", [])
        out.append(item("dashboard", "logo" if kind == "logo" else "icon", name,
                        f"{GH_DASH}/{'svg' if has_svg else 'png'}/{name}.{'svg' if has_svg else 'png'}",
                        "Apache-2.0", "https://dashboardicons.com/icons",
                        thumb=f"{GH_DASH}/png/{name}.png", ext="svg" if has_svg else "png",
                        extra={"png": f"{GH_DASH}/png/{name}.png", "trademark": True}))
    return out


def simple_slug(title):
    t = title.lower().replace("+", "plus").replace(".", "dot").replace("&", "and")
    t = re.sub(r"[àáâãäå]", "a", t)
    t = re.sub(r"[èéêë]", "e", t)
    return re.sub(r"[^a-z0-9]", "", t)


def p_simpleicons(home, q, n, kind, allow):
    data = cached(home, "simpleicons-data", TTL, lambda: fetch(GH_SIMPLE + "/data/simple-icons.json"))
    icons = data if isinstance(data, list) else data.get("icons", [])
    exact = [i for i in icons if i["title"].lower() == q.lower()]
    rest = [i for i in icons if i not in exact and hit(i["title"], q)]
    out = []
    for i in (exact + sorted(rest, key=lambda i: len(i["title"])))[:n]:
        s = i.get("slug") or simple_slug(i["title"])
        out.append(item("simpleicons", "logo", i["title"], f"{GH_SIMPLE}/icons/{s}.svg",
                        "CC0", i.get("source", "https://simpleicons.org"),
                        ext="svg", extra={"hex": i.get("hex", ""), "trademark": True}))
    return out


def p_polyhaven(home, q, n, kind, allow):
    t = {"texture": "textures", "hdri": "hdris", "model": "models"}[kind]
    data = cached(home, f"polyhaven-{t}", TTL, lambda: fetch(f"https://api.polyhaven.com/assets?t={t}"))
    out = []
    for aid, a in data.items():
        text = " ".join([aid, a.get("name", ""), " ".join(a.get("tags", [])), " ".join(a.get("categories", []))])
        if hit(text, q):
            # model dimensions are millimetres (floats), not pixels - only show pixel sizes
            dims = (a.get("dimensions") or [None, None])[:2] if t != "models" else [None, None]
            dims = [int(round(d)) if isinstance(d, (int, float)) else None for d in dims]
            out.append(item("polyhaven", kind, a.get("name", aid), aid, "CC0", f"https://polyhaven.com/a/{aid}",
                            ", ".join(a.get("authors", {}).keys()), *dims,
                            thumb=f"https://cdn.polyhaven.com/asset_img/thumbs/{aid}.png?width=256&height=256",
                            ext={"textures": "jpg", "hdris": "hdr", "models": "gltf"}[t],
                            extra={"downloads": a.get("download_count", 0)}))
    return sorted(out, key=lambda r: -r["extra"]["downloads"])[:n]


ACG_TYPE = {"texture": "Material", "hdri": "HDRI", "model": "3DModel"}
ACG_RES = {"texture": ("2K-JPG", "1K-JPG"), "hdri": ("2K-HDR", "1K-HDR", "4K-HDR"), "model": ()}


def p_ambientcg(home, q, n, kind, allow):
    """ambientCG: CC0 PBR materials, HDRIs and 3D models (no key). The API ignores its type filter -> filter here."""
    url = ("https://ambientcg.com/api/v2/full_json?" +
           urllib.parse.urlencode({"q": q, "limit": 80, "include": "downloadData,imageData", "sort": "Popular"}))
    data = fetch(url, timeout=30)
    out = []
    for a in data.get("foundAssets", []):
        if a.get("dataType") != ACG_TYPE[kind]:
            continue
        dls = []
        for folder in (a.get("downloadFolders") or {}).values():
            for cat in (folder.get("downloadFiletypeCategories") or {}).values():
                dls += cat.get("downloads") or []
        if not dls:
            continue
        pick = next((d for want in ACG_RES[kind] for d in dls if d.get("attribute") == want), dls[0])
        img = a.get("previewImage") or {}
        out.append(item("ambientcg", kind, a.get("displayName") or a["assetId"], pick.get("downloadLink") or pick.get("fullDownloadPath"),
                        "CC0", a.get("shortLink", ""), "ambientCG", thumb=img.get("256-PNG", ""), ext="zip",
                        extra={"downloads": a.get("downloadCount", 0), "file": pick.get("fileName"),
                               "size_mb": round((pick.get("size") or 0) / 1e6, 1)}))
    return out[:n]


SKETCHFAB_LIC = {"cc0": "CC0", "by": "CC BY 4.0"}


def p_sketchfab(home, q, n, kind, allow):
    """Sketchfab: downloadable CC0 models (incl. Smithsonian and museum scans); CC BY too with --allow-attribution.
    Search needs no key; downloading needs the user's free API token (assets.py keys set sketchfab=...)."""
    out = []
    for lic in (["cc0", "by"] if allow else ["cc0"]):
        url = "https://api.sketchfab.com/v3/search?" + urllib.parse.urlencode(
            {"type": "models", "q": q, "downloadable": "true", "license": lic, "count": min(24, n * 2), "sort_by": "-likeCount"})
        for r in fetch(url, timeout=30).get("results", []):
            thumbs = sorted((r.get("thumbnails") or {}).get("images") or [], key=lambda t: abs((t.get("width") or 0) - 256))
            out.append(item("sketchfab", "model", r.get("name", ""), r.get("uid", ""), SKETCHFAB_LIC[lic], r.get("viewerUrl", ""),
                            (r.get("user") or {}).get("username", ""), thumb=thumbs[0]["url"] if thumbs else "", ext="glb",
                            credit=lic != "cc0", extra={"faces": r.get("faceCount"), "likes": r.get("likeCount", 0)}))
    return out[:n]


NASA_REPO = "https://api.github.com/repos/nasa/NASA-3D-Resources/git/trees/master?recursive=1"
NASA_RAW = "https://raw.githubusercontent.com/nasa/NASA-3D-Resources/master/"


def p_nasa(home, q, n, kind, allow):
    """NASA 3D Resources (GitHub): spacecraft, planets, asteroids as .glb. Not copyrighted; NASA's media guidelines apply
    (no endorsement, no NASA logo use)."""
    tree = cached(home, "nasa-3d-tree", 7 * TTL, lambda: fetch(NASA_REPO, timeout=60))
    paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    imgs = {p.rsplit("/", 1)[0]: p for p in paths if p.lower().endswith((".jpg", ".png"))}
    out = []
    for p in paths:
        if not p.lower().endswith(".glb") or not hit(p, q):
            continue
        folder = p.rsplit("/", 1)[0]
        thumb = NASA_RAW + urllib.parse.quote(imgs[folder]) if folder in imgs else ""
        out.append(item("nasa", "model", folder.split("/")[-1], NASA_RAW + urllib.parse.quote(p),
                        "NASA (no copyright; no endorsement)", "https://science.nasa.gov/3d-resources/", "NASA",
                        thumb=thumb, ext="glb"))
    return out[:n]


def p_polypizza(home, q, n, kind, allow):
    """Poly Pizza: low-poly models (many from Quaternius, Kenney, Google Poly). Needs a free key (poly.pizza/settings/api)."""
    k = keys(home).get("polypizza")
    if not k:
        raise Skip("needs a free API key (poly.pizza): assets.py keys set polypizza=...")
    data = fetch(f"https://api.poly.pizza/v1.1/search/{urllib.parse.quote(q)}?Limit={min(32, n * 3)}",
                 headers={"x-auth-token": k})
    out = []
    for r in data.get("results", []):
        lic = str(r.get("Licence") or r.get("License") or "")
        cc0 = "cc0" in lic.lower() or "public" in lic.lower()
        if not cc0 and not allow:
            continue
        rid = r.get("ID") or r.get("PublicID") or ""
        out.append(item("polypizza", "model", r.get("Title", ""), r.get("Download", ""), "CC0" if cc0 else lic or "CC BY 3.0",
                        f"https://poly.pizza/m/{rid}", (r.get("Creator") or {}).get("Username", ""),
                        thumb=r.get("Thumbnail", ""), ext="glb", credit=not cc0))
    return out[:n]


def p_fontsource(home, q, n, kind, allow):
    data = cached(home, "fontsource-list", TTL, lambda: fetch("https://api.fontsource.org/v1/fonts"))
    out = []
    for f in data:
        if not hit(f.get("family", ""), q):
            continue
        lic = f.get("license")
        lic = (lic.get("type") or lic.get("id") or "") if isinstance(lic, dict) else (lic or "")
        free = lic.upper() in FREE_SPDX or lic.upper().startswith(("OFL", "APACHE"))
        if not free and not allow:
            continue
        out.append(item("fontsource", "font", f.get("family", ""), f.get("id", ""), lic or "?",
                        f"https://fontsource.org/fonts/{f.get('id', '')}", ext="ttf",
                        extra={"weights": f.get("weights", []), "category": f.get("category", "")}))
    return sorted(out, key=lambda r: (r["title"].lower() != q.lower(), len(r["title"])))[:n]


PROVIDERS = {
    "pexels": lambda h, q, n, k, a: p_pexels(h, q, n, "photo"),
    "pexels-video": lambda h, q, n, k, a: p_pexels(h, q, n, "video"),
    "pixabay": lambda h, q, n, k, a: p_pixabay(h, q, n, "photo"),
    "pixabay-video": lambda h, q, n, k, a: p_pixabay(h, q, n, "video"),
    "openverse": lambda h, q, n, k, a: p_openverse(h, q, n, "photo", a),
    "openverse-audio": p_openverse,
    "wikimedia": lambda h, q, n, k, a: p_wikimedia(h, q, n, "photo", a),
    "wikimedia-video": lambda h, q, n, k, a: p_wikimedia(h, q, n, "video", a),
    "freesound": p_freesound,
    "iconify": p_iconify,
    "dashboard": p_dashboard,
    "simpleicons": p_simpleicons,
    "polyhaven": p_polyhaven,
    "ambientcg": p_ambientcg,
    "sketchfab": p_sketchfab,
    "nasa": p_nasa,
    "polypizza": p_polypizza,
    "fontsource": p_fontsource,
}


# ---------------------------------------------------------------- commands
def fmt(i, r):
    size = f"{r['w']}x{r['h']}" if r.get("w") and r.get("h") else ""
    dur = f"{r['dur']:.0f}s" if r.get("dur") else ""
    meta = " ".join(x for x in (size, dur) if x)
    flag = ("  [credit needed]" if r.get("credit") else "") + ("  [brand mark]" if (r.get("extra") or {}).get("trademark") else "")
    return f"{i:>2}  {r['src']:<11} {meta:<14} {r['license'][:28]:<28} {r['title']}{flag}"


def cmd_search(a):
    home = home_dir(a.home)
    kind = a.type
    if kind not in TYPES:
        sys.exit(f"ERROR: type must be one of {', '.join(TYPES)} (templates, MOGRT, presets: links)")
    q = a.query
    if kind in QUERY_ADD and QUERY_ADD[kind] not in q.lower():
        q = f"{q} {QUERY_ADD[kind]}".strip()
    srcs = a.source.split(",") if a.source else TYPES[kind]

    def run(src):
        try:
            return src, cached(home, f"{src}|{kind}|{q}|{a.n}|{a.allow_attribution}", TTL,
                               lambda: PROVIDERS[src](home, q, a.n, kind, a.allow_attribution)), None
        except Skip as e:
            return src, [], str(e)
        except Exception as e:  # a changed API must not break the other sources
            return src, [], f"error {type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=len(srcs)) as ex:
        res = list(ex.map(run, srcs))
    rows, skipped = [], []
    for src, found, err in res:
        if err:
            skipped.append(f"{src}: {err}")
        rows += [r for r in found if r.get("url")]
    for r in rows:
        r["kind_req"] = kind
    with open(os.path.join(cache_dir(home), "last.json"), "w", encoding="utf-8") as f:
        json.dump({"type": kind, "query": q, "rows": rows}, f, ensure_ascii=False)
    for i, r in enumerate(rows, 1):
        print(fmt(i, r))
    if skipped:
        print("SKIPPED\t" + " | ".join(skipped))
    if not rows:
        blocked = any("no connection" in s_ or "HTTP 403" in s_ for s_ in skipped)
        print("NO_RESULTS" + ("\tsome sources are not reachable from here (network blocked?) - run the tool on the user's "
                              "computer, or use: assets.py links" if blocked else ""))
    elif kind in LINKS or kind in ("sfx", "music"):
        print(f"MORE\tassets.py links {kind} \"{a.query}\" - sites without an API")


def last(home):
    try:
        with open(os.path.join(cache_dir(home), "last.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        sys.exit("ERROR: no search yet - run assets.py search first")


def cmd_sheet(a):
    import previews
    home = home_dir(a.home)
    data = last(home)
    tdir = os.path.join(cache_dir(home), "thumbs")
    os.makedirs(tdir, exist_ok=True)
    tiles, skipped = [], []
    for i, r in enumerate(data["rows"], 1):
        t = r.get("thumb")
        if not t:
            skipped.append(str(i))
            continue
        p = os.path.join(tdir, hashlib.md5(t.encode()).hexdigest() + ".img")
        try:
            if not os.path.isfile(p):
                with open(p, "wb") as f:
                    f.write(fetch(t, raw=True))
            tiles.append((i, p))
        except Skip:
            skipped.append(str(i))
    ff = previews.ffmpeg()
    if not ff or not tiles:
        sys.exit("ERROR: nothing to show (no thumbnails or no ffmpeg)" + (f" - no thumbnail: {', '.join(skipped)}" if skipped else ""))
    W, H, cols = 400, 300, 4
    parts, labels = [], []
    for k, (i, p) in enumerate(tiles):
        draw = ",".join(previews.text_boxes(str(i), 10, 10, 5, "white"))
        parts.append(f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,format=rgba,"
                     f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x262626@1,format=rgb24,"
                     f"drawbox=x=0:y=0:w=60:h=48:color=0x000000@0.7:t=fill,{draw},pad={W + 6}:{H + 6}:3:3:color=0x111111[t{k}]")
        labels.append(f"[t{k}]")
    while len(labels) % cols and len(labels) > cols:
        k = len(labels)
        parts.append(f"color=c=0x111111:s={W + 6}x{H + 6}:d=1,format=rgb24[t{k}]")
        labels.append(f"[t{k}]")
    c = min(cols, len(labels))
    rows_ = [labels[j:j + c] for j in range(0, len(labels), c)]
    for j, row in enumerate(rows_):
        parts.append("".join(row) + (f"hstack=inputs={len(row)}[r{j}]" if len(row) > 1 else f"null[r{j}]"))
    parts.append("".join(f"[r{j}]" for j in range(len(rows_))) +
                 (f"vstack=inputs={len(rows_)}[out]" if len(rows_) > 1 else "null[out]"))
    out = a.out or os.path.join(cache_dir(home), "sheet.png")
    cmd = [ff, "-y", "-v", "error"]
    for _, p in tiles:
        cmd += ["-i", p]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-frames:v", "1", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("ERROR: ffmpeg: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    print(f"OK\t{out}\t{len(tiles)} item(s)" + (f"\tno thumbnail: {', '.join(skipped)}" if skipped else ""))


def sources_line(dest, fname, r):
    p = os.path.join(dest, "SOURCES.md")
    new = not os.path.isfile(p)
    with open(p, "a", encoding="utf-8") as f:
        if new:
            f.write("# Sources\n\nFile | Title | Source | Author | Licence | Date\n---|---|---|---|---|---\n")
        credit = " **(credit required)**" if r.get("credit") else ""
        tm = " (trademark of its owner)" if (r.get("extra") or {}).get("trademark") else ""
        f.write(f"{fname} | {r['title']} | {r.get('page') or r['src']} | {r.get('author', '')} | {r['license']}{credit}{tm} | "
                f"{date.today().isoformat()}\n")


def download(home, r, dest, fmt_=None):
    os.makedirs(dest, exist_ok=True)
    base = f"{r['src']}_{slug(r['title'], 30)}"
    files = []
    if r["src"] == "polyhaven":
        info = fetch(f"https://api.polyhaven.com/files/{r['url']}")
        if r["kind"] == "hdri":
            u = info["hdri"].get("2k", info["hdri"].get("1k"))["hdr"]["url"]
            files.append((u, base + ".hdr"))
        elif r["kind"] == "texture":
            for mp in ("Diffuse", "nor_gl", "Rough", "Displacement"):
                if mp in info:
                    res = info[mp].get("2k") or next(iter(info[mp].values()))
                    v = res.get("jpg") or res.get("png") or next(iter(res.values()))
                    files.append((v["url"], f"{base}_{mp.lower()}.{v['url'].rsplit('.', 1)[-1]}"))
        else:
            g = info["gltf"].get("1k") or next(iter(info["gltf"].values()))
            g = g["gltf"]
            files.append((g["url"], base + ".gltf"))
            for rel, v in (g.get("include") or {}).items():
                files.append((v["url"], rel))
    elif r["src"] == "sketchfab":
        tok = keys(home).get("sketchfab")
        if not tok:
            raise Skip("downloading from Sketchfab needs the user's free API token (sketchfab.com > Settings > Password & API): "
                       f"assets.py keys set sketchfab=...  - or download it by hand from {r.get('page')} and use assets.py import")
        info = fetch(f"https://api.sketchfab.com/v3/models/{r['url']}/download", headers={"Authorization": f"Token {tok}"})
        g = info.get("glb") or info.get("gltf")
        if not g:
            raise Skip("no glb/gltf download offered for this model")
        files.append((g["url"], base + (".glb" if "glb" in info else ".zip")))
    elif r["src"] == "fontsource":
        info = fetch(f"https://api.fontsource.org/v1/fonts/{r['url']}")
        var = info.get("variants", {})
        for w in ("400", "700"):
            try:
                sub = var[w]["normal"]
                u = (sub.get("latin-ext") or sub.get("latin") or next(iter(sub.values())))["url"]["ttf"]
                files.append((u, f"{slug(r['title'], 30)}-{w}.ttf"))
            except (KeyError, StopIteration, TypeError):
                pass
    elif r["src"] == "dashboard" and fmt_ == "png":
        files.append((r["extra"]["png"], base + ".png"))
    else:
        ext = r.get("ext") or os.path.splitext(urllib.parse.urlparse(r["url"]).path)[1].lstrip(".") or "bin"
        files.append((r["url"], f"{base}.{ext}"))
    saved = []
    for u, name in files:
        p = os.path.join(dest, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(fetch(u, raw=True, timeout=120))
        saved.append(p)
    if r["src"] == "ambientcg" and saved and saved[0].lower().endswith(".zip"):
        import zipfile
        folder = os.path.splitext(saved[0])[0]
        with zipfile.ZipFile(saved[0]) as z:
            for m in z.namelist():                     # refuse paths that leave the folder
                if os.path.isabs(m) or ".." in m.replace("\\", "/").split("/"):
                    raise Skip(f"unsafe path in zip: {m}")
            z.extractall(folder)
        os.remove(saved[0])
        saved = [folder] + [os.path.join(folder, m) for m in sorted(os.listdir(folder))]
    if r["src"] == "simpleicons" and (r.get("extra") or {}).get("hex") and saved:
        with open(saved[0], encoding="utf-8") as f:
            svg = f.read()
        if "fill=" not in svg:
            svg = svg.replace("<svg ", f'<svg fill="#{r["extra"]["hex"]}" ', 1)
            with open(saved[0], "w", encoding="utf-8") as f:
                f.write(svg)
    if saved:
        sources_line(dest, os.path.relpath(saved[0], dest).replace("\\", "/"), r)
    return saved


def cmd_get(a):
    home = home_dir(a.home)
    data = last(home)
    for n in a.numbers:
        if not 1 <= n <= len(data["rows"]):
            print(f"ERROR\t{n}\tno such result")
            continue
        r = data["rows"][n - 1]
        try:
            saved = download(home, r, a.out, a.format)
        except Skip as e:
            print(f"ERROR\t{n}\t{r['src']}: {e}")
            continue
        size = sum(os.path.getsize(p) for p in saved)
        note = "  CREDIT REQUIRED - see SOURCES.md" if r.get("credit") else ""
        print(f"OK\t{n}\t{os.path.basename(saved[0])}" + (f" (+{len(saved) - 1})" if len(saved) > 1 else "") +
              f"\t{size // 1024} KB\t{r['license']}{note}")
    if data["type"] == "font":
        print("NOTE\tfonts must be installed (double-click the .ttf > Install) before After Effects can use them")


def cmd_logo(a):
    home = home_dir(a.home)
    for name in a.names:
        r = None
        if not a.mono:
            try:
                found = p_dashboard(home, name, 1, "logo", False)
                r = found[0] if found and found[0]["title"] == slug(name) else None
            except Skip:
                r = None
        if r is None:
            try:
                found = p_simpleicons(home, name, 1, "logo", False)
                r = found[0] if found else None
            except Skip as e:
                print(f"ERROR\t{name}\t{e}")
                continue
        if r is None:
            print(f"NOT_FOUND\t{name}\ttry: assets.py search logo \"{name}\"")
            continue
        try:
            saved = download(home, r, a.out, "png" if a.png else None)
        except Skip as e:
            print(f"ERROR\t{name}\t{e}")
            continue
        kind = "one colour" if r["src"] == "simpleicons" else "colour"
        print(f"OK\t{name}\t{saved[0]}\t{kind}, {r['src']}")


def cmd_links(a):
    q = urllib.parse.quote(a.query.strip().replace(" ", "-")) if a.query else ""
    found = LINKS.get(a.type)
    if not found:
        sys.exit(f"ERROR: no link list for '{a.type}' - types: {', '.join(sorted(LINKS))}")
    for title, url in found:
        print(f"{title}\t{url.format(q=q)}" if url else title)
    print("NEXT\tafter downloading: assets.py import <file> -o <dir> --source <site> --license \"<licence>\" --url <page>")


def cmd_import(a):
    os.makedirs(a.out, exist_ok=True)
    for f in a.files:
        if not os.path.isfile(f):
            print(f"MISSING\t{f}")
            continue
        dst = os.path.join(a.out, os.path.basename(f))
        if os.path.abspath(f) != os.path.abspath(dst):
            shutil.copy2(f, dst)
        sources_line(a.out, os.path.basename(f), {"title": os.path.splitext(os.path.basename(f))[0], "page": a.url or a.source,
                                                  "src": a.source, "author": "", "license": a.license, "credit": a.credit})
        print(f"OK\t{dst}\t{a.license}")


def cmd_keys(a):
    home = home_dir(a.home)
    p = os.path.join(home, "settings", "keys.json")
    if a.action == "set":
        k = {}
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                k = json.load(f)
        for pair in a.pairs:
            name, _, val = pair.partition("=")
            if name not in KEYS:
                sys.exit(f"ERROR: unknown key '{name}' - {', '.join(KEYS)}")
            k[name] = val.strip()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(k, f, indent=1)
        print(f"OK\tsaved in {p} (only on this computer)")
        return
    have = keys(home)
    for name, env in KEYS.items():
        print(f"{name}\t{'set' if have.get(name) else 'not set'}")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="KeremKit free stock elements")
    ap.add_argument("--home")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("search")
    s.add_argument("type")
    s.add_argument("query")
    s.add_argument("--source")
    s.add_argument("--n", type=int, default=6, help="results per source")
    s.add_argument("--allow-attribution", action="store_true", help="also list items that need a credit")
    sh = sp.add_parser("sheet")
    sh.add_argument("-o", "--out")
    g = sp.add_parser("get")
    g.add_argument("numbers", type=int, nargs="+")
    g.add_argument("-o", "--out", required=True)
    g.add_argument("--format", choices=["svg", "png"])
    lg = sp.add_parser("logo")
    lg.add_argument("names", nargs="+")
    lg.add_argument("-o", "--out", required=True)
    lg.add_argument("--mono", action="store_true", help="one-colour Simple Icons version")
    lg.add_argument("--png", action="store_true", help="PNG instead of SVG where available")
    li = sp.add_parser("links")
    li.add_argument("type")
    li.add_argument("query", nargs="?", default="")
    im = sp.add_parser("import")
    im.add_argument("files", nargs="+")
    im.add_argument("-o", "--out", required=True)
    im.add_argument("--source", required=True)
    im.add_argument("--license", required=True)
    im.add_argument("--url")
    im.add_argument("--credit", action="store_true", help="the licence requires a credit")
    k = sp.add_parser("keys")
    k.add_argument("action", nargs="?", choices=["set"])
    k.add_argument("pairs", nargs="*")
    a = ap.parse_args(argv)
    {"search": cmd_search, "sheet": cmd_sheet, "get": cmd_get, "logo": cmd_logo, "links": cmd_links,
     "import": cmd_import, "keys": cmd_keys}[a.cmd](a)


if __name__ == "__main__":
    main()
