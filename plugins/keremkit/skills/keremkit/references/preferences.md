# Preferences

All remembered choices live in `KeremKit/settings/preferences.json`. Read with `keremkit.py pref get <key>`, write with `pref set key=value` (JSON values), list unanswered ones with `pref missing [section]`.

`pref set` replaces the whole value of a key. For lists (`custom_rules`, `sfx.rules`, `paths.footage_folders`), `pref get` the list, change it, and set the full list back.

## Principles

- **Never assume, never ask twice.** `null` means never answered: ask when the value is first needed, save the answer, don't ask again. A non-null value is the user's choice - use it silently.
- **"Doesn't matter / you decide"** is an answer: save the sensible default and say in one line which one you picked.
- **Scope.** A preference is global unless the user ties it to a style. Style values override global ones. If the scope is unclear, ask once: "Should this apply to all edits, or only to <style>?"
- **Conflicts.** If a global rule and a style rule disagree in a way that matters now (e.g. SFX off globally, the style wants a whoosh on every transition), state both and ask which wins this time and whether to update one of them.
- **Stated in passing still counts.** "Keep the captions a bit lower, always" -> save now, confirm in one line. A one-off ("for this video") is not saved.
- **One question at a time** where possible; recommended option first.
- **Language.** All templates below are in English; ask in the user's language.

## Keys and when to ask

| Key | Ask when | Question |
|---|---|---|
| `language.reply` | never (follow the user) | - |
| `language.library` | set silently from the user's language (SKILL.md) | - |
| `paths.materials.*` | setup / first time a material is needed | "Which folder holds your <kind> files?" |
| `paths.presets` | first time presets are learned | "Which folder holds your After Effects presets?" |
| `paths.footage_folders` | first edit that needs footage | "Which folder holds the material for this edit? (Tell me once - I'll remember it.)" |
| `paths.projects` | the first time an unsaved project must be saved (library save, checkpoint, save-prep) | "Where do you keep your main projects? I'll suggest saving new ones there." |
| `subtitles.enabled`, `engine`, `tools.whisper.model` | setup; the model again at the first transcription if still null - never chosen by Claude | see `setup.md` |
| `premiere.project_folder` | the first time a Premiere project is created | "Where should I save new Premiere projects? (1) your project folder `<paths.projects>`, (2) next to the video (e.g. `<video folder>/<video> - Bileşenler/`), or (3) ask me each time" → `projects` / `next_to_video` / `ask` (asks for `paths.projects` too if it is null) |
| `premiere.project_naming` | the first time a Premiere project is created | "How should Premiere projects be named? e.g. `{video}_{style}` → `IMG_3810_ecomelih.prproj`, `{date}_{video}`, or your own pattern" (fields: `{video}` `{style}` `{date}` `{part}` `{n}`) |
| `premiere.sequence_naming` | the first time a sequence is created | "How should sequences be named? e.g. `{video}_{format}` → `IMG_3810_9x16`, or the same as the project" |
| `download.mode` | default `premiere_fix`; changed when the user says "always ..." (`best_repair` for 4K + Premiere, `best` untouched, `ask` every time) | `downloads.md` |
| `download.folder` | default `ask` - every download asks for the folder (offering `download.last_folder`); `fixed` + `last_folder` only when the user says to always use one | `downloads.md` |
| `download.cookies` | default `ask` - only when a video needs sign-in | `downloads.md` -> Sign-in |
| `download.encoder` | default `auto` (GPU first) | `downloads.md` -> Repairing |
| `subtitles.rules.*` | first subtitle build | see `subtitles.md` |
| `subtitles.font`, `subtitles.look` | first subtitle build without a style | "Do you have a font and look in mind for subtitles, or shall I suggest one?" |
| `cutting.repeats` | first cut of a spoken recording | "Should I remove retakes and repeated phrases automatically? (I will still ask about unclear ones.)" |
| `subtitles.glossary` | a video with names/brands/jargon | "Are there names or terms I should always spell exactly?" |
| `cutting.preset` | first cut | "How tight should the cuts be? Tight (almost no pauses) / Normal / Relaxed" |
| `sfx.enabled` | first edit that could use SFX | "Should edits use sound effects?" |
| `render.mode` | first finished edit | "Should I render the final video? Start automatically / Ask me first / Only add it to the queue" |
| `render.format` | first render | "What should the default output be? (e.g. MP4 H.264, ProRes 422)" |
| `style_versioning.mode` | first time a style changes | "When a style changes, should I keep the old version? Every change / Only big changes / Only certain kinds (e.g. colors) / Never" |
| `design_import.preview` | first time a look is copied from an image | see `design-import.md` (HTML preview question) |
| `library.preview_repair` | broken previews found by `previews.py scan` | see `previews.md` -> Repairing old previews (`never` = don't ask again) |
| `design.plan` | default `big` - never asked; changed when the user says so ("don't ask, just build" -> `off`; "always show me the plan" -> `always`) | `design-plan.md` |
| `logos.confirm` | default `ask`; `off` when the user says logos may be added without asking | `assets.md` -> Logos |
| `library.ask_parts` | default `ask`; `always` / `never` when the user says so | `library-save.md` -> 1b |
| `presets.root` | default `<User Presets>/KeremKit`; changed only when the user names another folder | `presets.md` |
| `presets.save_method` | the first time a preset is saved | "Presets can't be written by scripts. Shall I (1) tell you the exact folder and name so you save it in AE - cheapest - or (2) do it myself by screen control - works, but costs ~10-25k tokens per preset and can break?" -> `user` / `screen` (`ask` if they want to choose each time) |
| `assets.allow_attribution` | default false; true when the user accepts items that need a credit | `assets.md` |
| `audio.target_lufs` | first audio processing without a known destination | "Where will this be published? (YouTube -14 LUFS, podcast -16, broadcast -23)" |
| `formats.targets` | first multi-format request | "Which formats do you publish to? (16:9, 9:16, 1:1, 4:5)" |
| `qc.mode` | default `ask` | "Should I always run the quality check before the final render?" |
| `organize.mode` | default `auto`; change when the user asks | - |
| `learning.ask_after_edit` | default true | - |

## Style versioning

`style_versioning.mode`: `always` | `major` | `types` | `never`; `rules` holds the user's own words (e.g. `["color changes", "font changes"]` for `types`). "Major" = anything touching structure, inputs, fonts, palette or subtitle rules - not a single value tweak. Archiving stores the change instruction with the old version: `keremkit.py style-archive <slug> --reason "<the user's instruction>"`.

## custom_rules

Durable rules that fit no field: `{"rule": "...", "scope": "global", "added": "YYYY-MM-DD"}`. Read them at the start of an edit (they are short). When several describe the same area, suggest turning them into a proper field or a style section.
