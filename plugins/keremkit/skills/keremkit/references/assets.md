# Free stock elements

When an edit or design needs something that is neither in the library nor worth building - a green-screen clip, a light-leak overlay, a sound, a music bed, an icon, a texture, a font - `assets.py` searches free sources at once and downloads only what the user picks. Claude reads short result lines; images are shown to the user, never opened by Claude. Order of preference: the user's library -> these sources -> building from scratch.

## Search, show, get

0. `assets.py have "<words>" [--type T]` - already downloaded? (`KeremKit/assets/INDEX.tsv`). A hit costs nothing - use it.
1. `assets.py search <type> "<words>"` - types: `photo video greenscreen overlay background vector lottie sfx music icon logo texture hdri model font`. It also prints `HAVE` lines for matches already downloaded. Numbered lines: source, size/length, licence, title. Results are cached 24 h; repeating a search costs nothing.
2. Pictures and video: `assets.py sheet` -> one numbered image of the thumbnails; send it to the chat (`library-use.md` -> Showing options, same rules: don't open it). Sound: list the lines (title, length) and let the user choose; offer to download 2-3 to compare.
3. `assets.py get 2 5` - downloads into **`KeremKit/assets/<type>/<source>/`** (the default; `-o` only when the user names another folder), adds a line per file to `SOURCES.md` there and to `KeremKit/assets/INDEX.tsv` so it is found again. Videos from `download.py` are the exception: they go where the user says.
4. Import into AE (`project.import_file`); SVG imports as vectors in AE versions that support SVG (else see "Using them" below). Offer once to save a keeper to the library (`library-save.md`).

Only licences that need **no credit** are listed (CC0, public domain, Pexels, Pixabay, MIT/Apache/ISC/BSD/OFL). Preference `assets.allow_attribution: true` (or `--allow-attribution` once, when the user asks) also lists CC BY items; they are marked `[credit needed]` and `SOURCES.md` says so - tell the user the credit line to put in the description.

## Which site for what - "what can I download?"

`assets.py sources [type] [--full]` prints, per site, what it is best at, its licence, whether a key is needed, how it is reached (API, or links + import) and the usual **token cost** (az / orta / çok). `--full` adds everything each site offers.

When the user asks which sites there are, or what they can download:
1. Run `assets.py sources` (with a type if they named one, `--full` when they want everything).
2. Answer per site with its **best side** first, then **everything it offers**, its licence (credit needed or not), whether a key is needed, and the **token cost** of using it.
3. Before any search or download, still give the one-line estimate (`token-budget.md`).

The same table, in short:

| Need | Best sites (via) | Token cost |
|---|---|---|
| Polished photos, textures, abstract backgrounds | Unsplash (API, free key), Pexels / Pixabay (API), StockSnap (API previews, full size on the page), Kaboompics / Magdeleine / Burst (links) | az (API), orta (links) |
| Video, green screen, overlays | Pexels, Pixabay (API), Mixkit (links) | az |
| Vector illustrations (SVG) | unDraw, Wikimedia, Openverse (API) | az |
| Real `.ai` / `.eps` vector files | Public Domain Vectors, Vector4Free, Getillustrations (links + import); Vecteezy / Freepik only with credit | orta-çok |
| Icons, logos | Iconify, Dashboard Icons, Simple Icons (API) | az |
| PBR textures, HDRIs | Poly Haven, ambientCG (API); Lost and Taken (grunge/paper/film textures, links) | az |
| 3D models | Poly Haven, Sketchfab (CC0, token for downloads), NASA, ambientCG, Poly Pizza (API); Quaternius, Kenney (links) | az-orta |
| Lottie animations | LottieFiles (API) | az |
| Sound effects, music | Freesound, Openverse (API); Pixabay / Mixkit / YouTube Audio Library (links) | az-orta |
| Fonts | Fontsource (API) | az |
| AE / Premiere templates, MOGRT | Mixkit (links) | orta |

Using them:
- **`.ai` / `.eps` / `.pdf`** import into After Effects directly (as footage or shape layers via "Create Shapes from Vector Layer"). **SVG** opens in Illustrator; whether the installed AE imports SVG directly depends on its version - check with a small import first. If it cannot, and Inkscape is installed, convert to PDF (`inkscape in.svg --export-filename=out.pdf`).
- **Lottie:** After Effects needs a Lottie importer plugin; Premiere cannot place Lottie (render it to a video with alpha in AE first).
- **Unsplash:** the kit tells Unsplash about each download (their API rule) and writes "Photo by <name> on Unsplash" into SOURCES.md. The user owes no credit, but it is a good habit.
- **Links-only sites:** `assets.py links <type> "<words>"` gives the search pages; the user downloads; `assets.py import <file> --type <type> --source <site> --license "<licence>" --url <page>` files it into `KeremKit/assets/` and the index.

## Sources

| Type | Sources (API) | Key |
|---|---|---|
| photo | Unsplash, Pexels, Pixabay, StockSnap (previews), Openverse (CC0/PD), Wikimedia Commons (PD/CC0) | Unsplash, Pexels, Pixabay: free key |
| vector | unDraw, Wikimedia Commons (SVG), Openverse (SVG) | - |
| lottie | LottieFiles | - |
| video, greenscreen, overlay, background | Pexels, Pixabay, Wikimedia Commons (+ Unsplash photos for background) | free key |
| sfx | Freesound (CC0 only), Openverse audio; or synthesise with `sfx.py` | Freesound: free key |
| music | Openverse audio (CC0/PD), Freesound (CC0) | - |
| icon | Iconify (permissively licensed sets only) | - |
| logo | Dashboard Icons (colour), Simple Icons (one colour) | - |
| texture, hdri | Poly Haven, ambientCG (CC0) | - |
| model | Poly Haven, Sketchfab (CC0 + downloadable, incl. Smithsonian/museum scans), NASA 3D Resources, ambientCG, Poly Pizza | Sketchfab: search free, **download needs the user's free API token** (`keys set sketchfab=...`); Poly Pizza: free key |
| font | Fontsource (Google Fonts, OFL/Apache) - the user installs the .ttf | - |

`SKIPPED pexels: no key` -> the source needs a free API key: tell the user once where to get it (pexels.com/api, pixabay.com/api/docs, freesound.org/apiv2/apply, unsplash.com/developers) and save it with `assets.py keys set pexels=...` - stored only in `KeremKit/settings/keys.json`, never in memory, logs or replies. Without keys the other sources still work.

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
