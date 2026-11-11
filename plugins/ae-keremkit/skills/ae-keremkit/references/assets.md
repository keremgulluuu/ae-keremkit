# Free stock elements

When an edit or design needs something that is neither in the library nor worth building - a green-screen clip, a light-leak overlay, a sound, a music bed, an icon, a texture, a font - `assets.py` searches free sources at once and downloads only what the user picks. Claude reads short result lines; images are shown to the user, never opened by Claude. Order of preference: the user's library -> these sources -> building from scratch.

## Search, show, get

1. `assets.py search <type> "<words>"` - types: `photo video greenscreen overlay background sfx music icon logo texture hdri model font`. Numbered lines: source, size/length, licence, title. Results are cached 24 h; repeating a search costs nothing.
2. Pictures and video: `assets.py sheet` -> one numbered image of the thumbnails; send it to the chat (`library-use.md` -> Showing options, same rules: don't open it). Sound: list the lines (title, length) and let the user choose; offer to download 2-3 to compare.
3. `assets.py get 2 5 -o <project>/assets/<type>` - downloads, and adds a line per file to `SOURCES.md` there (source page, author, licence, date).
4. Import into AE (`project.import_file`); SVG icons and logos import as vectors. Offer once to save a keeper to the library (`library-save.md`).

Only licences that need **no credit** are listed (CC0, public domain, Pexels, Pixabay, MIT/Apache/ISC/BSD/OFL). Preference `assets.allow_attribution: true` (or `--allow-attribution` once, when the user asks) also lists CC BY items; they are marked `[credit needed]` and `SOURCES.md` says so - tell the user the credit line to put in the description.

## Sources

| Type | Sources (API) | Key |
|---|---|---|
| photo | Pexels, Pixabay, Openverse (CC0/PD), Wikimedia Commons (PD/CC0) | Pexels, Pixabay: free key |
| video, greenscreen, overlay, background | Pexels, Pixabay, Wikimedia Commons | free key |
| sfx | Freesound (CC0 only), Openverse audio; or synthesise with `sfx.py` | Freesound: free key |
| music | Openverse audio (CC0/PD), Freesound (CC0) | - |
| icon | Iconify (permissively licensed sets only) | - |
| logo | Dashboard Icons (colour), Simple Icons (one colour) | - |
| texture, hdri | Poly Haven, ambientCG (CC0) | - |
| model | Poly Haven, Sketchfab (CC0 + downloadable, incl. Smithsonian/museum scans), NASA 3D Resources, ambientCG, Poly Pizza | Sketchfab: search free, **download needs the user's free API token** (`keys set sketchfab=...`); Poly Pizza: free key |
| font | Fontsource (Google Fonts, OFL/Apache) - the user installs the .ttf | - |

`SKIPPED pexels: no key` -> the source needs a free API key: tell the user once where to get it (pexels.com/api, pixabay.com/api/docs, freesound.org/apiv2/apply) and save it with `assets.py keys set pexels=...` - stored only in `KeremKit/settings/keys.json`, never in memory, logs or replies. Without keys the other sources still work.

`some sources are not reachable` -> the shell has no access to those sites (e.g. a cloud workspace). GitHub-hosted sources (logos) usually still work; for the rest run the tool on the user's computer, or use links.

## 3D models in After Effects

- Search: `assets.py search model "<words>"` (and `texture` / `hdri` for materials and lighting). Prefer `.glb` - one file with textures inside. More sites without an API: `assets.py links model "<words>"` (Quaternius, Kenney 3D, Smithsonian 3D...).
- NASA models are not copyrighted, but NASA's media guidelines apply: no endorsement implied, no NASA logo/insignia use. Sketchfab CC BY models (only with `--allow-attribution`) need the credit line from SOURCES.md.
- ambientCG materials arrive unpacked into a folder (colour, normal, roughness, displacement maps).
- After Effects 2024+ imports `.glb` / `.gltf` / `.obj` as 3D model layers (Advanced 3D renderer): import the file, set the comp renderer to Advanced 3D, light it with an environment light (an `.hdr` from the hdri search). Older AE: a 3D plugin (Element 3D) or a pre-rendered video. Check the user's AE version (`ae_context`) before promising native 3D.
- Heavy models (Sketchfab scans can be 100k+ faces): mention the face count from the search when it is large; render times grow.

## Sites without an API (templates, MOGRT, more music and sound)

`assets.py links <type> "<words>"` - types also include `template mogrt aep prfpset ffx game`. Gives search pages (Mixkit, Pixabay music and sound effects, YouTube Audio Library, Kenney). The user downloads; then `assets.py import <file> -o <dir> --source Mixkit --license "Mixkit Free License" --url <page>`. Mixkit also has a personal-use-only licence on some items - check the item page. Presets: then `presets.py learn`; templates: open a copy, never the downloaded original.

## Logos

`assets.py logo Instagram YouTube -o <project>/assets/logos` - colour version (Dashboard Icons) when there is one, else the one-colour Simple Icons mark in the brand colour; `--mono` for one colour, `--png` for PNG.

Preference `logos.confirm`: `ask` (default - list the logos first and get an OK) or `off` (add logos of brands named in the video or by the user without asking; one line in the report: "Added: Instagram logo (Dashboard Icons)"). Either way: never stretch, recolour (beyond the official one-colour version) or alter a logo, and don't place it so the video looks sponsored or official.
