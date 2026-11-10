# Transcript: correction and repeats

Every spoken recording goes through the same pipeline before it is cut or subtitled. Its goal: a final cut where pauses **and** retakes are gone, and subtitles where every word is right.

```
1 transcribe  (Whisper, word timestamps, initial prompt with topic + glossary)
2 review      transcript.py review           -> Claude reads the compact transcript
3 correct     transcript.py fix              -> sure fixes applied, unsure ones asked
4 repeats     transcript.py repeats          -> retakes / repeats / fillers, sure ones applied
5 cut         cutlist.py build --remove      -> audio-based silence cut + repeats removed
6 render      cutlist.py render --run
7 subtitles   subtitles.py build (from the corrected words, mapped through the cut list)
```

Run 2-4 on the corrected file (`*.fixed.json`) once corrections exist; the cut list and subtitles always use the latest words file.

## 1. Transcribe with context

Whisper mis-hears names, brands and jargon ("Claude" -> "Cloud", "Kılavd"). Give it the context up front - it prevents most errors:
- openai-whisper: `--initial_prompt "<topic>. <glossary terms, comma separated>."`
- faster-whisper: `initial_prompt=...`
- **Verbatim matters for repeats.** Whisper tends to "clean up" speech and silently drops false starts and repeated words - then they can't be found in the text. Make the prompt itself disfluent so Whisper keeps them, e.g. for Turkish: `"Ee, şey, bugün size, bugün size Claude'u anlatacağım. Iıı, yani..."` (adapt to the language), plus the topic and glossary. Audio that has no words at all is dropped by the cut anyway, which catches many of the retakes Whisper still skips.
- The topic comes from the user's request, the file name, or the style; the glossary from `subtitles.glossary` (global) plus the style's `subtitles.glossary`. If neither exists and the video is clearly about specific names, ask once: "What is this video about, and are there names or terms I should spell exactly?" and save the terms to the glossary.

faster-whisper on Windows can crash on the audio decoder (PyAV) - see `troubleshooting.md`: decode with ffmpeg to a 16 kHz mono WAV first and pass the samples in.

## Word indices

`transcript.py words cam.json [--cutlist cam.cut.json]` prints every word as `index:word`, one utterance per line - the cheapest way to point at a word. Use indices for corrections (`{"index": 28, "new": "Grok"}` in the corrections file; several words allowed) and for edit plans (`edit-plan.md`). Indices refer to that exact words file.

## 2-3. Smart correction

`transcript.py review cam.json` prints one line per utterance: `mm:ss.s | text`, with doubtful words marked `word(?0.42)` (Whisper's own low confidence). Read it **as an editor would**: knowing the video's topic, find words that make a sentence meaningless, ungrammatical or off-topic, mis-heard names (also the ones Whisper was confident about), split or merged words ("after a fax" -> "After Effects"), and wrong suffixes.

For each suspect decide:
- **Sure** - the topic and the sentence leave no doubt (the video is about Claude; "Cloud kullanarak kod yazdım" -> "Claude"). Apply it.
- **Unsure** - two readings are plausible, or the sentence is unclear. Don't apply; ask.

Write corrections to a file and apply them (anchored by time + old text, timestamps kept):

```json
[{"time": 12.4, "old": "Kılavd", "new": "Claude"}, {"time": 63.1, "old": "after a fax", "new": "After Effects"}]
```
`transcript.py fix cam.json --corrections corr.json -o cam.fixed.json`

**Report to the user - always this format, times as mm:ss, in the user's language:**

```
Düzeltilenler:
00:12 - Kılavd - Claude
01:03 - after a fax - After Effects

Emin olmadıklarım (onaylar mısın?):
00:31 - kuru - kurgu ?
02:14 - sınır - sinir ?
```

Wait for the answer before building subtitles from the unsure ones. The user can confirm, reject or give the right word; apply that with another `fix` run. Corrections the user confirms for names/terms go into the glossary (`subtitles.glossary`, or the style's if it is style-specific) so the next video gets them right from the start. Never store one-off word fixes as rules.

## 4. Repeats, retakes and fillers

`transcript.py repeats cam.fixed.json -o repeats.json` finds:

| Kind | Example | Default |
|---|---|---|
| `retake` | "Bugün size... / Bugün size Claude'u anlatacağım." - an utterance that is the start of the next one | removed (asks if the match is weak) |
| `repeat` | "bu araç bu araç çok güçlü" - a 2-6 word phrase said twice in a row | removed |
| `stutter` | "ben ben" - one word twice | **asked**: many doubles are intentional ("yavaş yavaş", "çok çok") |
| `filler` | "ııı", "eee", "um" when Whisper wrote them | removed |

The **later** take is always kept - speakers repeat to correct themselves. The removed range runs from the first take's start to the kept take's start, so no gap is left.

Preference `cutting.repeats`: `auto` (apply high-confidence, ask the rest - default when null after asking once), `ask` (ask about all), `off`. Report like corrections:

```
Silinen tekrarlar:
00:00 - "Bugün size Kılavd" (tekrar çekim, sonraki hali kaldı)
00:05 - "Bu araç" (tekrar)

Emin olmadıklarım:
00:08 - "Yavaş yavaş" - ilk "yavaş" silinsin mi?
```

Apply the user's answers with `transcript.py accept repeats.json --ids 3 --reject 4`, then build the cut.

## 5. Cut

`cutlist.py build --words cam.fixed.json --media cam.mp4 --preset <p> --remove repeats.json -o cam.cut.json`

Pauses are found in the **audio** (threshold = the speaker's own level inside the words minus 10 dB, `--rel-db`) and confirmed with the words: Whisper's word ends often run into the following pause, which is why word-only cutting leaves pauses half-cut. Audio regions with no words (coughs, clicks, background noise) are dropped too. The result line says `mode=audio+words`; `mode=words only` means ffmpeg could not analyse the audio (tell the user) or the audio has no pauses below the threshold.

If the user says a cut clips words or sounds rushed, raise `--pad-after` (e.g. 0.12) or use a looser preset; if pauses remain, raise the threshold (`--rel-db -8`, or a fixed `--noise-db -35`) so quieter room noise counts as silence.
