# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

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
