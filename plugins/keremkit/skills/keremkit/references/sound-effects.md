# Sound Effects

SFX rules come from two places: **global** (`preferences.sfx`) and **style** (`style.sfx`). The style wins where both speak, **but a real conflict is never resolved silently**: say what each says and ask which to use this time, and whether to update one of them.

Examples of conflicts worth asking about: global `enabled=false` but the style lists SFX; global level -18 dB vs style -10 dB; global "no SFX under speech" vs style "pop on every highlighted word".

## Rule format

`sfx.rules` (global or style) is a list of short objects; the user's own words go in `note`:

```json
{"event": "transition", "sound": "whoosh", "level_db": -16, "offset_s": -0.10, "note": "whoosh on transitions, slightly early"}
{"event": "subtitle_highlight", "sound": "pop_soft", "level_db": -22, "every_n": 3}
{"event": "ui_in", "sound": "click", "level_db": -20}
{"event": "interstitial", "sound": "riser", "level_db": -14, "offset_s": -0.5}
{"event": "cut", "sound": null, "note": "kesimlerde ses yok"}
```

Events: `transition`, `interstitial`, `ui_in`, `ui_out`, `subtitle_highlight`, `number_count`, `screen_in`, `screen_out`, `zoom`, `scene_start`, `scene_end`, or any event name the user defines (describe it in `note`). `sound` is a file name/stem searched in `paths.materials.sfx`, a subfolder ("whoosh/" = pick from it), or `null`.

Global limits (preferences): `level_db` default level, `min_gap_s` (no two SFX closer than this), `max_per_10s` (density cap). Keep SFX under the voice: default -18 dB relative to unity; never louder than the voice.

## Placing SFX

Where a sound goes and how it lines up (its start, its loudest point, a fixed offset) is the style's or the user's rule. When a rule refers to a sound's loudest point, measure it (`standards.md` -> Measuring a sound's peak) instead of guessing from the file start.


1. Collect the events from the timeline plan / what was placed (transition times, UI in-points, highlight times from `subs.json`).
2. Apply the rules, then the limits (drop the weakest when too dense; prefer structural events - transitions, interstitials - over decorative ones).
3. Find files: list the SFX folder once per session (names only) and match by stem. No folder, or a sound is missing: offer to synthesise basic ones - `sfx.py make whoosh impact pop tick click glitch flash riser typing -o <project>/_keremkit/sfx [--variants 3]` (licence-free, every file peaks at -3 dBFS, so set levels in AE). Never invent a file that does not exist.
4. AE, one batch: `project.import_file` each needed file once (put them in an `04_SES/SFX` folder), `layer.create_footage` per event named `SFX_<Event>_<nn>`, `layer.set_timing` (start = event time + `offset_s`), Audio Levels via `property.set` (`level_db`).
5. Verify with `comp.info` (count, times). Report one line: how many SFX, which kinds.

The first time an edit could use SFX and `sfx.enabled` is null, ask once: "Should edits use sound effects?" - if yes and there are no rules yet, propose a minimal set (whoosh on transitions, soft click on UI entrances) and save what the user accepts.
