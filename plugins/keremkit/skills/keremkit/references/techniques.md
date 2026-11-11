# Techniques

KeremKit keeps a catalogue of editing techniques - cuts, motion, audio, formats, QC, organisation, publishing - in `assets/techniques.json` (built in) plus the user's own in `KeremKit/settings/techniques.json`. `techniques.py` reads both; user techniques override built-ins with the same id.

## When the user asks for a kind of work, offer the techniques first

"I want to edit the audio", "add some cuts", "what can you do with the sound?", "make it more dynamic", "teknikleri göster":

1. `techniques.py list --group <group>` (`cuts`, `motion`, `audio`, `format`, `qc`, `organize`, `publish`; `groups` lists them).
2. Present them **with the technical name and a short explanation**, translated into the user's language, marking what KeremKit does automatically:

   > Ses için yapabileceklerim:
   > 1. **Loudness normalization** - Tüm sesi platform hedefine (-14 LUFS) getirir. *(otomatik)*
   > 2. **Noise reduction** - Arka plandaki uğultu ve cızırtıyı azaltır. *(otomatik)*
   > 3. **Music ducking** - Konuşma olduğunda müziği otomatik kısar. *(otomatik)*
   > ...
   > Hangilerini uygulayayım? (Önerim: 1, 2, 5)

3. Recommend 2-4 based on what you know (e.g. `audio.py analyze` results, the edit's style). Then apply the chosen ones (each card's `how` says with what) and report in one line each.
4. If the user's style or preferences already name techniques (e.g. the style uses jump-cut zoom), apply them without asking and mention them in the style confirmation instead.

Never apply a technique the user did not choose unless their style or a saved preference says so.

## Adding techniques

"Add a technique called X: ..." -> `techniques.py add --id x --group cuts --name "X" --what "..." [--when "..."] [--how "..."] [--auto]`. New groups are created on the fly. If the technique needs a recipe in AE (ops, an expression, a preset or a library item), put that in `--how` (e.g. `"preset FXP-012"` or `"library UI-004"`). `techniques.py remove <id>` removes user techniques.

A technique that needs its own script or a long recipe: put them in `KeremKit/extensions/<id>/` (`<name>.py`, `README.md`) and point `--how` at `extensions/<id>/README.md`. It is usable at once - never add it to the skill or to `KeremKit/tools/`.

## Applying the built-in ones

| id | How |
|---|---|
| `jump-cut` | `transcript.md` + `cutting.md` |
| `jump-cut-zoom`, `emphasis-punch-in` | `cutlist.py zoom cam.cut.json [--levels 100 110] [--emphasis subs.json] [--ease-frames 0] --at <placement start> -o zoom.json` -> import `zoom.json`, `expression.set` the printed expression on the camera layer's Scale. Check that the face stays inside the frame at the top level (`layer.bounds`). |
| `j-cut` / `l-cut` | At a cut between two sources: duplicate the incoming (J) or outgoing (L) layer, keep audio only on the copy (`layer.set_props` `audioEnabled`, and `enabled: false` for video), and move its in/out point 0.3-1.0 s across the cut (`layer.set_timing`). Verify with `comp.info`. |
| `smooth-push` | Scale keyframes 100 -> 103-105 % over the shot, `keyframe.set_easing` ease in-out. |
| `camera-shake` | Position expression `wiggle(freq, amp)` multiplied by a 0/1 gate around the hit time, or a learned preset. |
| `whip-transition` | Library transition or preset; motion blur on for the layers involved. |
| audio group | `audio.md` |
| `multi-format` | `formats.md` |
| `pre-render-qc` | `qc.md` |
| `layer-organize` | `organize.md` |
| publish group | `publish.md` |

`manual` techniques (match cut, cut on action, speed ramp, montage, cutaway) need the user's footage choices: explain what is needed and offer to set it up once they point at the shots.
