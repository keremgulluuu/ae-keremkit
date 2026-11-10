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

## 4. Write the self-contained file

`project.reduce` deletes everything else from the open project, so it only ever runs on a **work copy**; the user's file is never reduced. (Once a library save destroyed a user's project: Save As reported `saved:true` without writing, undo did not bring the reduce back, and `project.open` wrote the reduced project over the original.) Few calls, in this order:

1. **Shell, one call:** `ae_save_project()` first (path **P** - never saved -> ask for a path and stop), then `keremkit.py save-prep P <home>/library/_work/<Project>_work.aep --items <item folder>` - notes P, copies it, creates the item folder.
2. **AE:** `project.open` the work copy - the returned context's `project.file` must be the copy (if it is P: stop).
3. **AE:** `comp.info` of the `LIB_` comp (size, fps, duration for the meta).
4. **Preview** from the work copy, before the reduce: `previews.md` (usually 2 AE calls).
5. **AE:** `project.reduce {comps: ["LIB_UI-008_GoldCounter"]}` (alone).
6. **AE, one batch:** `font.list_used`, `footage.list_missing`, and `footage.replace` for external files copied into `<item>/sources/` (impossible -> `deps.footage` + tell the user).
7. **AE:** `ae_save_project(path=<item folder>/item.aep)`, then `project.open P`.
8. **Shell, one call:** `keremkit.py save-check <work> --items <item>/item.aep` - P unchanged and item.aep written. A failure -> the stop rules in SKILL.md (redo from step 2; P is safe).

A dialog ("second script while another script was running") can make a save silently not happen - step 8 catches it: `instance.dismiss_dialog`, check `ae_project_info`, save again.

Several items from one project: `library-pack.md`. A whole project as a template: `library-pack.md` -> Whole project.

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

**Several items** - write one tab-separated table instead of one meta.json each, and run `keremkit.py add-many items.tsv` (folders, meta.json and catalog rows in one go). Columns: `id category name local tags summary comp size fps duration` (required) plus `pack original_comp fonts footage usage_note`; `tags`, `fonts`, `footage` comma-separated, `size` as `1080x1920`, `local` = the name in `language.library`. Add `params` afterwards only for items that have them.

## 6. Tell the user (one short block)

- Saved: **Gold Counter** (`UI-008`)
- Call it with: "gold counter" (or its local name)
- Adjustable: end number, duration, main color
- Warnings, if any (missing font, uncopied file)

## Updating an item

"Update this item": same ID/folder, overwrite `item.aep` (from a work copy, as in section 4), `version` +1, one line in `changes`. A clearly different look (not just a parameter) = a new item with a new ID.
