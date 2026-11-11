# Edit plan (shots on words)

For voice-led edits (explainers, reels, documentaries, style runs with several shots), write the edit as data before touching After Effects. The plan is small, exact and cheap to change; AE work happens once it passes the check.

## 1. Word anchors

`transcript.py words cam.fixed.json [--cutlist cam.cut.json]` prints every word with its index, one utterance per line:

```
00:00.0 | 0:What 1:if 2:I 3:told 4:you...
00:01.4 | 5:So 6:here's 7:the 8:thing
```

Indices belong to that words file. If the transcript is corrected later in a way that changes the word count (one word replaced by two), re-list the words and update the plan.

## 2. Write edit.json (next to the project, in `_keremkit/`)

```json
{"words": "cam.fixed.json", "cutlist": "cam.cut.json", "at": 0, "fps": 30,
 "keys": [6, 15],
 "shots": [
  {"at": 0,  "kind": "type",  "text": "WHAT IF I TOLD YOU..."},
  {"at": 5,  "kind": "host"},
  {"at": 14, "kind": "clip",  "file": "clips/c01.mp4", "in": 0.5, "hit": "invert"},
  {"at": 24, "kind": "cards", "items": [{"at": 24, "file": "img/a.png", "name": "ChatGPT"}]}]}
```

- `at` = the word where the shot starts; the cut lands one frame before it (`rules.lead_frames`).
- `kind` is free: use the style's names (`host`, `clip`, `screen`, `type`, `giant`, `cards`, `broll`...). Kinds map to techniques and library items when building.
- `in` = source second the clip starts at. One longer clip can feed several shots at different `in` values.
- `keys` = words shown as emphasised captions (`key-flicker` technique).
- Rules come from the style's `editing.rules` (fallback: defaults in `editplan.py`): shot length range, longer limits per kind, kinds that must not follow each other, no repeated seconds, keys per sentence.

## 3. Check

`editplan.py check _keremkit/edit.json -o _keremkit/edit.times.json` prints the shot table (start, end, duration, kind, first words), then `ERROR` lines (must fix: missing files, word cut out, indices not rising) and `WARN` lines (rhythm: too short/long, two host shots in a row, repeated seconds, too many keys). Fix the plan, re-run - each run costs a few lines of text.

Show the user the table only when the style run's confirmation asks for it or something needs a decision.

## 4. Build

`edit.times.json` has frame-exact `start`/`end` per shot. Build in AE from it in as few batches as possible: one layer (or precomp) per shot, `layer.set_timing` with those times, then the shot's techniques (`hit`, flashes, frames, pages). Subtitles use the same words and cut list (`subtitles.md`) and are hidden on pages that carry their own text (`type`, `giant`, `cards`) by giving those ranges their own zone.

Change requests ("start the clip one word later", "swap shots 4 and 5") are plan edits + check + a small AE update, never a rebuild by hand.
