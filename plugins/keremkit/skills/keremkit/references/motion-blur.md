# Motion blur - how it works in After Effects, and how the kit applies it

Whether animations get motion blur, and how strong, is the user's choice: preference `motion.blur` (`always` | `ask` | `off`; null = ask once, the first time something animates) and the active style's numbers. This file is the mechanism, not a look. The style's or the user's values always win over the starting points below.

## 1. The switches (all must be on)

| Level | Where | Op |
|---|---|---|
| Comp | Enable Motion Blur for the comp | `comp.set_props {motionBlur: true}` |
| Layer | the layer's Motion Blur switch | `layer.set_props {props: {motionBlur: true}}` |
| Precomp | the switch on the precomp LAYER blurs its own transform; layers INSIDE need their own switch and the inner comp's switch | per comp |

- Inner layers blur with the inner comp's shutter settings. With Collapse Transformations on, they render with the parent's settings.
- Text animators (per-character position/scale) get blur through the same layer switch.
- Footage and things that move inside a frame (not by keys) get no layer blur: use Pixel Motion Blur (optical flow, footage) or CC Force Motion Blur (precomps).

## 2. Comp shutter settings

| Setting | Script name | Range / default | What it does |
|---|---|---|---|
| Shutter Angle | `shutterAngle` | 0-720, default 180 | length of the streak: 180 = half a frame, 360 = a whole frame, above 360 = exaggerated |
| Shutter Phase | `shutterPhase` | -360..360, default -90 | where the streak sits; centred on the frame = -angle/2 (180 → -90, 360 → -180) |
| Samples Per Frame | `motionBlurSamplesPerFrame` | default 16 | minimum samples; also what 3D layers and effects use |
| Adaptive Sample Limit | `motionBlurAdaptiveSampleLimit` | default 128, max 256 | upper limit for fast 2D moves; raise it when fast moves look stepped |

Set them in one op: `comp.set_props {motionBlur: true, shutterAngle, shutterPhase, motionBlurSamplesPerFrame, motionBlurAdaptiveSampleLimit}`, then read them back (`comp.set_props` accepts unknown keys silently - `ae-ops.md`).

## 3. Choosing values per motion (starting points only)

| Motion | Starting point | Watch for |
|---|---|---|
| Fast slide / whip / pop-in | 180-360 | stepping (raise the adaptive limit) |
| Slow drift, gentle float | 180 or off | barely visible; costs render time |
| Readable text in motion | 90-180 | smeared, unreadable letters at high angles |
| Counters / fast-changing numbers | layer blur does nothing (no movement) | a Directional Blur driven by the value's speed (expression) if the style wants a streak |
| 3D layers in Classic 3D | comp settings apply; samples come from Samples Per Frame | noise: raise samples |
| Advanced 3D comp | layer blur is not supported (warning) | CC Force Motion Blur on that precomp's layer in a Classic 3D parent |
| Precomp whose content moves inside | CC Force Motion Blur on the precomp layer: Override Shutter Angle on, angle, Motion Blur Samples | render cost grows with samples |
| Footage with fast camera moves | Pixel Motion Blur (or RSMB if the user has it) | artefacts on edges |

Say in one line which values you use when the style has none, and save what the user keeps into their style (or `house-style.md` for every edit).

## 4. Building it

1. Read `motion.blur` and the style. `off` → skip. `ask` / null → one question with what it changes (render time vs. smoother motion) and a ★ recommendation.
2. One batch per comp: comp switch + shutter settings, layer switches for the animated layers (from the keyframe list you just built - no extra read), CC Force Motion Blur where the table says so.
3. Verify with numbers: `property.get` of the comp settings; one `ae_render_frame` with `analyze` on a fast frame only when the user asks to look.

## 5. QC

`qc.md` → "Motion blur": animated layers whose switch is off while `motion.blur` is `always`; Advanced 3D layers with the layer switch on (no effect, warning); text whose blur makes it unreadable at the style's angle.
