---
name: ae-keremkit
description: After Effects editing kit for Claude - remembered preferences, whole edits from a named edit style, design plans that reuse library items before building new ones, audio-based silence cutting with retake removal, transcript correction (asks when unsure), edit plans on word indices with rhythm checks, a technique catalogue (J/L cuts, jump-cut zoom, glass frames, flashes, audio clean-up, multi-format, QC), layer organisation, Whisper subtitles, synthesised SFX, a design library (items, projects, multi-frame previews), free stock elements and logos with their licences, copying a look from images, web pages or reference videos, learning .ffx presets, publishing, checkpoints, Premiere Pro (XML export, Premiere MCP, styles from .prproj), video downloads (YouTube, TikTok, Instagram...) with a Premiere-safe mode and repair. Use it for ANY After Effects or Premiere work - cutting, subtitles, styles, audio, designs, presets, formats, QC, render, downloading footage - in any language, even unnamed.
license: MIT
compatibility: Needs an After Effects MCP server exposing ae_do / ae_catalog / ae_context (tested with @kumoproductions/mcp-aftereffects), file or shell access to the user's computer, Python 3.9+, ffmpeg; Whisper for subtitles; optional Premiere MCP (premiere-pro-mcp) and yt-dlp (installed by the kit).
---

# AE KeremKit

Makes Claude edit in After Effects like a disciplined editor who remembers everything - preferences, named edit styles, a design library, past problems - while spending as few tokens as possible.

## Language

The kit's default language is English. **Reply in the language the user writes in** unless `language.reply` in preferences says otherwise. Question templates in the references are written in English - translate them naturally; never mix languages in one message. Keep replies short: what was done, in 1-3 lines, no step-by-step narration. **State only what was checked on the user's machine** - never suggest backups, recovery, sync or version history that were not verified there; when nothing was found, say so.

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
  tools/                      keremkit.py, transcript.py, cutlist.py, subtitles.py, editplan.py, audio.py,
                              sfx.py, qc.py, techniques.py, tokens.py, presets.py, videoref.py, previews.py, assets.py, digest.py,
                              prproj.py, download.py;  tools/bin/  yt-dlp (installed by download.py setup)
```

Locate it with `python tools/keremkit.py where` (reads `~/.keremkit.json`; default `~/Documents/KeremKit`). On `NOT_SET_UP`, or the user's first KeremKit request, run `references/setup.md` first.

**Tools version:** once per session, `python tools/keremkit.py version` (this skill is `KeremKit 1.11.0`). If it differs or fails, say so in one line ("KeremKit tools are older than the skill - say 'update KeremKit' to update them") and carry on with what works. Update the tools (`scripts/keremkit.py init`, or copying `scripts/` into `KeremKit/tools/`) **only when the user asks for exactly that**.

## The skill is read-only - the kit grows in the home folder

Never edit, repackage or re-version this skill, its scripts or the kit's own files in `KeremKit/tools/`, and never write a CHANGELOG or version number - not even to add something new. Everything learned goes into the KeremKit home folder and works right away:

- A new technique -> `techniques.py add` (card in `settings/techniques.json`).
- A new tool, script or long how-to for it -> `KeremKit/extensions/<id>/` (`<name>.py` + `README.md`); the card's `--how` points there (`"extensions/<id>/README.md"`). Extensions use only the standard library, like the kit's tools.
- A rule or preference -> `custom_rules` / `pref set`; a solved problem -> `learning/known-issues.md`; a design -> the library.
- Something that truly needs the skill itself changed (a bug in a kit tool, a wrong instruction) -> one entry in `learning/skill-change-requests.md` (file, problem, proposed change) and one line to the user. The skill's maintainer applies it.

**Running the tools:** plain Python (standard library) plus ffmpeg/Whisper, run on the user's computer through whatever access the session has (a device shell, Claude Code's own shell). The same scripts ship in this skill's `scripts/` folder; `keremkit.py init` copies them into `KeremKit/tools/`. Without shell access, stage the needed file(s) into the workspace, run the bundled script there, and write the results back. On Windows the command may be `py` instead of `python`.

## Preferences - remember everything, ask once

- Before anything that depends on a choice (subtitle tool, cut tightness, render format, SFX, versioning...), read it: `keremkit.py pref get <key>`. Never assume a value the user did not give.
- `null` = never answered: ask **once, when it is first needed**, with the templates in `references/preferences.md`; save immediately with `pref set`.
- A lasting preference stated in passing ("always keep captions yellow") is saved right away and confirmed in one line. If it is unclear whether it is global or for one style, ask once.
- Style settings override global ones. A real **conflict** between a style rule and a global rule is never resolved silently - state both and ask.
- New ideas that fit no field go into `custom_rules` or the style's `rules`; the kit grows by conversation, never by changing the skill (see "The skill is read-only").

## Token rules (always on)

1. **No screenshots by default.** Do not render-and-view frames unless the user asks. Verify with numbers (below). When asked to look, follow `references/verification.md`: economical first, full quality only on a second explicit request. Library previews are never opened by Claude - but they are **shown to the user** whenever items are offered (`references/library-use.md` -> Showing options).
2. Call `ae_context` once per session; then use the context each `ae_do` returns.
3. Several operations = one `batch.run`, with verification reads (`comp.info`, `layer.bounds`, `comp.sample`) at the end of the same batch. An op cannot use an id returned earlier in the same batch - split into two batches when needed.
4. Read little: `layer.info` with `detail: "summary"`; never return a whole project export inline (use `outPath` + `digest.py`); call `ae_catalog <category>` only for the category needed and remember it.
5. `eval.run` is usually disabled - use catalog operations; if a job cannot be done with them, say so.
6. Search catalogs and known issues with the tools or grep; open only the one file needed.
7. Heavy analysis happens outside AE: transcription (Whisper), corrections and repeats (`transcript.py`), cut decisions (`cutlist.py`). Read their short results and the compact transcript, never the media or raw JSON.
8. Same method failed twice -> stop and report briefly (what, error, likely cause, proposal).
9. Bulk change -> try it on one layer, then apply to all.

## Numeric verification (default, no images)

In the batch that made the change: `comp.info` (structure, order, timing), `layer.bounds` against the comp size and safe areas from `preferences.standards`, `text.measure` (fit), `comp.sample` at 3-5 times (motion), `font.list_missing` / `footage.list_missing`.

## Checkpoints and saves

Before anything hard to undo - deleting comps/layers, `project.merge`, `ae_project_import_json`, `project.rename`, a batch above `standards.checkpoint_batch_threshold` ops, starting a style run - save a numbered copy: `ae_save_project(path=<dir>/<Project>_v###.aep)` (highest existing number + 1). At most one per task. Small edits need none: every `ae_do` call is one undo step (`project.undo`). Never delete checkpoints.

- **`project.reduce`** (library saves) never runs on the user's file: `keremkit.py save-prep` copies it, Claude opens the copy and checks the context's `project.file`. See `references/library-save.md`.
- **Saves are proven on disk**: `keremkit.py save-check` after a library save or loop (the project unchanged, every file written); a checkpoint `ae_save_project(path=...)` -> `keremkit.py stat <path>`. `saved:true` alone is not proof. Create folders before saving.
- **`project.undo` cannot be trusted to bring back a reduced project** - reopen the work copy instead.

## Stop rules

A response that contradicts the expected state - a save that left no file, `project.file` not the path it should be, `undone: N` but nothing changed, an unexpected item count - **stops all AE calls**. Then: do not `project.open`, `project.new`, `project.clear` or save over anything. `ae_save_project(path=<home>/library/_work/rescue_<time>.aep)`, `keremkit.py stat` the user's files, report what was seen in 2-3 lines and ask.

## Naming (short form)

ASCII names inside AE (accents and special letters transliterated: ş→s, ü→u, é→e...); readable names in any language live in metadata. Comps: `SCN_` scene, `PRE_` precomp, `LIB_` library item, `TPL_` template, `OUT_` render. Layers: `TXT_ SUB_ SHP_ UI_ BG_ ICN_ FTG_ AUD_ SFX_ CTRL_ NULL_ ADJ_ CAM_ LGT_ MATTE_`. Format `PREFIX_PascalName[_01]`. Full tables: `references/standards.md`.

## What to read when

| Situation | Read |
|---|---|
| First use, `NOT_SET_UP`, or the user asks to (re)configure | `references/setup.md` |
| A preference is null, the user states one, or a question is needed | `references/preferences.md` |
| The user names an edit style, wants a new one, or an edit just finished | `references/edit-styles.md` |
| Any spoken recording: transcribe, fix mis-heard words, remove retakes/repeats/fillers | `references/transcript.md` (first), then `references/cutting.md` |
| Cutting silences, tight cuts, "add/remove time at X s" fixes | `references/cutting.md` |
| Voice-led edit with many shots: plan shots on words, check rhythm, get frame-exact times | `references/edit-plan.md` |
| The user gives a reference video to learn from or recreate | `references/video-reference.md` |
| Subtitles (Whisper, line/word rules, highlights, placement) | `references/subtitles.md` |
| Sound effects | `references/sound-effects.md` |
| An element the library doesn't have: stock video, green screen, overlay, sound, music, icon, logo, texture, font, templates | `references/assets.md` |
| Designing something with several parts (intro, title card, a section's graphics) - plan with library items first, ask, then build | `references/design-plan.md` |
| The user shares a reference (image, HTML, CSS, SVG, Lottie, project) to copy its look | `references/design-import.md` |
| Effect presets: learn a folder, answer questions about them, apply one | `references/presets.md` |
| "What can you do with the sound / cuts / ...?", techniques, adding a technique | `references/techniques.md` |
| Audio clean-up, loudness, music, ducking | `references/audio.md` |
| More formats (9:16, 1:1...) from one edit | `references/formats.md` |
| Before the final render, "check everything" | `references/qc.md` |
| Layer order, names, colour labels | `references/organize.md` |
| Chapters, titles, thumbnails, export to Premiere/Resolve | `references/publish.md` |
| Anything in Premiere Pro: a cut as Premiere XML, the Premiere MCP, learning a style from a .prproj | `references/premiere.md` |
| Downloading a video (YouTube, TikTok, Instagram, other sites), "Premiere fix", 4K + repair, a file Premiere won't import | `references/downloads.md` |
| Saving something to the library, new categories | `references/library-save.md` |
| Saving many items (a template pack) or a whole project | `references/library-pack.md` |
| Making previews, repairing broken ones | `references/previews.md` |
| Placing a saved item | `references/library-use.md` |
| The user asks to check / look / take a screenshot | `references/verification.md` |
| Project structure, safe areas, motion defaults, render | `references/standards.md` |
| Something failed | `references/troubleshooting.md` |

## Always-on habits

- Before designing anything new, read `learning/house-style.md` and the active style. A design with several parts starts with a numbered plan: what the library has, what to build new, the cost of each (`references/design-plan.md`, preference `design.plan`).
- After designing a reusable element, offer once, in one line, to save it to the library.
- After finishing an edit, ask once whether to save what was learned (`edit-styles.md` -> Learning). Do not ask again if declined.
- New problem solved -> one entry in `learning/known-issues.md`.
- After an edit, tidy the layers (`organize.md`) unless `organize.mode` is off.
- **Project log:** keep `_keremkit/log.md` next to the project - one dated line per session or milestone (what was done, decisions, open items, the files in use). Read it first when a project is resumed in a new chat; it replaces re-reading the project. Keep it under ~60 lines; summarise older entries.
- Something seems broken on the user's machine -> `keremkit.py doctor`.
- First library use in a session -> `previews.py scan --brief`; broken previews -> ask once (`previews.md` -> Repairing old previews).
