# Subtitles

Pipeline: **Whisper (outside AE) -> `subtitles.py` (rules) -> one data file -> ONE text layer in AE that reads it by expression.** This is the token-cheapest way: no per-cue layers, no per-cue tool calls, and any rule change is a rebuild + reload.

## Transcribe

Use `tools.whisper` from preferences (impl, path, model, device, language). Always request **word timestamps** and **JSON** output. Examples:

- openai-whisper: `whisper "cam.mp4" --model turbo --language en --word_timestamps True --output_format json --output_dir _keremkit`
- faster-whisper (Python): `WhisperModel(model, device=...)`, `transcribe(path, word_timestamps=True, language=...)`, then save `{"segments":[{"words":[{"word","start","end"}]}]}`
- whisper.cpp: `-ojf` (full JSON) gives tokens; if word times are missing, use another impl or tell the user.

Language: `tools.whisper.language` if set, else the style's language, else auto-detect. Always pass an initial prompt with the topic and glossary (`transcript.md`). Transcribe each spoken input once and keep the JSON; all later rule/cut changes reuse it.

**Before building subtitles, correct the transcript** (`transcript.md` -> Smart correction) and build from the `*.fixed.json`. Subtitles never show a word the user has not had the chance to confirm when it was uncertain.

For decisions that need the words (split points, highlight choices), read **compact text** only: Whisper's `.txt`, or `subtitles.py preview` (one line per cue). Never paste the JSON into the conversation.

## Rules - flexible, remembered

Defaults live in `subtitles.py` (`subtitles.py rules` prints them). Effective rules = defaults <- `preferences.subtitles.rules` <- style `subtitles.rules` <- one-off `--set` overrides. Save to preferences or style when the user states a lasting choice.

| Rule | Meaning | Default |
|---|---|---|
| `max_words_per_line` | words on one line | 4 |
| `max_lines` | lines per cue | 2 |
| `min_words` / `max_words` | words per cue (max null = words_per_line x lines) | 2 / null |
| `max_chars_per_line` | optional hard limit; too-long cues are split | null |
| `split_mode` | `words` = fill cues regardless of sentences; `sentence` = never cross a sentence end; `hybrid` = sentence-aware and prefers breaking after commas | hybrid |
| `split_mode: pairs` | for short cues (1-2 words): pairs words with the fewest one-word cues, may run over a sentence end, never over a long pause (`break_on_pause`), a zone or a time in `break_at`; a one-word cue only where two words would exceed `max_chars_per_line` (or an odd word count forces one) | - |
| `break_at` | timeline times a cue never crosses - the section cuts | [] |
| `skip_before` | no captions before this time - an intro whose own texts carry the hook | null |
| `proper_nouns` | with `case: lower`, these keep their spelling, suffixes included ("Türkiye'de", "Nike'ın", "DM'den") | [] |
| `orphan` | a 1-word leftover: `rebalance` (re-split evenly), `extra_line` (add a line to the previous cue), `allow` | rebalance |
| `orphan_max_words` | what counts as a leftover | 1 |
| `break_on_pause` | a pause this long (s) always starts a new cue | 0.6 |
| `min_duration` / `max_duration` | on-screen time limits (s); long cues are split | 0.5 / 4.0 |
| `close_gaps` | gaps shorter than this are closed (no flicker) | 0.25 |
| `no_break_after` | never end a line on these words or on a number ("3 / steps") | built-in list for the language (en, tr, de, es, fr, pt, it) |
| `case` | `as_is` / `upper` / `lower` / `sentence` (dotted/dotless i handled for `tr` and `az`) | as_is |
| `language` | language of the words; null = read from the Whisper output | null |
| `strip_punctuation` / `keep_punctuation` | `none` / `trailing` / `all`; marks always kept | trailing / ?! |
| `highlight.modes` | any of `keywords`, `numbers`, `longest`, `manual` | keywords+numbers |
| `highlight.keywords`, `max_per_cue`, `min_chars` | words/stems to highlight; limit per cue | [], 1, 3 |

**First subtitle build without saved rules:** ask once, compactly, then save (style or global as the user says):

> A few subtitle rules: how many words per line, and how many lines? (e.g. 3-4 words, 2 lines) Should subtitles follow sentences, or only the word count? If one word of a sentence is left over: rebalance the lines, or add one more line? Which words should be highlighted - keywords, numbers, or none?

Ask in the user's language.

Accept partial answers; unanswered parts use defaults and are recorded as chosen.

## Build

Single input: `subtitles.py build --words cam.json --cutlist cam.cut.json --zone camera -o _keremkit/subs`
Several inputs on one timeline (style runs): `subtitles.py build --plan plan.json [--rules rules.json] [--set key=value ...] -o _keremkit/subs`

- Words removed by the cut are dropped; times are mapped onto the final timeline; each cue carries its zone (`camera`, `voice`, ...). Overlapping placements are rejected - fix the plan.
- Output: `subs.json` (for AE) and `subs.srt` (for platforms / other editors). The result line reports cue count, average words, cues below minimum, highlighted cues.
- Check quality cheaply with `preview` (first 20 cues). Highlight mode `manual` or a user request ("highlight 'amazing' in cue 3"): `subtitles.py highlight subs.json --cue 3 --words 2`.

## Put it in After Effects (once per project)

1. `project.import_file` the `subs.json` (keep its exact item name, e.g. `subs.json`).
2. One batch: `layer.create_text` named `SUB_Captions` (point text, centered), `text.set_style` (font/size/colors/stroke from the style or `subtitles.look`, `justification: center`), then `expression.set` on Source Text.
3. Highlight: `text.add_animator` with `selector: "expression"` and the highlight properties from the style (default `{"ADBE Text Fill Color": <highlight color>}`; a scale pop or other properties are fine). Set the Expression Selector's **Based On = Words** and its **Amount** expression. Find exact property paths once with `property.list` on the layer.
4. Zone positions (different place for camera vs voice parts): `expression.set` on Position with the positions map from the style for this format.
5. Print all three expressions with: `subtitles.py ae-expr subs.json --footage subs.json --positions positions.json` and paste them as-is.
6. Verify numerically: `comp.sample` on `SUB_Captions` Position at a camera time and a voice time; `layer.bounds` at the longest cue vs title-safe.

After any change (rules, cut fixes): rebuild `subs.json` at the same path -> `footage.reload`. Nothing else in AE changes.

**Fallback - one layer per cue** (only if the user wants to hand-edit individual cues in AE or the data approach is unavailable): create layers in chunks of ~40 cues per batch (`layer.duplicate` a styled template, `text.set_content`, `layer.set_timing`, `text.set_style_range` for highlights). Warn first: many more tool calls and tokens.

## Animation of cues

Entrance/exit motion (pop, fade, slide) belongs to the style or `subtitles.look`. Implement with an animator whose expression uses the current cue's start/end (`c.s`, `c.e` from the same data) so every cue animates without keyframes. Keep it subtle unless the style says otherwise; typical: 4-6 frame ease-out scale 90->100 % with opacity.
