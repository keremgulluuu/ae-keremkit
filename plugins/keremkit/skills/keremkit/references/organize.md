# Layer organisation

After every edit (and on "tidy the project"), KeremKit orders, names and colour-labels layers so the project reads at a glance. `organize.mode`: `auto` (default - do it silently and mention it in one line), `ask`, `off`. The user can change the order, colours or any rule; save changes to `organize.*` (or the style if style-specific).

## Rules

1. **Names** - every layer gets its role prefix (`standards.md`). Unprefixed layers are renamed from what they are: text -> `TXT_<first words>`, footage -> `FTG_<file name>`, audio-only -> `AUD_<file name>`, shape -> `SHP_<role>`, solids used as backgrounds -> `BG_`, adjustment -> `ADJ_`, nulls with sliders -> `CTRL_`. Keep names the user typed if they already have a prefix.
2. **Order** - top to bottom by `organize.order` (default: ADJ, SUB, TXT, UI, ICN, SHP, CTRL, NULL, CAM, LGT, FTG, BG, AUD, SFX). Within one role keep time order (earlier starts lower down, like a stack). **Never reorder in a way that changes the picture**: track mattes stay directly above their target, parented layers keep their parents, and blending/adjustment layers stay above the layers they affect - if a reorder would change the render, skip that layer and say so.
3. **Colours** - label by prefix from `organize.labels` (AE label indices: 0 none, 1 red, 2 yellow, 3 aqua, 4 pink, 5 lavender, 6 peach, 7 sea foam, 8 blue, 9 green, 10 purple, 11 orange, 12 brown, 13 fuchsia, 14 cyan, 15 sandstone, 16 dark green). Comps get labels the same way (`comp.set_label`).
   **Per project:** if the project's `_keremkit/brandkit.md` has an "Organisation" label table, it wins over `organize.labels` - every chat uses the same colour for the same type. Record the table there the first time you label a project.
4. **Project panel** - when `organize.folders` is true, items go into `01_SCENES`, `02_PRECOMPS`, `03_FOOTAGE`, `04_AUDIO`, `05_LIBRARY`, `99_ARCHIVE`.

5. **Names** - the same thing keeps the same name in every chat: check `keremkit.py map name <project> <thing>` before naming, register new ones (`project-map.md`).
6. **Precomping elements** - preference `organize.precomp_elements` (`on` | `off` | `ask`; null = ask once). When on: a multi-layer element in the main comp becomes one precomp layer (+ its control null), unless precomping would change it. Check before: 3D layers sharing the main comp's camera/lights, Collapse Transformations, parents or expressions pointing in or out (`thisComp.layer(...)`), track mattes across the boundary, adjustment layers that must affect what is below. If any applies, leave it and say why in one line.

## Doing it cheaply

- One `comp.info` per comp gives names, types, indices, mattes and parents - enough to plan everything.
- Renames: `project.rename` with a `map` (one call per project); `dryRun` first if more than ~20 layers change.
- Order: one `comp.set_layer_order` per comp. Labels: `layer.set_props {label: n}` - group layers with the same label into one call (`layer` accepts an array).
- Verify with `comp.info` (order) - no images.
- One-line report: "Katmanlar düzenlendi: 18 isim, sıralama, renkler."
