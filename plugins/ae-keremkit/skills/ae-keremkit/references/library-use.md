# Using Library Items

Goal: "add the gold counter, 0 to 25,000, at 2 seconds" in ~4 tool calls - no design, no code.

## 1. Find

`keremkit.py search gold counter --type item` - accents and case are ignored; English and local names, tags and summaries are searched; the best few rows come back with their folder.

- One clear hit -> continue.
- Several close hits -> offer up to 3 in one line each (number, ID, name, summary) **and show them** (below); let the user pick by number.
- No hit -> say it is not in the library and offer to design it (do not start designing unasked).

## Showing options

Whenever library items are offered - search results, "which animated titles do I have?", "show me UI-008" - the user sees their previews in the chat, in **one** image:

1. `previews.py compare <ID> [<ID> ...] -o <home>/library/_work/compare.png` - each item's preview as a full-width row (1920 px), numbered 1, 2, 3 in the same order as the reply, with its ID and name.
2. Put that file in the chat with the session's send-file tool (when the file is on the user's computer, bring it into the session first). **Don't open or Read it** - the user looks, Claude doesn't. If the session has no way to send files (e.g. Claude Code in a terminal), give the file's path in one line instead.
3. `WARN ... preview is empty` -> mention it in the same line and offer to repair (`library-save.md` -> Repairing previews).

Up to 4 items per image; for more, show the best 4 and say how many more there are.

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
