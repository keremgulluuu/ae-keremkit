#!/usr/bin/env python3
"""KeremKit design-token extractor - read a look from HTML/CSS, SVG or Lottie JSON (stdlib only).

Turns a reference design into a small, editable tokens file (palette, type, shapes,
effects, motion) plus After Effects-ready values (tracking, leading, easing influence),
so a theme can be copied without pasting the whole source into the conversation.

  python tokens.py SOURCE [SOURCE ...] [--scope SELECTOR] -o tokens.json

SOURCE: .html .htm .css .svg .json (Lottie). --scope keeps only CSS rules whose selector
contains the given text (repeatable), e.g. --scope .poster --scope .hero to ignore
unrelated parts of a page. Embedded data URIs (images, fonts) are skipped.
Prints a short summary; the full result goes to -o.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
RGB = re.compile(r"rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)")
DATA_URI = re.compile(r"url\(\s*['\"]?data:[^)]*\)")
BEZIER = re.compile(r"cubic-bezier\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)")
NAMED_EASE = {"ease": (.25, .1, .25, 1), "ease-in": (.42, 0, 1, 1), "ease-out": (0, 0, .58, 1),
              "ease-in-out": (.42, 0, .58, 1), "linear": (0, 0, 1, 1)}


# ---------------------------------------------------------------- colours
def to_rgba(token):
    token = token.strip()
    m = HEX.fullmatch(token)
    if m:
        h = token[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return r, g, b, round(a, 3)
    m = RGB.fullmatch(token)
    if m:
        r, g, b = (float(m.group(i)) for i in (1, 2, 3))
        a = m.group(4)
        a = (float(a[:-1]) / 100 if a and a.endswith("%") else float(a)) if a else 1.0
        return int(r), int(g), int(b), round(a, 3)
    return None


def hexof(rgba):
    return "#%02X%02X%02X" % rgba[:3]


def ae_color(rgba):
    return [round(c / 255, 4) for c in rgba[:3]]


def colors_in(value):
    out = []
    for m in HEX.finditer(value):
        c = to_rgba(m.group(0))
        if c:
            out.append(c)
    for m in RGB.finditer(value):
        c = to_rgba(m.group(0))
        if c:
            out.append(c)
    return out


# ---------------------------------------------------------------- css parsing
def css_blocks(text):
    """Yield (selector, declarations dict) from CSS, flattening @media blocks."""
    text = DATA_URI.sub("url(DATA)", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    out = []
    depth, start, sel_stack = 0, 0, []
    buf = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "{":
            sel_stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            if sel_stack:
                sel = sel_stack.pop()
                if buf.strip() and not sel.startswith("@"):
                    decls = {}
                    for part in buf.split(";"):
                        if ":" in part:
                            k, _, v = part.partition(":")
                            decls[k.strip().lower()] = v.strip()
                    media = next((s for s in sel_stack if s.startswith("@media")), None)
                    out.append((sel, decls, media))
            buf = ""
        else:
            buf += ch
        i += 1
    return out


def extract_css(text, scopes):
    blocks = css_blocks(text)
    variables = {}
    for sel, decls, media in blocks:
        if media:
            continue
        for k, v in decls.items():
            if k.startswith("--"):
                variables.setdefault(k, v)

    def resolve(v, depth=0):
        if depth > 5:
            return v
        return re.sub(r"var\((--[\w-]+)(?:\s*,\s*([^)]*))?\)",
                      lambda m: resolve(variables.get(m.group(1), m.group(2) or ""), depth + 1), v)

    keep = [(s, d, m) for s, d, m in blocks
            if not scopes or any(sc in s for sc in scopes) or s.strip() in (":root", "html", "body")]
    return keep, variables, resolve


def px_values(v):
    """All px numbers in a value; clamp()/min()/max() give their largest px (desktop size)."""
    return [float(x) for x in re.findall(r"(-?[\d.]+)px", v)]


def analyse_css(text, scopes):
    blocks, variables, resolve = extract_css(text, scopes)
    t = {"palette": {}, "colors": Counter(), "roles": defaultdict(Counter), "fonts": Counter(),
         "weights": Counter(), "sizes": [], "tracking": Counter(), "line_height": Counter(),
         "radius": Counter(), "shadows": [], "gradients": [], "easing": Counter(), "durations": Counter(),
         "grid": [], "borders": Counter()}
    for k, v in variables.items():
        c = to_rgba(resolve(v))
        if c:
            t["palette"][k.lstrip("-")] = c
    for sel, decls, media in blocks:
        if media:
            continue
        for k, raw in decls.items():
            if k.startswith("--"):
                continue
            v = resolve(raw)
            for c in colors_in(v):
                t["colors"][c] += 1
                role = ("text" if k == "color" else "background" if k.startswith("background") else
                        "border" if k.startswith("border") or k == "outline" else "shadow" if "shadow" in k else
                        "fill" if k in ("fill", "stroke") else k)
                t["roles"][role][c] += 1
            if k == "font-family":
                t["fonts"][v.split(",")[0].strip().strip("'\"")] += 1
            elif k == "font":
                m = re.match(r"\s*(\d{3})?\s*([\d.]+px)?.*?([A-Za-z\"' -]+)(,|$)", v)
                if m and m.group(3):
                    t["fonts"][m.group(3).strip().strip("'\"")] += 1
                if m and m.group(1):
                    t["weights"][int(m.group(1))] += 1
                if m and m.group(2):
                    t["sizes"].append((sel, float(m.group(2)[:-2])))
            elif k == "font-weight" and v.isdigit():
                t["weights"][int(v)] += 1
            elif k == "font-size":
                pv = px_values(v)
                if pv:
                    t["sizes"].append((sel, max(pv)))
            elif k == "letter-spacing":
                m = re.match(r"(-?[\d.]+)em", v)
                if m:
                    t["tracking"][round(float(m.group(1)) * 1000)] += 1
            elif k == "line-height" and re.fullmatch(r"[\d.]+", v):
                t["line_height"][float(v)] += 1
            elif k == "border-radius":
                for x in px_values(v)[:1]:
                    t["radius"][x] += 1
            elif "shadow" in k and v != "none":
                t["shadows"].append(v)
            elif k.startswith("background") and "gradient" in v:
                for g in re.findall(r"(radial-gradient\((?:[^()]|\([^()]*\))*\)|linear-gradient\((?:[^()]|\([^()]*\))*\))", v):
                    t["gradients"].append((sel, g))
            if k in ("transition", "transition-timing-function", "animation", "animation-timing-function"):
                for m in BEZIER.finditer(v):
                    t["easing"][tuple(float(x) for x in m.groups())] += 1
                for name, curve in NAMED_EASE.items():
                    if re.search(rf"(?<![\w-]){name}(?![\w-])", v):
                        t["easing"][curve] += 1
                for d in re.findall(r"([\d.]+)(m?s)\b", v):
                    t["durations"][float(d[0]) / (1000 if d[1] == "ms" else 1)] += 1
            if k == "background-size" and "px" in v:
                t["grid"].append(v)
            if k.startswith("border") and re.search(r"\d+px\s+solid", v):
                t["borders"][re.search(r"\d+px", v).group(0)] += 1
    for v in variables.values():
        for m in BEZIER.finditer(v):
            t["easing"][tuple(float(x) for x in m.groups())] += 1
    return t


# ---------------------------------------------------------------- svg / lottie
def analyse_svg(text, t):
    for attr in ("fill", "stroke", "stop-color"):
        for v in re.findall(rf'{attr}="([^"]+)"', text):
            c = to_rgba(v)
            if c:
                t["colors"][c] += 1
                t["roles"]["fill" if attr != "stroke" else "border"][c] += 1
    for v in re.findall(r'font-family="([^"]+)"', text):
        t["fonts"][v.split(",")[0].strip().strip("'\"")] += 1
    for v in re.findall(r'font-size="([\d.]+)', text):
        t["sizes"].append(("svg", float(v)))
    for v in re.findall(r'rx="([\d.]+)"', text):
        t["radius"][float(v)] += 1
    style = "".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S))
    if style:
        merge(t, analyse_css(style, []))


def analyse_lottie(data, t):
    t["lottie"] = {"size": [data.get("w"), data.get("h")], "fps": data.get("fr"),
                   "duration_s": round((data.get("op", 0) - data.get("ip", 0)) / (data.get("fr") or 30), 3),
                   "layers": len(data.get("layers", []))}
    for f in (data.get("fonts") or {}).get("list", []):
        t["fonts"][f.get("fFamily") or f.get("fName")] += 1

    def walk(n):
        if isinstance(n, dict):
            if n.get("ty") in ("fl", "st") and isinstance(n.get("c"), dict):
                k = n["c"].get("k")
                if isinstance(k, list) and len(k) >= 3 and all(isinstance(x, (int, float)) for x in k[:3]):
                    c = tuple(int(round(x * 255)) for x in k[:3]) + (1.0,)
                    t["colors"][c] += 1
                    t["roles"]["fill" if n["ty"] == "fl" else "border"][c] += 1
            if "o" in n and "i" in n and isinstance(n["o"], dict) and isinstance(n["i"], dict):
                try:
                    ox, oy = n["o"]["x"], n["o"]["y"]
                    ix, iy = n["i"]["x"], n["i"]["y"]
                    first = lambda v: v[0] if isinstance(v, list) else v
                    t["easing"][(round(first(ox), 3), round(first(oy), 3), round(first(ix), 3), round(first(iy), 3))] += 1
                except (KeyError, TypeError):
                    pass
            if n.get("ty") == "rd" and isinstance(n.get("r"), dict) and isinstance(n["r"].get("k"), (int, float)):
                t["radius"][float(n["r"]["k"])] += 1
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(data)


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, Counter):
            a[k].update(v)
        elif isinstance(v, list):
            a[k].extend(v)
        elif isinstance(v, dict) and k == "palette":
            a[k].update(v)
        elif isinstance(v, defaultdict):
            for r, cnt in v.items():
                a[k][r].update(cnt)


# ---------------------------------------------------------------- output
def ease_to_ae(curve):
    """CSS cubic-bezier -> AE temporal ease influence (%) for the outgoing and incoming keyframe."""
    x1, y1, x2, y2 = curve
    return {"cubic_bezier": list(curve), "out_influence": round(max(.1, x1) * 100, 1),
            "in_influence": round(max(.1, 1 - x2) * 100, 1),
            "feel": "ease-out (fast start, soft stop)" if x1 < .35 and y1 > .5 else
                    "ease-in (soft start, fast stop)" if x2 > .65 and y2 > .9 and x1 > .3 else
                    "linear" if curve == (0, 0, 1, 1) else "ease-in-out"}


def build(t):
    exact = {(hexof(c), c[3]): n for n, c in t["palette"].items()}
    opaque = {hexof(c): n for n, c in t["palette"].items() if c[3] >= .99}
    named = {hexof(c) for c in t["palette"].values()}

    def label(c):
        return exact.get((hexof(c), c[3])) or opaque.get(hexof(c))
    palette = {n: {"hex": hexof(c), "alpha": c[3], "ae": ae_color(c)} for n, c in t["palette"].items()}
    top = [c for c, _ in t["colors"].most_common(12)]
    unnamed = [c for c in top if hexof(c) not in named and c[3] >= .99]
    for i, c in enumerate(unnamed[:6], 1):
        palette.setdefault(f"color{i}", {"hex": hexof(c), "alpha": c[3], "ae": ae_color(c)})
    roles = {r: [{"hex": hexof(c), "alpha": c[3], "name": label(c)} for c, _ in cnt.most_common(3)]
             for r, cnt in t["roles"].items() if r in ("text", "background", "border", "fill", "shadow")}
    sizes = sorted({s for _, s in t["sizes"]}, reverse=True)
    biggest = sorted(t["sizes"], key=lambda x: -x[1])[:6]
    lh = t["line_height"].most_common(1)[0][0] if t["line_height"] else None
    glows = []
    for sel, g in t["gradients"]:
        if g.startswith("radial"):
            for m in re.finditer(r"ellipse\s+([\d.]+)px\s+([\d.]+)px\s+at\s+(-?[\d.]+)%\s+(-?[\d.]+)%\s*,\s*"
                                 r"(rgba?\([^)]*\)|#[0-9a-fA-F]{3,8})\s*,\s*transparent\s*([\d.]+)?%?", g):
                c = to_rgba(m.group(5))
                if c:
                    glows.append({"where": sel, "size_px": [float(m.group(1)), float(m.group(2))],
                                  "at_percent": [float(m.group(3)), float(m.group(4))], "color": hexof(c),
                                  "name": label(c), "opacity": c[3], "fade_end_percent": float(m.group(6) or 100)})
    return {
        "palette": palette,
        "roles": roles,
        "type": {
            "fonts": [f for f, _ in t["fonts"].most_common(4)],
            "weights": sorted(t["weights"]),
            "sizes_px": sizes[:10],
            "largest": [{"where": s, "px": v} for s, v in biggest],
            "tracking_ae": [{"value": v, "uses": n} for v, n in t["tracking"].most_common(6)],
            "line_height": lh,
            "_note": "tracking_ae = CSS letter-spacing em x 1000 (AE tracking units). Leading px = size x line_height.",
        },
        "shape": {"radius_px": [r for r, _ in t["radius"].most_common(4)],
                  "border_px": [b for b, _ in t["borders"].most_common(2)],
                  "grid": t["grid"][:2]},
        "effects": {"glows": glows[:8], "shadows": list(dict.fromkeys(t["shadows"]))[:4]},
        "motion": {"easing": [ease_to_ae(c) for c, _ in t["easing"].most_common(3)],
                   "durations_s": [d for d, _ in t["durations"].most_common(4)]},
        **({"lottie": t["lottie"]} if "lottie" in t else {}),
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--scope", action="append", default=[], help="keep only CSS rules whose selector contains this")
    ap.add_argument("-o", "--output", required=True)
    a = ap.parse_args()
    t = {"palette": {}, "colors": Counter(), "roles": defaultdict(Counter), "fonts": Counter(), "weights": Counter(),
         "sizes": [], "tracking": Counter(), "line_height": Counter(), "radius": Counter(), "shadows": [],
         "gradients": [], "easing": Counter(), "durations": Counter(), "grid": [], "borders": Counter()}
    for src in a.sources:
        low = src.lower()
        with open(src, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if low.endswith((".html", ".htm")):
            css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", text, re.S | re.I))
            inline = "\n".join(f"inline{{{s}}}" for s in re.findall(r'style="([^"]+)"', text))
            merge(t, analyse_css(css + "\n" + inline, a.scope))
        elif low.endswith(".css"):
            merge(t, analyse_css(text, a.scope))
        elif low.endswith(".svg"):
            analyse_svg(text, t)
        elif low.endswith(".json"):
            analyse_lottie(json.loads(text), t)
        else:
            sys.exit(f"ERROR: unsupported source {src} (use .html .css .svg .json)")
    out = build(t)
    out["sources"] = a.sources
    out["scope"] = a.scope
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    pal = ", ".join(f"{n}={v['hex']}" + (f"@{v['alpha']}" if v["alpha"] < 1 else "") for n, v in list(out["palette"].items())[:8])
    print(f"PALETTE {pal or '-'}")
    print(f"FONTS {', '.join(out['type']['fonts']) or '-'}  WEIGHTS {out['type']['weights'] or '-'}")
    print(f"SIZES_PX {out['type']['sizes_px'][:6]}  TRACKING_AE {[x['value'] for x in out['type']['tracking_ae'][:4]]}  "
          f"LINE_HEIGHT {out['type']['line_height']}")
    print(f"RADIUS_PX {out['shape']['radius_px']}  BORDER {out['shape']['border_px']}  GRID {out['shape']['grid'][:1]}")
    print(f"GLOWS {len(out['effects']['glows'])}  SHADOWS {len(out['effects']['shadows'])}  "
          f"EASING {[e['feel'] for e in out['motion']['easing']]}  DURATIONS {out['motion']['durations_s']}")
    print(f"-> {a.output}")


if __name__ == "__main__":
    main()
