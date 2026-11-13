# Downloading videos

`download.py` gets videos from YouTube, TikTok, Instagram and most other sites (X, Facebook, Vimeo, Twitch, Reddit... - everything yt-dlp supports) and makes sure Premiere and After Effects can import them. Download only what the user asks for; respect the platform's terms and the creator's rights - the user decides what they may use.

## First use

`download.py setup` - finds yt-dlp, or installs it into `KeremKit/tools/bin/` from the official GitHub release, and checks ffmpeg (needed to merge and repair) and deno (optional, gives yt-dlp every YouTube client). Installing yt-dlp into the kit is allowed; installing anything system-wide is asked first. `setup --update` when a site stops working - sites change often and an old yt-dlp is the usual cause.

## Why Premiere refuses downloads, and the two fixes

Premiere cannot import **VP9 / AV1** video or **Opus** audio (the "vp09" error). YouTube serves 1440p and 2160p **only** as VP9/AV1; H.264 (avc1) only up to 1080p. So:

| Mode | What it does | Result | Cost |
|---|---|---|---|
| `premiere_fix` | asks for H.264 + AAC streams, no thumbnail/metadata embedding (they can break the MP4 atoms), `+faststart` | imports everywhere; **YouTube max 1080p** | fast |
| `best_repair` | best streams (4K/60, VP9/AV1, SDR preferred over HDR), then re-encodes to H.264 + AAC, same resolution and fps | **4K stays 4K** and imports | re-encode time (GPU if available) |
| `best` | best streams, untouched | may be VP9/AV1 + Opus - **Premiere refuses it** | fast |

So "4K + Premiere" always means `best_repair`. If `premiere_fix` still ends up with a non-H.264 file (a site with no H.264 stream), it is repaired automatically. TikTok and Instagram usually serve H.264 already - then nothing is re-encoded.

## The user's words -> the command

Listen for quality, mode, folder, audio and subtitles in the request; ask only for what is missing.

| User says | Pass |
|---|---|
| nothing about quality | `--mode <download.mode>` (the user's preference; `ask` -> ask) |
| "4K", "en yüksek kalite", "best quality" + Premiere / editing | `--mode best_repair --quality 2160p` (or `best`) |
| "4K indir + onarım yap" | `--mode best_repair --quality 2160p` |
| "Premiere fix", "Premiere'e atılacak", "hızlı" | `--mode premiere_fix` |
| "1080p", "720p" | `--quality 1080p` ... (with the mode as above) |
| "onarma", "ham dosya", "olduğu gibi" | `--mode best` |
| "sadece ses", "mp3" | `--audio mp3` (or `m4a`, `wav`) |
| "altyazısıyla" | `--subs tr,en` (as .srt) |
| a playlist / "hepsini" | `--playlist` (say how many items first: `info`) |

**Switching the Premiere fix on/off:** a request in passing ("bu sefer Premiere fix kapalı") applies to that download only. "Always / from now on" -> `pref set download.mode premiere_fix|best|best_repair|ask` and confirm in one line.

## Steps

1. **Folder:** `download.folder` is `ask` -> ask every time, offering `download.last_folder`:
   > Where should I save it? (last time: <last_folder>)
   For an edit, a sensible offer is the project's footage folder. A folder named in the request is used without asking. Only if the user says "always save to X": `pref set download.folder "fixed"` and `download.last_folder` = X.
2. Unsure what a video offers (e.g. "is there 4K?") -> `download.py info URL` (one call, a few lines): best quality, best H.264 quality, and what each mode will give. When the user asked for 4K with `premiere_fix`, say in one line that YouTube gives 1080p that way and offer `best_repair`.
3. `download.py get URL --out <folder> --mode <mode> [--quality ...] [--audio ...] [--subs ...]`
   - One `OK` line per file: path, codec, resolution, fps, `premiere=ok|NO (...)`, and `repaired=<strategy>` when re-encoded. The original VP9/AV1 file is deleted after a successful repair (`--keep-raw` keeps it).
   - `download.last_folder` is saved by the script.
   - Long downloads/repairs (4K, long videos): run in the background and report when done.
4. Report in 1-2 lines: file name, quality, Premiere-safe or not, where it is.

## Sign-in / cookies

Public videos need nothing. When the error says sign-in, private, age-restricted or rate-limited (the script adds a `HINT`), follow `download.cookies`:
- `ask` (default): ask once for that download -
  > This video needs a signed-in session. May I use your browser's cookies? Which browser (Firefox works best; Chrome/Edge may block it while open) - or do you have a cookies.txt?
  then pass `--cookies-from-browser <name>` or `--cookies <file>`. Remember the answer only if the user says "always".
- `never`: report that it needs sign-in and stop.
- a browser name or a cookies.txt path: use it.
Never ask for passwords; cookies stay on the user's computer.

Windows: Chrome, Edge and Brave (127+) use app-bound encryption - yt-dlp cannot read their cookies, open or closed ("Failed to decrypt with DPAPI", "Could not copy Chrome cookie database"). Working routes: **Firefox** (`--cookies-from-browser firefox`) or a cookies.txt exported by an extension from a browser that is signed in. A logged-out export gives "empty media response": for Instagram check the file contains a `sessionid` cookie - by name only (`grep -c sessionid cookies.txt`), never print the values.

## Repairing a file that is already there

`download.py check FILE` -> `premiere=ok` or the reasons (VP9/AV1/Opus, 10-bit H.264, variable frame rate). `--scan` decodes the whole file and scores damage (none / mild / moderate / severe / catastrophic).

`download.py repair FILE [-o OUT]` writes `<name>_premiere.mp4` next to it; **the original is never changed**. `--strategy auto` scans first and starts at the matching step of the chain, moving on when the result does not validate:

| Step | What | For |
|---|---|---|
| `container` | stream copy + faststart | broken container / index, codec already fine |
| `standard` | re-encode H.264 + AAC 48 kHz, yuv420p, same size/fps; VFR -> constant fps | VP9/AV1/Opus, 10-bit, VFR (the usual "Premiere won't import") |
| `conceal` | re-encode ignoring decode errors | corrupt frames |
| `aggressive` | large probe, regenerated timestamps, error ignore, light denoise | timestamp chaos, heavy damage |
| `segmented` | split into 10 s pieces, repair each, join | catastrophic damage; recovers what it can |

Encoder: `download.encoder` (`auto` = NVIDIA NVENC -> Intel QSV -> AMD AMF -> libx264, each tested first; a failing GPU encode falls back to libx264). Quality CRF 18 (`--crf`). A result is accepted when it decodes cleanly, keeps the duration (±5 %), has a sane size and is Premiere-safe. All steps failing -> say so; the original is untouched.

HDR sources: `best`/`best_repair` prefer SDR streams. A repaired HDR file keeps its HDR flags - tell the user to set the sequence's Color Setup (`premiere.md`).

## Troubleshooting

- `ERROR ... needs to be reloaded` (YouTube): the script already retries once with other player clients; then `setup --update`.
- TikTok "unable to extract": `setup --update` (TikTok changes often); the script uses browser impersonation and a 1 s request delay.
- Instagram: most reels need cookies (above). `premiere_fix` may still re-encode (Instagram's served stream is not always Premiere-safe); a `_1` suffix on the output is the repaired file's name, not a clash.
- TikTok "Impersonate target chrome not available": the system yt-dlp without impersonation may get only 540p HEVC - re-encode to H.264 (`download.py repair`) before AE/Premiere.
- Repeated failure with the same method -> stop and report (Token rule 8); log the cause in `learning/known-issues.md`.
