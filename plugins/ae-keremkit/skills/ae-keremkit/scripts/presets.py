#!/usr/bin/env python3
"""KeremKit preset learner - catalogue After Effects animation/effect presets (.ffx).

.ffx files are binary, so presets are learned by applying them to test layers in a
throw-away "lab" comp, exporting that comp once, and reading back what each preset
created: effects (and which need third-party plugins), keyframed properties with their
timing and easing, and expressions. The result is one small card per preset in the
KeremKit library, searchable like any other item.

  scan    DIR [DIR ...] -o scan.json             list .ffx files (recursive)
  plan    scan.json --batch N [--from I] [--lab NAME] -o batch.json
                                                 batch.run ops that build the lab layers
  learn   scan.json --export EXPORT.json [--errors ERR.json] [--lab NAME] [--home H]
                                                 write cards + catalog rows from the lab export
  show    ID_OR_NAME [--home H]                  compact card (effects, plugins, keyframes)
  insights [--home H]                            patterns across learned presets -> learning/presets-insights.md
"""
import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from datetime import date

LAB = "KK_PRESET_LAB"
CATEGORY, PREFIX = "fx-preset", "FXP"

# matchName prefixes that ship with After Effects
BUILT_IN = ("ADBE", "CC ", "APC ", "Keylight", "Mettle", "CS ", "ISL ", "Cineware", "Lumetri")
# matchName prefix -> vendor / product (third-party plugins)
VENDORS = [
    ("tc ", "Red Giant Trapcode"), ("RG Universe", "Red Giant Universe"), ("UNI.", "Red Giant Universe"),
    ("RG ", "Red Giant"), ("MBL", "Magic Bullet Looks"), ("Magic Bullet", "Magic Bullet"),
    ("VIDEOCOPILOT", "Video Copilot"), ("PEDG", "Deep Glow (Plugin Everything)"), ("Deep Glow", "Deep Glow"),
    ("BCC", "Boris FX Continuum"), ("S_", "Boris FX Sapphire"), ("Sapphire", "Boris FX Sapphire"),
    ("Twixtor", "RE:Vision Twixtor"), ("RSMB", "RE:Vision ReelSmart Motion Blur"), ("RE:Vision", "RE:Vision Effects"),
    ("REVisionFX", "RE:Vision Effects"), ("FilmConvert", "FilmConvert"), ("Neat Video", "Neat Video"),
    ("AEJuice", "AEJuice"), ("FXF", "FX Factory"), ("NewBlue", "NewBlue"), ("Mocha", "Boris FX Mocha"),
    ("ft", "Frischluft"), ("AK ", "Plugin Everything"), ("Signal", "Plugin Everything"), ("Plexus", "Rowbyte Plexus"),
    ("Stardust", "Superluminal Stardust"), ("Saber", "Video Copilot Saber"),
]
TEXTY = re.compile(r"text|type|typewriter|yazi|metin", re.I)
_TR = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
                     "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c"})


def norm(t):
    t = unicodedata.normalize("NFKD", (t or "").translate(_TR))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def rjson(p, default=None):
    if not p or not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def wjson(p, data):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def home_dir(override):
    if override:
        return os.path.abspath(override)
    ptr = rjson(os.path.join(os.path.expanduser("~"), ".keremkit.json"), {})
    return ptr.get("home") or os.path.join(os.path.expanduser("~"), "Documents", "KeremKit")


def plugin_of(match):
    if not match or match.startswith(BUILT_IN):
        return None
    for prefix, vendor in VENDORS:
        if match.startswith(prefix):
            return vendor
    return f"third-party ({match})"


# ---------------------------------------------------------------- scan / plan
def cmd_scan(a):
    items = []
    for root in a.dirs:
        for base, _, files in os.walk(root):
            for f in sorted(files):
                if f.lower().endswith(".ffx"):
                    p = os.path.join(base, f)
                    rel = os.path.relpath(p, root)
                    items.append({"name": os.path.splitext(f)[0], "path": os.path.abspath(p),
                                  "folder": os.path.dirname(rel).replace("\\", "/"),
                                  "kind": "text" if TEXTY.search(rel) else "solid"})
    for i, it in enumerate(items):
        it["lab_layer"] = f"FXP_{i + 1:04d}"
    wjson(a.output, {"lab": a.lab, "items": items})
    folders = Counter(it["folder"].split("/")[0] or "(root)" for it in items)
    print(f"OK presets={len(items)} text_presets={sum(it['kind'] == 'text' for it in items)} "
          f"folders={len(folders)} -> {a.output}")
    for f, n in folders.most_common(8):
        print(f"  {f}\t{n}")


def cmd_plan(a):
    scan = rjson(a.scan)
    lab = a.lab or scan.get("lab") or LAB
    part = scan["items"][a.start:a.start + a.batch]
    ops = []
    if a.start == 0:
        ops.append({"operation": "comp.create", "args": {"name": lab, "width": 1920, "height": 1080, "fps": 30, "duration": 10}})
    for it in part:
        if it["kind"] == "text":
            ops.append({"operation": "layer.create_text", "args": {"comp": lab, "text": "Preset", "name": it["lab_layer"]}})
        else:
            ops.append({"operation": "layer.create_solid", "args": {"comp": lab, "name": it["lab_layer"],
                                                                    "width": 400, "height": 400}})
        ops.append({"operation": "layer.apply_preset", "args": {"comp": lab, "layer": it["lab_layer"], "path": it["path"]}})
    wjson(a.output, {"ops": ops, "stopOnError": False})
    left = max(0, len(scan["items"]) - a.start - len(part))
    print(f"OK ops={len(ops)} presets={len(part)} next_from={a.start + len(part) if left else 'done'} -> {a.output}")


# ---------------------------------------------------------------- reading the export
def find_comp(node, name):
    if isinstance(node, dict):
        if node.get("name") == name and isinstance(node.get("layers"), list):
            return node
        for v in node.values():
            r = find_comp(v, name)
            if r:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_comp(v, name)
            if r:
                return r
    return None


KF_KEYS = ("keyframes", "keys", "kf")
EASE_KEYS = ("inTemporalEase", "outTemporalEase", "easeIn", "easeOut", "inEase", "outEase",
             "inInterpolationType", "outInterpolationType", "interpolation", "in", "out")


def rnd(v):
    if isinstance(v, (int, float)):
        return round(v, 3)
    if isinstance(v, list):
        return [rnd(x) for x in v[:4]]
    if isinstance(v, str):
        return v[:40]
    return v


def ease_word(k):
    blob = json.dumps({e: k.get(e) for e in EASE_KEYS if e in k}).lower()
    if "hold" in blob:
        return "hold"
    if "bezier" in blob or "influence" in blob or "speed" in blob or "ease" in blob:
        return "eased"
    if "linear" in blob:
        return "linear"
    return None


def read_layer(layer):
    effects, keyframes, expressions, animators = [], [], [], []

    def walk(n, path, in_effects):
        if isinstance(n, dict):
            name = n.get("name") or n.get("matchName")
            match = n.get("matchName")
            here = path + [name] if name else path
            eff_zone = in_effects or (match == "ADBE Effect Parade")
            if match and in_effects and match != "ADBE Effect Parade" and len(path) and path[-1] in ("__effects__",):
                effects.append({"name": n.get("name") or match, "matchName": match, "plugin": plugin_of(match)})
            if match == "ADBE Text Animator":
                animators.append(n.get("name") or "Animator")
            for k in KF_KEYS:
                kfs = n.get(k)
                if isinstance(kfs, list) and kfs and isinstance(kfs[0], dict) and ("time" in kfs[0] or "t" in kfs[0]):
                    times = [float(x.get("time", x.get("t", 0))) for x in kfs]
                    vals = [x.get("value", x.get("v")) for x in kfs]
                    eases = Counter(filter(None, (ease_word(x) for x in kfs)))
                    keyframes.append({"property": name or k, "path": " > ".join(p for p in here[-3:] if p),
                                      "count": len(kfs), "start": round(min(times), 3), "end": round(max(times), 3),
                                      "from": rnd(vals[0]), "to": rnd(vals[-1]),
                                      "easing": eases.most_common(1)[0][0] if eases else None})
                    break
            expr = n.get("expression")
            if isinstance(expr, str) and expr.strip() and n.get("expressionEnabled", True) is not False:
                expressions.append({"property": name or "?", "code": " ".join(expr.split())[:120]})
            for k, v in n.items():
                if k in KF_KEYS:
                    continue
                is_eff_list = k.lower() in ("effects", "effect", "adbe effect parade") or (
                    isinstance(v, (dict, list)) and match == "ADBE Effect Parade")
                walk(v, here + (["__effects__"] if is_eff_list else []), eff_zone or is_eff_list)
        elif isinstance(n, list):
            for v in n:
                walk(v, path, in_effects)

    walk(layer, [], False)
    # effects listed as plain objects directly in an "effects" list
    seen, uniq = set(), []
    for e in effects:
        key = (e["matchName"], e["name"])
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return uniq, keyframes, expressions, animators


# ---------------------------------------------------------------- learn
def catalog_add(home, meta, folder):
    cat = os.path.join(home, "library", "CATALOG.tsv")
    cols = ["id", "type", "category", "name", "local_name", "summary", "folder", "search"]
    rows = []
    if os.path.exists(cat):
        with open(cat, encoding="utf-8") as f:
            head = f.readline().rstrip("\n").split("\t")
            for line in f:
                if line.strip():
                    p = line.rstrip("\n").split("\t")
                    r = dict(zip(head, p + [""] * (len(head) - len(p))))
                    if "name" not in r:                       # 1.0 catalog columns
                        r["name"] = r.pop("name_en", "") or r.get("name_tr", "")
                        r["local_name"] = r.pop("name_tr", "")
                    rows.append(r)
    toks = []
    for p in [meta["id"], meta["name"], CATEGORY, "preset", "ffx", meta["summary"]] + meta["tags"]:
        for t in norm(str(p)).split():
            if (len(t) > 1 or t.isdigit()) and t not in toks:
                toks.append(t)
    row = {"id": meta["id"], "type": "item", "category": CATEGORY, "name": meta["name"], "local_name": "",
           "summary": meta["summary"], "folder": folder, "search": " ".join(toks)}
    rows = [r for r in rows if r["id"] != meta["id"]] + [row]
    with open(cat + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(cols) + "\n")
        for r in sorted(rows, key=lambda r: r["id"]):
            f.write("\t".join(str(r.get(c, "")).replace("\t", " ") for c in cols) + "\n")
    os.replace(cat + ".tmp", cat)


def existing_ids(home):
    known, top = {}, 0
    base = os.path.join(home, "library", "items", CATEGORY)
    if os.path.isdir(base):
        for d in os.listdir(base):
            m = rjson(os.path.join(base, d, "meta.json"))
            if m:
                known[m.get("source_path")] = (m["id"], d)
                top = max(top, int(m["id"].split("-")[1]))
    return known, top


def summary_line(effects, keyframes, plugins):
    parts = []
    if effects:
        parts.append(", ".join(e["name"] for e in effects[:4]) + (" +" + str(len(effects) - 4) if len(effects) > 4 else ""))
    if keyframes:
        props = sorted({k["property"] for k in keyframes})
        span = max(k["end"] for k in keyframes)
        parts.append(f"animates {', '.join(props[:4])} over {span:g}s")
    if plugins:
        parts.append("needs " + ", ".join(plugins))
    return "; ".join(parts) or "no effects or keyframes detected"


def cmd_learn(a):
    home = home_dir(a.home)
    if not os.path.isdir(os.path.join(home, "library")):
        sys.exit(f"NOT_SET_UP home={home} (run keremkit.py init)")
    scan = rjson(a.scan)
    lab = a.lab or scan.get("lab") or LAB
    export = rjson(a.export)
    comp = find_comp(export, lab)
    if comp is None:
        sys.exit(f"ERROR: comp '{lab}' not found in {a.export}")
    layers = {l.get("name"): l for l in comp["layers"] if isinstance(l, dict)}
    errors = rjson(a.errors, {}) or {}
    known, top = existing_ids(home)
    os.makedirs(os.path.join(home, "library", "items", CATEGORY), exist_ok=True)
    learned = failed = updated = 0
    vendors = Counter()
    for it in scan["items"]:
        layer = layers.get(it["lab_layer"])
        err = errors.get(it["lab_layer"]) or errors.get(it["name"])
        if layer is None and not err:
            continue  # not part of the batches that ran
        effects, keyframes, expressions, animators = read_layer(layer or {})
        plugins = sorted({e["plugin"] for e in effects if e["plugin"]})
        status = "ok"
        if err:
            status = "failed"
            if re.search(r"missing|not (found|installed)|plug-?in|effect.*unavailable", str(err), re.I):
                plugins = plugins or ["unknown plugin (preset could not be applied)"]
        elif not effects and not keyframes and not expressions:
            status = "empty"
        for p in plugins:
            vendors[p] += 1
        if it["path"] in known:
            pid, dname = known[it["path"]]
            updated += 1
        else:
            top += 1
            pid = f"{PREFIX}-{top:03d}"
            dname = f"{pid}_{norm(it['name']).replace(' ', '-')[:40] or 'preset'}"
            learned += 1
        folder = os.path.join(home, "library", "items", CATEGORY, dname)
        os.makedirs(folder, exist_ok=True)
        if os.path.exists(it["path"]):
            shutil.copy2(it["path"], os.path.join(folder, "preset.ffx"))
        name = it["name"] + (" [requires plugin]" if plugins else "")
        tags = ([it["folder"]] if it["folder"] else []) + [e["name"] for e in effects] + \
               [k["property"] for k in keyframes] + plugins + (["text animator"] if animators else [])
        meta = {
            "id": pid, "name": name, "preset_name": it["name"], "category": CATEGORY,
            "summary": summary_line(effects, keyframes, plugins), "tags": sorted(set(tags))[:30],
            "file": "preset.ffx", "source_path": it["path"], "source_folder": it["folder"],
            "applies_to": it["kind"], "status": status, "error": err,
            "requires_plugins": plugins, "effects": effects, "keyframes": keyframes,
            "expressions": expressions, "text_animators": animators,
            "duration_s": max([k["end"] for k in keyframes] or [0]),
            "learned": date.today().isoformat(), "version": 1,
        }
        if status == "failed":
            failed += 1
        wjson(os.path.join(folder, "meta.json"), meta)
        catalog_add(home, meta, os.path.relpath(folder, home).replace("\\", "/"))
    print(f"OK learned={learned} updated={updated} failed={failed} plugin_presets={sum(vendors.values())}")
    for v, n in vendors.most_common(8):
        print(f"  needs\t{v}\t{n}")


# ---------------------------------------------------------------- show / insights
def all_cards(home):
    base = os.path.join(home, "library", "items", CATEGORY)
    if not os.path.isdir(base):
        return []
    return [m for d in sorted(os.listdir(base)) for m in [rjson(os.path.join(base, d, "meta.json"))] if m]


def cmd_show(a):
    home = home_dir(a.home)
    q = norm(a.query)
    cards = all_cards(home)
    hit = next((c for c in cards if c["id"].lower() == a.query.lower()), None) or \
        next((c for c in cards if norm(c["preset_name"]) == q), None) or \
        next((c for c in cards if q in norm(c["preset_name"])), None)
    if not hit:
        print("NO_MATCH")
        return
    print(f"{hit['id']}\t{hit['name']}\tstatus={hit['status']}\tapplies_to={hit['applies_to']}\tduration={hit['duration_s']}s")
    if hit["requires_plugins"]:
        print(f"REQUIRES\t{', '.join(hit['requires_plugins'])}")
    for e in hit["effects"]:
        print(f"EFFECT\t{e['name']}\t{e['matchName']}" + (f"\t[{e['plugin']}]" if e["plugin"] else ""))
    for k in hit["keyframes"]:
        print(f"KEYS\t{k['path'] or k['property']}\t{k['count']} keys {k['start']}-{k['end']}s\t"
              f"{json.dumps(k['from'])} -> {json.dumps(k['to'])}\t{k['easing'] or ''}")
    for x in hit["expressions"]:
        print(f"EXPR\t{x['property']}\t{x['code']}")
    if hit.get("text_animators"):
        print(f"TEXT_ANIMATORS\t{', '.join(hit['text_animators'])}")
    if hit.get("error"):
        print(f"ERROR\t{hit['error']}")


def cmd_insights(a):
    home = home_dir(a.home)
    cards = [c for c in all_cards(home) if c["status"] != "failed"]
    if not cards:
        print("NO_PRESETS")
        return
    eff = Counter(e["name"] for c in cards for e in c["effects"])
    props = Counter(k["property"] for c in cards for k in c["keyframes"])
    durs = sorted(c["duration_s"] for c in cards if c["duration_s"])
    eases = Counter(k["easing"] for c in cards for k in c["keyframes"] if k["easing"])
    plug = Counter(p for c in all_cards(home) for p in c["requires_plugins"])
    med = durs[len(durs) // 2] if durs else 0
    lines = ["# Preset insights", "",
             f"Learned from {len(cards)} presets on {date.today().isoformat()}. Regenerate with `presets.py insights`.", "",
             f"- Most used effects: {', '.join(f'{k} ({v})' for k, v in eff.most_common(8)) or '-'}",
             f"- Most animated properties: {', '.join(f'{k} ({v})' for k, v in props.most_common(8)) or '-'}",
             f"- Typical animation length: median {med:g}s, range {durs[0] if durs else 0:g}-{durs[-1] if durs else 0:g}s",
             f"- Keyframe interpolation: {', '.join(f'{k} ({v})' for k, v in eases.most_common()) or '-'}",
             f"- Plugins the user's presets rely on: {', '.join(f'{k} ({v})' for k, v in plug.most_common()) or 'none'}", ""]
    path = os.path.join(home, "learning", "presets-insights.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[4:9]))
    print(f"-> {path}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("scan")
    s.add_argument("dirs", nargs="+")
    s.add_argument("--lab", default=LAB)
    s.add_argument("-o", "--output", required=True)
    p = sp.add_parser("plan")
    p.add_argument("scan")
    p.add_argument("--batch", type=int, default=30)
    p.add_argument("--from", dest="start", type=int, default=0)
    p.add_argument("--lab")
    p.add_argument("-o", "--output", required=True)
    le = sp.add_parser("learn")
    le.add_argument("scan")
    le.add_argument("--export", required=True)
    le.add_argument("--errors")
    le.add_argument("--lab")
    sh = sp.add_parser("show")
    sh.add_argument("query")
    sp.add_parser("insights")
    a = ap.parse_args()
    {"scan": cmd_scan, "plan": cmd_plan, "learn": cmd_learn, "show": cmd_show, "insights": cmd_insights}[a.cmd](a)


if __name__ == "__main__":
    main()
