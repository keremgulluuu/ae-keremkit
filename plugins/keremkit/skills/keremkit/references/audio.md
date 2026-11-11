# Audio

Sound is processed outside AE with `audio.py` (ffmpeg), then the processed file replaces the original in the comp. AE keeps only levels and timing.

## Flow

1. `audio.py analyze <voice or video>` -> one line: LUFS, true peak, loudness range, noise floor, plus advice.
2. Offer the audio techniques (`techniques.md`; `techniques.py list --group audio`), recommending what the analysis points to. Saved choices (`audio.chain`, or the style's) are applied without asking.
3. `audio.py process <in> <out> --chain highpass,denoise,deess,eq,compress,loudnorm --target <audio.target_lufs>`
   - Steps always run in that order whatever order they are given. Video inputs keep their picture (stream copy).
   - `loudnorm` is two-pass and lands within ~0.5 LU of the target; true peak is limited to -1 dBTP.
   - Run on the **cut** voice file (after `cutlist.py render`), so the loudness is measured on what is heard.
4. In AE: `footage.replace` the old file with the processed one (or import and swap the layer source with `layer.replace_source`). Nothing else moves.
5. Report the before/after LUFS in one line.

## Targets

| Destination | Integrated | True peak |
|---|---|---|
| YouTube, Spotify, most social | -14 LUFS | -1 dBTP |
| Apple podcasts | -16 LUFS | -1 dBTP |
| Broadcast (EBU R128) | -23 LUFS | -1 dBTP |

Ask once if the destination is unknown and `audio.target_lufs` is null; default -14.

## Music

- Level: music sits around `audio.music_db` (-18 dB) under speech.
- **Ducking**: `audio.py duck voice_cut.wav music.wav music_ducked.wav` - sidechain compression, music dips while there is speech. Import the result as the `AUD_Music` layer.
- Alternative inside AE (keeps the original file): Audio Levels keyframes on the music layer at the speech regions from the cut list (dip -10 to -14 dB, 0.2 s ramps). Use this if the user wants to adjust ducking by hand later.
- Fade music in/out over 0.5-1.5 s at the start and end of the edit.

## Judgement

- Denoise is gentle by default; heavy noise reduction makes voices metallic. If the noise floor is very high, say so - re-recording beats fixing.
- Do not compress music that is already mastered.
- Keep SFX under the voice (`sound-effects.md`).
