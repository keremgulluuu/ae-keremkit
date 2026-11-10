# Learning from a reference video

Give Claude a video you like and ask for its style:

```
Learn the editing style of reference.mp4 and save it as a style.
```

Claude can't watch video the way you do; it reads still frames, and every frame costs tokens. So KeremKit measures the video with code first (`videoref.py`):

- **Shots** — where the cuts are, found from how much the picture changes between frames.
- **Motion** — inside each shot, the windows where something moves (text pops, zooms, camera moves) and how many frames they take.
- **Colours** — the main colours of each shot.
- **Audio** — loudness and the moments where the sound jumps, and how many of them land on a cut.
- **Contact sheets** — small time-stamped images: a few frames where the picture holds, every frame where it moves.

Claude reads the numbers, looks at one overview image, and opens only the sheets it needs. A 15-second reel costs roughly as much as a page of text instead of hundreds of images. With a Whisper transcript next to it, cut points and caption styles line up with the words.

From there Claude drafts a style — shot rhythm, colours, caption look, transitions, sound effects — and asks you to confirm before saving it.

**Limits.** Real footage can't be recreated: use your own clips or generate replacements. Fonts are matched approximately, and effects from unknown plugins are rebuilt with built-in tools. Learning a style for your own videos is the point; republishing a one-to-one copy of someone else's video isn't.
