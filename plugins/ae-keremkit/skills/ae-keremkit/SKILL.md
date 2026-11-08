---
name: ae-keremkit
description: After Effects editing kit for Claude - remembers the user's preferences, runs a whole edit from a named edit style, cuts silences tightly with quick time-based fixes ("add 1 s of breathing room at 0:10-0:12"), builds flexible Whisper subtitles, applies sound-effect rules, keeps a searchable design library, copies a look from an image, HTML/CSS, SVG, Lottie or AE project, and saves checkpoints. Use it for ANY After Effects work through the aftereffects MCP tools - cutting, subtitles/captions, applying or creating an edit style, saving or reusing a design ("save this", "add the gold counter"), copying a theme from a reference ("use the look of this poster"), sound effects, safe areas, render - in any language, even when the user does not name the kit.
license: MIT
compatibility: Needs an After Effects MCP server exposing ae_do / ae_catalog / ae_context (tested with @kumoproductions/mcp-aftereffects), file or shell access to the user's computer, Python 3.9+, ffmpeg; Whisper for subtitles.
---

# AE KeremKit

Makes Claude edit in After Effects like a disciplined editor who remembers everything - preferences, named edit styles, a design library, past problems - while spending as few tokens as possible.

## Language

The kit's default language is English. **Reply in the language the user writes in** unless `language.reply` in preferences says otherwise. Question templates in the references are written in English - translate them naturally; never mix languages in one message. Keep replies short: what was done, in 1-3 lines, no step-by-step narration.

Library items, categories and styles always have an English `name`. If the user works in another language, `language.library` holds that language code and items also get a local name in `names` (e.g. `{"tr": "Altın Sayaç"}`) so they can be found in both languages. When `language.library` is null and the user writes in a language other than English, set it to that language (no question needed) and mention it once.

## The KeremKit home folder

Everything that changes over time lives in a folder on the user's computer, not in this skill, so the skill never needs re-installing:

```
KeremKit/
  settings/preferences.json   remembered preferences (null = never asked)
  settings/categories.json    library categories (user-extendable)
  library/CATALOG.tsv         one row per item and style - search it, never read it whole
  library/items/<category>/<ID>_<slug>/   item.aep, meta.json, preview.png, sources/
  styles/<slug>/style.json    edit styles;  styles/_archive/<slug>/v###/  previous versions
  learning/house-style.md     the user's general design rules
  learning/known-issues.md    solved problems (search by keyword)
  tools/                      keremkit.py, cutlist.py, subtitles.py, tokens.py, digest.py
```

Locate it with `python tools/keremkit.py where` (reads `~/.keremkit.json`; default `~/Documents/KeremKit`). On `NOT_SET_UP`, or the user's first KeremKit request, run `references/setup.md` first.

**Running the tools:** plain Python (standard library) plus ffmpeg/Whisper, run on the user's computer through whatever access the session has (a device shell, Claude Code's own shell). The same scripts ship in this skill's `scripts/` folder; `keremkit.py init` copies them into `KeremKit/tools/`. Without shell access, stage the needed file(s) into the workspace, run the bundled script there, and write the results back. On Windows the command may be `py` instead of `python`.

## Preferences - remember everything, ask once

- Before anything that depends on a choice (subtitle tool, cut tightness, render format, SFX, versioning...), read it: `keremkit.py pref get <key>`. Never assume a value the user did not give.
- `null` = never answered: ask **once, when it is first needed**, with the templates in `references/preferences.md`; save immediately with `pref set`.
- A lasting preference stated in passing ("always keep captions yellow") is saved right away and confirmed in one line. If it is unclear whether it is global or for one style, ask once.
- Style settings override global ones. A real **conflict** between a style rule and a global rule is never resolved silently - state both and ask.
- New ideas that fit no field go into `custom_rules` or the style's `rules`; the kit grows by conversation. If an idea needs a change to this skill itself, say so and offer an updated version.

## Token rules (always on)

1. **No screenshots by default.** Do not render-and-view frames unless the user asks. Verify with numbers (below). When asked to look, follow `references/verification.md`: economical first, full quality only on a second explicit request. The library preview PNG is written to disk and never opened.
2. Call `ae_context` once per session; then use the context each `ae_do` returns.
3. Several operations = one `batch.run`, with verification reads (`comp.info`, `layer.bounds`, `comp.sample`) at the end of the same batch. An op cannot use an id returned earlier in the same batch - split into two batches when needed.
4. Read little: `layer.info` with `detail: "summary"`; never return a whole project export inline (use `outPath` + `digest.py`); call `ae_catalog <category>` only for the category needed and remember it.
5. `eval.run` is usually disabled - use catalog operations; if a job cannot be done with them, say so.
6. Search catalogs and known issues with the tools or grep; open only the one file needed.
7. Heavy analysis happens outside AE: transcription (Whisper) and cut decisions (`cutlist.py`). Read their one-line results, not the media.
8. Same method failed twice -> stop and report briefly (what, error, likely cause, proposal).
9. Bulk change -> try it on one layer, then apply to all.

## Numeric verification (default, no images)

In the batch that made the change: `comp.info` (structure, order, timing), `layer.bounds` against the comp size and safe areas from `preferences.standards`, `text.measure` (fit), `comp.sample` at 3-5 times (motion), `font.list_missing` / `footage.list_missing`.

## Checkpoints

Before anything hard to undo - deleting comps/layers, `project.reduce`, `project.merge`, `ae_project_import_json`, `project.rename`, a batch above `standards.checkpoint_batch_threshold` ops, saving to the library, starting a style run - save a numbered copy: `ae_save_project(path=<dir>/<Project>_v###.aep)` (highest existing number + 1). At most one per task. Small edits need none: every `ae_do` call is one undo step (`project.undo`). Never delete checkpoints.

## Naming (short form)

ASCII names inside AE (accents and special letters transliterated: ş→s, ü→u, é→e...); readable names in any language live in metadata. Comps: `SCN_` scene, `PRE_` precomp, `LIB_` library item, `TPL_` template, `OUT_` render. Layers: `TXT_ SUB_ SHP_ UI_ BG_ ICN_ FTG_ AUD_ SFX_ CTRL_ NULL_ ADJ_ CAM_ LGT_ MATTE_`. Format `PREFIX_PascalName[_01]`. Full tables: `references/standards.md`.

## What to read when

| Situation | Read |
|---|---|
| First use, `NOT_SET_UP`, or the user asks to (re)configure | `references/setup.md` |
| A preference is null, the user states one, or a question is needed | `references/preferences.md` |
| The user names an edit style, wants a new one, or an edit just finished | `references/edit-styles.md` |
| Cutting silences, tight cuts, "add/remove time at X s" fixes | `references/cutting.md` |
| Subtitles (Whisper, line/word rules, highlights, placement) | `references/subtitles.md` |
| Sound effects | `references/sound-effects.md` |
| The user shares a reference (image, HTML, CSS, SVG, Lottie, project) to copy its look | `references/design-import.md` |
| Saving something to the library, new categories | `references/library-save.md` |
| Placing a saved item | `references/library-use.md` |
| The user asks to check / look / take a screenshot | `references/verification.md` |
| Project structure, safe areas, motion defaults, render | `references/standards.md` |
| Something failed | `references/troubleshooting.md` |

## Always-on habits

- Before designing anything new, read `learning/house-style.md` and the active style.
- After designing a reusable element, offer once, in one line, to save it to the library.
- After finishing an edit, ask once whether to save what was learned (`edit-styles.md` -> Learning). Do not ask again if declined.
- New problem solved -> one entry in `learning/known-issues.md`.
