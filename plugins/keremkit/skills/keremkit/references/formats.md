# Multi-format delivery

One finished edit -> several aspect ratios (e.g. 16:9 for YouTube, 9:16 for Shorts/Reels/TikTok, 1:1 or 4:5 for feeds). Targets come from `formats.targets` (ask once: "Which formats do you publish to?") or the style's `formats`.

## Steps (per extra format)

1. Checkpoint.
2. `comp.duplicate` the finished `SCN_`/`OUT_` comp -> `OUT_<Project>_9x16` and `comp.resize` it to the target size (`anchor: "center"`). Nested comps keep their own size, so content is not distorted.
3. **Reframe the main footage**: scale the camera/screen layer to fill the new frame (cover, not fit) and keep the subject centred. For a talking head, keep the eyes in the upper third: measure with `layer.bounds` and offset Position.
4. **Re-place text and UI** in the new safe area (`standards.safe_area`, plus `vertical_ui_margin_px` for 9:16): subtitles use the style's per-format positions (zone-based Position expression - update its positions map for this comp); UI items are moved inside the title-safe rectangle; large titles may need a smaller size or a line break (`text.measure`).
5. Vertical-specific: platform UI covers the bottom ~20 % and right edge - nothing important there.
6. Verify numerically (`layer.bounds` against the safe rect for every TXT/SUB/UI layer).
7. Render each format with the format in the file name (`render.naming`).

Do the 16:9 edit first and derive the others, unless the style is vertical-first. If one format needs a genuinely different design, suggest a separate style variant rather than piling exceptions into one comp.
