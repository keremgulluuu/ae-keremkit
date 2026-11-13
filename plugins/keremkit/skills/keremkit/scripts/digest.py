#!/usr/bin/env python3
"""KeremKit project digest - turn a large After Effects project export into a short summary.

Used to learn or update an edit style from a finished project without reading the whole
project into the conversation. Input: the JSON written by ae_project_export_json(outPath=...).
The walker is schema-tolerant: it looks for fonts, colors, effect names, layer-name
prefixes, texts, comps and durations wherever they appear.

  python digest.py PROJECT.json [--comp NAME] [--texts 12]
  python digest.py PROJECT.json --comp NAME --deep [--params REGEX] [--noaudio]
      every layer: in/out, parent, 3D; keyed properties as +t=value[ease] relative to the in-point; expressions
      verbatim; effect names. --params adds static values only for matching layers. Ends with a GAPS line
      (what the export never contains).
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

PREFIX = re.compile(r"^([A-Z]{2,5})_")
SKIP_MATCH = re.compile(r"^ADBE (Transform Group|Root Vectors Group|Vector|Text Properties|Effect Parade|"
                        r"Mask Parade|Marker|Time Remapping|Layer Styles|Plane Options|Audio Group|Material Options|"
                        r"Extrsn|Light Options|Camera Options|Text Document|Text Path|Text More Options|Text Animators)")


def hexcol(v):
    try:
        r, g, b = [max(0, min(1, float(x))) for x in v[:3]]
    except (TypeError, ValueError):
        return None
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def walk(node, acc, key=""):
    if isinstance(node, dict):
        name = node.get("name")
        if isinstance(name, str) and isinstance(node.get("layers"), list):
            acc["comps"].append({"name": name, "w": node.get("width"), "h": node.get("height"),
                                 "fps": node.get("frameRate") or node.get("fps"),
                                 "dur": node.get("duration"), "layers": len(node["layers"])})
            for ly in node["layers"]:
                if isinstance(ly, dict) and isinstance(ly.get("name"), str):
                    m = PREFIX.match(ly["name"])
                    acc["prefix"][m.group(1) if m else "(none)"] += 1
        for k, v in node.items():
            lk = k.lower()
            if isinstance(v, str):
                if "font" in lk and "size" not in lk and v:
                    acc["fonts"][v] += 1
                elif lk == "matchname" and v.startswith(("ADBE", "CC ", "VIDEOCOPILOT", "tc", "PEDG")) and not SKIP_MATCH.match(v):
                    acc["effects"][v] += 1
                elif lk in ("text", "sourcetext", "content") and v.strip():
                    acc["texts"].append(v.strip().replace("\r", " / ")[:80])
            elif isinstance(v, (int, float)) and lk in ("fontsize", "size") and "font" in key.lower() + lk:
                acc["sizes"][round(v)] += 1
            elif isinstance(v, list) and "color" in lk and len(v) in (3, 4) and all(isinstance(x, (int, float)) for x in v):
                h = hexcol(v)
                if h:
                    acc["colors"][h] += 1
            walk(v, acc, k)
    elif isinstance(node, list):
        for x in node:
            walk(x, acc, key)


# ------------------------------------------------------------------ --deep: per-layer dump for learning a style
VERBOSE_FX = ("Keylight", "PEDG", "S_Blur", "textevo", "Deep Glow", "Sapphire")
TDEF = {"Anchor Point", "Position", "Scale", "Rotation", "Opacity"}
LAYER_KNOWN = {"index", "id", "name", "type", "enabled", "solo", "shy", "locked", "inPoint", "outPoint", "startTime",
               "stretch", "parentIndex", "label", "width", "height", "hasVideo", "hasAudio", "threeDLayer", "sourceId",
               "sourceName", "parent", "transformGroup", "effectsGroup", "masksGroup", "timeRemapEnabled", "text",
               "fontSize", "font", "fillColor", "textGroup", "contentsGroup", "audioGroup", "materialOptionsGroup"}
EXPORT_GAPS = ("text-animator selector keys, blend modes, track mattes, adjustment flag, mask modes, "
               "Geometry/Material/Light options - read them with property.get (numKeys) / comp.sample if they matter")


def rnd(v, n=2):
    if isinstance(v, float):
        return round(v, n)
    if isinstance(v, list):
        return [rnd(x, n) for x in v]
    return v


def ease_str(k):
    try:
        i, o = k["inEase"][0], k["outEase"][0]
        s = ""
        if k.get("inInterpName") != "bezier" or k.get("outInterpName") != "bezier":
            s = f"{k.get('inInterpName', '?')[:3]}/{k.get('outInterpName', '?')[:3]} "
        return s + "i%d/%d o%d/%d" % (i["speed"], i["influence"], o["speed"], o["influence"])
    except (KeyError, IndexError, TypeError):
        return k.get("inInterpName", "")


def walk_props(g, t0, path, out, params):
    for p in g.get("properties", []) or []:
        name = p.get("name", "?")
        if p.get("keyframes"):
            keys = " ".join("%+.3f=%s[%s]" % (k.get("time", 0) - t0, json.dumps(rnd(k.get("value")), ensure_ascii=False),
                                              ease_str(k)) for k in p["keyframes"])
            out.append(f"      K {path}/{name}: {keys}")
        if p.get("expression"):
            out.append(f"      E {path}/{name}: " + p["expression"].replace("\n", " \\n ")[:900])
        elif params and not p.get("keyframes") and "value" in p and "GPU" not in name \
                and not p.get("matchName", "").endswith("Mask Opacity"):
            out.append(f"        {name}=" + json.dumps(rnd(p["value"]), ensure_ascii=False)[:120])
    for sg in g.get("groups", []) or []:
        if sg.get("matchName") != "ADBE Effect Built In Params":
            walk_props(sg, t0, path + "/" + sg.get("name", ""), out, params)


def deep_layer(L, params):
    out = []
    t0 = L.get("inPoint", 0) or 0
    hdr = "#%s %s [%s] in=%.3f out=%.3f st=%.3f" % (L.get("index"), L.get("name"), L.get("type"), t0,
                                                    L.get("outPoint", 0) or 0, L.get("startTime", 0) or 0)
    for cond, txt in ((L.get("sourceName"), f" src={L.get('sourceName')}"),
                      (L.get("parent"), f" parent={(L.get('parent') or {}).get('name') if isinstance(L.get('parent'), dict) else L.get('parent')}"),
                      (L.get("threeDLayer"), " 3D"), (L.get("enabled", True) is False, " DISABLED"),
                      (L.get("stretch", 100) not in (100, None), f" stretch={L.get('stretch')}"),
                      (L.get("timeRemapEnabled"), " TIMEREMAP")):
        if cond:
            hdr += txt
    out.append(hdr)
    if "text" in L:
        out.append(f"    TEXT {str(L['text'])[:80]!r} font={L.get('font')} size={L.get('fontSize')} fill={rnd(L.get('fillColor'))}")
    tg = L.get("transformGroup") or {}
    st = ["%s=%s" % (p["name"][:3], json.dumps(rnd(p.get("value"), 1))) for p in tg.get("properties", []) or []
          if p.get("name") in TDEF and not p.get("keyframes")]
    out.append("    T " + " ".join(st))
    walk_props(tg, t0, "T", out, False)
    for fx in (L.get("effectsGroup") or {}).get("groups", []) or []:
        out.append(f"    FX {fx.get('name')} ({fx.get('matchName')})")
        verbose = any(v in (fx.get("matchName") or "") + (fx.get("name") or "") for v in VERBOSE_FX)
        walk_props(fx, t0, fx.get("name", ""), out, params and not verbose)
    for m in ((L.get("masksGroup") or {}).get("groups") or []):
        out.append(f"    MASK {m.get('name')}")
        walk_props(m, t0, "Mask", out, params)
    for k in ("contentsGroup", "textGroup"):
        if L.get(k):
            sub = []
            walk_props(L[k], t0, k, sub, params)
            out.extend(sub[:90])
    if params:
        for k in L:
            if k not in LAYER_KNOWN:
                out.append(f"    ?{k}=" + json.dumps(L[k], ensure_ascii=False)[:300])
    return out


def deep_dump(comp, a):
    rx = re.compile(a.params, re.I) if a.params else None
    print("COMP %s %sx%s %sfps %ss layers=%s mb=%s shutter=%s/%s" % (
        comp.get("name"), comp.get("width"), comp.get("height"), comp.get("frameRate"), comp.get("duration"),
        len(comp.get("layers") or []), comp.get("motionBlur"), comp.get("shutterAngle"), comp.get("shutterPhase")))
    if comp.get("markers"):
        print("  MARKERS " + json.dumps(comp["markers"], ensure_ascii=False)[:500])
    audio = []
    for L in comp.get("layers") or []:
        if not isinstance(L, dict):
            continue
        if a.noaudio and L.get("hasAudio") and not L.get("hasVideo"):
            audio.append(((L.get("inPoint") or 0), "%.3f %s (%s) %.2fs" % (
                L.get("inPoint") or 0, L.get("name"), L.get("sourceName"), (L.get("outPoint") or 0) - (L.get("inPoint") or 0))))
            continue
        for ln in deep_layer(L, bool(rx and rx.search(str(L.get("name", ""))))):
            print(ln)
    if audio:
        print(f"AUDIO LAYERS {len(audio)}")
        for _, s in sorted(audio):
            print("  " + s)
    print("GAPS not in the export: " + EXPORT_GAPS)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--comp", help="only this comp (exact name)")
    ap.add_argument("--texts", type=int, default=12)
    ap.add_argument("--deep", action="store_true", help="per-layer dump of --comp: keys with ease, expressions, effects")
    ap.add_argument("--params", metavar="REGEX", help="--deep: also static effect/shape values, only for layers whose "
                                                       "name matches (filter first, read less)")
    ap.add_argument("--noaudio", action="store_true", help="--deep: audio-only layers as one sorted list")
    a = ap.parse_args()
    if a.deep and not a.comp:
        ap.error("--deep needs --comp NAME")
    if not os.path.isfile(a.file):
        sys.exit(f"ERROR: file not found: {a.file}")
    try:
        with open(a.file, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        sys.exit(f"ERROR: {a.file} is not valid JSON: {e}")
    if a.comp:
        found = []

        def find(n):
            if isinstance(n, dict):
                if n.get("name") == a.comp and isinstance(n.get("layers"), list):
                    found.append(n)
                for v in n.values():
                    find(v)
            elif isinstance(n, list):
                for v in n:
                    find(v)
        find(data)
        if not found:
            sys.exit(f"ERROR: comp '{a.comp}' not found")
        data = found[0]
        if a.deep:
            return deep_dump(data, a)
    acc = {"comps": [], "prefix": Counter(), "fonts": Counter(), "sizes": Counter(), "colors": Counter(),
           "effects": Counter(), "texts": []}
    walk(data, acc)
    print(f"COMPS {len(acc['comps'])}")
    for c in sorted(acc["comps"], key=lambda c: -(c["layers"] or 0))[:12]:
        size = f"{c['w']}x{c['h']}" if c["w"] and c["h"] else "size ?"
        fps = f"{c['fps']}fps" if c["fps"] else "fps ?"
        dur = f"{c['dur']}s" if c["dur"] is not None else "duration ?"
        print(f"  {c['name']}\t{size}\t{fps}\t{dur}\t{c['layers']} layers")
    def top(cnt, n=10):
        return ", ".join(f"{k}({v})" for k, v in cnt.most_common(n)) or "-"
    print(f"LAYER_PREFIXES {top(acc['prefix'])}")
    print(f"FONTS {top(acc['fonts'])}")
    print(f"FONT_SIZES {top(acc['sizes'], 8)}")
    print(f"COLORS {top(acc['colors'], 12)}")
    print(f"EFFECTS {top(acc['effects'], 15)}")
    uniq = list(dict.fromkeys(acc["texts"]))
    print(f"TEXT_SAMPLES {len(uniq)} unique")
    for t in uniq[:a.texts]:
        print(f"  {t}")
    if not acc["comps"] and not acc["fonts"]:
        print("NOTE nothing recognised - the export schema may differ; use ae_layer_info(detail='summary') on key comps instead")


if __name__ == "__main__":
    main()
