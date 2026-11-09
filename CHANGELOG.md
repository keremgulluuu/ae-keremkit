# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Repository consistency tests (`tests/test_repo.py`): plugin metadata, `SKILL.md` frontmatter, reference links, docs links, examples, changelog/version agreement, Python 3.9 syntax, standard-library-only imports and the claude.ai zip.
- `requirements-dev.txt` and pytest configuration in `pyproject.toml`.
- CI: manual runs, pip cache, concurrency, Ubuntu ffmpeg, build artifact upload and a tag/version check before release.

### Fixed
- `tools/build_skill.py` writes POSIX paths inside the zip, so builds made on Windows are portable.

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
