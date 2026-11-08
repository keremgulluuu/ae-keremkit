# Usage

KeremKit doesn't have commands to memorise. You talk to Claude the way you'd talk to an editor sitting next to you; the skill decides which tool to use. This page shows what's possible and how to phrase things so you get what you mean on the first try.

## The KeremKit folder

```
KeremKit/
  settings/preferences.json   your remembered choices
  settings/categories.json    library categories
  library/                    saved designs (CATALOG.tsv + one folder per item)
  styles/                     edit styles and their archived versions
  learning/                   your house style and solved problems
  tools/                      the scripts Claude runs on your machine
```

You can open and edit any of these files by hand. Claude reads them fresh each time.

## Preferences

Claude never guesses a preference. The first time something matters — cut tightness, render format, whether to use sound effects — it asks once and saves the answer.

- **Make something permanent:** say *always*, *never*, *from now on*. "From now on render ProRes 422 HQ."
- **Keep it one-off:** say *just this time* or *for this video*.
- **Global or style?** If it's unclear, Claude asks whether the rule is for every edit or only for one style.
- **See or change everything:** "Show me my KeremKit settings", "Run the setup again".

## Cutting

```
Cut the silences in camera.mp4. Tight.
```

Claude transcribes the file with Whisper, builds a cut list, renders a cut file with ffmpeg and places it. The cut list remembers every decision, so fixes are quick:

| Say | Effect |
|---|---|
| "0:10–0:12 is too fast, add a second" | gives back up to 1 s of removed pause in that range |
| "a little air at 0:23" | ~0.3 s at the nearest cut |
| "remove 0:40–0:42" | cuts that output range |
| "bring back 1:20–1:25 from the original" | restores source time |
| "undo that" | reverts the last cut change (20 steps kept) |
| "where are the cuts around 0:30?" | lists cuts and how much pause each removed |

Times are **output** times unless you say "in the original". After any fix, clips placed later on the timeline move with it and subtitles are rebuilt.

## Subtitles

```
Add subtitles. 3-4 words, two lines, follow sentences, highlight numbers.
```

The first time, Claude asks a few rule questions and remembers the answers. Subtitles live in a single text layer that reads a JSON file, so you can change rules, fix cuts or re-time the edit and only the file is rebuilt. You also get an `.srt` for YouTube or other editors. Details: [subtitles-and-cutting.md](subtitles-and-cutting.md).

## Library

```
Save this as "glass info card".
Put the glass info card at the top left, 0:05 to 0:09, text "New update".
```

Saved items keep their adjustable values (text, numbers, colors, duration) as parameters. Each item has an English name and, if you work in another language, a name in that language — search works with either, with or without accents.

If something doesn't fit any category, Claude suggests a new one. You can also ask: "Add a category for 3D objects."

## Edit styles

```
Edit D:\Shoot\0412 in my Kerem style, vertical.
```

See [edit-styles.md](edit-styles.md).

## Checking work

By default Claude verifies with numbers: positions against safe areas, text fit, timing, missing fonts or footage. No images.

- "Check it" → numeric checks and, if needed, one small frame.
- "Show me properly / full quality" → a full-resolution frame or contact sheet.

## Checkpoints and undo

Before risky operations Claude saves `Project_v001.aep`, `_v002`, … next to your project. Each Claude action in After Effects is a single undo step, so Ctrl+Z works the way you'd expect.
