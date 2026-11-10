# Setup (first use)

Goal: create the KeremKit home folder, detect tools silently, and ask the three setup questions once - in the user's language. If the user skips a question, record it in `setup.skipped` and ask it again only when that answer is actually needed.

Use the session's multiple-choice question tool when there is one; otherwise ask in plain text, one question at a time.

## 1. Settings folder

> Do you have a specific folder for your KeremKit settings? If so, where is it? (If not, `Documents/KeremKit` will be used.)

Then run `keremkit.py init [PATH]`. It creates the folders, default `preferences.json` and `categories.json`, the learning files, copies the tools into `KeremKit/tools/`, and writes the pointer file `~/.keremkit.json` so later sessions find the folder. Re-running `init` only adds what is missing; it never overwrites user data.

Set `language.library` now if the user writes in a language other than English (see SKILL.md -> Language).

## 2. Detect tools (silently)

Check on the user's computer and save the results with `pref set`:

| Tool | Check | Save to |
|---|---|---|
| Python | `python --version`, `py --version`, `python3 --version` | `tools.python` (the command that worked) |
| ffmpeg / ffprobe | `ffmpeg -version`, `ffprobe -version` | `tools.ffmpeg`, `tools.ffprobe` |
| openai-whisper | `whisper --help` or `python -c "import whisper"` | `tools.whisper.impl = "openai-whisper"`, `path` |
| faster-whisper | `python -c "import faster_whisper"` | `tools.whisper.impl = "faster-whisper"` |
| whisper.cpp | `whisper-cli -h` (or `main -h`) in a folder the user names | `tools.whisper.impl = "whisper.cpp"`, `path` |
| NVIDIA GPU (optional) | `nvidia-smi -L` | `tools.whisper.device = "cuda"`, else `"cpu"` |

Mention only problems, in one line (e.g. "ffmpeg was not found - it is needed for cutting").

## 3. Materials

> Where do you keep your edit materials? Give folder paths - or websites Claude can reach - for images, icons, sound effects, music and fonts. Leave out anything you don't have.

Save to `paths.materials.*` and `paths.web_sources`. The **projects folder** (`paths.projects`, where the user keeps main projects) is asked the first time an unsaved project has to be saved. A project's **footage folders** (camera, voice, screen recordings) are asked the first time an edit needs them and appended to `paths.footage_folders`; once given, they are remembered.

## 4. Subtitles

> Will you add subtitles to your videos?

**No** -> `subtitles.enabled = false`, done.
**Yes** -> `subtitles.enabled = true`, then ask how, based on step 2:

- Whisper found:
  > I found Whisper on your computer (<impl>). Shall we create subtitles with it? Which model should we use?
- Whisper not found:
  > Would you like to create subtitles with Whisper? Is it installed? If so, where - or shall I help you install it?

Show this summary with the question:

| Model | Speed | Accuracy | Needs |
|---|---|---|---|
| tiny / base | fastest | weak, misses words | any CPU |
| small | fast | fair | ~2 GB VRAM or CPU |
| medium | medium | good | ~5 GB VRAM |
| **turbo** (large-v3-turbo) | fast | close to large | ~6 GB VRAM - best balance |
| large-v3 | slowest | best | ~10 GB VRAM |

Save `subtitles.engine = "whisper"`, `tools.whisper.model`, and a language if the user names one (`tools.whisper.language`, e.g. "en"; null = auto-detect). Detailed line/word rules are **not** asked here - they come the first time subtitles are built (`subtitles.md`).

Installing Whisper: give the one command that fits their setup (e.g. `pip install -U openai-whisper`; it needs ffmpeg) and ask before running anything that installs software.

## 5. Finish

`setup.completed = true`; asked keys into `setup.asked`, skipped ones into `setup.skipped`. One-line summary. Nothing else is asked now - every other preference is asked when first needed.

## Re-running

"Change my settings" / "run setup again": ask the questions again with current values shown as defaults. `init` is safe to re-run.
