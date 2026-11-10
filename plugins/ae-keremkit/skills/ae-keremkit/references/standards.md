# Standards

Values come from `preferences.standards` (user-editable). Inside an existing project, follow the project's own size/fps; apply these standards to anything new.

## Naming

Why: consistent prefixes let Claude find layers by name (`project.find_layers namePattern: "SUB_"`) instead of scanning, keep expressions stable, and make projects readable for anyone.

- ASCII only in AE names: transliterate accents and special letters (ş→s, ü→u, é→e, ñ→n, ß→ss). Readable names in any language live in metadata.
- `PREFIX_PascalName`, `_01` when needed. Turkish or English words - be consistent within a project.

| Comps | Meaning | Example |
|---|---|---|
| `SCN_` | scene / main timeline part | `SCN_01_Intro` |
| `PRE_` | helper precomp | `PRE_LogoParts` |
| `LIB_` | library item | `LIB_UI-008_GoldCounter` |
| `TPL_` | template to fill | `TPL_LowerThird` |
| `OUT_` | final render comp | `OUT_YouTube_16x9` |

| Layers | Meaning | Example |
|---|---|---|
| `TXT_` | text | `TXT_Title` |
| `SUB_` | subtitle layer | `SUB_Captions` |
| `SHP_` | shape | `SHP_Card` |
| `UI_` | UI element (usually a library precomp) | `UI_GoldCounter` |
| `BG_` | background | `BG_Gradient` |
| `ICN_` | icon | `ICN_Bell` |
| `FTG_` | footage (role in name) | `FTG_Camera_Part1`, `FTG_Screen` |
| `AUD_` | voice/music | `AUD_Voice`, `AUD_Music` |
| `SFX_` | sound effect | `SFX_Transition_03` |
| `CTRL_` | control null with sliders | `CTRL_Counter` |
| `NULL_` / `ADJ_` / `CAM_` / `LGT_` / `MATTE_` | null / adjustment / camera / light / matte source | `ADJ_Grade` |

Project folders: `01_SCENES`, `02_PRECOMPS`, `03_FOOTAGE`, `04_AUDIO` (with `SFX`), `05_LIBRARY`, `99_ARCHIVE`. Apply in new projects or when asked; never reorganise an existing project unasked. Bulk renames: `project.rename` with `dryRun: true` first, then checkpoint, then apply.

## Safe areas

| Format | Default |
|---|---|
| 16:9 | action-safe 93 %, title-safe 90 % |
| 9:16 (Reels/Shorts/TikTok) | title-safe 90 % + platform UI margins (`vertical_ui_margin_px`, approximate, user-editable) |
| 1:1, 4:5 | title-safe 90 % |

Text and key UI inside title-safe; decoration inside action-safe; backgrounds full-bleed. Check with `layer.bounds`. Guides on request: `comp.add_guide`.

## Technical defaults

New comps: `standards.default_comp[<format>]` = [width, height, fps]. One frame rate per project; conform mismatched footage (`footage.interpret`) or tell the user. Cut files from `cutlist.py` are constant-frame-rate.

## Motion defaults (when neither style nor house style says otherwise)

- Entrances ease-out, exits ease-in, A-to-B moves ease-in-out; linear only for continuous loops.
- At 30 fps: UI pop/entrance 8-14 frames, big title 12-20, transitions 10-20.
- Stagger elements entering together by 2-4 frames.
- Easing via `keyframe.set_easing`; check timing with `comp.sample`.

## Render

`render.mode`: `auto` (start when the edit is verified), `ask` (ask first), `queue` (add to queue, user starts). `render.format`: the user's words (e.g. "MP4 H.264", "ProRes 422 HQ"); map to an AE output-module template from `render.list_templates` - if none fits, say so and suggest `render.queue_in_ame`. Output path: `render.output_folder` (ask once if null) + `render.naming`. Report the file path and duration when done; check `render.status` sparingly (not in a tight loop).

## After Effects speed

- Creating a text layer is slow (about 1-2 s each in recent AE). Build one styled text layer per caption/title style, then `layer.duplicate` it and change only the text and timing.
- Close heavy comps in the viewer before big batches (`timeline.set_active_comp` on a small comp); the viewer re-rendering slows every operation.
- Prefer one data-driven layer (subtitles, zoom) over hundreds of keyed layers.
- Expressions that read JSON are evaluated per frame: keep data files compact (as the tools write them) and avoid nesting such layers in many precomps.

## Checkpoints

`<Project>_v001.aep`, `_v002`... next to the project; if the name already ends in `_vNNN`, increment it. Claude never deletes checkpoints.
