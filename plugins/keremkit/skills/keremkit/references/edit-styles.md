# Edit Styles

An edit style is a complete, named recipe: which inputs an edit has, how they are cut and ordered, how subtitles look and move, which fonts/colors/transitions/interstitials/motion designs/UI/SFX are used, and the rules that tie it together. With a style, "edit this in my Kerem style" is enough to run the whole edit.

Styles live in `KeremKit/styles/<slug>/style.json` and are listed in the catalog (`type=style`, prefix `STY`). Schema with comments: `assets/style.example.json` in this skill. Library items are referenced by ID (`UI-007`), never copied into the style.

## What a style holds

| Section | Contents |
|---|---|
| `inputs` | Roles the edit expects (e.g. `camera` video, `voice` audio, `screen` recording), whether required, how to recognise the file (name patterns), what each is for |
| `structure` | Ordered rules for how roles interleave, in plain language plus hints, e.g. "split the camera after a sentence like 'let's look at the screen' or before 'so how did I do it'; play the voice recording; resume the camera". `split_cues` lists example phrases and whether the cut goes **before** or **after** them - they are examples of a pattern, not exact strings |
| `formats` | Per aspect ratio (`16x9`, `9x16`, ...): comp size/fps and any overrides (positions, sizes). If the user wants a truly different look for vertical, it is a separate style linked in `variants` |
| `cutting` | Preset/overrides per role (e.g. camera `tight`, voice `normal`) |
| `subtitles` | Rules (overrides of the subtitle defaults), font, colors, highlight rule, `positions` per role/zone and per format, the library item used as the subtitle look |
| `look` | `fonts` (combinations and their uses), `palette` (named colors), `transitions`, `interstitials`, `motion`, `ui` (per role: which items appear, e.g. a progress bar during `voice`) - all library IDs |
| `screen_recording` | When it appears (e.g. over the voice part), how (frame, scale, corner radius, shadow, in/out motion - or a library item), sync rules |
| `sfx` | Style-level SFX rules (see `sound-effects.md`) |
| `render` | Overrides of render preferences |
| `editing` | Rhythm rules for edit plans (`edit-plan.md`): shot length range, per-kind limits, kinds that must not follow each other, keys per sentence |
| `rules` | Any other rule, one sentence each |
| `changelog` | Version history; `version` |

## Applying a style

1. **Find it:** `keremkit.py search <name> --type style`. Read only that `style.json`. Read `learning/house-style.md` only if the style leaves design decisions open.
2. **Resolve the format:** the user's request, else the style's `default_format`, else ask once ("Vertical or horizontal?").
3. **Find the inputs:** look in the remembered footage folder(s) (`paths.footage_folders`; ask once if empty - see preferences). Match files to roles using the style's patterns; list the folder only (no media reading). Ask only for roles you cannot match or that match several files.
4. **Confirm - always, before starting.** Send one compact message that lists what will be used, then ask (in the user's language):

   > I'm starting the whole operation with these settings. Do you have any other preferences beyond these?

   The list (short lines): style + version, format, matched files per role, cut presets, subtitle rules (words/lines, font, highlight, positions), fonts, palette, transitions/interstitials/motion/UI (names, not IDs), screen recording behaviour, SFX on/off + rules, render mode/format. Then wait. Apply the answer: one-off changes for this edit only; if the user says to keep a change, update the style (versioning rules apply).
5. **Run the pipeline** (checkpoint first):
   1. Transcribe each spoken input with Whisper (word timestamps) - see `subtitles.md` -> Transcribe. Keep the compact transcript text (`subtitles.py` is not needed for this; Whisper's `.txt`/`.json`).
   2. Build a cut list per spoken input (`cutting.md`) with the style's preset; render the cut files.
   3. For voice-led styles with many shots, write and check an edit plan (`edit-plan.md`) before building.
   4. **Plan the timeline** from the `structure` rules: find the split points by reading the compact transcript (text with times) and matching the style's `split_cues` *pattern* (meaning, not exact words). Convert source times to cut times with `cutlist.py map`. Write `plan.json` (placements: role, file, from, to, at, zone) - this is also the subtitle plan. If a split point is ambiguous, show the 2-3 candidates in one line each and ask.
   5. Build subtitles from the plan (`subtitles.md`); positions per zone from the style.
   6. Assemble in AE in as few batches as possible: comp per format (`SCN_`), import cut files, place layers per plan, screen recording per style, subtitle layer (data-driven), UI/transitions/interstitials from the library (`library-use.md`), SFX (`sound-effects.md`).
   7. Numeric verification (structure, timing vs plan, safe areas, missing fonts/footage).
   8. Render according to `render.mode` (ask/auto/queue).
6. **Report** in 2-4 lines: duration, what was placed, anything that needed a judgement call.
7. **Learning question** (below).

## Creating a style

Three ways - all end with a draft shown to the user for confirmation, then `keremkit.py new-id STY`, write `styles/<slug>/style.json`, `keremkit.py add styles/<slug>/style.json`:

- **By conversation:** walk the sections in the table above, asking only for what the user has not already said, a few questions at a time. Accept "sen karar ver" and record the choice made.
- **From the current chat:** if the user just edited a video here, extract the decisions and corrections they made in this conversation.
- **From a reference video:** `video-reference.md` - rhythm, look and motion measured from the video, then confirmed with the user.
- **From a finished project:** `ae_project_export_json(outPath=...)` -> `digest.py <file> [--comp SCN_...]` -> draft style from the digest (fonts, palette, layer roles, effects, comp formats) -> ask about what a project cannot show (cut tightness, split cues, SFX intent).
- **From a Premiere project (.prproj):** on a copy, `prproj.py analyze` -> draft; Premiere-only parts go under `"premiere"` in style.json. Steps in `premiere.md` -> Learning a style.
- **Before writing `styles/<slug>/style.json`, always** `keremkit.py search "<name>" --type style`. Same name = same slug = same folder: if it exists, ask (a new version through the archive, or a new name). Never write over a style.

### Learning from a finished project: the checklist

A style learned from a project must hold every element of the edit. Missing one means the next edit is built without it, and the user has to find it. Go through the inventory line by line, not from memory of what "usually matters":

1. **Make the inventory.** Premiere: `prproj.py analyze <copy> --seq <edited sequence> --out a.json`, then `prproj.py inventory a.json`. After Effects: the project export, then `digest.py` per scene comp, and `layer.info` for animated layers. The inventory is the list to work through. Note its TOTAL line.
2. **Every track, top to bottom, video and audio.** What it holds (camera, b-roll, product, text, captions, overlays, SFX, music), and whether the track is muted or locked.
3. **Every clip on it.** Source file, start and end, in/out, speed, reverse, clip gain, the disabled flag. Also how its length is chosen: follows a sentence, a section, a fixed duration or the product video.
4. **Every effect on every clip, including on nested clips** (product videos, cards, intros).
   - Its name and match name, and every parameter that differs from the effect's default.
   - Effects that are applied twice: each one separately, in stack order.
5. **Every keyframed parameter.**
   - Start and end values and the number of keys.
   - Timing relative to the clip, as the inventory prints it: `start+0.000..+0.833` = an in animation, `end-0.816..end+0.017` = an out animation.
   - The easing: bezier speed and influence, from the raw keyframe string when it matters.
   - Write the rule, not the reference's absolute times: "every product video: Transform IN over its first 0.833 s, OUT over its last 0.833 s".
6. **Repeated patterns.** The same effect and keys on several clips (all product videos, every section cut) is one rule of the style. Check that each instance matches; differences are either variants to record or leftovers.
7. **Text.** Font (PostScript name), size, fill, stroke colour and width, shadow, box, alignment, position and anchor, case. Also the timing of each line, and whether it is one graphic or one per line.
8. **Transitions.** Placed transitions plus "made" ones (adjustment layers with keyed effects, overlays with blend modes). Record where they sit relative to the cut point.
9. **Audio.** Every SFX (file, which event, offset, level), music (file, start rule, level, fades, ducking), and track effects and levels.
10. **Sequence settings.** Size, frame rate, colour setup, and the work-area length rule.
11. **Write-offs, each with a reason:** disabled clips, keys OUTSIDE THE CLIP (leftovers after trimming), one-off fixes. They go into the style as "not part of the style: <why>" so the next reader does not re-add them.
12. **Account for the TOTAL.** Every inventory line is either in the style or written off. Say in the report: "N lines: M in the style, K written off". Then ask the user only about intent the project cannot show.

### Building from a style: the checklist

- Before building, list every element of the style (intro parts, sections, product rules, animations, transitions, SFX, music, captions) and tick each one off when it is built.
- Build animations and effects as **real, editable keyframes and effects** in the target app (Premiere: `apply_effect` + `add_keyframe`, or copy from a reference clip; AE: properties and keys). Never bake a style's movement into a rendered video unless the user asks: it cannot be adjusted and its easing drifts from the original.
- Apply the style's rules with **this video's data**: word times from its corrected transcript, sizes from ffprobe, peaks from measurement (`premiere.md` -> Building a style's video: mechanisms). Never copy absolute times or factors from the reference project; the rules themselves come only from the style.
- At the end, read every element back (`get_keyframes`, `get_effect_properties`, `comp.info`) and report anything that could not be built, saying why.

Names: English `name` (e.g. "Kerem Style"), local names in `names` (e.g. `{"tr": "Kerem Stili"}`), `aliases` for how the user refers to it; slug = ASCII of the name.

## Learning after an edit

Everything learned here is the user's taste and goes into **their style** (or `house-style.md` / `custom_rules` when they say it is for every edit). It never goes into the kit or `skill-change-requests.md`, which are only for bugs and missing mechanisms.


When an edit made with (or toward) a style is finished, ask **once**:

> While making this edit I learned: <2-5 short points>. Shall I save them to the style?

- **Edit done in this single chat:** the list comes from this conversation - every correction the user made, values they changed, things they asked to repeat.
- **Edit spread over several chats or edited by hand:** compare the final project with the style: export -> `digest.py` -> diff against `style.json` (fonts, colors, positions, layer roles, effects, durations). Present only real differences.
- On yes: apply versioning (`style_versioning.mode`; ask it the first time), `keremkit.py style-archive <slug> --reason "<change>"` when an archive is due, then edit `style.json`. On no: do not ask again for this edit.
- Lessons that are general (not style-specific) go to `learning/house-style.md` or preferences instead - ask if unsure.

## Changing a style by conversation

"Make the captions yellow in the Kerem style" -> check versioning mode (archive if due, with the instruction as the reason) -> update -> confirm in one line with the new version number. Restoring: "Go back to the previous Kerem style" -> list archived versions with their reasons (one line each) -> copy the chosen one back as a new version.
