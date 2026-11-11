# Token budget

Every job costs tokens: tool answers, files read, images. This file covers three things: how to estimate the cost and tell the user before acting, how to keep it low in After Effects and Premiere, and how the agent reports what was expensive so the kit gets cheaper.

## 1. Estimate before every operation

Before each operation (a search, a download, a cut, a build step, a render, a style learn), say the expected cost in one short line, in the user's language. For example: `Tahmini token: az` / `orta` / `çok`. A multi-step plan gets one estimate per step and one total. When the real cost turns out a class higher, say so in the report.

| Class | Tokens (rough) | Typical |
|---|---|---|
| **az** (low) | up to ~3k | one search/download, a preference, `keremkit.py` / `cutlist.py` one-liners, one `ae_do` batch, a `prbatch.py` plan |
| **orta** (medium) | ~3k-15k | transcript review of a 2-min video, a design plan with library search, a contact sheet the user looks at, 5-15 direct Premiere calls, a manual import |
| **çok** (high) | 15k+ | a whole edit built call by call, reading a project export, learning a style from a big project, screenshots/frames Claude looks at, 40+ direct MCP calls, one MOGRT per caption cue |

Typical costs (direct tool calls from the chat):

| Operation | Class | Why / cheaper way |
|---|---|---|
| `ae_context` | az | once per session |
| `ae_catalog <category>` | az-orta | once per category; keep a short list in `cache/ae_catalog/<category>.txt` and read that next time |
| one `ae_do` / `batch.run` (with verification reads at the end) | az | put many ops in one batch |
| `ae_project_export_json` read inline | çok | always `outPath` + `digest.py` (az) |
| `ae_render_frame` with `analyze` numbers | az | looking at the PNG is orta-çok, only on request |
| Premiere read (`get_sequence_structure`, one sequence) | az | never `get_full_project_overview` on big projects (çok) |
| Premiere write, direct | az each (~1-2k) | many writes -> `prbatch.py` (one line per step) |
| Premiere build of one video, call by call | çok (60-150k) | `prbatch.py` plans: orta |
| `import_mogrt` per caption cue (80-100 cues) | çok | `prbatch.py`: orta |
| Transcription (Whisper / CrisperWhisper) | az | runs locally; read `transcript.py review`, never the raw JSON |
| `assets.py search` + `get` | az | `assets.py have` first - already downloaded = free |
| `assets.py sheet` (user looks) | az | Claude never opens it |
| Video download (`download.py get`) | az | 4K repair takes time, not tokens |
| Style learned from a .prproj (`analyze` + `inventory`) | orta | read the inventory, not analysis.json |
| Reading a reference file of this skill | az-orta (1-3k each) | read only the one the task needs |

## 2. After Effects: the cheap way

- `ae_context` once per session; then use the context each `ae_do` returns.
- Many operations = one `batch.run`, with `comp.info` / `layer.bounds` / `comp.sample` at the end of the same batch. An id created inside a batch cannot be used in that batch, so split into two.
- Read little: `layer.info` with `detail: "summary"`; project exports to a file + `digest.py`; `ae_catalog` only for the needed category. Save the category's op list in `KeremKit/cache/ae_catalog/<category>.txt` (op names + key args, one line each) and read that in later sessions instead of calling again; refresh it when the AE MCP version changes (`ae_context`).
- Heavy work outside AE: Whisper, `transcript.py`, `cutlist.py`, `subtitles.py`, ffmpeg. Read their one-line results.
- Verify with numbers, not frames (`verification.md`).
- Try a bulk change on one layer, then apply to all in one batch.

## 3. Premiere: the cheap way

- **`prbatch.py` for anything over ~5 calls.** Write the calls into a plan file, run `prbatch.py run plan.json`, and read one line per step. The full answers go to `plan.results.json`; open it only for the step that failed or a value needed next (`pick` the field in the plan instead). Preview → apply with tokens works inside one plan (`save_as` / `token_from`).
- Direct MCP calls from the chat only for a first look and for decisions that need the answer at once.
- `expected_project_path` on every write (the plan adds it to every step).
- Writes one at a time. A parallel batch that hits a recovery lock (`HOST_RECOVERY_REQUIRED`) wastes every call after it; `prbatch.py` stops at the first error.
- Narrow reads: `get_sequence_structure` for one sequence, `get_track_info` for one track. On projects with many sequences (180 in Ecomelih Reels1) never ask for a full overview.
- Effects with keys: copy from a template clip in the same sequence (`copy_effects_between_clips`) instead of building keys one by one. That is ~3-5 calls instead of ~20 per clip. It keeps both Transform effects and the exact bezier easing.
- Set a call budget per task in the plan (e.g. "intro 6 calls, each product nest 4, film burn 3") and report when it is exceeded.

## 4. General

- Resume from `_keremkit/log.md` instead of re-reading the project.
- Search catalogues, known issues and indexes with the tools or grep; open one file, not a folder.
- Scripts print one line per result; use `--brief` where it exists.
- Same method failed twice → stop and report (SKILL.md Token rule).
- Large outputs (transcripts, inventories) go to files; read only the part needed (`--from/--to`, `grep`).

## 5. Token notes and session report (the agent writes these, every task)

**The agent writes these notes after every task, without asking and without holding back.** Mistakes, waste and guesses that turned out wrong go in too. Write them plainly; the maintainer needs the real picture to make the next version cheaper.

1. **`learning/token-notes.md`:** append one entry per task.
   ```
   ## 2026-11-12 IMG_3820 Premiere build (estimate: orta, felt: çok)
   - Expensive: 34 direct add_keyframe calls (~1.5k each) - the template nest was missing, so keys were built one by one.
   - Expensive: read analysis.json (180 sequences) instead of the inventory - ~20k.
   - Saved: prbatch plan for cuts (12 steps -> 12 lines).
   - Saved: assets.py have found the textures from last week - no new search.
   - Proposal: ship a template nest with the style; add a `prproj.py inventory --seq` filter.
   ```
   Each line names the call or file, the rough cost and the reason. Proposals may target the skill, a tool or the user's workflow.
2. **`learning/sessions/<YYYY-MM-DD>-<topic>.md`:** the session report.
   - What was asked, what was done (files, settings, decisions) and what is still open or was not verified.
   - The token notes in short.
   - The commands or prompt to continue in a new chat.

   At the end of the task, give the user its full path in one line so they can take it to another chat.
3. Something that needs the skill itself changed still goes to `learning/skill-change-requests.md` (SKILL.md, "The skill is read-only").
