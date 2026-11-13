# UI-008 Gold Counter - logic

How it works, so the same effect can be rebuilt on ANY other element (another icon, text, video, 2D or 3D, another position or timing) without copying this comp.

## Looks like
Gold gradient number that counts up 0 → end in 3 s with one shine sweep at the end.

## Rig
- `CTRL_Counter` (null, top level): sliders Start, End, Color MainColor. Everything reads from it.
- `TXT_Value`: Source Text expression reads the sliders; no own keys.
- `PRE_Shine` (precomp, track matte = TXT_Value alpha): the shine bar.
- Transforms are driven by: CTRL_Counter (parent) - the text layer has no own position keys.

## Effects (non-default values only)
- TXT_Value › Gradient Ramp: Start Color #F5B800, End Color #8A5A00, Ramp Shape Linear, Start (0,-40) End (0,40) relative to the text.
- TXT_Value › Bevel Alpha: Edge Thickness 2, Light Angle -60, Light Intensity 0.4.

## Keys (times relative to the element's in-point)
- CTRL_Counter › Value: +0.000 = Start [ease out influence 10] → +2.400 = End [ease in influence 90].
- PRE_Shine › Position X: +2.400 = -300 → +3.000 = +300 (linear).

## Expressions (verbatim)
```
var c = thisComp.layer("CTRL_Counter").effect("Value")("Slider");
Math.round(c).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".")
```

## Rules
- Shine starts when the count lands; the count never overshoots End.
- Position/size: centred on the target; scale so the number fits the title-safe width.

## Apply to another element
- Text: replace TXT_Value's source; keep the expression.
- Icon / image: put Gradient Ramp + Bevel Alpha on the icon, matte PRE_Shine to it, skip the counter expression.
- 3D layer: shine as a 2D layer track-matted to the 3D precomp's alpha.
- Adjustment-layer parts (zoom, glass, focus blur): copy those layers into the target comp - do not nest them.

## Sound
`SFX_Tick` per 1000 steps (optional), `SFX_Shine` on +2.400.

## Dependencies and hand-only steps
Fonts: Montserrat-Black. Plugins: none. Hand-only: none.

## Techniques
`gold-counter-shine` (techniques.py) - the reusable mechanism on its own.
