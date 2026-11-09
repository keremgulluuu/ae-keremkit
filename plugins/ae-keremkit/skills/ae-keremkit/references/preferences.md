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
| `subtitles.enabled`, `engine`, `tools.whisper.model` | setup | see `setup.md` |
| `subtitles.rules.*` | first subtitle build | see `subtitles.md` |
| `subtitles.font`, `subtitles.look` | first subtitle build without a style | "Do you have a font and look in mind for subtitles, or shall I suggest one?" |
| `cutting.preset` | first cut | "How tight should the cuts be? Tight (almost no pauses) / Normal / Relaxed" |
| `sfx.enabled` | first edit that could use SFX | "Should edits use sound effects?" |
| `render.mode` | first finished edit | "Should I render the final video? Start automatically / Ask me first / Only add it to the queue" |
| `render.format` | first render | "What should the default output be? (e.g. MP4 H.264, ProRes 422)" |
| `style_versioning.mode` | first time a style changes | "When a style changes, should I keep the old version? Every change / Only big changes / Only certain kinds (e.g. colors) / Never" |
| `design_import.preview` | first time a look is copied from an image | see `design-import.md` (HTML preview question) |
| `learning.ask_after_edit` | default true | - |

## Style versioning

`style_versioning.mode`: `always` | `major` | `types` | `never`; `rules` holds the user's own words (e.g. `["color changes", "font changes"]` for `types`). "Major" = anything touching structure, inputs, fonts, palette or subtitle rules - not a single value tweak. Archiving stores the change instruction with the old version: `keremkit.py style-archive <slug> --reason "<the user's instruction>"`.

## custom_rules

Durable rules that fit no field: `{"rule": "...", "scope": "global", "added": "YYYY-MM-DD"}`. Read them at the start of an edit (they are short). When several describe the same area, suggest turning them into a proper field or a style section.
