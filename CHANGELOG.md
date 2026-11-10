# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.7.0] - 2026-11-10

### Changed
- **Library saves use far fewer calls.** `keremkit.py save-prep` (note the project, copy it, create the folders) and `save-check` (project unchanged, every item file written) replace the separate copy / stat / mkdir steps; checks in a pack loop happen once at the end instead of after every item.
- **Previews through the render queue:** `previews.py queue` prints one batch of ops for any number of items, `previews.py auto` builds static and continuous previews and prints a second batch only for animated ones - 2-4 AE calls in total instead of 2-4 per item. Frames are TIFF with alpha, so black items no longer vanish on black.
- Previews pick their backdrop: light grey behind dark content, dark grey behind light content.
- `library-save.md` covers one item only; packs and whole projects moved to `library-pack.md`, previews and repair to `previews.md` - less to read per save.

### Added
- `keremkit.py add-many items.tsv`: folders, meta.json and catalog rows for many items from one table instead of one hand-written meta.json each.
- Known issues: a save blocked by the "second script" dialog, glass/adjustment items that render empty alone.

## [1.6.0] - 2026-11-10

### Added
- Design plans: before a design with several parts, Claude splits it into parts, searches the library for all of them at once (`keremkit.py plan`), and asks one numbered question - use what's there, build better from scratch, or build what's missing - with a low / medium / high cost per part and the proposed items' previews in one image. Preference `design.plan` (`big` by default, `always`, `off`).

## [1.5.1] - 2026-11-10

### Added
- Library options are shown in the chat: `previews.py compare` puts the previews of the offered items into one sharp image (full-width rows, numbered in the order of the reply, with id and name); Claude sends it without opening it.
- Sharper previews: 360 px frames for vertical items, 640 px for horizontal ones.

## [1.5.0] - 2026-11-10

### Fixed
- **Library saves can no longer touch the user's project.** `project.reduce` runs only on a shell work copy (`keremkit.py safe-copy`), every save is proven on disk (`keremkit.py stat`), and the pack loop reopens the work file instead of trusting `project.undo`. Follows a real incident where a save overwrote a project.
- Blank library previews: the old "one frame at 65 %" rule often caught transparent or empty moments.
- Outdated tools in the KeremKit folder went unnoticed (e.g. `add` asking for `name_tr`/`name_en`); the skill now checks `keremkit.py version` once per session and updates them.

### Added
- `previews.py`: finds broken previews (`scan`: size, pixels and identical images), reads probe frames as numbers to tell static, animated and continuously moving items apart (`pick`), and builds a 6-frame preview over a dark backdrop (`sheet`). Claude offers once to repair broken previews; `library.preview_repair: never` turns the question off.
- Stop rules: an unexpected tool response stops all AE calls, saves a rescue copy and asks.
- Only verified facts: no recovery or backup advice that wasn't checked on the user's machine.
- Troubleshooting: lost or overwritten project files; MCP behaviours seen in real use.
- `keremkit.py version`, `stat`, `safe-copy`.

## [1.4.0] - 2026-11-10

### Added
- `editplan.py`: edits written as shots on word indices (`edit.json`), checked against rhythm rules (shot length, per-kind limits, no two host shots in a row, no repeated clip seconds, keys per sentence) with frame-exact times for the build.
- `transcript.py words` (every word with its index) and index-based corrections (`{"index": 28, "new": "Grok"}`).
- `videoref.py`: a reference video becomes a small package - shots, motion windows, colours, audio onsets and time-stamped contact sheets (dense where the picture moves) - so Claude can learn or recreate a style for a few thousand tokens. Standard library + ffmpeg.
- `sfx.py`: licence-free synthesised whoosh, impact, pop, tick, click, glitch, flash, riser and typing sounds, normalised to the same peak.
- Techniques: cut on the word, human editorial rhythm, one clip for many moments, glass frame, blurred ambient backlight, moving perspective grid, keyword flip, flicker-in emphasis, bleach flash, negative flick, strobe, burn-out frames, film grain, typewriter / giant-word / photo-card pages.
- `keremkit.py reindex` rebuilds the catalog from the meta files.
- References: edit plans, learning from reference videos; AE speed tips; logo-rights rules.
- Repository consistency tests (`tests/test_repo.py`): plugin metadata, `SKILL.md` frontmatter, reference links, docs links, examples, changelog/version agreement, Python 3.9 syntax, standard-library-only imports and the claude.ai zip.
- `requirements-dev.txt` and pytest configuration in `pyproject.toml`.
- CI: manual runs, pip cache, concurrency, Ubuntu ffmpeg, build artifact upload and a tag/version check before release.

### Changed
- Silence detection is relative to the speaker: the median level inside Whisper's words minus 10 dB (`--rel-db`), instead of a fixed offset from the file's average loudness. Pure Python envelope, no extra dependencies. Cut fades are 8 ms.

### Fixed
- Subtitle plan zones without a cut list ended at twice the placement start (`at` was added twice).
- `cutlist.py cut/add/restore` with reversed, negative or out-of-range values now stop with an error instead of a silent "OK".
- `keremkit.py pref set` into a parent that is `null` (e.g. `subtitles.look.font`) crashed; parents are created.
- `keremkit.py add` on a missing or broken file printed a traceback; it now prints one error line.
- Catalogs with missing columns (`search`, `category`, `type`) crashed search and summary; missing columns are filled in.
- `transcript.py review --cutlist` used the first word's middle as the sentence time and dropped sentences that started before `--from`; it now uses the sentence's start and end.
- `keremkit.py unpack` trusted folder paths in a package's manifest and could write outside the KeremKit folder; such packages are rejected. `pack` refuses catalog rows that point outside the folder.
- Whisper output without word timestamps gave a misleading "check cut list" error in `subtitles.py`; words are now spread over each segment with a warning, like `cutlist.py`.
- Audio-only renders to `.m4a` failed (PCM in an MP4 container); AAC is used.
- `digest.py` printed `None` for missing comp fields; `presets.py` crashed on a `meta.json` without an id; `audio.py analyze` mis-reported silent files; renders fall back to `-vsync` on ffmpeg before 5.1.
- `tools/build_skill.py` writes POSIX paths inside the zip, so builds made on Windows are portable.
- Unused code removed (`tokens.py`, `subtitles.py`, `tools/make_art.py`, a test import).

## [1.3.0] - 2026-11-09

### Added
- Techniques catalogue (`techniques.py`, `assets/techniques.json`): cuts (jump cut, jump-cut zoom, J-cut, L-cut, cutaway, match cut, cut on action, smash cut, whip, speed ramp, montage), motion, audio, formats, QC, organisation and publishing. Asking for a kind of work lists the techniques with names and explanations first; users can add their own.
- `audio.py`: analysis (LUFS, true peak, range, noise floor) with advice, a clean-up chain (high-pass, denoise, de-ess, EQ, compression, two-pass loudness normalisation) and music ducking.
- `qc.py`: render checks (black, frozen, long silence, loudness, true peak) and thumbnail frame candidates.
- `cutlist.py zoom` (jump-cut zoom and emphasis punch-ins as one Scale expression) and `cutlist.py export` (EDL, FCPXML).
- `transcript.py review --cutlist` for timeline times (chapters).
- Library categories `project` (whole projects as templates with swappable footage) and `technique`.
- `keremkit.py doctor`, `pack`/`unpack` for sharing styles and items with font/plugin requirements.
- References for audio, formats, QC, layer organisation (automatic, preference-driven), publishing, and a project log habit.
- Lessons from the first real library import (135 items from a template pack): fast split loop with `project.reduce` + `project.undo`, one AE call at a time, `project.rename` verification, nested-comp parameters, faster-whisper decoder workaround.

### Fixed
- Catalogs created by 1.0 (`name_tr`/`name_en` columns) broke search; they are now read transparently and migrated by `init`.

## [1.2.0] - 2026-11-09

### Added
- `transcript.py`: compact transcript review with doubtful words marked; time-anchored word corrections that keep timestamps (multi-word too); detection of retakes, repeated phrases, stutters and filler sounds with confidence levels; `accept` for the user's answers.
- Smart correction workflow: Claude fixes mis-heard words from context, reports them as `time - old - new`, and asks before applying the ones it isn't sure about. Confirmed names go into a glossary that is also passed to Whisper as an initial prompt.

### Changed
- `cutlist.py build` finds pauses in the real audio (ffmpeg `silencedetect`, threshold from the file's loudness) and confirms them with the words; noise without words is dropped; `--remove` cuts retakes and repeats. Word-only cutting remains as a fallback.

## [1.1.0] - 2026-11-09

### Added
- `presets.py`: learns `.ffx` effect presets through a lab comp - effects, keyframed properties (timing, values, easing), expressions and text animators per preset; third-party plugins detected from effect match names and failed applies; `show` for answering questions; `insights` summarises patterns across all presets.
- `fx-preset` library category; presets that need a plugin are labelled `[requires plugin]`.
- `.gitattributes` with LF line endings; the skill builder tolerates CRLF checkouts.

## [1.0.0] - 2026-11-08

### Added
- Edit styles: inputs, structure rules, formats, cutting, subtitles, look, screen recording, sound effects, versioned archive.
- `cutlist.py`: word-based silence cutting with tight/normal/relaxed presets, frame snapping, click-free audio, quick fixes (`add`, `cut`, `restore`, `undo`, `map`) and ffmpeg rendering.
- `subtitles.py`: rule-driven cues (words per line, lines, sentence modes, orphan handling, glue words for seven languages), highlights, multi-source plans with zones, SRT output and After Effects expressions.
- `keremkit.py`: home folder setup, preferences, extensible categories, multilingual library catalog, style archiving.
- `tokens.py`: design tokens from HTML/CSS, SVG and Lottie (palette, type, radii, glows, easing) with After Effects conversions; scoped extraction.
- Design import: copy a look from any reference, with an optional HTML preview step for images.
- `digest.py`: compact summary of an After Effects project export for learning styles.
- First-run setup, numeric verification levels, checkpoints, naming and safe-area standards.
