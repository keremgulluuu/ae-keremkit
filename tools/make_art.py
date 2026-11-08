#!/usr/bin/env python3
"""Generate the README artwork (docs/assets/*.svg) from one design system.

Theme: dark editorial grid poster - near-black background with a faint 64 px grid,
lime (#C6FF3C) and red (#FF3B30) accents with soft radial glows, Inter 400/700/900 with
tight tracking, IBM Plex Mono for small labels, 20-24 px radii, hairline borders.
Fonts are embedded (base64) so the SVGs look the same on GitHub as they do here.

    python tools/make_art.py
"""
import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "docs", "assets")
FONTS = os.path.join(ASSETS, "fonts")

BG = "#0A0C0F"
CARD = "#050607"
INK = "#EAEEF3"
MUT = "#9EA8B2"
LIME = "#C6FF3C"
RED = "#FF3B30"
LINE = "rgba(234,238,243,.13)"
GRID = "rgba(234,238,243,.032)"
SANS = "Inter, Arial, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, monospace"


def font_css():
    faces = [("Inter", 400, "Inter-400.woff", "woff"), ("Inter", 700, "Inter-700.woff", "woff"),
             ("Inter", 900, "Inter-900.woff", "woff"), ("IBM Plex Mono", 500, "IBMPlexMono-500.woff2", "woff2")]
    out = []
    for fam, w, fn, fmt in faces:
        with open(os.path.join(FONTS, fn), "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        out.append(f"@font-face{{font-family:'{fam}';font-weight:{w};src:url(data:font/{fmt};base64,{b64}) format('{fmt}')}}")
    return "".join(out)


def frame(w, h, body, glows, label):
    """Poster frame: background, grid, glows, hairline border."""
    grads = []
    for i, (cx, cy, rx, ry, color, alpha) in enumerate(glows):
        grads.append(
            f'<radialGradient id="g{i}" gradientUnits="userSpaceOnUse" cx="{cx}" cy="{cy}" r="{rx}" '
            f'gradientTransform="translate({cx} {cy}) scale(1 {ry / rx:.4f}) translate({-cx} {-cy})">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="{alpha}"/>'
            f'<stop offset=".78" stop-color="{color}" stop-opacity="0"/></radialGradient>')
    glow_rects = "".join(f'<rect width="{w}" height="{h}" fill="url(#g{i})"/>' for i in range(len(glows)))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">
<defs>
<style>{font_css()}
.s{{font-family:{SANS}}}.m{{font-family:{MONO};font-weight:500}}</style>
<pattern id="grid" width="64" height="64" patternUnits="userSpaceOnUse" x="{(w % 64) / 2}" y="0">
<path d="M64 0H0V64" fill="none" stroke="{GRID}" stroke-width="1"/></pattern>
<clipPath id="clip"><rect width="{w}" height="{h}" rx="24"/></clipPath>
{"".join(grads)}
</defs>
<g clip-path="url(#clip)">
<rect width="{w}" height="{h}" fill="{BG}"/>
<rect width="{w}" height="{h}" fill="url(#grid)"/>
{glow_rects}
{body}
</g>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="23.5" fill="none" stroke="{LINE}"/>
</svg>'''


def card(x, y, w, h, r=20):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{CARD}" stroke="{LINE}"/>'


def icon(name, x, y, size, color=LIME, sw=1.8):
    """Line icons on a 24-unit grid (drawn for this kit)."""
    p = {
        "style": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M9 21V9"/><circle cx="15" cy="15" r="2.5"/>',
        "cut": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
        "subs": '<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M6 12h4M13 12h5M6 15.5h8M16.5 15.5h1.5"/>',
        "library": '<path d="M4 4h4v16H4zM10 4h4v16h-4z"/><path d="m16.5 5.2 3.6-1 3.4 15.4-3.6 1z"/>',
        "sfx": '<path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
        "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
        "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
        "spark": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
        "terminal": '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m6 9 3 3-3 3M12 15h6"/>',
        "film": '<rect x="2" y="3" width="20" height="18" rx="3"/><path d="M7 3v18M17 3v18M2 8h5M2 16h5M17 8h5M17 16h5"/>',
    }[name]
    s = size / 24
    return (f'<g transform="translate({x} {y}) scale({s})" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round">{p}</g>')


def text(x, y, content, size, weight=400, fill=INK, ls=None, anchor="start", cls="s", opacity=None):
    ls_attr = f' letter-spacing="{ls}"' if ls is not None else ""
    op = f' fill-opacity="{opacity}"' if opacity is not None else ""
    return (f'<text class="{cls}" x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}"{op}'
            f'{ls_attr} text-anchor="{anchor}">{content}</text>')


def contact_line(x, y, left, right):
    return (f'<text class="s" x="{x}" y="{y}" font-size="13" font-weight="700" fill="{INK}" fill-opacity=".66" '
            f'letter-spacing="-.16">{left}<tspan fill="{LIME}" fill-opacity=".75" dx="9">/</tspan>'
            f'<tspan dx="9">{right}</tspan></text>')


# ------------------------------------------------------------------ banner
def banner():
    w, h = 1280, 480
    body = []
    # hero headline: light weight, lime 900 accent, tight tracking (-0.063em)
    body.append(text(64, 212, f'<tspan font-weight="900" fill="{LIME}">One</tspan> style name,', 80, 400, ls=-5))
    body.append(text(64, 298, "a finished edit.", 80, 700, ls=-5))
    body.append(text(64, 356, f'After Effects editing kit for Claude. <tspan font-weight="700" fill="{LIME}">Every token counts.</tspan>',
                     24, 400, ls=-.67))
    # stat cards (red 900 numbers, muted labels, lime line icons)
    stats = [("1", "style name runs a full edit", "film"),
             ("4", "local tools, no cloud", "terminal"),
             ("0", "screenshots by default", "shield")]
    x0, y0, cw, ch, gap = 912, 112, 304, 92, 12
    for i, (num, label, ic) in enumerate(stats):
        y = y0 + i * (ch + gap)
        body.append(card(x0, y, cw, ch))
        body.append(text(x0 + 22, y + 52, num, 44, 900, fill=RED, ls=-2.9))
        body.append(text(x0 + 22, y + 74, label, 13, 700, fill=MUT))
        body.append(icon(ic, x0 + cw - 22 - 46, y + (ch - 46) / 2, 46, sw=1.6))
    glows = [(int(w * .94), 0, 460, 240, LIME, .19), (int(-w * .08), int(h * .96), 420, 260, RED, .16)]
    return frame(w, h, "\n".join(body), glows, "KeremKit — one style name, a finished edit. After Effects editing kit for Claude.")


# ------------------------------------------------------------------ features
def features():
    w, h = 1280, 364
    items = [("style", "Styles"), ("cut", "Cuts"), ("subs", "Subtitles"),
             ("library", "Library"), ("sfx", "Sound"), ("shield", "Safety")]
    notes = ["one name, whole edit", "tight, and fixable by time", "rules, highlights, zones",
             "save once, place by name", "global + style rules", "checkpoints, numeric checks"]
    body = []
    cols, gap, cw, ch = 3, 12, (w - 128 - 24) / 3, 112
    for i, ((ic, label), note) in enumerate(zip(items, notes)):
        x = 64 + (i % cols) * (cw + gap)
        y = 64 + (i // cols) * (ch + gap)
        body.append(card(x, y, cw, ch))
        body.append(icon(ic, x + 16, y + (ch - 60) / 2, 60, sw=1.75))
        body.append(text(x + cw - 24, y + 60, label, 28, 700, ls=-1.26, anchor="end"))
        body.append(text(x + cw - 24, y + 84, note, 13, 700, fill=MUT, anchor="end"))
    glows = [(int(w * .19), int(h * .30), 370, 190, LIME, .23), (int(w * .82), int(h * .61), 410, 260, RED, .15),
             (int(w * .98), int(h * .14), 270, 195, LIME, .11)]
    return frame(w, h, "\n".join(body), glows, "What KeremKit does: styles, cuts, subtitles, library, sound, safety.")


# ------------------------------------------------------------------ workflow
def workflow():
    w, h = 1280, 276
    steps = [("01", "You", "ask in any language", "user"),
             ("02", "Claude + skill", "plans, batches, checks", "spark"),
             ("03", "Local tools", "Whisper · ffmpeg · Python", "terminal"),
             ("04", "After Effects", "via MCP, one undo per step", "film")]
    body = []
    gap, cw, ch, y = 40, (w - 128 - 3 * 40) / 4, 148, 64
    for i, (num, title, note, ic) in enumerate(steps):
        x = 64 + i * (cw + gap)
        body.append(card(x, y, cw, ch))
        body.append(text(x + 20, y + 34, num, 12, cls="m", fill=MUT, ls=.5))
        body.append(icon(ic, x + cw - 20 - 34, y + 16, 34, sw=1.8))
        body.append(text(x + 20, y + 96, title, 24, 700, ls=-1.0))
        body.append(text(x + 20, y + 122, note, 13, 700, fill=MUT))
        if i < len(steps) - 1:
            ax = x + cw + 8
            body.append(f'<path d="M{ax} {y + ch / 2}h{gap - 16}m-6 -6 6 6-6 6" fill="none" stroke="{LIME}" '
                        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')
    glows = [(int(w * .97), int(h * .49), 390, 220, LIME, .13), (0, h, 280, 200, RED, .11)]
    return frame(w, h, "\n".join(body), glows, "How KeremKit works: you, Claude with the skill, local tools, After Effects.")


def main():
    for name, fn in (("banner", banner), ("features", features), ("workflow", workflow)):
        path = os.path.join(ASSETS, f"{name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(fn())
        print(f"{path} ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    main()
