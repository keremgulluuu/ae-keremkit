# Effect presets

KeremKit can learn your After Effects presets (`.ffx`) and remember what each one does.

```
Learn my presets in Documents/Adobe/After Effects 2025/User Presets.
```

## How it learns

`.ffx` files can't be read directly, so KeremKit applies each preset to a test layer in a temporary comp (`KK_PRESET_LAB`), exports that comp once, and reads back what every preset created. Then the comp is deleted. Your own comps are never touched.

For every preset you get a card in your library with:

- **Effects** it adds, by name and internal match name
- **Required plugins** — anything that isn't built into After Effects is identified (Trapcode, Deep Glow, Sapphire, Continuum, Video Copilot, …) and the preset's name is marked `[requires plugin]`. Presets that fail to apply because a plugin is missing are marked too.
- **Keyframes** — which properties animate, how many keys, over what time, from which value to which, and with what interpolation
- **Expressions** and **text animators**
- A copy of the `.ffx`, so it keeps working if you move your presets folder

## Asking about presets

```
Which of my presets use Deep Glow?
What does "Soft Glow Pop" do?
Which presets need plugins I don't have?
What kind of animations do my presets usually have?
```

Answers come from the cards, not from memory. The last one comes from `learning/presets-insights.md`, a short summary of your most used effects, typical animation lengths and easing — Claude also reads it when it designs new motion, so new work feels like yours.

## Applying a preset

```
Put Soft Glow Pop on the title.
```

If a preset needs a plugin, KeremKit checks whether it's installed first and tells you which one is missing instead of failing halfway.

## Saving your own

Scripts can't create `.ffx` files. Save the effect in After Effects with *Animation → Save Animation Preset*, then ask Claude to learn it. Or save the layer as a library item instead.
