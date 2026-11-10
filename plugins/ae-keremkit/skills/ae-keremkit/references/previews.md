# Library previews

A preview shows what an item **does**. Claude never opens the frames: they are measured as numbers, and the user sees the finished image (`library-use.md` -> Showing options).

## Making previews

Render from the work copy **before** `project.reduce`. Frames come from the `ae_render_frame` tool at exact times - transparency kept, colour managed (`render.frame` in a batch writes no alpha: black items vanish on black; the render queue ignores `skipFrames` and renders every frame).

1. **Shell:** `previews.py queue <ID> [<ID> ...] --ae-home <KeremKit folder as AE sees it>` -> a run folder and **one line per item**: the `ae_render_frame` arguments (comp, outPath, ~12 probe times). `--ae-home` only when the tools see the disk differently from AE (e.g. a Linux shell on a Windows machine). The comp comes from `meta.json` (which needs `fps` and `duration`); `--map m.json` (`{"ID": comp}`) overrides it.
2. **AE:** one `ae_render_frame` call per line, exactly those arguments (no `contactSheet`, no `analyze` - keeps the response short), one at a time.
3. **Shell:** `previews.py auto <run>` - static and continuously moving items get their preview now (1 / 6 frames). Animated items print a second line each: 6 times inside the motion, ending on the settled frame.
4. **AE:** those calls (animated items only) -> **Shell:** `previews.py auto <run>` again.

Per item: 1 AE call, 2 when animated. Each preview is checked (`OK` / `BLANK`); dark content is shown on light grey, light content on dark grey. Probe frames are full size: for long comps keep the default 12 (`--probes` max 32).

- **Glass, blur, adjustment items** need something under them or they render empty: make `TMP_PREVIEW_<ID>` (the item over a gradient-ramp solid) and pass it with `--map`. `project.reduce` drops it later.
- `MISSING` / `WARN n of m frames` from `auto` = a render failed: run that item's call again, then `auto`.
- `BLANK` = every frame empty: wrong comp, hidden layers, missing footage - tell the user rather than saving an empty preview.
- One item by hand: `previews.py probe-times`, `ae_render_frame` with those `times`, `previews.py pick` + `previews.py sheet`.

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
