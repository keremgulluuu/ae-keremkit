# Learning from a reference video

The user gives a finished video and wants its style, rhythm or a recreation in After Effects. Claude cannot watch video; it reads frames as images, which are expensive. So code measures first and Claude looks only where it matters.

## 1. Package the video

`videoref.py <video> -o _keremkit/ref_<name>` (ffmpeg + standard library, a few seconds for a short reel) writes:
- `README.md`: shots with start/end/duration (cuts found from frame differences), motion windows inside each shot, main colours per shot, audio loudness and onsets (and how many land on cuts), the list of sheets with their token cost;
- `sheets/00_overview.jpg`: one frame per shot;
- `sheets/shotNN*.jpg`: start/middle/end of each shot and the frames where something moves (up to 12 per motion window), each stamped with its time;
- `data.json`: the same plus the frame-by-frame motion curve.

Also transcribe the video with Whisper (`transcript.md`) when it has speech: words + timing explain most cut points and caption styles.

Tuning: `--cut` (default 28) lower finds softer cuts/dissolves; `--move` (default 2.5) lower catches subtler motion; `--max-motion-frames` raises density for fast animations.

## 2. Read it economically

1. Read `README.md` (text).
2. Open `00_overview.jpg` once.
3. Open shot sheets only for the shots the question is about. A 15 s reel is typically ~9k tokens for all sheets; most questions need two or three.
4. Never open the original video frames one by one.

## 3. Turn it into reusable knowledge

- **Rhythm**: shot durations and the cut/onset alignment -> the style's `editing.rules` (`edit-plan.md`) and SFX rules (`sound-effects.md`).
- **Look**: colours from the README, type and layout from the sheets -> tokens (`design-import.md`) and the style's `look`.
- **Motion**: a motion window's frame count and the positions across its frames give duration and easing (fast start + long settle = ease-out). Match them to techniques (`techniques.py list`) or build library items.
- Confirm with the user in a compact list before building, as with any design import.

## 4. Limits - tell the user up front

- Real footage (people, places) cannot be recreated; the user supplies their own or generates replacements.
- Fonts are identified approximately; plugins and presets used in the original are unknown - effects are rebuilt with built-in tools.
- Recreating someone else's video one-to-one for publishing can infringe their rights; learning the style and applying it to the user's own content is the intended use.
