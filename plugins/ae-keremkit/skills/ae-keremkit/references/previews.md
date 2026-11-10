# Library previews

A preview shows what an item **does**. Claude never opens the frames: they are measured as numbers, and the user sees the finished image (`library-use.md` -> Showing options).

## Making previews (one item or a hundred - same calls)

Render from the work copy **before** `project.reduce`. Frames go through the render queue as TIFF with alpha, so transparent items keep their transparency (`render.frame` writes no alpha - black items vanish on black).

1. **Shell:** `previews.py queue <ID> [<ID> ...] --ae-home <KeremKit folder as AE sees it>` -> prints a run folder and **one line of ops**. (`--ae-home` only when the tools run in a different view of the disk than AE, e.g. a Linux shell on a Windows machine.) The item's comp name comes from its `meta.json` (which needs `fps` and `duration`); `--map m.json` (`{"ID": comp}`) overrides it.
2. **AE, one call:** send those ops as one `batch.run` (`timeoutMs` ~15 s per item; above ~25 items split into two batches). The project must be a copy - the ops clear its render queue.
3. **Shell:** `previews.py auto <run>` - static and continuously moving items get their preview now (1 frame / 6 frames). Animated items print a second line of ops: 6 frames inside the motion, ending on the settled frame.
4. **AE, one call** (only if step 3 printed ops) -> **Shell:** `previews.py auto <run>` again.

So: 2 AE calls when nothing is animated, 4 at most - for any number of items. Each preview is checked (`OK` / `BLANK`); dark content is shown on light grey, light content on dark grey.

- **Glass, blur, adjustment items** need something under them or they render empty: make `TMP_PREVIEW_<ID>` (the item over a gradient-ramp solid) and pass it with `--map`. `project.reduce` drops it later.
- `MISSING` from `auto` = no frames yet (render still running or failed): `render.status`, then `auto` again.
- `BLANK` = every frame empty: wrong comp, hidden layers, missing footage - tell the user rather than saving an empty preview.
- If the output template isn't found (another AE language), `render.list_templates` and pass the TIFF-with-alpha one with `--template`.
- One item at a time without the render queue: `ae_render_frame` with `times` (from `previews.py probe-times`), then `previews.py pick` + `previews.py sheet`.

## Repairing old previews

Older versions saved some previews blank (black, empty or fully transparent; usually under 20 KB, often the very same image for many items).

**Finding them:** once per session, when the library is first used, run `previews.py scan --brief` (one line). If `blank`, `missing` or `suspect` is above 0 and preference `library.preview_repair` is not `never`, ask once:

> N library items have empty previews (left from an older version). Shall I re-render them? I'd work on copies of the item files, so save your project first.
> Options: All of them / Show me the list / Not now / Don't ask again

Not now -> don't ask again this session. Don't ask again -> `pref set library.preview_repair=never`. Show me the list -> `previews.py scan`.

**Repairing** (only after a yes):
1. `ae_save_project()` on the user's project, note **P**.
2. Items from one pack whose work file holds their `LIB_` comps (`library/packs/<Pack>/<Pack>_work.aep`): `keremkit.py safe-copy` that file once, open the copy, and run the steps above for all of them together. Other items: `safe-copy <item>/item.aep <home>/library/_work/repair.aep --overwrite`, open it, same steps (several items can't share one run here - one run per opened file).
3. `previews.py scan --brief`; report "Fixed N previews; M still empty (reason)". Finally `project.open P`.
