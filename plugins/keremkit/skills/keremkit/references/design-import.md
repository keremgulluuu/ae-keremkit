# Copying a Look (design import)

The user shows a reference - an image, a web page, CSS, an SVG, a Lottie file, an AE project - and wants its look in After Effects: as a style's `look`, as library items, or applied to the current edit.

The core idea: **every source is first turned into design tokens** (palette, type, shapes, effects, motion), the user confirms them, and only then is anything built in AE. Tokens are small, exact and reusable; AE iterations are the expensive part, so mistakes are caught before them.

## Sources, best to weakest

| Source | How to read it | Accuracy | Cost |
|---|---|---|---|
| AE project / comp | `ae_project_export_json(outPath)` -> `digest.py`; `layer.info summary` for key layers | exact | low |
| Lottie JSON | `tokens.py file.json` (colors, fonts, easing, fps, duration) | exact, includes motion | low |
| HTML / CSS / SVG | `tokens.py file.html --scope <selector>` | exact for static values | low |
| Image (PNG/JPG/screenshot) | look at it **once**, write tokens by hand | estimated | one image |
| Video | ask for a still or the project; frames cannot show timing reliably | weak | high |

Never paste a large HTML/JSON file into the conversation - pass the path to `tokens.py`, which prints ~5 lines and writes the full result to a file.

## Scope - copy only what was asked

If the user points at part of a reference ("only the top poster", "ignore the examples at the bottom"), honour it strictly:
- Files: `--scope` with the selectors of that part (repeatable). Find selectors by grepping the source for class names, not by reading it whole.
- Images: describe in one line which region you are reading.
- **Stay inside the theme.** Use only the palette, fonts, weights, radii, borders, effects and motion found in the tokens. If something the edit needs is missing (e.g. a warning color), derive it from the tokens (an existing color at lower opacity, a lighter weight of the same font) and say so - never introduce a new color or font silently.

## From an image

1. Look at the image once. Write the tokens file by hand in the same schema `tokens.py` produces (see `assets/tokens.example.json`); mark guessed values with `"est": true`. Name colors by role (`bg`, `ink`, `accent`...).
2. Fonts: name the closest family you recognise and say it is a guess; `font.list` shows what is installed. Offer the user the chance to name the real font.
3. **HTML preview step** - preference `design_import.preview` (`ask` | `always` | `never` | `auto`; null -> ask once):
   > Should I first rebuild this as a quick HTML preview so you can confirm colors, fonts and spacing before I build it in After Effects? It's more accurate for complex designs and costs a little more up front.
   - `auto`: preview only when the design has many elements or layout relationships (grids, cards, multi-part posters) or fonts are uncertain; skip it for a single text style, a color theme or one simple element.
   - The preview is a single self-contained HTML file built only from the tokens. The user looks at it; Claude does not need to view it. Corrections go into the tokens, then the preview is regenerated, then `tokens.py preview.html` re-extracts exact values.
4. Continue with "Confirm" below.

## Confirm (always, one compact message)

Palette (name = hex), fonts and weights, the 3-4 key sizes, tracking, radii, borders/grid, glows/shadows, easing feel and durations. Ask: "Shall I build it with these?" Apply corrections to the tokens file before building.

## Mapping tokens to After Effects

| Token | After Effects |
|---|---|
| color `#RRGGBB` | `[r,g,b]` 0-1 (`ae` field) for `text.set_style fillColor`, solids, shape fills |
| color with alpha | same color + layer/fill opacity = alpha x 100 |
| font family + weight | PostScript name via `font.list` (e.g. `Inter-Black` for 900) |
| `letter-spacing` em | `tracking` = em x 1000 (`tracking_ae`) |
| `line-height` | `leading` = font size x line-height (px) |
| `font-size` px | `fontSize` px at the same canvas width; scale by comp width / design width |
| `border-radius` | shape rectangle roundness, or `shape.add_rounded_corners` |
| `1px solid` hairline | shape stroke 1-2 px at the border color/alpha (scale with comp) |
| background grid (`background-size: 64px`) | Grid effect or a repeater of 1 px lines at that spacing and alpha |
| radial-gradient glow | ellipse shape with radial gradient fill (color -> transparent), or a solid + Gaussian Blur; position from `at_percent`, size from `size_px`, opacity from `opacity` |
| `box-shadow` | Drop Shadow effect: distance = y offset, softness = blur, opacity = alpha |
| `cubic-bezier` | keyframe temporal ease: outgoing influence = `out_influence`, incoming = `in_influence` (`keyframe.set_easing`) |
| durations | seconds -> frames at the comp fps |

Scale: web pixel sizes assume the design's width (often 1200-1440 px). For a 1920 px comp multiply by 1920 / design width; for 1080 px vertical, by 1080 / design width. Say which factor you used.

## Where the result goes

- **A style's look:** write the tokens into the style's `look` (`palette`, `fonts`) and save the tokens file next to it (`styles/<slug>/tokens.json`), noting the source in `look.source`.
- **Library items:** build the reusable pieces (title style, card, stat block, button) as `LIB_` comps and save them (`library-save.md`); tag them with the theme name so "everything from the lime poster theme" is one search.
- **Just this edit:** build directly; offer once to keep it as a style or library items.

Verify numerically as usual. A visual check of the built result is a normal Level 1 check (`verification.md`) and only on request.
