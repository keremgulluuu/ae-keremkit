# Saving to the Library

Goal: store an element the user liked so it can later be placed **without redesigning it**, by its Turkish or English name. A good entry = clear bilingual names + rich tags + adjustable parameters + a self-contained file.

## 1. What and where

- What to save: the comp/layers the user points at, or "what you just made" (active comp / selected layers from the `ae_do` context). Ask one question only if still unclear.
- Category: `keremkit.py cat list` (keys, prefixes, TR/EN names). Pick the best fit.
- **New category:** if the element fits no category well (and "other" would be a stretch), suggest one in a single line: "This doesn't fit any existing category. Shall I create a new one called '3D Objects' (3DO)?" On yes: `keremkit.py cat add --key 3d-objects --prefix 3DO --name "3D Objects" [--local tr="3D Objeler"] --desc "..."`. Do not create categories for one-off oddities; `summary` reporting `HINT` (5+ items in other) is a good moment to suggest one.
- ID: `keremkit.py new-id <PREFIX>` -> e.g. `UI-008`.

## 2. Names (English + the user's language)

Propose good names without asking; adopt the user's corrections.

- `name` (English): what it is + its distinguishing trait - "Gold Counter", "Neon Title – Flicker", "Glass Info Card".
- `names`: the same in `language.library` when set, e.g. `{"tr": "Altın Sayaç"}`. Write it as a native speaker would, not word-for-word.
- `tags`: 6-15 search words **in English and the library language, with synonyms** - type (counter, number), look (gold, shiny, metallic), use (subscriber count, stat), motion (count up). Think of every word the user might say when asking for it.
- `summary` (English, ~15 words max) and optionally `summaries` (`{"tr": "..."}`): enough to choose from a search result.
- Folder `library/items/<category>/<ID>_<ascii-kebab of name>`; AE comp `LIB_<ID>_<PascalAscii>` (e.g. `LIB_UI-008_GoldCounter`).

## 3. Make it one clean comp

- Not a single comp yet? `comp.precompose` the layers into the `LIB_` comp (moveAll true). Name its layers with standard prefixes.
- **Parameters** (values that will change per use: text, numbers, main color, duration, size) must sit on **top-level** layers of the `LIB_` comp - nested precomps are shared between duplicates. Best: a `CTRL_<Name>` null with Slider/Color/Checkbox controls wired by expression. If that already exists, use it. If building it would take more than a few ops, map parameters directly to the target properties instead (e.g. `TXT_Value` Source Text) - the user can ask for a control layer later.

## 4. Write the self-contained file (order matters)

`project.reduce` deletes everything else from the open project. It **never** runs on the user's project file - only on a work copy made by the shell. (A library save once destroyed a user's project: Save As reported `saved:true` without writing, `project.undo` did not bring the reduce back, and `project.open` then wrote the reduced project over the original.)

1. `ae_save_project()` (current path **P**; never saved -> ask for a path and stop). `keremkit.py stat P` - note size and time.
2. `keremkit.py safe-copy P <home>/library/_work/<Project>_work.aep --overwrite` (a shell copy, not an AE save).
3. `project.open` the copy. The context's `project.file` must be the copy - **if it is P, stop**.
4. Create the item folder (`mkdir`) before any save: `ae_save_project(path)` may report success without writing into a missing folder.
5. `project.reduce {comps: ["LIB_UI-008_GoldCounter"]}` (alone in its call).
6. One batch: `font.list_used`, `item.list`, `footage.list_missing` -> dependencies.
7. External files (images, video, audio): copy them into the item folder `sources/` and `footage.replace` to the copies, so the item works on any computer. If copying is impossible, record them in `deps.footage` and tell the user.
8. `ae_save_project(path=<item folder>/item.aep)`, then `keremkit.py stat <item>/item.aep` - it must exist, be larger than 0 and have a fresh time. `saved:true` alone is not proof.
9. Preview (section 4b).
10. `project.open P`. Then `keremkit.py stat P` again: size and time must match step 1.

Any surprise on the way (wrong path in a response, item count not what it should be, a file missing after a save) -> the stop rules in SKILL.md.

Optional outputs when useful or asked: `preset.ffx` (the user saves it in AE: Animation > Save Animation Preset - scripts cannot create .ffx), `template.mogrt` via `egp.export_mogrt` for Premiere.

## 4b. Preview

A preview shows what the item **does**, measured with numbers - Claude never opens the frames. Temporary frames go to `<home>/library/_work/frames/` and reuse the same names, so they never pile up.

1. `previews.py probe-times <duration> --fps <fps>` -> 8-16 times spread over the comp.
2. Render them in one call: `batch.run` with one `render.frame {comp, time, outPath: <frames>/p00.png ...}` per time. In a colour-managed project (`project.get_settings` workingSpace not `None`) use the `ae_render_frame` tool with `times` instead (`render.frame` writes raw working-space values there).
3. `previews.py pick <frames>/p*.png --times <same times> --fps <fps>` decides:
   - `static` - nothing moves: one frame (the fullest one). `FRAMES` lists it; no new render.
   - `continuous` - it moves all the time (a drifting gradient, a loop): 6 frames spread over the duration, taken from the probe frames; no new render.
   - `animated` - movement in some windows only (an intro, an outro): 6 times inside those windows, ending on the settled frame. Render those 6 into `<frames>/a00.png...` (one batch).
   - `blank` - every frame is empty. Don't save a preview; check the comp (wrong comp, hidden layers, missing footage) and tell the user.
4. `previews.py sheet <frames> -o <item>/preview.png --kind <kind> --times <times> --meta <item>/meta.json` - one image (6 frames in a row for vertical items, 3x2 for horizontal ones, transparent parts on dark grey). It prints `OK` or `BLANK`; never open the image.

Cost: two or three short AE calls per item; no images enter the conversation.

## 5. meta.json and catalog

Template: `assets/meta.example.json`. Required: `id, name, category, tags, summary, comp, file, size, fps, duration, params, deps, created, version`.

A parameter:

```json
{"key": "end", "label": "End number", "type": "number", "default": 1000,
 "target": {"layer": "CTRL_Counter", "property": ["Effects", "End", "Slider"]}, "op": "property.set"}
```

`type`: number | text | color ([r,g,b] 0-1) | bool | seconds | point. Text uses `"op": "text.set_content"`.

Then `keremkit.py add <item folder>/meta.json` (re-running updates the row).

## 6. Tell the user (one short block)

- Saved: **Gold Counter** (`UI-008`)
- Call it with: "gold counter" (or its local name)
- Adjustable: end number, duration, main color
- Warnings, if any (missing font, uncopied file)

## Saving many items at once (a template pack)

When the user brings a pack (one `.aep` with dozens of finished comps), keep the source and split it:

1. Copy the pack's `.aep` and its footage to `library/packs/<PackName>/` (`<PackName>_source.aep`, `sources/`), open that copy - never the user's original.
2. Plan all items first (names, tags, categories, params) from one `comp.info`/`item.list` pass, so the loop below is mechanical.
3. Build all `LIB_` comps in that copy, `ae_save_project(path=<pack>/<PackName>_work.aep)`, `keremkit.py stat` it.
4. Per item, **one AE call at a time**: `project.reduce {comps:[...]}` (alone) -> [`footage.replace` to the item's `sources/` copies] -> `ae_save_project(path=<item>/item.aep)` -> `keremkit.py stat` -> preview (4b) -> `project.open <PackName>_work.aep`. Do not use `project.undo` to bring the pack back: it can report success while the reduce stays.
5. Write `meta.json` per item (with `source: {pack, original_comp}`), then one `keremkit.py add` per item (or a short loop on the user's machine).
6. Finish with `project.open` on the pack work copy (or the user's project) so nothing can overwrite the last item.
7. Report: items saved per category, any that failed and why.

Parameters inside nested comps: record `target.comp` for each parameter (the nested comp that holds the control), and say in `usage_note` that nested comps are shared between duplicates.

## Saving a whole project (category `project`, prefix `PRJ`)

"Save this project to the library" keeps everything - all comps, footage, audio, effects - as a reusable template.

1. `ae_save_project()`, note **P**, `keremkit.py stat P`; `keremkit.py safe-copy P <folder>/item.aep`; `project.open` that copy and check `project.file` is the copy (if it is P, stop).
2. `item.list` -> every footage file path. Copy them into `library/items/project/<ID>_<slug>/sources/` (keep sub-folders by type: `footage/`, `audio/`, `images/`), and `footage.replace` each item to its copy. Large files: say the total size first and ask - a project template with raw footage can be many GB; offer "structure only" (footage swapped for placeholders with `footage.replace_with_placeholder`) as the light option.
3. `ae_save_project()` (saves the copy in place), `keremkit.py stat` it, preview of the main comp (4b), then `project.open P` and `stat P` (unchanged).
4. `meta.json` as for items, plus: `main_comp`, `comps` (names), `swappable` - the footage the user will replace next time (e.g. camera, voice, screen), each `{"role": "camera", "item": "<project item name>", "note": "..."}` - ask the user which ones are swappable if it isn't obvious from names, and `deps` (fonts, plugins).
5. `keremkit.py add`.

Using it: "start a new video from the <name> project" -> copy `item.aep` to the user's new project folder (never edit the library copy), `project.open` the copy, then `footage.replace` each `swappable` item with the new files (matched by role, like style inputs). The style/transcript/cut pipeline can then run on the new footage.

## Updating an item

"Update this item": same ID/folder, overwrite `item.aep` (from a work copy, as in section 4), `version` +1, one line in `changes`. A clearly different look (not just a parameter) = a new item with a new ID.

## Repairing previews

Older versions saved some previews blank (black, empty or fully transparent; usually under 10 KB, often the very same image for many items).

**Finding them:** once per session, when the library is first used, run `previews.py scan --brief` (one line). If `blank`, `missing` or `suspect` is above 0 and preference `library.preview_repair` is not `never`, ask once:

> N library items have empty previews (left from an older version). Shall I re-render them? About <minutes>; I'd open each item file in After Effects, so save your project first.
> Options: All of them / Show me the list / Not now / Don't ask again

Not now -> don't ask again this session. Don't ask again -> `pref set library.preview_repair=never`. Show the list -> `previews.py scan` (one line per item) and let the user pick.

**Repairing** (only after a yes):
1. `previews.py scan --json <home>/library/_work/repair.json`; tell the user the count. Above ~30 items, offer to do it in rounds.
2. `ae_save_project()` on the user's project, note **P**.
3. Items that came from one pack whose work file holds their `LIB_` comps (`library/packs/<Pack>/<Pack>_work.aep`): safe-copy that file once, open the copy and render every item from it. Otherwise per item: `keremkit.py safe-copy <item>/item.aep <home>/library/_work/repair.aep --overwrite`, `project.open` the copy (the library file itself is never opened).
4. Preview steps of section 4b per item (`comp` from `meta.json`). Several items from one open project can share one probe batch.
5. `previews.py scan --brief` again; report "Fixed N previews; M still empty (reason)". Finally `project.open P`.

