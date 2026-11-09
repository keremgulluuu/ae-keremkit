# Effect Presets (.ffx)

KeremKit learns the user's After Effects presets so it can find, explain and apply them without guessing: which effects a preset adds, which properties it animates (timing, values, easing), its expressions, and **which presets need third-party plugins**. Each preset becomes a card in the library (category `fx-preset`, prefix `FXP`); presets that need a plugin carry `[requires plugin]` in their name and list the plugin.

`.ffx` files are binary. They are learned by applying them to test layers in a throw-away lab comp, exporting that comp once, and reading the export with `presets.py`. Nothing in the user's own comps is touched.

## Learning presets

1. **Where:** `paths.presets` from preferences; if empty, ask once:
   > Which folder holds your After Effects presets? (Your own are usually in `Documents/Adobe/After Effects <version>/User Presets`.)
   Learning the ~300 presets that ship with After Effects is optional - ask before including the program's `Support Files/Presets` folder.
2. `presets.py scan <dir> [<dir> ...] -o _keremkit/presets_scan.json` - lists every `.ffx`, decides a test layer (text presets get a text layer, others a solid) and a lab layer name.
3. Checkpoint, then build the lab in batches of ~30: `presets.py plan scan.json --batch 30 --from 0 -o batch.json`, run its `ops` as one `batch.run` (`stopOnError: false`), continue with the printed `next_from`. Collect failed `layer.apply_preset` results into a small JSON `{ "<lab layer name>": "<error text>" }` - a failure usually means a missing plugin.
4. `ae_project_export_json(outPath=_keremkit/preset_lab.json)` - one export for all presets.
5. `presets.py learn scan.json --export preset_lab.json --errors errors.json` - writes one card per preset (`meta.json` + a copy of the `.ffx`), adds catalog rows, prints totals and the plugins found. Re-running updates existing cards instead of duplicating them.
6. `comp.delete KK_PRESET_LAB` (one undo step if anything goes wrong). Do not save the project for the lab.
7. `presets.py insights` - refreshes `learning/presets-insights.md`: most used effects, most animated properties, typical lengths, interpolation, plugins relied on.
8. Report in 2-3 lines: how many learned, how many need plugins (by plugin), how many failed.

If the export schema yields empty cards for presets that clearly did something, read the lab layers instead with one `ae_layer_info(KK_PRESET_LAB, "all", detail: "summary")` call and write the cards from that.

## Saving one effect stack as a preset

Scripts cannot create `.ffx` files. When the user says "save this effect as a preset":
- Ask them to save it in AE (*Animation > Save Animation Preset*) into their presets folder, then learn just that file (scan + plan + learn on that folder, or that one file's folder).
- Or, if they prefer, save it as a normal library item (`library-save.md`) - the effects and keyframes live in the item's `.aep`.

## Answering questions about presets

Use the cards - never guess from memory.

| Question | How |
|---|---|
| "Which of my presets use Deep Glow?" | `keremkit.py search deep glow --type item` (cards are tagged with effect, property and plugin names) |
| "What does Soft Glow Pop do?" | `presets.py show "soft glow pop"` - effects, keyframes (count, time span, from/to values, easing), expressions |
| "Which presets need plugins?" | search `requires plugin`, or read the totals from the last `learn` |
| "What kind of animations do my presets have?" | `learning/presets-insights.md` |

Answer in plain language from the card: e.g. "It adds Glow and animates Glow Intensity 0→2.5 and Scale 80→100 % in 0.4 s with eased keyframes. No plugins needed."

## Applying a learned preset

1. Find the card; if `requires_plugins` is not empty, check once per session whether the plugin is installed: `project.list_effects` and look for the effect's `matchName`. Missing -> tell the user which plugin is needed and stop.
2. `layer.apply_preset` with the card's `preset.ffx` (the copy in the library, so it works even if the original folder moves). Text presets need a text layer.
3. Verify with `comp.sample` at the card's keyframe times if timing matters.

## Using presets as knowledge

When designing new motion, read `learning/presets-insights.md` (it is short) and prefer the durations and easing the user's own presets use. If a learned preset already does what is asked, offer it instead of building from scratch.
