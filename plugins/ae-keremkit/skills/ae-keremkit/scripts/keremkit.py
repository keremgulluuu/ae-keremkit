#!/usr/bin/env python3
"""KeremKit home tool - settings, preferences, categories, library catalog, edit styles.

The KeremKit home folder holds everything that changes over time (preferences, library,
styles, lessons), so the skill itself never needs re-installing. This tool does the
bookkeeping on the user's computer and prints only short results.

  where                                   print the home folder (pointer file or default)
  init     [HOME]                         create/repair the home folder + pointer file
  pref     get  [KEY]                     read a preference (dotted key) or the whole section
  pref     set  KEY=VALUE [KEY=VALUE ...] write preferences (VALUE is JSON, or a plain string)
  pref     missing [SECTION]              list preferences that were never answered (null)
  cat      list                           list categories
  cat      add  --key K --prefix P --name "Name" [--local tr="Ad"] [--desc "..."]
  search   WORD [WORD ...] [--type item|style] [--n 5]
  new-id   PREFIX                         next free id, e.g. UI -> UI-008
  add      META_OR_STYLE.json             add/update a catalog row (library item or style)
  style-archive SLUG --reason "..."       snapshot styles/SLUG/style.json into the archive
  validate                                check catalog rows point at real files
  summary                                 counts per category

All commands except `where`/`init` use the home from the pointer file; pass --home to override.
"""
import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import date

POINTER = os.path.join(os.path.expanduser("~"), ".keremkit.json")
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), "Documents", "KeremKit")
CATALOG_COLS = ["id", "type", "category", "name", "local_name", "summary", "folder", "search"]

DEFAULT_CATEGORIES = [
    {"key": "text", "prefix": "TXT", "name": "Text Styles", "desc": "titles, captions, kinetic type"},
    {"key": "ui", "prefix": "UI", "name": "UI Elements", "desc": "cards, counters, lower thirds, buttons, progress bars"},
    {"key": "background", "prefix": "BG", "name": "Backgrounds", "desc": "gradients, textures, animated backdrops"},
    {"key": "icon", "prefix": "ICN", "name": "Icons", "desc": "icons and icon animations"},
    {"key": "transition", "prefix": "TRN", "name": "Transitions", "desc": "scene and shot transitions"},
    {"key": "interstitial", "prefix": "INT", "name": "Interstitials", "desc": "bumpers, chapter cards, inserts between parts"},
    {"key": "motion", "prefix": "ANM", "name": "Motion Designs", "desc": "in/out moves, pops, bounces, .ffx presets"},
    {"key": "fx-preset", "prefix": "FXP", "name": "Effect Presets", "desc": "learned .ffx presets: effects, keyframes, required plugins"},
    {"key": "color", "prefix": "CLR", "name": "Color Themes", "desc": "palettes and grades"},
    {"key": "edit-style", "prefix": "STY", "name": "Edit Styles", "desc": "complete edit recipes (stored under styles/)"},
    {"key": "other", "prefix": "OTH", "name": "Other", "desc": "anything that fits nowhere else (suggest a new category when these pile up)"},
]

# null = never answered -> ask when first needed (see references/setup.md)
DEFAULT_PREFS = {
    "kk_version": 1,
    "language": {
        "reply": "auto",       # auto = the language the user writes in; or a code like "en", "tr"
        "library": None,       # extra language for library/style names besides English, e.g. "tr" (null = ask once)
    },
    "setup": {"completed": False, "asked": [], "skipped": []},
    "paths": {
        "materials": {"images": None, "icons": None, "sfx": None, "music": None, "fonts": None, "luts": None, "other": []},
        "presets": [],
        "web_sources": [],
        "footage_folders": [],
        "work_files": "next_to_project",
    },
    "tools": {
        "python": None, "ffmpeg": None, "ffprobe": None,
        "whisper": {"impl": None, "path": None, "model": None, "device": None, "language": None},
    },
    "subtitles": {"enabled": None, "engine": None, "build_mode": "data", "rules": {}, "font": None, "look": None,
                  "glossary": []},
    "cutting": {"preset": None, "repeats": None, "silence": "auto", "overrides": {}, "intermediate_codec": "h264", "crf": 18, "x264_preset": "veryfast"},
    "sfx": {"enabled": None, "rules": [], "level_db": -18, "min_gap_s": 0.4, "max_per_10s": 6},
    "render": {"mode": None, "format": None, "output_folder": None, "naming": "{project}_{format}_v{nnn}"},
    "verification": {"screenshots": "on_request", "economic_thumb_width": 480, "motion_max_frames": 6},
    "style_versioning": {"mode": None, "rules": []},
    "learning": {"ask_after_edit": True},
    "design_import": {"preview": None},
    "standards": {
        "safe_area": {"action": 0.93, "title": 0.90},
        "vertical_ui_margin_px": {"top": 220, "bottom": 380, "right": 140, "left": 60},
        "default_comp": {"16x9": [1920, 1080, 30], "9x16": [1080, 1920, 30], "1x1": [1080, 1080, 30]},
        "checkpoint_batch_threshold": 10,
    },
    "custom_rules": [],
}
FILLER = {"a", "an", "the", "with", "from", "to", "of", "and", "or", "in", "on", "for",
          "ve", "ile", "bir", "icin", "da", "de", "ya", "dan", "den", "bu", "su"}
_TR = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
                     "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c"})


# ---------------------------------------------------------------- basics
def norm(text):
    t = unicodedata.normalize("NFKD", (text or "").translate(_TR))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def display(c):
    """Category label: English name plus any stored translations."""
    loc = " / ".join(v for v in (c.get("names") or {}).values() if v)
    return c.get("name", c["key"]) + (f" / {loc}" if loc else "")


def parse_local(pairs):
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        if k and v:
            out[k.strip()] = v.strip().strip('"')
    return out


def meta_names(meta):
    """English name + local names; accepts the older name_en / name_tr fields too."""
    name = meta.get("name") or meta.get("name_en") or ""
    local = dict(meta.get("names") or {})
    for k, v in meta.items():
        m = re.fullmatch(r"name_([a-z]{2})", k)
        if m and m.group(1) != "en" and v:
            local.setdefault(m.group(1), v)
    if not name and local:
        name = next(iter(local.values()))
    return name, local


def slug(text):
    return norm(text).replace(" ", "-") or "item"


def rjson(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def wjson(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def home_dir(override=None):
    if override:
        return os.path.abspath(override)
    p = rjson(POINTER)
    if p and p.get("home"):
        return p["home"]
    return DEFAULT_HOME


def need_home(h):
    if not os.path.isdir(os.path.join(h, "settings")):
        sys.exit(f"NOT_SET_UP home={h} (run: keremkit.py init [HOME])")
    return h


def deep_fill(target, defaults):
    """Add keys missing from target (keeps every user value)."""
    for k, v in defaults.items():
        if k not in target:
            target[k] = json.loads(json.dumps(v))
        elif isinstance(v, dict) and isinstance(target[k], dict):
            deep_fill(target[k], v)
    return target


# ---------------------------------------------------------------- init / where
def cmd_where(a):
    h = home_dir(a.home)
    ok = os.path.isdir(os.path.join(h, "settings"))
    print(f"{'READY' if ok else 'NOT_SET_UP'}\t{h}")


def cmd_init(a):
    h = os.path.abspath(a.path or a.home or home_dir())
    for d in ("settings", "library/items", "styles/_archive", "learning", "tools"):
        os.makedirs(os.path.join(h, d), exist_ok=True)
    prefs_p = os.path.join(h, "settings", "preferences.json")
    wjson(prefs_p, deep_fill(rjson(prefs_p, {}), DEFAULT_PREFS))
    cats_p = os.path.join(h, "settings", "categories.json")
    cats = rjson(cats_p) or {"categories": []}
    have = {c["key"] for c in cats["categories"]}
    cats["categories"] += [c for c in DEFAULT_CATEGORIES if c["key"] not in have]
    wjson(cats_p, cats)
    for c in cats["categories"]:
        if c["key"] != "edit-style":
            os.makedirs(os.path.join(h, "library", "items", c["key"]), exist_ok=True)
    cat_file = os.path.join(h, "library", "CATALOG.tsv")
    if not os.path.exists(cat_file):
        with open(cat_file, "w", encoding="utf-8", newline="\n") as f:
            f.write("\t".join(CATALOG_COLS) + "\n")
    for name, text in LEARNING_FILES.items():
        p = os.path.join(h, "learning", name)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    # copy the tools next to the data so they run on this computer
    here = os.path.dirname(os.path.abspath(__file__))
    for s in ("keremkit.py", "transcript.py", "cutlist.py", "subtitles.py", "tokens.py", "presets.py", "digest.py"):
        src = os.path.join(here, s)
        if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(os.path.join(h, "tools", s)):
            shutil.copy2(src, os.path.join(h, "tools", s))
    wjson(POINTER, {"home": h})
    print(f"OK home={h} pointer={POINTER}")


LEARNING_FILES = {
    "house-style.md": "# House Style\n\nShort, durable design rules the user stated (one line each, max ~60 lines).\n"
                      "Read before designing anything new. Style-specific rules belong in the style, not here.\n\n"
                      "## Typography\n\n## Color\n\n## Motion\n\n## Layout\n\n## Avoid\n",
    "known-issues.md": "# Known Issues\n\nOne entry per solved problem. Search by keyword; never read the whole file.\n"
                       "Format: `## [tags] title` then Symptom / Cause / Fix.\n\n"
                       "## [font, postscript, text] Font not applied\n- Symptom: text.set_style ignores the font.\n"
                       "- Cause: display name given; AE needs the PostScript name.\n- Fix: font.list / font.info, use e.g. Montserrat-Bold.\n\n"
                       "## [project.open, lost] Changes gone after opening another project\n- Symptom: last edits missing.\n"
                       "- Cause: project.open closes without saving.\n- Fix: always ae_save_project first.\n\n"
                       "## [duplicate, precomp, shared] Editing a duplicate changed the original\n"
                       "- Cause: comp.duplicate shares nested precomps.\n- Fix: keep parameters on top-level layers (CTRL_ null).\n\n"
                       "## [batch, id] New item id unknown inside the same batch\n"
                       "- Cause: ops in a batch cannot read earlier results.\n- Fix: get the id with comp.info at the end of batch A, use it in batch B.\n\n"
                       "## [json, sourceData, subtitles] Subtitle expression error 'footage not found'\n"
                       "- Cause: footage() name differs from the imported item name.\n- Fix: use the exact project item name (with extension).\n",
}


# ---------------------------------------------------------------- preferences
def prefs_path(h):
    return os.path.join(h, "settings", "preferences.json")


def get_key(d, key):
    for part in key.split(".") if key else []:
        if not isinstance(d, dict) or part not in d:
            return "__MISSING__"
        d = d[part]
    return d


def cmd_pref(a):
    h = need_home(home_dir(a.home))
    prefs = deep_fill(rjson(prefs_path(h), {}), DEFAULT_PREFS)
    if a.action == "get":
        v = get_key(prefs, a.args[0] if a.args else "")
        print("MISSING" if v == "__MISSING__" else json.dumps(v, ensure_ascii=False))
    elif a.action == "set":
        for pair in a.args:
            k, _, raw = pair.partition("=")
            try:
                val = json.loads(raw)
            except json.JSONDecodeError:
                val = raw
            node = prefs
            parts = k.split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = val
            print(f"OK {k}={json.dumps(val, ensure_ascii=False)}")
        wjson(prefs_path(h), prefs)
    elif a.action == "missing":
        root = get_key(prefs, a.args[0]) if a.args else prefs
        out = []

        def walk(d, p):
            for k, v in d.items():
                q = f"{p}.{k}" if p else k
                if v is None:
                    out.append(q)
                elif isinstance(v, dict):
                    walk(v, q)
        if isinstance(root, dict):
            walk(root, a.args[0] if a.args else "")
        print("\n".join(out) if out else "NONE")


# ---------------------------------------------------------------- categories
def categories(h):
    return rjson(os.path.join(h, "settings", "categories.json"), {"categories": DEFAULT_CATEGORIES})["categories"]


def cmd_cat(a):
    h = need_home(home_dir(a.home))
    cats = categories(h)
    if a.action == "list":
        for c in cats:
            print(f"{c['prefix']}\t{c['key']}\t{display(c)}\t{c.get('desc', '')}")
        return
    key, prefix = slug(a.key), a.prefix.upper()
    if not re.fullmatch(r"[A-Z0-9]{2,4}", prefix):
        sys.exit("ERROR: prefix must be 2-4 letters/digits, e.g. 3DO")
    clash = [c for c in cats if c["key"] == key or c["prefix"] == prefix]
    if clash:
        sys.exit(f"ERROR: key or prefix already used by {clash[0]['key']} ({clash[0]['prefix']})")
    cats.append({"key": key, "prefix": prefix, "name": a.name, "names": parse_local(a.local), "desc": a.desc or "",
                 "created": date.today().isoformat()})
    wjson(os.path.join(h, "settings", "categories.json"), {"categories": cats})
    os.makedirs(os.path.join(h, "library", "items", key), exist_ok=True)
    print(f"OK category {prefix} {key} ({display(cats[-1])})")


# ---------------------------------------------------------------- catalog
def catalog_path(h):
    return os.path.join(h, "library", "CATALOG.tsv")


def read_catalog(h):
    rows = []
    with open(catalog_path(h), encoding="utf-8") as f:
        head = f.readline().rstrip("\n").split("\t")
        for line in f:
            line = line.rstrip("\n")
            if line.strip():
                parts = line.split("\t")
                rows.append(dict(zip(head, parts + [""] * (len(head) - len(parts)))))
    return rows


def write_catalog(h, rows):
    tmp = catalog_path(h) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(CATALOG_COLS) + "\n")
        for r in sorted(rows, key=lambda x: x["id"]):
            f.write("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ") for c in CATALOG_COLS) + "\n")
    os.replace(tmp, catalog_path(h))


def cmd_search(a):
    h = need_home(home_dir(a.home))
    q = [w for w in norm(" ".join(a.words)).split() if w not in FILLER] or norm(" ".join(a.words)).split()
    hits = []
    for r in read_catalog(h):
        if a.type and r.get("type") != a.type:
            continue
        toks = r["search"].split()
        blob = " ".join(toks)
        score = matched = 0
        for w in q:
            if w == norm(r["id"]).replace(" ", "") or w in norm(r["id"]).split():
                score, matched = score + 6, matched + 1
            elif w in toks:
                score, matched = score + 3, matched + 1
            elif any(t.startswith(w) for t in toks):
                score, matched = score + 2, matched + 1
            elif len(w) >= 3 and w in blob:
                score, matched = score + 1, matched + 1
        if matched:
            if matched == len(q):
                score += 2 * matched
            if " ".join(q) in norm(r["name"] + " " + r["local_name"]):
                score += 4
            hits.append((score, r))
    hits.sort(key=lambda x: (-x[0], x[1]["id"]))
    if not hits:
        print("NO_MATCH")
        return
    for s, r in hits[:a.n]:
        label = r["name"] + (f" / {r['local_name']}" if r["local_name"] else "")
        print(f"{s}\t{r['id']}\t{r['type']}\t{label}\t{r['summary']}\t{os.path.join(h, r['folder'])}")


def cmd_new_id(a):
    h = need_home(home_dir(a.home))
    prefix = a.prefix.upper().rstrip("-")
    cats = {c["prefix"]: c["key"] for c in categories(h)}
    if prefix not in cats:
        sys.exit(f"ERROR: unknown prefix {prefix}. Known: {', '.join(cats)} (add one with: cat add)")
    top = 0
    for r in read_catalog(h):
        m = re.fullmatch(rf"{re.escape(prefix)}-(\d+)", r["id"])
        if m:
            top = max(top, int(m.group(1)))
    folder = os.path.join(h, "styles") if cats[prefix] == "edit-style" else os.path.join(h, "library", "items", cats[prefix])
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            m = re.match(rf"{re.escape(prefix)}-(\d+)", name)
            if m:
                top = max(top, int(m.group(1)))
            meta = rjson(os.path.join(folder, name, "style.json")) if cats[prefix] == "edit-style" else None
            if meta and re.fullmatch(rf"{re.escape(prefix)}-(\d+)", meta.get("id", "")):
                top = max(top, int(meta["id"].split("-")[1]))
    print(f"{prefix}-{top + 1:03d}")


def cmd_add(a):
    h = need_home(home_dir(a.home))
    meta = rjson(a.file)
    is_style = meta.get("kind") == "edit-style" or os.path.basename(a.file) == "style.json"
    name, local = meta_names(meta)
    need = ["id"] + ([] if is_style else ["category", "tags", "summary"])
    miss = [k for k in need if not meta.get(k)] + ([] if name else ["name"])
    if miss:
        sys.exit(f"ERROR: missing fields: {', '.join(miss)}")
    folder = os.path.relpath(os.path.dirname(os.path.abspath(a.file)), h).replace("\\", "/")
    parts = ([meta["id"], name, meta.get("category", "edit-style"), meta.get("summary", "")]
             + list(local.values()) + list((meta.get("summaries") or {}).values())
             + [meta.get(k, "") for k in meta if re.fullmatch(r"summary_[a-z]{2}", k)]
             + list(meta.get("tags", [])) + list(meta.get("aliases", [])))
    toks = []
    for p in parts:
        for t in norm(str(p)).split():
            if t not in FILLER and (len(t) > 1 or t.isdigit()) and t not in toks:
                toks.append(t)
    row = {"id": meta["id"], "type": "style" if is_style else "item",
           "category": "edit-style" if is_style else meta["category"], "name": name,
           "local_name": " / ".join(local.values()), "summary": meta.get("summary", ""),
           "folder": folder, "search": " ".join(toks)}
    rows = read_catalog(h)
    existed = any(r["id"] == meta["id"] for r in rows)
    write_catalog(h, [r for r in rows if r["id"] != meta["id"]] + [row])
    label = name + (f" / {row['local_name']}" if row["local_name"] else "")
    print(f"{'UPDATED' if existed else 'ADDED'}\t{meta['id']}\t{label}")


def cmd_style_archive(a):
    h = need_home(home_dir(a.home))
    cur = os.path.join(h, "styles", a.slug, "style.json")
    st = rjson(cur)
    if st is None:
        sys.exit(f"ERROR: {cur} not found")
    v = int(st.get("version", 1))
    dst = os.path.join(h, "styles", "_archive", a.slug, f"v{v:03d}")
    os.makedirs(dst, exist_ok=True)
    shutil.copy2(cur, os.path.join(dst, "style.json"))
    with open(os.path.join(dst, "CHANGE.txt"), "w", encoding="utf-8") as f:
        f.write(f"archived {date.today().isoformat()} (v{v} -> v{v + 1})\nreason: {a.reason}\n")
    st["version"] = v + 1
    st.setdefault("changelog", []).append({"version": v + 1, "date": date.today().isoformat(), "change": a.reason})
    wjson(cur, st)
    print(f"OK archived v{v:03d} -> now v{v + 1:03d} ({dst})")


def cmd_validate(a):
    h = need_home(home_dir(a.home))
    bad = 0
    for r in read_catalog(h):
        folder = os.path.join(h, r["folder"])
        meta_p = os.path.join(folder, "style.json" if r["type"] == "style" else "meta.json")
        meta = rjson(meta_p)
        if meta is None:
            print(f"MISSING_META\t{r['id']}\t{meta_p}")
            bad += 1
            continue
        f = meta.get("file")
        if f and not os.path.isfile(os.path.join(folder, f)):
            print(f"MISSING_FILE\t{r['id']}\t{f}")
            bad += 1
    print("OK" if not bad else f"PROBLEMS\t{bad}")


def cmd_summary(a):
    h = need_home(home_dir(a.home))
    count = {}
    for r in read_catalog(h):
        count[r["category"]] = count.get(r["category"], 0) + 1
    print(f"TOTAL\t{sum(count.values())}")
    for c in categories(h):
        if count.get(c["key"]):
            print(f"{c['key']}\t{count[c['key']]}")
    other = count.get("other", 0)
    if other >= 5:
        print(f"HINT\t{other} items in 'other' - consider suggesting a new category")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("where")
    i = sp.add_parser("init")
    i.add_argument("path", nargs="?")
    p = sp.add_parser("pref")
    p.add_argument("action", choices=["get", "set", "missing"])
    p.add_argument("args", nargs="*")
    c = sp.add_parser("cat")
    c.add_argument("action", choices=["list", "add"])
    c.add_argument("--key")
    c.add_argument("--prefix")
    c.add_argument("--name")
    c.add_argument("--local", nargs="*", help='translations, e.g. tr="3D Objeler"')
    c.add_argument("--desc")
    s = sp.add_parser("search")
    s.add_argument("words", nargs="+")
    s.add_argument("--type", choices=["item", "style"])
    s.add_argument("--n", type=int, default=5)
    n = sp.add_parser("new-id")
    n.add_argument("prefix")
    ad = sp.add_parser("add")
    ad.add_argument("file")
    sa = sp.add_parser("style-archive")
    sa.add_argument("slug")
    sa.add_argument("--reason", required=True)
    sp.add_parser("validate")
    sp.add_parser("summary")
    a = ap.parse_args()
    if a.cmd == "cat" and a.action == "add" and not all([a.key, a.prefix, a.name]):
        ap.error("cat add needs --key --prefix --name")
    {"where": cmd_where, "init": cmd_init, "pref": cmd_pref, "cat": cmd_cat, "search": cmd_search,
     "new-id": cmd_new_id, "add": cmd_add, "style-archive": cmd_style_archive,
     "validate": cmd_validate, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
