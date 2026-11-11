---
name: keremkit
description: KeremKit - editing kit for Claude in After Effects and Premiere Pro. Remembered preferences, whole edits from a named edit style (learned from projects with a full checklist), design plans that reuse a library first, audio-based silence cutting with retake removal, transcript correction, edit plans on word indices, techniques (J/L cuts, jump-cut zoom, audio clean-up, formats, QC), Whisper/CrisperWhisper subtitles, SFX, a design library with previews, free stock elements with licences (photos, video, textures, vectors and .ai sources, icons, logos, 3D, Lottie, fonts, sound), copying a look from references, .ffx presets, Premiere XML/MOGRT/MCP builds, video downloads (YouTube, TikTok, Instagram) with a Premiere-safe mode and repair, and token budgeting with cost estimates. Use it for ANY After Effects or Premiere work, footage or element downloads, in any language, even when the kit is not named.
license: MIT
compatibility: After Effects MCP (ae_do / ae_catalog / ae_context; tested with @kumoproductions/mcp-aftereffects); optional Premiere MCP (premiere-pro-mcp); shell access to the user's computer; Python 3.9+, ffmpeg; Whisper for subtitles; yt-dlp is installed by the kit.
---

# KeremKit

Makes Claude edit in After Effects and Premiere Pro like a disciplined editor who remembers everything (preferences, named styles, a design library, past problems) while spending as few tokens as possible.

## Language

- Reply in the language the user writes in (`language.reply` can override). Translate the English question templates naturally; never mix languages in one message.
- Keep replies short: what was done, 1-3 lines.
- **State only what was checked on the user's machine.** Never suggest backups, recovery, sync or version history that were not verified there.
- Library items, categories and styles have an English `name` plus local names in `names` (`language.library`, set silently from the user's language).

## The KeremKit home folder

```
KeremKit/
  settings/       preferences.json (null = never asked), categories.json, keys.json (API keys, local only)
  library/        CATALOG.tsv (search it, never read it whole), items/<category>/<ID>_<slug>/, mogrt/
  styles/<slug>/  style.json (+ template project); styles/_archive/<slug>/v###/
  assets/         downloaded free elements: <type>/<source>/ + SOURCES.md; INDEX.tsv (check before downloading)
  learning/       house-style.md, known-issues.md, token-notes.md, sessions/, skill-change-requests.md
  tools/          the kit's scripts (+ tools/bin/ yt-dlp);  extensions/  user tools;  models/  local models;  cache/
```

- Find the folder with `python tools/keremkit.py where`. On `NOT_SET_UP` or a first request, follow `references/setup.md`.
- **Tools version:** once per session run `keremkit.py version` (this skill is `KeremKit 2.0.0`). If it differs, say so in one line; update the tools only when the user asks.
- **Tools:** keremkit.py, transcript.py, cutlist.py, subtitles.py, editplan.py, audio.py, sfx.py, qc.py, techniques.py, tokens.py, presets.py, videoref.py, previews.py, assets.py, digest.py, prproj.py, download.py, prbatch.py. They are plain Python (standard library) plus ffmpeg; on Windows the command may be `py`.

## The skill is read-only - the kit grows in the home folder

Never edit, repackage or re-version this skill or `KeremKit/tools/`. What is learned goes to the home folder:
- techniques → `techniques.py add`
- new tools → `extensions/<id>/`
- rules → `custom_rules` / `pref set`
- solved problems → `learning/known-issues.md`
- designs → the library

A real bug or wrong instruction in the skill goes into `learning/skill-change-requests.md` (file, problem, proposed change), plus one line to the user.

## Preferences - remember everything, ask once

- Before anything that depends on a choice, read it with `keremkit.py pref get <key>`. Never assume a value.
- `null` = never asked: ask once, when first needed (`references/preferences.md`), and save at once.
- A lasting preference said in passing is saved and confirmed in one line.
- Style settings override global ones. A real conflict is never resolved silently: state both and ask.

## Token rules (always on)

1. **Estimate first.** Before every operation, say the expected cost in one line: `Tahmini token: az / orta / çok` (in the user's language), with a total for a multi-step plan. Classes and typical costs: `references/token-budget.md`.
2. **No screenshots by default.** Verify with numbers (`references/verification.md`). Library previews and contact sheets are shown to the user; Claude does not open them.
3. **After Effects:**
   - Call `ae_context` once.
   - Many ops go into one `batch.run`, with the verification reads at the end.
   - `layer.info` with `detail: "summary"`.
   - Project exports go to a file, read through `digest.py`.
   - Call `ae_catalog` once per category, then use the cached list.
4. **Premiere:**
   - More than ~5 calls → a `prbatch.py` plan (one line per step).
   - `expected_project_path` on every write.
   - Writes one at a time.
   - Narrow reads (one sequence, one track).
5. **Heavy work runs locally** (Whisper, transcript.py, cutlist.py, subtitles.py, ffmpeg). Read their short results, never media or raw JSON.
6. **Search, don't read:** catalogues, known issues and `assets/INDEX.tsv` via the tools or grep; one reference file at a time; resume a project from `_keremkit/log.md`.
7. **Same method failed twice → stop** and report: what, error, likely cause, proposal.
8. **Bulk change:** try it on one item, then apply to all.

## After every task (always)

1. Append to `learning/token-notes.md`: what was expensive, what saved tokens, and proposals. Write it plainly and completely, without asking; mistakes included.
2. Write the session report `learning/sessions/<date>-<topic>.md` (done, files, decisions, open items, how to continue). Give the user its path in one line.
3. A new problem solved → one entry in `learning/known-issues.md`.

Formats: `references/token-budget.md` section 5.

## Safety: checkpoints, saves, stop rules

- **Checkpoints:** before anything hard to undo, save a numbered copy `<Project>_v###.aep`, at most one per task. Small edits need none.
- **Never reduce or rebuild in the user's own file.** `project.reduce` runs only on a `keremkit.py save-prep` copy. Premiere work runs on a `safe-copy` of the .prproj.
- **Saves are proven on disk:** `keremkit.py stat` / `save-check`. `saved:true` alone is not proof. Create folders first.
- **Stop rule:** an answer that contradicts the expected state (no file after a save, wrong `project.file`, undo that changed nothing, a recovery lock) stops all host calls. Rescue-save to `library/_work/`, `stat` the user's files, report in 2-3 lines and ask.

## Naming

ASCII names inside AE. Comps `SCN_ PRE_ LIB_ TPL_ OUT_`; layers `TXT_ SUB_ SHP_ UI_ BG_ ICN_ FTG_ AUD_ SFX_ CTRL_ NULL_ ADJ_ CAM_ LGT_ MATTE_`; format `PREFIX_PascalName[_01]`. Premiere project and sequence names follow `premiere.project_naming` / `sequence_naming`. Full tables: `references/standards.md`.

## What to read when

| Situation | Read |
|---|---|
| First use, `NOT_SET_UP`, (re)configure | `references/setup.md` |
| A preference is null or the user states one | `references/preferences.md` |
| Cost estimates, saving tokens, token notes, session reports | `references/token-budget.md` |
| A named edit style, a new style, learning a style from a project | `references/edit-styles.md` |
| Spoken recording: transcribe, fix words, retakes/repeats | `references/transcript.md`, then `references/cutting.md` |
| Cutting silences, "add/remove time at X s" | `references/cutting.md` |
| Voice-led edit with many shots | `references/edit-plan.md` |
| A reference video to learn from | `references/video-reference.md` |
| Subtitles | `references/subtitles.md` |
| Sound effects | `references/sound-effects.md` |
| Free elements: photo, video, texture, background, vector/.ai, icon, logo, 3D, Lottie, font, sound, templates; "which sites / what can I download?" | `references/assets.md` |
| A design with several parts | `references/design-plan.md` |
| Copying a look from a reference | `references/design-import.md` |
| Effect presets (.ffx) | `references/presets.md` |
| "What can you do with ...?", techniques | `references/techniques.md` |
| Audio clean-up, loudness, music, ducking | `references/audio.md` |
| More formats (9:16, 1:1...) | `references/formats.md` |
| Before the final render | `references/qc.md` |
| Layer order, names, colour labels | `references/organize.md` |
| Chapters, titles, thumbnails, export to other editors | `references/publish.md` |
| Anything in Premiere Pro (XML, MCP, MOGRT, project/sequence names, styles from .prproj) | `references/premiere.md` |
| Downloading a video, Premiere fix, 4K + repair | `references/downloads.md` |
| Saving to the library / a pack / a whole project | `references/library-save.md`, `references/library-pack.md` |
| Previews | `references/previews.md` |
| Placing a saved item | `references/library-use.md` |
| The user asks to look / take a screenshot | `references/verification.md` |
| Project structure, safe areas, motion, render | `references/standards.md` |
| Something failed | `references/troubleshooting.md` |

## Always-on habits

- Before designing, read `learning/house-style.md` and the active style. A design with several parts starts with a numbered plan.
- Offer once to save a reusable element. After an edit, ask once whether to save what was learned.
- Tidy layers after an edit (`organize.md`) unless `organize.mode` is off.
- **Project log** `_keremkit/log.md` next to the project: one dated line per session (done, decisions, open items, files). Read it first when resuming. Under ~60 lines.
- Something broken on the user's machine → `keremkit.py doctor`. First library use in a session → `previews.py scan --brief`.
