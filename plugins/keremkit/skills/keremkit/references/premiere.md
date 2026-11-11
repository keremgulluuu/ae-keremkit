# Premiere Pro

The kit edits in After Effects first; Premiere is a second target for the same work. Transcript, cuts and subtitles are shared (`transcript.md`, `cutting.md`, `subtitles.md`); only the last step differs. There are two ways to get the work into Premiere:

| Route | When | How |
|---|---|---|
| **Files** (no MCP needed) | a cut, SRT captions, a finished AE render | `cutlist.py export --format xmeml` + `subs.srt` -> the user imports them |
| **Premiere MCP** (`premiere-pro` server, e.g. `leancoderkavy/premiere-pro-mcp`) | the user wants Claude to build the sequence | the tools below, on a work copy |

## Safety (always)

- **Work on a copy.** `keremkit.py safe-copy <project.prproj> <home>/library/_work/<job>/<Project>_work.prproj` and open the copy (`open_project`). The user's project is only read. Same rule as `project.reduce` in AE.
- Every write call carries `expected_project_path` = the work copy. A call answered for another path stops the job (Stop rules in SKILL.md).
- Before host work: `verify_premiere_connection`. Find tools with `get_capabilities` (`tool_query`, `tool_limit: 10`) and read a tool's schema before calling it.
- **Preview tokens** (`confirmation_token` from a dry run) only work in the same server process. In a chat where the MCP is loaded this just works; when calling it from a script, run preview and apply in one process (a batch).
- **Unknown outcome = recovery lock.** A write whose result could not be confirmed locks further edits (`HOST_RECOVERY_REQUIRED`, saves refused). Then: `inspect_operation_recovery`, re-read the timeline, tell the user what is and is not there, and call `acknowledge_operation_recovery` **only after the user has reviewed it**.
- Prove saves on disk: `save_project` -> `keremkit.py stat <copy>`.
- The MCP must be installed **before** the chat starts; tools registered mid-session are not loaded until a new session (`setup.md`).

## New project: folder and names (ask once)

Before creating a Premiere project or sequence, read `premiere.project_folder`, `premiere.project_naming` and `premiere.sequence_naming`. If one is null, ask once with the templates in `preferences.md`, then save the answer.
- `projects`: save the project in `paths.projects`.
- `next_to_video`: save it in `<video folder>/<video> - Bileşenler/`.
- `ask`: ask the folder each time.

Work copies of the user's existing projects still go to `library/_work/` (Safety, below).

## Many calls: prbatch.py (token rule)

More than ~5 calls in a row (a cut, intro MOGRTs, captions, SFX, keys) → write them into a plan and run `prbatch.py run plan.json`. It runs them in one server process and prints one line per step; the full answers go to `plan.results.json`.
- Name the fields to print with `pick`.
- Chain a preview to its apply with `save_as` / `token_from`.
- The plan-level `expected_project_path` is added to every step.
- It stops at the first error and always at a recovery lock.

Direct MCP calls stay for a first look and for answers that decide the next step. `prbatch.py list <regex>` / `schema <tool>` look tools up without loading the schema into the chat.

```json
{"expected_project_path": "C:/.../IMG_3820_work.prproj",
 "steps": [
  {"tool": "import_mogrt", "args": {"mogrt_path": ".../Satır1.mogrt", "start_seconds": 0.30, "duration_seconds": 2.1, "track_index": 4, "text_values": {"Satır1": "ÜRÜN"}}, "pick": ["data.textVerification"]},
  {"tool": "ripple_remove_timeline_ranges", "args": {"ranges": [...], "dry_run": true}, "save_as": "cut"},
  {"tool": "ripple_remove_timeline_ranges", "args": {"ranges": [...]}, "token_from": "cut", "pick": ["data.verified"]}]}
```

## Known MCP limits (premiere-pro-mcp 1.30, CEP; seen in builds 2026-11-11)

| Limit | Do instead |
|---|---|
| `import_mogrt` first lays the template at its own length, then trims: on a track with clips it **overwrites** them | place MOGRTs on empty tracks, or before other clips on that track; read the track back |
| Name-based effect tools (`get_effect_properties`, `set_effect_property`, `add_keyframe`) reach only the **first** effect of a name; a second Transform cannot be keyed | copy both from a template clip (`copy_effects_between_clips`, same sequence) |
| `copy_effects_between_clips` / `paste_clip_attributes` work only inside the active sequence | keep a template clip in the work sequence, copy, then delete it |
| `unnest_sequence` places the parts at the right times but **drops every effect and keyframe** | effect-carrying presets: the user pastes attributes, or copy from a template clip in the same sequence |
| Bezier speed/influence cannot be set (only "bezier") | copying keeps exact easing |
| `add_keyframe` past the clip end → refused **and** recovery lock; `import_media` to a missing bin → same | key the last frame at exactly the clip duration; writes one at a time |
| Premiere-authored MOGRT (`authorApp: ppro`) → "exposes no MGT component"; writing its text fails and locks | text MOGRTs must be After Effects-authored (`aefx`); check definition.json before using one, and tell the user if a style's MOGRT is `ppro` |
| `overwrite_clip` of a nest adds an empty linked audio clip | remove it |
| Clip speed cannot be changed | - |
| 1920x1080 overlay in a 1080x1920 sequence comes in at Scale 56.25 | set the absolute scale (e.g. 178 to cover the height) |
| `relink_media` can hang Premiere | import the file and `overwrite_clip` at the right time |

Opacity blend modes in a .prproj are numbers: 22 = Screen, 2 = Color Dodge, 18 = Normal (alphabetical index, `set_blend_mode`). `prproj.py inventory` prints the known names.

## Building a style's video: per-video rules

- **Intro texts on spoken words:** when an intro text matches a spoken word ("ürün", "part", the number), place its MOGRT and its SFX at that word's start in the corrected transcript, for every video. The style's fixed offsets are only a fallback. `import_mogrt` takes `start_seconds` / `duration_seconds`.
- **Camera scale = sequence width / source width × 100**, from ffprobe for every source. A 2160x3840 iPhone clip in a 1080x1920 sequence = 50.
- **Risers / whooshes into a cut:** measure the file's loudest point (RMS peak) and put that peak on the cut, not the file start.
- **Section clips with in/out animations** end exactly at the next section cut. The previous OUT must finish before the next IN starts; never overlap them.
- **Captions in the style's look:** use the style's caption MOGRT (`premiere.caption_mogrt`, AE-authored, one text field). Place one `import_mogrt` per cue through `prbatch.py` on an empty track. Without such a MOGRT, build the SRT and remind the user that a caption MOGRT is needed; never fake the look.
- **Style template project** (`styles/<slug>/template.prproj`, made from a copy): one ready example of each effect-heavy part (product nest with its two Transform effects, film-burn presets, SFX with levels). Import the needed sequence, place the template clip in the work sequence, `copy_effects_between_clips` to each target, then delete it. Keep the template small: one sequence per part.
- **MOGRTs the user still has to fix** (a note in the style): place them as usual, and remind the user at the start and in the final report until they say they are fixed. Never edit or re-export them.

## What works through the MCP (tested 2026-11-11, premiere-pro-mcp 1.30.0, CEP bridge, Premiere 2026)

| Job | Tool(s) | Note |
|---|---|---|
| Read project, sequences, settings, items | `get_project_info`, `list_sequences`, `get_sequence_settings`, `get_sequence_structure`, `list_project_items` | `enabled:false` shows disabled clips |
| Read effect values | `get_effect_properties` | Position / Scale / Tint colours read correctly |
| New sequence from a clip | `create_sequence_from_clips` | |
| **Cuts** | `ripple_remove_timeline_ranges` (dry run -> token -> apply) | ranges = the cut list's removed parts in **sequence** time; apply from the end backwards or in one call. Re-read the timeline after; on some Premiere 26 builds a cut can be ignored silently - compare clip count and duration with the cut list |
| Effects | `apply_effect` + `set_effect_property` | discover names first (`list_available_effects`, `get_effect_properties`); verify by readback |
| Sound effects | `import_media` -> `overwrite_clip` (`audio_track_index: "auto_empty"`) -> `set_clip_volume` dB -> `get_clip_volume` | the whole file is placed: trim the SFX file with ffmpeg first if only part is wanted |
| Export | `export_sequence` / `export_and_verify`, presets from `get_encoder_presets` | check the file with `qc.py` |

## What does not (yet)

- **Text / titles:** `add_title` with font/size/fill is refused (`TITLE_STYLE_UNSUPPORTED`); text-only `add_title` failed to import its template and set a recovery lock. `add_text_overlay` is unavailable. Premiere-authored Essential Graphics text cannot be read or written by scripts.
- **Caption style:** `create_caption_track` from an SRT works but uses Premiere's default caption style and cannot be read back (`committed_unverified`).
- **Clip speed** cannot be changed; clip In/Out on placement is not available in `overwrite_clip`.

**Tested route (2026-11-11):** an After Effects-authored `.mogrt` (definition.json `authorApp: aefx`) with its text fields exposed. One template may hold several fields (the Ecomelih intro has four: Satır 1-4). `import_mogrt` with `text_values: {"<field name>": "<text>", ...}` writes every field and reads it back (`textChecks` all `verified`). Premiere-authored graphics (`.aegraphic` only) stay unreadable by scripts. Field names come from the .mogrt's definition.json (`clientControls[].uiName`) - read them with a few lines of Python instead of guessing.

**Text routes (decide per style, record it in the style's `premiere.text_route`):**
1. **Titles / intro text:** build the look in After Effects (KeremKit's own path), export it as a `.mogrt` with the text, font size and colours exposed as properties, then `import_mogrt` and set the text. One .mogrt per text look; keep them in the library.
2. **Captions:** `subtitles.py build` -> `subs.srt` -> `create_caption_track` (or the user imports the SRT) -> the user runs "Upgrade Caption to Graphic" once and saves a Track Style; tell them the exact steps.
3. **Burned-in captions** instead: render them in AE over the cut and import the render.

## Preset transitions (film burn, light leaks...) made in Premiere

A preset sequence usually holds adjustment layers (Tint, blurs) **plus** overlay clips with blend modes. Rebuilding it from files in XML loses both. And a preset placed as a **nested clip does not work as a transition**: its adjustment layers only affect what is inside the nest, not the video under it. Use a nest only to carry the parts:
1. `import_sequences` the preset sequences from a **copy** of the preset project into the work project.
2. Place the preset as a nest on the cut point, then `unnest_sequence` it (or copy its track items) so every part sits on the main timeline above the video, at its own time and track, with its effects and blend modes intact.
3. Size for another frame format on the overlay clips only (e.g. Scale 160 for a 1920x1080 preset on 1080x1920 - check the edges: 3072x1728 does not cover 1920 px height, it needs ~178); adjustment layers are not scaled.
4. Read back: track items, effects and blend modes as in the preset (`get_effect_properties`). Not tested yet - report what happened.

## Cut in AE's way, finish in Premiere (files route)

1. Transcript + cut list as usual (`transcript.md`, `cutting.md`).
2. `cutlist.py export cam.cut.json --format xmeml -o "<video> - Bileşenler/<video>_cut.xml"` - one master clip linked by path (no offline media), V1 + one audio track, contiguous frames. EDL (`--format edl`) is the fallback: frame-exact, one audio track, but Premiere always brings an EDL in **offline** (Link Media by hand).
3. Subtitles: `subtitles.py build ... -o subs` -> `subs.srt`.
4. Tell the user: File > Import the XML; import the SRT onto a caption track.
5. **HDR phone footage** (ffprobe `color_transfer` = arib-std-b67 / smpte2084): the XML carries no colour management - after import set Sequence > Sequence Settings > Color Management > Color Setup to the user's standard (e.g. "Direct Rec.709 (SDR)"), or the picture looks yellow/flat. Say this with the files.
6. Downloaded web videos: get them Premiere-safe first (`downloads.md`).

## Learning a style from a Premiere project

1. `keremkit.py search "<style name>" --type style` - **if the slug exists, ask** (new version via the archive, or a new name). Never write over an existing `styles/<slug>/style.json`.
2. `keremkit.py safe-copy <project.prproj> <home>/library/_work/<job>/<Project>_copy.prproj`.
3. `prproj.py sequences <copy>` -> pick the edited sequence with the user if unclear.
4. `prproj.py analyze <copy> --out <job>/analysis.json [--seq NAME]`, then `prproj.py inventory <job>/analysis.json` - one line per track, clip, effect, keyframed parameter, text style and transition, nested sequences included. Work through it with the checklist in `edit-styles.md` -> Learning from a finished project: the checklist. Every line ends up in the style or is written off with a reason. Example of what is easy to miss: two Transform effects on each product video nest (IN over the first 0.833 s, OUT over the last 0.833 s), which show up only as keyframes on the nested clip.
5. Draft the style (`edit-styles.md`): shared parts as usual (cut tightness from clip durations, SFX levels, caption timing), Premiere-only parts under `"premiere"`:
   ```json
   "premiere": {
     "sequence": {"size": [1080, 1920], "fps": 30},
     "tracks": {"V1": "camera", "V2": "b-roll", "V3": "text", "A1": "voice", "A2": "music", "A3": "sfx"},
     "effects": [{"match": "AE.ADBE Tint", "params": {"Amount to Tint": 62}}],
     "sfx": [{"file": "click.wav", "level_db": -12}],
     "text_route": "mogrt | captions-upgrade | burn-in",
     "text_looks": [{"role": "intro", "font": "Montserrat-Bold", "size": 120, "fill": [255,255,255], "stroke": [0,0,0], "stroke_width": 8}]
   }
   ```
6. Ask what a project cannot show (why a cut, SFX intent), save, `reindex`.

What `prproj.py` reads: track items (start/end, source file, in/out, gain, disabled = `IsMuted`), transitions, effects with values and keyframes, nested sequences, and the text style inside Essential Graphics (font, size, fill, stroke, shadow, box, alignment - best effort; the blob has no public schema). Not decoded: blend-mode numbers and text-animation settings.
