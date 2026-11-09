# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

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
