# FAQ

**Does it work with any After Effects MCP server?**
It needs a server that exposes `ae_do` (with `batch.run`), `ae_catalog` and `ae_context`. It was built against [`@kumoproductions/mcp-aftereffects`](https://github.com/kumoproductions/mcp-aftereffects). Other servers will need small changes to the references.

**Why doesn't Claude look at the screen after every change?**
An image costs many times more tokens than the same information as numbers. KeremKit checks positions, text fit, timing and missing files numerically. Ask "check it" when you want eyes on something.

**Why is cutting done outside After Effects?**
After Effects has no transcription, and hundreds of layer splits are slow and fragile. ffmpeg cuts in seconds and the cut list keeps every decision editable.

**Can I use it in a language other than English or Turkish?**
Yes. Claude replies in the language you write in. Library items get an English name plus a name in your language. Subtitles work in any language Whisper supports; line-break rules are built in for seven languages and you can add your own words with `no_break_after`.

**Where are my styles stored? What happens if I reinstall?**
In your `KeremKit` folder, not in the skill. Reinstalling or updating the skill doesn't touch it. A pointer file in your home folder (`.keremkit.json`) tells Claude where it is.

**Can I share my styles and library?**
Zip the `KeremKit` folder (or just `styles/` and `library/`). The other person installs the skill and points setup at the unzipped folder. Library items carry their own footage in `sources/`; fonts and third-party plugins have to be installed on their machine.

**Python isn't found on Windows.**
Try `py` instead of `python`. Claude saves whichever command works.

**The subtitle layer is empty.**
The name in `footage("subs.json")` must match the imported item exactly. Times after the last cue are intentionally empty.

**Claude made a change I don't like.**
Ctrl+Z — each Claude action is one undo step. For bigger rollbacks, open the latest `_vNNN.aep` checkpoint.

**Is this an official Adobe or Anthropic product?**
No. It's an independent open-source project.
