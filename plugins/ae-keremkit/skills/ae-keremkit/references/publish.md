# Publishing helpers

## Chapters (YouTube)

1. `transcript.py review cam.fixed.json --cutlist cam.cut.json --at <placement start>` - the transcript in **timeline** times, with cut parts skipped. For multi-part edits run it per placement and merge by time.
2. Group into topics. YouTube rules: first chapter at `00:00`, at least 3 chapters, each at least 10 s.
3. Output in the user's language:
   ```
   00:00 Giriş
   01:12 Claude'u kurmak
   04:30 İlk edit
   ```

## Titles and description

From the corrected transcript: 3-5 title options (under ~60 characters, the main promise first), and a description draft (2-3 sentence summary, the chapters, any links the user mentions). Ask about tone if unclear. These are suggestions; nothing is published.

## Thumbnail frames

`qc.py thumbs <render> -n 6 -o _keremkit/thumbs` writes sharp, representative frames spread over the video. Give the user the folder; don't open the images yourself unless asked (`verification.md`). If they pick one, it can be used in a thumbnail design (`design-import.md` / library).

## Logos and brand marks

Use a logo only when that name is actually said or shown in the video, or the user asks for it. Preference `logos.confirm`: `ask` (default) - get the user's OK for the list first; `off` - add them without asking and name them in one line of the report. Get them with `assets.py logo <Brand> -o <project>/assets/logos` (`assets.md`), or the official press kit; `SOURCES.md` records file, source and licence. Never recolour or alter a logo beyond a single-colour version for dark backgrounds, and don't make the video look sponsored.

## Finishing in another editor

- **Premiere Pro:** `cutlist.py export cam.cut.json --format xmeml -o cam_cut.xml` (FCP7 XML: media linked, one master clip, frame-exact) - details, HDR colour note and the MCP route in `premiere.md`.
- **DaVinci Resolve / Avid:** `--format edl -o cam.edl` (CMX3600, frame-exact, one audio track; media is linked by hand).
- **Final Cut Pro / Resolve:** `--format fcpxml -o cam.fcpxml`.

One event per kept segment, pointing at the original recording; subtitles go along as `subs.srt`. Deliverables go into `<video name> - Bileşenler` next to the video when the user has that rule.
