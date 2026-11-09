# Subtitles and cutting

Both are done outside After Effects by two small scripts, then handed to AE as finished files. That keeps edits fast and cheap, and every decision reversible.

## Transcription

Whisper runs once per recording and its JSON (with word timestamps) is reused for every later change.

| Model | Speed | Accuracy | Needs |
|---|---|---|---|
| tiny / base | fastest | weak | any CPU |
| small | fast | fair | ~2 GB VRAM or CPU |
| medium | medium | good | ~5 GB VRAM |
| turbo | fast | close to large | ~6 GB VRAM |
| large-v3 | slowest | best | ~10 GB VRAM |

## Corrections and repeats — `transcript.py`

```bash
python transcript.py review cam.json                                   # compact transcript, doubtful words marked
python transcript.py fix cam.json --corrections corr.json -o cam.fixed.json
python transcript.py repeats cam.fixed.json -o repeats.json            # retakes, repeats, stutters, fillers
python transcript.py accept repeats.json --ids 3 --reject 4
```

Claude reads the transcript with the video's topic in mind and fixes mis-heard words. You get the list in this form, and anything uncertain is asked before it's used:

```
00:12 - Kılavd - Claude
01:03 - after a fax - After Effects
```

Retakes keep the later, finished take. Single repeated words are asked about, since many are intentional ("slowly slowly", "yavaş yavaş").

## Cutting — `cutlist.py`

A cut list records which parts of one recording are kept, with both source and output times.

```bash
python cutlist.py build --words cam.json --media cam.mp4 --preset tight -o cam.cut.json
python cutlist.py render cam.cut.json -o cam_cut.mp4 --run
python cutlist.py add cam.cut.json --from 10 --to 12 --sec 1
python cutlist.py map cam.cut.json --out 42.5
```

| Preset | Kept before a word | After a word | Longest pause left alone |
|---|---|---|---|
| tight | 0.05 s | 0.08 s | 0.15 s |
| normal | 0.10 s | 0.15 s | 0.35 s |
| relaxed | 0.15 s | 0.25 s | 0.70 s |

Pauses are detected in the audio itself and confirmed with the words, so they are removed completely even when Whisper's word timings run long. `--remove repeats.json` cuts the retakes too. Cuts snap to the source frame rate, every cut gets a 5 ms audio fade, and the output is constant frame rate so After Effects stays in sync.

## Subtitles — `subtitles.py`

```bash
python subtitles.py build --words cam.json --cutlist cam.cut.json -o subs
python subtitles.py build --plan plan.json --rules rules.json -o subs
python subtitles.py preview subs.json
python subtitles.py ae-expr subs.json --footage subs.json --positions positions.json
```

Rules (all optional):

| Rule | Default | |
|---|---|---|
| `max_words_per_line` | 4 | |
| `max_lines` | 2 | |
| `min_words` / `max_words` | 2 / lines × words | per cue |
| `max_chars_per_line` | – | long cues are split |
| `split_mode` | `hybrid` | `words`, `sentence`, `hybrid` |
| `orphan` | `rebalance` | `rebalance`, `extra_line`, `allow` |
| `break_on_pause` | 0.6 s | a pause this long starts a new cue |
| `min_duration` / `max_duration` | 0.5 / 4 s | |
| `case` | `as_is` | `upper`, `lower`, `sentence` |
| `no_break_after` | per language | lines never end on these words or on a number |
| `highlight` | keywords + numbers, 1 per cue | |

Line breaks are chosen for even line lengths, never leaving a number or a glue word ("the", "and"…) at the end of a line. Built-in glue words exist for English, Turkish, German, Spanish, French, Portuguese and Italian; Turkish and Azerbaijani get correct dotted/dotless *i* casing.

### Several recordings on one timeline

`plan.json` places parts of different recordings one after another — for example camera, then voice-over, then the rest of the camera. Each cue knows which part (zone) it belongs to, so subtitles can sit lower over the camera and centered over a screen recording. See [`examples/plan.json`](../examples/plan.json).

### In After Effects

One text layer (`SUB_Captions`) reads `subs.json` with an expression. Highlights use a text animator with an expression selector based on words; positions per zone use a position expression. `ae-expr` prints all three expressions. After any change, the JSON is rebuilt and reloaded — the layer itself is never touched.
