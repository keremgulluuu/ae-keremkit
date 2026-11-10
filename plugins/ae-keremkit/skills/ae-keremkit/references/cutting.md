# Cutting

Analysis and cutting happen **outside** After Effects (Whisper + `cutlist.py` + ffmpeg); AE receives a finished cut file. Why: AE has no transcription or silence analysis here, and hundreds of layer splits in AE are slow and expensive. The cut list keeps every cut editable, so later fixes are one command.

## Files (per spoken input, next to the project in `_keremkit/` unless `paths.work_files` says otherwise)

```
cam.json          Whisper output (word timestamps)
cam.cut.json      cut list: kept segments with source AND output times + edit history
cam_cut.mp4       rendered cut (audio-only inputs -> .wav)
plan.json         timeline plan when a style interleaves several inputs
```

## Build

0. Run the transcript pipeline first (`transcript.md`): corrected words + `repeats.json`.
1. Transcribe (see `transcript.md` -> Transcribe with context) - word timestamps are required.
2. Preset: the style's `cutting` for this role, else `cutting.preset` (ask once if null: "How tight should the cuts be? Tight / Normal / Relaxed"), plus any `overrides`.
   | preset | keeps before a word | after a word | longest pause kept |
   |---|---|---|---|
   | tight | 0.05 s | 0.08 s | 0.15 s |
   | normal | 0.10 s | 0.15 s | 0.35 s |
   | relaxed | 0.15 s | 0.25 s | 0.70 s |
3. `cutlist.py build --words cam.fixed.json --media cam.mp4 --preset tight --remove repeats.json [--pad-before .. --pad-after .. --max-pause .. --noise-db ..] -o cam.cut.json`
   Pauses come from the real audio, with a threshold relative to the speaker: the median level inside Whisper's words minus 10 dB (`--rel-db`, or an absolute `--noise-db`), confirmed by the words; retakes, repeats and fillers from `repeats.json` are removed; segments snap to the source frame rate; every cut gets an 8 ms audio fade (no clicks). Check the result line says `mode=audio+words`.
   `WARN loud audio without words A-B s` = sound as loud as the speaker for over 1 s where Whisper heard no words (music, laughter, or a sentence Whisper missed). It is **kept**; tell the user the times in one line and ask. Rebuild with `--drop-wordless` only if they want it gone.
4. `cutlist.py render cam.cut.json -o cam_cut.mp4 --run [--crf N --x264-preset P]` (defaults from `cutting.crf` / `cutting.x264_preset`; constant frame rate output so AE stays in sync).
5. Import into AE (`project.import_file`), or if the layer already exists and the path is the same, `footage.reload`.

## Quick fixes from the user's words

Times the user gives are **final timeline** seconds unless they say "in the original recording". If the cut file starts later on the timeline (e.g. camera part 2 placed at 63 s), convert first: `cut_time = timeline_time - placement.at + placement.from` (from `plan.json`). For a source-time question use `cutlist.py map --src T` / `--out T`.

| User says | Command |
|---|---|
| "0:10-0:12 is cut too fast, add 1 second of breathing room" | `add cam.cut.json --from 10 --to 12 --sec 1` |
| "give it a little air at 23 s" (no amount) | `add cam.cut.json --at 23 --sec 0.3` (say the amount used) |
| "remove 40-42" | `cut cam.cut.json --from 40 --to 42` |
| "bring back 1:20-1:25 from the original" | `restore cam.cut.json --src-from 80 --src-to 85` |
| "undo that" | `undo cam.cut.json` (20 steps kept) |
| "this is too tight overall, loosen it" | rebuild with a looser preset or larger pads; ask whether to save it as the preference |
| "show me where it was cut around 0:30" | `show cam.cut.json --from A --to B` (boundaries + removed pause per cut) |

`add` gives back removed pause at the cuts in the range, evenly, never more than was removed; if the range has too little, it borrows from cuts within 1.5 s (`--window`, or `--strict` to forbid). If even that is not enough, the tool says how much could not be added - tell the user (a held frame would be needed; ask).

After any fix:
1. `render ... --run` (seconds of ffmpeg), then `footage.reload` in AE.
2. The cut file's duration changed by Δ = new `out_duration` - old. Everything placed **after** it on the timeline shifts by Δ: update `plan.json` (`at` values) and the AE layers' start times in one batch (`layer.set_timing shift`), and the layer's out point (`outPoint`) for the changed clip.
3. Rebuild subtitles from the plan (cheap) and `footage.reload` the subtitle JSON.
4. Verify numerically (`comp.info`: no gaps/overlaps between placements).
Report in one line: what changed and the new total duration.

## Judgement notes

- Breaths and filler sounds ("um", "uh"): Whisper often omits fillers, so pauses containing them get cut automatically. If the user wants to keep breaths, use larger `pad-after`.
- Very tight cuts can clip word endings with fast speech; if the user says words sound cut off, raise `pad-after` by 0.03-0.05 s for that range or globally.
- Do not cut music, SFX or screen recordings with this tool - only spoken inputs.
- Long inputs: Whisper is the slow step; run it once and keep the JSON - every later cut change reuses it.
