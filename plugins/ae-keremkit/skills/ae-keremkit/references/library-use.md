# Using Library Items

Goal: "add the gold counter, 0 to 25,000, at 2 seconds" in ~4 tool calls - no design, no code.

## 1. Find

`keremkit.py search gold counter --type item` - accents and case are ignored; English and local names, tags and summaries are searched; the best few rows come back with their folder.

- One clear hit -> continue.
- Several close hits -> offer up to 3 in one line each (ID, name, summary); let the user pick.
- No hit -> say it is not in the library and offer to design it (do not start designing unasked).

## 2. Read

Only that item's `meta.json`: comp name, file, size/fps, params, deps. If `deps.fonts` might be missing, add `font.list_missing` to the first batch and warn (the item can still be placed).

## 3. Bring it in, set it, place it

Batch A (works by names):
- `folder.create` `05_LIBRARY` if missing
- `project.merge {path: <folder>/item.aep, folderName: <ID>, parentFolder: "05_LIBRARY"}` - skip if a `LIB_<ID>_...` comp is already in the project (reuse it)
- Non-default values? `comp.duplicate` -> `LIB_UI-008_GoldCounter__01` (next free number) and set params **on the duplicate** (`property.set` / `text.set_content` per `meta.params`)
- `comp.info` on the comp to use -> its numeric id

Batch B (needs that id):
- `layer.create_footage {comp: <target>, sourceItemId: <id>, name: "UI_GoldCounter"}`
- position (`transform.set`) - the user's, else `meta.suggested_position`, else centre
- time (`layer.set_timing startTime`)
- verify: `layer.bounds` (inside title-safe), `comp.sample` if timing matters

A parameter whose `target.comp` is a **nested** comp: that nested comp is shared by every copy. For a single use, set it directly. For a second copy with different values, duplicate the nested comp too and swap it into the copy with `layer.replace_source` before setting values.

If the user asks for a value that is not a defined parameter, change the property anyway, then ask in one line whether to make it a permanent parameter.

Size mismatch (e.g. 16:9 item into a 9:16 comp): scale to fit the safe area and mention it.

## 4. Report

One line: "Gold Counter (UI-008) added to `SCN_Intro`: 0→25,000, 3 s, starts at 0:02." Warnings on a second line.
