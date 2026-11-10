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
  plan     "PART: words" ["PART: words" ...] [--n 2]   library hits for every part of a design at once
  new-id   PREFIX                         next free id, e.g. UI -> UI-008
  add      META_OR_STYLE.json             add/update a catalog row (library item or style)
  style-archive SLUG --reason "..."       snapshot styles/SLUG/style.json into the archive
  validate                                check catalog rows point at real files
  reindex                                 rebuild CATALOG.tsv from all meta.json / style.json files
  doctor                                  check Python, ffmpeg, Whisper, home folder, tool versions
  pack   [--items ID ...] [--styles SLUG ...] [--all] -o share.zip   package styles/items to share
  unpack share.zip                        import a package (ids renumbered on clashes; fonts/plugins listed)
  summary                                 counts per category
  version                                 the kit version of this copy (compare with the skill's)
  stat     PATH [PATH ...]                size, modified time and short hash - proof a save really happened
  safe-copy SRC DST [--overwrite]         shell copy of a project before anything destructive (verified)
  save-prep PROJECT WORK [--items DIR ...]  one step before a library save: note the project, copy it to WORK,
                                          create the item folders
  save-check WORK [--items ITEM.aep ...]  one step after: the project is unchanged, every item.aep was written
  add-many ITEMS.tsv                      create item folders + meta.json + catalog rows from one table

All commands except `where`/`init` use the home from the pointer file; pass --home to override.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import date

KIT_VERSION = "1.8.1"
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
    {"key": "project", "prefix": "PRJ", "name": "Projects", "desc": "whole projects saved as reusable templates (all comps, footage, audio)"},
    {"key": "technique", "prefix": "TEC", "name": "Techniques", "desc": "editing techniques (cuts, motion, audio, formats, QC, organisation) - see techniques.py"},
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
    "organize": {
        "mode": "auto",        # auto | ask | off - tidy layers after each edit
        "order": ["ADJ", "SUB", "TXT", "UI", "ICN", "SHP", "CTRL", "NULL", "CAM", "LGT", "FTG", "BG", "AUD", "SFX"],
        "labels": {"ADJ": 5, "SUB": 1, "TXT": 2, "UI": 11, "ICN": 11, "SHP": 6, "CTRL": 0, "NULL": 0, "CAM": 14,
                   "LGT": 14, "FTG": 8, "BG": 12, "AUD": 9, "SFX": 10, "MATTE": 15, "PRE": 3, "LIB": 13},
        "folders": True,
    },
    "audio": {"chain": None, "target_lufs": -14, "music_db": -18},
    "formats": {"targets": None},
    "qc": {"mode": "ask"},
    "publish": {"chapters": None, "thumbnails": None},
    "design_import": {"preview": None},
    "library": {"preview_repair": None},
    "design": {"plan": "big"},
    "logos": {"confirm": "ask"},            # ask | off - add logos of named brands without asking
    "assets": {"allow_attribution": False},  # also list free items that need a credit (CC BY)              # always | big (several parts) | off - plan and ask before designing   # ask | never - offer to re-render broken previews
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
    for d in ("settings", "library/items", "styles/_archive", "learning", "tools", "extensions"):
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
    if os.path.exists(cat_file):
        with open(cat_file, encoding="utf-8") as f:
            old = "name_en" in f.readline()
        if old:
            write_catalog(h, read_catalog(h))   # migrate 1.0 columns
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
    for s in TOOLS:
        src = os.path.join(here, s) if os.path.exists(os.path.join(here, s)) else os.path.join(here, "..", "assets", s)
        if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(os.path.join(h, "tools", s)):
            shutil.copy2(src, os.path.join(h, "tools", s))
    wjson(POINTER, {"home": h})
    print(f"OK home={h} pointer={POINTER}")


TOOLS = ("keremkit.py", "transcript.py", "cutlist.py", "subtitles.py", "editplan.py", "audio.py", "sfx.py", "qc.py",
         "techniques.py", "tokens.py", "presets.py", "videoref.py", "previews.py", "assets.py", "digest.py", "techniques.json")

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
                       "## [ae, parallel, dialog] 'second script while another script was already running'\n"
                       "- Cause: two AE calls sent at the same time.\n- Fix: one AE call at a time; instance.dismiss_dialog, retry.\n\n"
                       "## [rename, project.rename] Some names were not changed\n"
                       "- Cause: project.rename with a map can skip names in big batches.\n- Fix: recheck counts, fix the rest with item.set_props by id.\n\n"
                       "## [reduce, project.open, save, undo, lost] Never reduce the user's project\n"
                       "- Symptom: a library save overwrote the user's project with a reduced copy.\n"
                       "- Cause: project.reduce ran on the open original; Save As reported saved:true without writing; "
                       "undo did not restore the reduce; project.open then wrote over the file.\n"
                       "- Fix: safe-copy the .aep first, open the copy, check project.file; stat after every save; "
                       "reopen the work copy instead of undo. Unexpected state -> stop and ask.\n\n"
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
                if not isinstance(node.get(p), dict):
                    node[p] = {}              # create (or replace a null) parent on the way down
                node = node[p]
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
                rows.append(migrate_row(dict(zip(head, parts + [""] * (len(head) - len(parts))))))
    return rows


def migrate_row(r):
    """Catalogs written by 1.0 used name_tr / name_en columns; map them to name / local_name."""
    if "name" not in r:
        r["name"] = r.pop("name_en", "") or r.get("name_tr", "")
        r["local_name"] = r.pop("name_tr", "")
    for c in CATALOG_COLS:                       # hand-edited catalogs may miss columns
        r.setdefault(c, "")
    if not r["type"]:
        r["type"] = "style" if r["category"] == "edit-style" or r["id"].startswith("STY-") else "item"
    if not r["search"]:
        r["search"] = norm(" ".join([r["id"], r["name"], r["local_name"], r["category"], r["summary"]]))
    return r


def write_catalog(h, rows):
    tmp = catalog_path(h) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(CATALOG_COLS) + "\n")
        for r in sorted(rows, key=lambda x: x["id"]):
            f.write("\t".join(str(r.get(c, "")).replace("\t", " ").replace("\n", " ") for c in CATALOG_COLS) + "\n")
    os.replace(tmp, catalog_path(h))


def find(h, words, kind=None, rows=None):
    """Score catalog rows against the words -> [(score, matched_all, row)], best first."""
    q = [w for w in norm(" ".join(words)).split() if w not in FILLER] or norm(" ".join(words)).split()
    hits = []
    for r in rows if rows is not None else read_catalog(h):
        if kind and r.get("type") != kind:
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
            hits.append((score, matched == len(q), r))
    hits.sort(key=lambda x: (-x[0], x[2]["id"]))
    return hits


def cmd_search(a):
    h = need_home(home_dir(a.home))
    hits = [(s, r) for s, _, r in find(h, a.words, a.type)]
    if not hits:
        print("NO_MATCH")
        return
    for s, r in hits[:a.n]:
        label = r["name"] + (f" / {r['local_name']}" if r["local_name"] else "")
        print(f"{s}\t{r['id']}\t{r['type']}\t{label}\t{r['summary']}\t{os.path.join(h, r['folder'])}")


def cmd_plan(a):
    """One search per part of a design: what the library already has for each."""
    h = need_home(home_dir(a.home))
    rows = read_catalog(h)
    for n, part in enumerate(a.parts, 1):
        label, _, words = part.partition(":")
        words = words.strip() or label
        hits = find(h, words.split(), "item", rows)[:a.n]
        print(f"PART {n}\t{label.strip()}\t{len(hits)} hit(s)")
        for score, full, r in hits:
            prev = os.path.join(h, r["folder"], "preview.png")
            pv = "" if os.path.isfile(prev) and os.path.getsize(prev) >= 20000 else "\tpreview: check"
            name = r["name"] + (f" / {r['local_name']}" if r["local_name"] else "")
            print(f"  {'good' if full else 'partial'}\t{score}\t{r['id']}\t{name}\t{r['summary']}{pv}")


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
    if not os.path.isfile(a.file):
        sys.exit(f"ERROR: file not found: {a.file}")
    try:
        meta = rjson(a.file)
    except ValueError as e:
        sys.exit(f"ERROR: {a.file} is not valid JSON: {e}")
    if not isinstance(meta, dict):
        sys.exit(f"ERROR: {a.file} must contain a JSON object")
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


def cmd_reindex(a):
    """Rebuild CATALOG.tsv from every meta.json / style.json on disk."""
    h = need_home(home_dir(a.home))
    keep_paths = []
    for base, dirs, files in os.walk(os.path.join(h, "library", "items")):
        if "meta.json" in files:
            keep_paths.append(os.path.join(base, "meta.json"))
            dirs[:] = []
    for base, dirs, files in os.walk(os.path.join(h, "styles")):
        dirs[:] = [d for d in dirs if d != "_archive"]
        if "style.json" in files:
            keep_paths.append(os.path.join(base, "style.json"))
    write_catalog(h, [])
    ok = bad = 0
    for p in sorted(keep_paths):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--home", h, "add", p],
                           capture_output=True, text=True)
        if r.returncode == 0:
            ok += 1
        else:
            bad += 1
            print(f"SKIPPED\t{os.path.relpath(p, h)}\t{(r.stderr or r.stdout).strip().splitlines()[-1]}")
    print(f"OK reindexed={ok} skipped={bad}")


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


def cmd_doctor(a):
    import platform
    import hashlib
    import subprocess as sp_
    ok = lambda k, v: print(f"OK\t{k}\t{v}")
    warn = lambda k, v: print(f"WARN\t{k}\t{v}")
    ok("python", platform.python_version()) if sys.version_info >= (3, 9) else warn("python", platform.python_version() + " (3.9+ needed)")
    h = home_dir(a.home)
    if os.path.isdir(os.path.join(h, "settings")):
        ok("home", h)
    else:
        warn("home", f"{h} not set up - run init")
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            v = sp_.run([tool, "-version"], capture_output=True, text=True).stdout.split("\n")[0][:60]
            ok(tool, v)
        else:
            warn(tool, "not found (needed for cutting, audio, QC)")
    found = []
    if shutil.which("whisper"):
        found.append("openai-whisper (cli)")
    for mod, label in (("whisper", "openai-whisper"), ("faster_whisper", "faster-whisper")):
        r = sp_.run([sys.executable, "-c", f"import {mod}"], capture_output=True)
        if r.returncode == 0:
            found.append(label)
    if shutil.which("whisper-cli"):
        found.append("whisper.cpp")
    ok("whisper", ", ".join(sorted(set(found)))) if found else warn("whisper", "not found (needed for transcripts and subtitles)")
    here = os.path.dirname(os.path.abspath(__file__))
    tools = os.path.join(h, "tools")
    if os.path.isdir(tools) and os.path.abspath(tools) != here:
        stale = []
        for t in TOOLS:
            src = os.path.join(here, t) if os.path.exists(os.path.join(here, t)) else os.path.join(here, "..", "assets", t)
            dst = os.path.join(tools, t)
            if os.path.exists(src):
                if not os.path.exists(dst) or hashlib.md5(open(src, "rb").read()).digest() != hashlib.md5(open(dst, "rb").read()).digest():
                    stale.append(t)
        warn("tools", "differ from the skill: " + ", ".join(stale) + " - update only if the user asks") if stale else ok("tools", "up to date")
        own = sorted(f for f in os.listdir(tools) if f not in TOOLS and f.endswith(".py"))
        if own:
            warn("tools", "not kit files: " + ", ".join(own) + " - user tools belong in extensions/<id>/")
    ext = os.path.join(h, "extensions")
    if os.path.isdir(ext):
        names = sorted(d for d in os.listdir(ext) if os.path.isdir(os.path.join(ext, d)))
        ok("extensions", ", ".join(names) if names else "none")
    if os.path.isdir(os.path.join(h, "settings")):
        prefs = deep_fill(rjson(prefs_path(h), {}), DEFAULT_PREFS)
        n = 0

        def walk(d):
            nonlocal n
            for v in d.values():
                if v is None:
                    n += 1
                elif isinstance(v, dict):
                    walk(v)
        walk(prefs)
        ok("preferences", f"{n} not answered yet (asked when needed)")
    print("NOTE\tAfter Effects: Claude checks the MCP connection with ae_context")


def cmd_version(a):
    print(f"KeremKit {KIT_VERSION}")


def file_stat(path):
    import hashlib
    from datetime import datetime
    st = os.stat(path)
    with open(path, "rb") as f:
        digest = hashlib.md5(f.read()).hexdigest()[:10]
    return st.st_size, datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"), digest


def cmd_stat(a):
    bad = False
    for p in a.paths:
        if os.path.isfile(p):
            size, mtime, digest = file_stat(p)
            print(f"OK\t{p}\t{size} B\t{mtime}\t{digest}")
        else:
            bad = True
            print(f"MISSING\t{p}")
    if bad:
        sys.exit(1)


def cmd_safe_copy(a):
    src, dst = os.path.abspath(a.src), os.path.abspath(a.dst)
    if not os.path.isfile(src):
        sys.exit(f"ERROR: not found: {src}")
    if os.path.normcase(src) == os.path.normcase(dst):
        sys.exit("ERROR: source and destination are the same file")
    if os.path.exists(dst) and not a.overwrite:
        sys.exit(f"ERROR: {dst} exists - pick a new name (or --overwrite for your own work copy)")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    s1, d1 = file_stat(src), file_stat(dst)
    if s1[0] != d1[0] or s1[2] != d1[2]:
        sys.exit(f"ERROR: copy does not match the source ({d1[0]} vs {s1[0]} B)")
    print(f"OK\t{dst}\t{d1[0]} B\t{d1[1]}\tsource untouched: {src}")


def cmd_save_prep(a):
    import time
    src, work = os.path.abspath(a.project), os.path.abspath(a.work)
    if not os.path.isfile(src):
        sys.exit(f"ERROR: project not found: {src} - save it first")
    if os.path.normcase(src) == os.path.normcase(work):
        sys.exit("ERROR: the work copy must be a different file")
    os.makedirs(os.path.dirname(work), exist_ok=True)
    shutil.copy2(src, work)
    size, mtime, digest = file_stat(src)
    if file_stat(work)[2] != digest:
        sys.exit("ERROR: work copy does not match the project")
    for d in a.items or []:
        os.makedirs(d, exist_ok=True)
    wjson(work + ".state.json", {"project": src, "size": size, "mtime": mtime, "digest": digest,
                                 "prepared": time.time() - 2})
    print(f"OK\tproject {os.path.basename(src)} {size} B noted\twork copy {work}\t{len(a.items or [])} item folder(s) ready")


def cmd_save_check(a):
    work = os.path.abspath(a.work)
    st = rjson(work + ".state.json")
    if not st:
        sys.exit(f"ERROR: no save-prep state next to {work}")
    problems = []
    if not os.path.isfile(st["project"]):
        problems.append(f"PROJECT MISSING\t{st['project']}")
    else:
        size, _, digest = file_stat(st["project"])
        if digest != st["digest"]:
            problems.append(f"PROJECT CHANGED\t{st['project']}\t{st['size']} -> {size} B")
    for p in a.items or []:
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            problems.append(f"NOT WRITTEN\t{p}")
        elif os.path.getmtime(p) < st["prepared"]:
            problems.append(f"OLD FILE\t{p}\t(not saved in this run)")
    for line in problems:
        print(line)
    if problems:
        sys.exit(1)
    print(f"OK\tproject unchanged\t{len(a.items or [])} item file(s) written")


def cmd_add_many(a):
    """Rows: id category name local tags summary comp size fps duration [pack original_comp fonts footage usage_note]."""
    h = need_home(home_dir(a.home))
    lang = (deep_fill(rjson(prefs_path(h), {}), DEFAULT_PREFS)["language"].get("library") or "tr")
    with open(a.file, encoding="utf-8") as f:
        lines = [ln.rstrip("\n\r") for ln in f if ln.strip() and not ln.startswith("#")]
    head = lines[0].split("\t")
    need = ["id", "category", "name", "tags", "summary", "comp", "size", "fps", "duration"]
    miss = [k for k in need if k not in head]
    if miss:
        sys.exit(f"ERROR: header misses: {', '.join(miss)}")
    done = 0
    for n, ln in enumerate(lines[1:], 2):
        row = dict(zip(head, ln.split("\t")))
        bad = [k for k in need if not row.get(k, "").strip()]
        if bad:
            print(f"SKIP\tline {n}\tmissing {', '.join(bad)}")
            continue
        cat = row["category"].strip()
        folder = os.path.join(h, "library", "items", cat, f"{row['id'].strip()}_{slug(row['name'])}")
        os.makedirs(folder, exist_ok=True)
        mp = os.path.join(folder, "meta.json")
        meta = rjson(mp, {}) or {}
        w, _, hgt = row["size"].lower().partition("x")
        meta.update({
            "id": row["id"].strip(), "name": row["name"].strip(), "category": cat,
            "tags": [t.strip() for t in row["tags"].split(",") if t.strip()],
            "summary": row["summary"].strip(), "comp": row["comp"].strip(), "file": "item.aep",
            "preview": meta.get("preview", "preview.png"), "size": [int(w), int(hgt)],
            "fps": float(row["fps"]), "duration": float(row["duration"]),
        })
        if row.get("local", "").strip():
            meta["names"] = {lang: row["local"].strip()}
        meta.setdefault("params", [])
        deps = meta.setdefault("deps", {"fonts": [], "plugins": [], "footage": []})
        for k in ("fonts", "footage"):
            if row.get(k, "").strip():
                deps[k] = [x.strip() for x in row[k].split(",") if x.strip()]
        if row.get("pack", "").strip():
            meta["source"] = {"pack": row["pack"].strip(), "original_comp": row.get("original_comp", "").strip()}
        if row.get("usage_note", "").strip():
            meta["usage_note"] = row["usage_note"].strip()
        meta.setdefault("created", date.today().isoformat())
        meta.setdefault("version", 1)
        meta.setdefault("changes", [])
        wjson(mp, meta)
        r_ = subprocess.run([sys.executable, os.path.abspath(__file__), "--home", h, "add", mp], capture_output=True, text=True)
        if r_.returncode:
            print(f"ERROR\t{row['id']}\t{(r_.stderr or r_.stdout).strip()}")
            continue
        done += 1
    print(f"OK\t{done} item(s) written\t(folders, meta.json, catalog)")


def inside(home, rel):
    """True when rel (a catalog/manifest folder) stays inside home."""
    if not rel or os.path.isabs(rel) or re.match(r"^[A-Za-z]:", rel) or ".." in rel.replace("\\", "/").split("/"):
        return False
    full = os.path.realpath(os.path.join(home, rel))
    return os.path.commonpath([full, os.path.realpath(home)]) == os.path.realpath(home)


ID_RE = re.compile(r"^[A-Z0-9]{2,4}-\d{3,}$")


def safe_members(z):
    for m in z.namelist():
        if m.startswith("/") or ".." in m.replace("\\", "/").split("/"):
            sys.exit(f"ERROR: unsafe path in package: {m}")
    return z.namelist()


def cmd_pack(a):
    import zipfile
    h = need_home(home_dir(a.home))
    rows = read_catalog(h)
    want = set(a.items or [])
    styles = set(a.styles or [])
    if a.all:
        want = {r["id"] for r in rows if r["type"] == "item"}
        styles = {os.path.basename(r["folder"]) for r in rows if r["type"] == "style"}
    picked = [r for r in rows if r["id"] in want] + [r for r in rows if r["type"] == "style" and os.path.basename(r["folder"]) in styles]
    outside = [r["id"] for r in picked if not inside(h, r["folder"])]
    if outside:
        sys.exit(f"ERROR: catalog rows point outside the KeremKit folder: {outside[:5]}")
    if not picked:
        sys.exit("ERROR: nothing selected (use --items, --styles or --all)")
    fonts, plugins = set(), set()
    with zipfile.ZipFile(a.output, "w", zipfile.ZIP_DEFLATED) as z:
        for r in picked:
            folder = os.path.join(h, r["folder"])
            for base, _, files in os.walk(folder):
                for f in files:
                    full = os.path.join(base, f)
                    z.write(full, os.path.relpath(full, h).replace("\\", "/"))
            meta = rjson(os.path.join(folder, "style.json" if r["type"] == "style" else "meta.json"), {})
            fonts.update((meta.get("deps") or {}).get("fonts", []))
            fonts.update(f.get("font") for f in (meta.get("look") or {}).get("fonts", []) if isinstance(f, dict) and f.get("font"))
            plugins.update(meta.get("requires_plugins") or [])
            plugins.update((meta.get("deps") or {}).get("plugins", []))
        for extra in ("settings/categories.json", "settings/techniques.json") + (("learning/house-style.md",) if a.house_style else ()):
            if os.path.exists(os.path.join(h, extra)):
                z.write(os.path.join(h, extra), "shared/" + extra)
        manifest = {"kit": "keremkit", "created": date.today().isoformat(),
                    "rows": picked, "fonts": sorted(f for f in fonts if f), "plugins": sorted(plugins)}
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"OK packed items={sum(r['type'] == 'item' for r in picked)} styles={sum(r['type'] == 'style' for r in picked)} "
          f"fonts={len(manifest['fonts'])} plugins={len(manifest['plugins'])} -> {a.output}")


def cmd_unpack(a):
    import zipfile
    h = need_home(home_dir(a.home))
    with zipfile.ZipFile(a.file) as z:
        safe_members(z)
        man = json.loads(z.read("manifest.json"))
        bad = [r.get("folder") for r in man.get("rows", [])
               if not inside(h, str(r.get("folder", ""))) or not str(r.get("folder", "")).replace("\\", "/").startswith(("library/", "styles/"))
               or not ID_RE.match(str(r.get("id", "")))]
        if bad:
            sys.exit(f"ERROR: package rejected - unsafe or invalid entries in manifest.json: {bad[:3]}")
        rows = read_catalog(h)
        have = {r["id"]: r for r in rows}
        cats = categories(h)
        known_prefix = {c["prefix"] for c in cats}
        added, renamed = 0, 0
        for r in man["rows"]:
            src_folder = r["folder"].rstrip("/")
            new_id, new_folder = r["id"], src_folder
            if r["id"] in have and have[r["id"]]["folder"] != src_folder:
                prefix = r["id"].split("-")[0]
                top = max([int(x.split("-")[1]) for x in have if x.startswith(prefix + "-")] + [0])
                new_id = f"{prefix}-{top + 1:03d}"
                new_folder = src_folder.replace(r["id"], new_id) if r["id"] in src_folder else src_folder + "-" + new_id
                renamed += 1
            for m in z.namelist():
                if m == src_folder or m.startswith(src_folder + "/"):
                    dst = os.path.join(h, new_folder + m[len(src_folder):])
                    if m.endswith("/"):
                        continue
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "wb") as f:
                        f.write(z.read(m))
            meta_name = "style.json" if r["type"] == "style" else "meta.json"
            mp = os.path.join(h, new_folder, meta_name)
            meta = rjson(mp, {})
            meta["id"] = new_id
            wjson(mp, meta)
            row = dict(r, id=new_id, folder=new_folder)
            rows = [x for x in rows if x["id"] != new_id] + [row]
            have[new_id] = row
            added += 1
            if new_id.split("-")[0] not in known_prefix and r.get("category"):
                cats.append({"key": r["category"], "prefix": new_id.split("-")[0], "name": r["category"].title(), "desc": "imported"})
                known_prefix.add(new_id.split("-")[0])
        write_catalog(h, rows)
        wjson(os.path.join(h, "settings", "categories.json"), {"categories": cats})
        if "shared/settings/techniques.json" in z.namelist():
            mine = rjson(os.path.join(h, "settings", "techniques.json"), {"groups": {}, "techniques": []})
            theirs = json.loads(z.read("shared/settings/techniques.json"))
            ids = {t["id"] for t in mine.get("techniques", [])}
            mine.setdefault("techniques", []).extend(t for t in theirs.get("techniques", []) if t["id"] not in ids)
            mine.setdefault("groups", {}).update({k: v for k, v in theirs.get("groups", {}).items() if k not in mine["groups"]})
            wjson(os.path.join(h, "settings", "techniques.json"), mine)
    print(f"OK imported={added} renamed_ids={renamed}")
    if man.get("fonts"):
        print("FONTS_NEEDED\t" + ", ".join(man["fonts"]))
    if man.get("plugins"):
        print("PLUGINS_NEEDED\t" + ", ".join(man["plugins"]))


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
    pl = sp.add_parser("plan")
    pl.add_argument("parts", nargs="+", help='"intro: animated title" "counter: gold subscriber count"')
    pl.add_argument("--n", type=int, default=2)
    n = sp.add_parser("new-id")
    n.add_argument("prefix")
    ad = sp.add_parser("add")
    ad.add_argument("file")
    sa = sp.add_parser("style-archive")
    sa.add_argument("slug")
    sa.add_argument("--reason", required=True)
    sp.add_parser("validate")
    sp.add_parser("reindex")
    sp.add_parser("doctor")
    pk = sp.add_parser("pack")
    pk.add_argument("--items", nargs="*")
    pk.add_argument("--styles", nargs="*", help="style folder names (slugs)")
    pk.add_argument("--all", action="store_true")
    pk.add_argument("--house-style", action="store_true")
    pk.add_argument("-o", "--output", required=True)
    up = sp.add_parser("unpack")
    up.add_argument("file")
    sp.add_parser("summary")
    sp.add_parser("version")
    st = sp.add_parser("stat")
    st.add_argument("paths", nargs="+")
    spp = sp.add_parser("save-prep")
    spp.add_argument("project")
    spp.add_argument("work")
    spp.add_argument("--items", nargs="*")
    scc = sp.add_parser("save-check")
    scc.add_argument("work")
    scc.add_argument("--items", nargs="*")
    am = sp.add_parser("add-many")
    am.add_argument("file")
    sc = sp.add_parser("safe-copy")
    sc.add_argument("src")
    sc.add_argument("dst")
    sc.add_argument("--overwrite", action="store_true")
    a = ap.parse_args()
    if a.cmd == "cat" and a.action == "add" and not all([a.key, a.prefix, a.name]):
        ap.error("cat add needs --key --prefix --name")
    {"where": cmd_where, "init": cmd_init, "pref": cmd_pref, "cat": cmd_cat, "search": cmd_search,
     "new-id": cmd_new_id, "plan": cmd_plan, "add": cmd_add, "style-archive": cmd_style_archive,
     "validate": cmd_validate, "reindex": cmd_reindex, "summary": cmd_summary, "doctor": cmd_doctor, "pack": cmd_pack,
     "unpack": cmd_unpack, "version": cmd_version, "stat": cmd_stat, "safe-copy": cmd_safe_copy, "save-prep": cmd_save_prep,
     "save-check": cmd_save_check, "add-many": cmd_add_many}[a.cmd](a)


if __name__ == "__main__":
    main()
