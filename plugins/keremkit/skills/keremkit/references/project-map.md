# Project map - memory across chats, cheap to write and read

One project (After Effects or Premiere) is often continued in several chats. Everything a later chat needs lives next to the project in `_keremkit/`, written as short lines and read by search, never whole.

```
<project folder>/_keremkit/
  log.md        one dated line per session: done, decisions, open items, files (under ~60 lines)
  map.tsv       kind  name  comp  time  purpose  status  updated   (one row per comp / element / open item)
  names.tsv     thing  canonical  note                            (the one name each thing has in this project)
  brandkit.md   colours, fonts, stroke/shadow, logos, motion values, effect values, layer labels of THIS project
```

Create it once: `keremkit.py map init <project.aep|.prproj|folder>` (never overwrites existing files).

## Before work (resuming a project)

1. `keremkit.py map show <project> --open` - what is still open.
2. `keremkit.py map find <project> <words>` - the rows about the part you will touch (comp, element, time).
3. `keremkit.py find <project name>` - earlier session reports in `learning/sessions/` (decisions, colours and reasons behind a KeremKit-built project come free from there).
4. Before building any new element: `map find <project> <colour|font|motion|effect words>` in `brandkit.md`. New elements reuse these values.

Read `log.md` only when the map has no answer.

## While working

- **New comp / element / precomp:** `keremkit.py map add <project> --kind element --name PRE_UI_Card --comp SCN_Main --time 52:00-54:15 --purpose "supply lines with light dots" --status done`. Re-running with the same kind + name + comp updates the row.
- **Open item:** `--kind open --name "film burn tint" --purpose "user pastes Tint by hand" --status open`; set `--status done` when solved.
- **Names:** before naming a new element, `keremkit.py map name <project> iphone mockup`. `CANONICAL` → use that name. `NONE` → make one by `standards.md` naming (e.g. `UI_IPhone17ProMax_<Content>`) and register it: `map name <project> iphone mockup --canon UI_IPhone17ProMax`. A second name for the same thing is refused. QC checks names against this list (`qc.md`).
- **Brand kit:** when a colour, font, size, stroke, ease value, effect setting or layer label is decided or measured, add one line to the matching section of `brandkit.md` (HEX colours, PostScript font names, exact numbers). The user's own taste decisions still belong in their style; `brandkit.md` records what THIS project uses.

## After work

- One line in `log.md` (date, done, decisions, open items, files).
- `map.tsv` rows for what was added or changed; open items closed or added.
- A bulk update ends with the review checklist (`qc.md` → Review checklist); write it into the session report and the log line.

## Cost

`map add` / `map name` / `map find` print one line each (az). Never print `map.tsv` whole on big projects; use `find` or `show --open`.
