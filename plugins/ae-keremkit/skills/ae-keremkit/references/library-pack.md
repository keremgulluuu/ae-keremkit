# Saving many items, or a whole project

Read `library-save.md` first (names, tags, categories, meta). This file only covers the loops.

## A template pack (one .aep with many finished comps)

1. **Shell:** `keremkit.py save-prep <pack.aep> <home>/library/packs/<Pack>/<Pack>_work.aep --items <every item folder>` (copy the pack's footage into `library/packs/<Pack>/sources/` too). The user's pack file is never opened.
2. **AE:** open the work copy; one `comp.info`/`item.list` pass; plan every item (names, tags, categories) so the rest is mechanical. Build all `LIB_` comps there; copy each item's external files to its `sources/` and `footage.replace` in the work file. `ae_save_project()` (in place).
3. **Previews for all items at once** from the work file - `previews.md` (2-4 AE calls in total, whatever the count).
4. **Per item, one AE call each:** `project.reduce` (alone) -> `ae_save_project(path=<item>/item.aep)` -> `project.open <Pack>_work.aep`. No `stat` per item and no `project.undo` (it can report success while the reduce stays).
5. **Shell, once:** `keremkit.py save-check <work> --items <every item.aep>`; redo only the ones it lists.
6. **Shell, once:** `keremkit.py add-many items.tsv`.
7. Report: items saved per category, any that failed and why.

Parameters inside nested comps: record `target.comp` for each parameter (the nested comp that holds the control), and say in `usage_note` that nested comps are shared between duplicates.

An `item.aep` that still holds the whole pack (several `LIB_` comps) is a broken save - re-save it reduced to its own comp.

## Whole project (category `project`, prefix `PRJ`)

"Save this project to the library" keeps everything - all comps, footage, audio, effects - as a reusable template.

1. **Shell:** `ae_save_project()`, then `keremkit.py save-prep P <folder>/item.aep --items <folder>`; **AE:** `project.open` that copy, check `project.file`.
2. `item.list` -> every footage file path. Copy them into `<folder>/sources/` (sub-folders `footage/`, `audio/`, `images/`), and `footage.replace` each item to its copy. Large files: say the total size first and ask - raw footage can be many GB; offer "structure only" (`footage.replace_with_placeholder`) as the light option.
3. `ae_save_project()` (the copy, in place), preview of the main comp (`previews.md`), `project.open P`, then `keremkit.py save-check <folder>/item.aep --items <folder>/item.aep`.
4. `meta.json` as for items, plus: `main_comp`, `comps` (names), `swappable` - the footage the user will replace next time (camera, voice, screen), each `{"role": "camera", "item": "<project item name>", "note": "..."}` - ask which ones if it isn't obvious from names, and `deps` (fonts, plugins).
5. `keremkit.py add`.

Using it: "start a new video from the <name> project" -> copy `item.aep` to the user's new project folder (never edit the library copy), `project.open` the copy, then `footage.replace` each `swappable` item with the new files (matched by role, like style inputs).
