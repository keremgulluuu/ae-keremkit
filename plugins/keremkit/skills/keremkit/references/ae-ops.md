# After Effects MCP: op cheat sheet and pitfalls

Learned the hard way with `@kumoproductions/mcp-aftereffects` on AE 2026 (26.x), `eval.run` disabled. Grep this file for the op you need instead of guessing parameter names or loading `ae_catalog`. If an op here fails, check `ae_catalog <category>` once and record the correction in `learning/known-issues.md`.

## Parameter names that cost failed calls

| Op | Right | Wrong / note |
|---|---|---|
| `batch.run` | `{ops: [...]}` | not `steps` |
| `effect.add` | `matchName` | not `effect` |
| `effect.set_property` | flat path `["Scale Width"]`; % params take 0-1 (Opacity, Blend With Original, Amount of Noise, Interpolation) | not `["Transform","Scale Width"]`, not 0-100 |
| `layer.set_props` | `{props: {name, label, ...}}` | |
| `item.set_props` | `{name: ...}` directly | not `{props}` |
| `layer.duplicate` | `newName` | |
| `layer.create_footage` | `sourceItemId` (a real id, never a placeholder 0) | |
| `layer.set_parent` | `parentLayer` (+ `jump: true` to keep the look) | |
| `layer.set_track_matte` | `matteType` | |
| `comp.create` | `fps` | |
| `text.set_box` | `boxSize` | |
| `layer.set_enabled` | one layer per call | an array returns `updated: 0` silently |
| `comp.set_props` | only real CompItem keys (`draft3d`, ...) | unknown keys return ok with no warning: ok ≠ the setting exists |
| `render.set_settings` | `{"Use this frame rate": "30"}` | `{"Frame Rate": ...}` → Invalid Value |
| `render.set_output` | breaks paths with non-ASCII characters (Masaüstü) | use `render.set_om_settings {"Output File Info": {"Base Path", "Subfolder Path", "File Name"}}` AFTER the template is set |
| `comp.info` / `ae_comp_info` | by numeric item id when the comp name looks like a number ("121") | |
| `keremkit.py pref set` | `key=value` in ONE argument | two arguments are refused |

## Reading cheaply

- Verify with `layer.bounds` and `comp.sample`. `comp.info` of a big comp (60+ layers), `layer.info` on precomps, and `item.list` without a filter cost 5-25k tokens each.
- Never `effect.list_on_layer` / `layer.info` on layers carrying Deep Glow, Keylight or other plugins with 80-160 params: address effects by index.
- Fonts: grep `C:/Windows/Fonts` (and the user font folder) instead of `font.list` (~6k tokens).
- Effects and keys of a whole project: `ae_project_export_json(outPath)` + `digest.py` (`--deep --comp X` for per-layer keys/expressions). The export lacks text-animator selector keys, blend modes, track mattes, adjustment flag, mask modes and 3D material/geometry/light options - read those with `property.get` (numKeys) on the few layers that need them.
- `batch.run` answers echo layer lists per op: keep verification reads at the end, few per batch.

## Session flow pitfalls

- **AE not up yet:** calls during boot give `NO_INSTANCE`. Check the AfterFX process has a window title / `Responding=True` before the first call. Start AE normally, not with `-m`.
- **Big project open:** `project.open` of a 15+ MB project can time out while AE keeps opening it. Use `timeoutMs: 300000`, then wait for `Responding=True` and `ae_project_info`.
- **"Attempt was made to run a second script" dialog:** appears after big batches, saves or `project.open`; the next call is discarded entirely (nothing applied). `instance.dismiss_dialog {id}` and resend the same call - no partial-state check needed. Run `project.merge` as its own call, never inside a batch. If it keeps coming back and the project is saved from outside, another client drives the same AE: stop and ask.
- `project.open` closes the open project without saving: save first.
- `layer.copy_to_comp` fails on layers with a parent or a linked expression ("while an Undo Group is open"). On a work copy: `set_parent null` with `jump: true`, remove the linked expression, copy, re-parent with `jump: true` in the target, set the expression again, `keyframe.shift` if the copy got a time offset and the expression uses `valueAtTime`.
- `layer.set_props {timeRemapEnabled: true}` is ignored silently. Freeze a frame with a stretched copy instead (stretch 6000 %), or the user enables Time Remap.

## AE 2026 defaults and 3D

- New Null anchor is `[0,0,0]`; a new camera sits at `[0,0,-2666]`: set both explicitly.
- `.svg` imports directly as a comp holding one shape layer (the op may still say `null is not an object`; the import is done). No Illustrator step. Check `closed` on converted paths: an open path extrudes with no front cap (black face).
- Shape layers: Contents group 1 draws on top - add background groups last or `property.move` them down.
- Shape Stroke Dashes: `property.add` the Dash/Gap/Offset first, then set them. Bevel Alpha's angle is "Light Angle".
- **Advanced 3D:** Environment light Source cannot be set by script (the user sets it); `copy_to_comp` loses it. Layer motion blur is not supported (use CC Force Motion Blur on the precomp layer in a Classic 3D parent - `motion-blur.md`). Reflection Intensity/Sharpness refuse values. An extruded body reaches about depth + 2 × bevel behind the layer plane. Set the renderer in its own call before building and check for a dialog; the Cinema 4D renderer fails on some machines (Render Failed 5070) and silently falls back.
- Displacement Map in a 3D adjustment layer misaligns: keep glass/refraction adjustments 2D and feed them a 3D precomp.
- GLB models: orientation and pivot come in arbitrary; measure bounds frontal and edge-on under a 3D null, then offset the model inside the null. Footage colour profile has no op (user sets it).

## Renders and check frames

- A fresh `outPath` for every check render: re-rendering to an existing PNG can fail with EBUSY and leave the old file.
- A check frame shows impossible content → `project.purge {target: "image"}` before judging.
- PNGs can be read before AE finished writing them: retry a moment later.
- An H.264 render can fail mid-way (Error 6662) and still probe fine: check frames, not just ffprobe.
- Long `render.start`: short `timeoutMs` (~20 s); AE keeps rendering and answers nothing meanwhile - watch the file size until it is stable. Never a Lossless AVI/MOV unless asked (disk).
