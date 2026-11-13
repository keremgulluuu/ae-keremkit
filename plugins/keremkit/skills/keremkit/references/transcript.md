# Transcript: correction and repeats

Every spoken recording goes through the same pipeline before it is cut or subtitled. Its goal: a final cut where pauses **and** retakes are gone, and subtitles where every word is right.

```
1 transcribe  (Whisper, word timestamps, initial prompt with topic + glossary)
2 review      transcript.py review           -> Claude reads the compact transcript
3 correct     transcript.py fix              -> sure fixes applied, unsure ones asked
4 repeats     transcript.py repeats          -> retakes / restarts / repeats / fillers, sure ones applied
4b hidden     transcript.py bursts + retakes -> takes Whisper merged into one stretched word (always run)
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

**Verbatim model (CrisperWhisper 2.0).** When `tools.whisper.impl` is `crisperwhisper`, the transcript keeps every false start, repetition and cut-off word ("ürete-") and marks sounds as `[laughter]`, `[UH]`. Tested on a Turkish talking-head clip (IMG_3810): it showed all retakes in one pass, including ones large-v3 had merged or hidden, with no stretched words. Notes: numbers come out as words ("yirmi bir", "beş on") - write them as digits in the subtitle corrections; a few words are mis-heard like with any model (review as usual); the model licence is **non-commercial research** (Nyra Health) - the user decides whether their use fits. Runs with PyTorch (`crisperwhisper[transformers]`; the faster CT2 backend is Linux only); ~2 min load + ~1 min for a 2 min clip on an RTX 4060.
```python
from crisperwhisper import CrisperWhisperModel
r = CrisperWhisperModel().transcribe("cam_16k.wav", language="tr", word_timestamps=True)
words = [{"word": w.word, "start": w.start, "end": w.end} for w in r.words]   # -> {"segments": [{"words": words}]}
```

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
| `filler` | "ııı", "eee", "um", `[UH]` when Whisper wrote them | removed |
| `restart` | "ya bunu Türkiye'de ürete- bunu Türkiye'de üretebilecek..." - a cut-off word (verbatim transcripts mark it with `-`) and the words before it said again | removed (never reaches back over a sentence end) |

Sound tags (`[laughter]`, `[sniff]`) are ignored here; the silence cut treats them like any wordless sound.

By default the **later** take is kept, since speakers repeat to correct themselves. A style or the user can choose otherwise. The removed range runs from the first take's start to the kept take's start, so no gap is left.

Preference `cutting.repeats`: `auto` (apply high-confidence, ask the rest - default when null after asking once), `ask` (ask about all), `off`. Report like corrections:

```
Silinen tekrarlar:
00:00 - "Bugün size Kılavd" (tekrar çekim, sonraki hali kaldı)
00:05 - "Bu araç" (tekrar)

Emin olmadıklarım:
00:08 - "Yavaş yavaş" - ilk "yavaş" silinsin mi?
```

Apply the user's answers with `transcript.py accept repeats.json --ids 3 --reject 4`, then build the cut.

Other spans to drop (chatter, a sentence the user wants out): `transcript.py remove cam.json --index 412-431 --reason "off-topic" --into repeats.json` - indices from `transcript.py words`, taken from the same file you pass (no scratch scripts).

## 4b. Hidden retakes (every edit, before cutting)

A normal Whisper model can write several takes of a sentence **once** and stretch one word over the extra takes (IMG_3810: "üretebilecek" 4.76 s over 3 takes). Text comparison cannot see that. Check every edit:

1. `transcript.py bursts cam.fixed.json --media cam_16k.wav --wav-dir _keremkit/bursts -o _keremkit/bursts.json` - lists `SUSPECT` spots (a word > 1.2 s, or an utterance slower than 0.6 s/word, over 2+ speech bursts) and cuts every burst of those spots into its own wav. No suspects -> done.
2. Transcribe **each wav on its own** with the user's Whisper (`condition_on_previous_text=False`, word timestamps, same language) and fill `text` and `words` (`[{"w","s","e"}]` in source seconds = the burst's `offset` + word time) into bursts.json. faster-whisper:
   ```python
   for g in m["groups"]:
       for b in g["bursts"]:
           segs = list(model.transcribe(load_wav(b["wav"]), language=lang, condition_on_previous_text=False, word_timestamps=True)[0])
           b["text"] = " ".join(s.text.strip() for s in segs)
           b["words"] = [{"w": w.word.strip(), "s": b["offset"] + w.start, "e": b["offset"] + w.end} for s in segs for w in s.words]
   ```
3. `transcript.py retakes _keremkit/bursts.json --into repeats.json` - a burst whose end repeats the start of the next take (one burst may sit in between, e.g. a number) is removed up to the next take; tiny bursts and known Whisper hallucinations ("Altyazı M.K.") are ignored. List the found retakes to the user like the other repeats.

On IMG_3810 this found exactly the known retakes (4 takes at 0:29, "Arkadaşlar her..." at 0:52) plus the intro said twice, and left "Tavsiye etmem" alone. With a verbatim model (above) the takes are usually already in the text and `repeats` finds them; run the check anyway - it is cheap when nothing is suspect.

## 5. Cut

`cutlist.py build --words cam.fixed.json --media cam.mp4 --preset <p> --remove repeats.json -o cam.cut.json`

Pauses are found in the **audio** (threshold = the speaker's own level inside the words minus 10 dB, `--rel-db`) and confirmed with the words: Whisper's word ends often run into the following pause, which is why word-only cutting leaves pauses half-cut. Audio regions with no words (coughs, clicks, background noise) are dropped too. The result line says `mode=audio+words`; `mode=words only` means ffmpeg could not analyse the audio (tell the user) or the audio has no pauses below the threshold.

If the user says a cut clips words or sounds rushed, raise `--pad-after` (e.g. 0.12) or use a looser preset; if pauses remain, raise the threshold (`--rel-db -8`, or a fixed `--noise-db -35`) so quieter room noise counts as silence.
