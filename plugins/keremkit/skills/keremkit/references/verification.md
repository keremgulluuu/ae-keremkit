# Verification Levels

User rule: **screenshots are off by default.** Images are used only when the user asks; first economically; full quality only when they ask again. Why: one image costs many times the tokens of the same facts as numbers, and most problems (overflow, position, timing, missing fonts) show up in numbers.

## Level 0 - numbers (always, unasked)

Append to the batch that made the change:

| Question | Operation |
|---|---|
| Structure, order, timing right? | `comp.info` |
| Inside frame / safe area? | `layer.bounds` (comp-space corners) vs safe rect |
| Text fits? | `text.measure` |
| Motion right at the right time? | `comp.sample` at 3-5 times, only relevant layers |
| Anything missing? | `font.list_missing`, `footage.list_missing` |
| Cut timeline consistent? | `comp.info`: placements end-to-start, no gaps/overlaps |

Safe rect for comp W x H and ratio r (`standards.safe_area.title`, e.g. 0.90): x in [W(1-r)/2, W(1+r)/2], y in [H(1-r)/2, H(1+r)/2]. For 9:16 also subtract `standards.vertical_ui_margin_px` (top/bottom/left/right).

## Level 1 - economical look (user says "check it", "take a look", "screenshot" - in any language)

1. Measure first: `ae_render_frame` with `analyze: true`; read only the numbers (edge bands, content bounds, coverage). Do not open the PNG.
2. If the numbers do not answer the question, or the user wants a visual judgement: open **one** image.
   - A moment: one frame, small (`contactSheet` with `thumbWidth` = `verification.economic_thumb_width`, default 480).
   - Motion: up to `verification.motion_max_frames` (6) `times` + `contactSheet {thumbWidth: 320}` -> open only the sheet.
3. Fix, re-verify with Level 0. Never reopen the same frame without a change in between.

## Level 2 - full quality (only on a second, explicit request)

Full-resolution frame(s) or a large contact sheet (thumbWidth 960-1280). Keep `colorManaged: "auto"`; report any `colorWarning`. Still the fewest images possible.

## Not verification

- Library `preview.png` - written, never opened.
- Final renders (`render.*`) - output, not checks.
