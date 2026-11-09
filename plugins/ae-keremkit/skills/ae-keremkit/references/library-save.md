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

`project.reduce` deletes everything else from the open project, so the real project must be safe first:

1. `ae_save_project` (current path). Never saved? Ask for a path and stop.
2. Note the project path **P** (from context).
3. `ae_do project.reduce {comps: ["LIB_UI-008_GoldCounter"]}`.
4. One batch: `font.list_used`, `item.list`, `footage.list_missing` -> dependencies.
5. External files (images, video, audio): copy them into the item folder `sources/` and `footage.replace` to the copies, so the item works on any computer. If copying is impossible, record them in `deps.footage` and tell the user.
6. `ae_save_project(path=<item folder>/item.aep)` (Save As).
7. Preview: `ae_render_frame` -> `<item folder>/preview.png` at the most representative moment (~65 % of the duration); animated items may use `times` (4 frames) + `contactSheet: {thumbWidth: 320}`. **Do not open the image.**
8. `ae_do project.open {path: P}` (nothing to save - the original was saved in step 1). Confirm from context that P is open again.

Optional outputs when useful or asked: `preset.ffx` (the user saves it in AE: Animation > Save Animation Preset - scripts cannot create .ffx), `template.mogrt` via `egp.export_mogrt` for Premiere.

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
3. Per item, **one AE call at a time**: `project.reduce {comps:[...]}` (alone) -> [`footage.replace` to the item's `sources/` copies] -> `ae_save_project(path=<item>/item.aep)` -> `ae_render_frame` preview -> `project.undo` (count = 1 + number of replaces). Undo restores the full pack project - much faster than reopening.
4. Write `meta.json` per item (with `source: {pack, original_comp}`), then one `keremkit.py add` per item (or a short loop on the user's machine).
5. Finish with `project.open` on the pack copy (or the user's project) so nothing can overwrite the last item.
6. Report: items saved per category, any that failed and why.

Parameters inside nested comps: record `target.comp` for each parameter (the nested comp that holds the control), and say in `usage_note` that nested comps are shared between duplicates.

## Saving a whole project (category `project`, prefix `PRJ`)

"Save this project to the library" keeps everything - all comps, footage, audio, effects - as a reusable template.

1. Checkpoint the open project (`ae_save_project`), note its path **P**.
2. `item.list` -> every footage file path. Copy them into `library/items/project/<ID>_<slug>/sources/` (keep sub-folders by type: `footage/`, `audio/`, `images/`), and `footage.replace` each item to its copy. Large files: say the total size first and ask - a project template with raw footage can be many GB; offer "structure only" (footage swapped for placeholders with `footage.replace_with_placeholder`) as the light option.
3. `ae_save_project(path=<folder>/item.aep)` (Save As), preview frame of the main comp (not opened), then `project.open P`.
4. `meta.json` as for items, plus: `main_comp`, `comps` (names), `swappable` - the footage the user will replace next time (e.g. camera, voice, screen), each `{"role": "camera", "item": "<project item name>", "note": "..."}` - ask the user which ones are swappable if it isn't obvious from names, and `deps` (fonts, plugins).
5. `keremkit.py add`.

Using it: "start a new video from the <name> project" -> copy `item.aep` to the user's new project folder (never edit the library copy), `project.open` the copy, then `footage.replace` each `swappable` item with the new files (matched by role, like style inputs). The style/transcript/cut pipeline can then run on the new footage.

## Updating an item

"Update this item": same ID/folder, overwrite `item.aep`, `version` +1, one line in `changes`. A clearly different look (not just a parameter) = a new item with a new ID.
