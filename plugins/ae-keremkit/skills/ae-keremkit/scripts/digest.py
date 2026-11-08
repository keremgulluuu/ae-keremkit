#!/usr/bin/env python3
"""KeremKit project digest - turn a large After Effects project export into a short summary.

Used to learn or update an edit style from a finished project without reading the whole
project into the conversation. Input: the JSON written by ae_project_export_json(outPath=...).
The walker is schema-tolerant: it looks for fonts, colors, effect names, layer-name
prefixes, texts, comps and durations wherever they appear.

  python digest.py PROJECT.json [--comp NAME] [--texts 12]
"""
import argparse
import json
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


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--comp", help="only this comp (exact name)")
    ap.add_argument("--texts", type=int, default=12)
    a = ap.parse_args()
    with open(a.file, encoding="utf-8") as f:
        data = json.load(f)
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
    acc = {"comps": [], "prefix": Counter(), "fonts": Counter(), "sizes": Counter(), "colors": Counter(),
           "effects": Counter(), "texts": []}
    walk(data, acc)
    print(f"COMPS {len(acc['comps'])}")
    for c in sorted(acc["comps"], key=lambda c: -(c["layers"] or 0))[:12]:
        print(f"  {c['name']}\t{c['w']}x{c['h']}\t{c['fps']}fps\t{c['dur']}s\t{c['layers']} layers")
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
