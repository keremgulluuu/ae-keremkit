# Quality control

Before a final render (and on "check everything"): `qc.mode` decides - `auto` (always run), `ask` (offer once per render, default), `off`.

## In After Effects (numbers only, one or two batches)

| Check | Operation | Issue when |
|---|---|---|
| Missing fonts | `font.list_missing` | anything listed |
| Offline footage | `footage.list_missing` | anything listed |
| Expression errors | `project.find_layers` + `layer.info summary` on suspects | error text present |
| Safe areas | `layer.bounds` for TXT_/SUB_/UI_/ICN_ layers at their mid time | outside title-safe |
| Gaps / overlaps | `comp.info` of the main comp | holes between clips, layers past the comp end |
| Text spelling | read text layer contents (`project.find_layers type: TextLayer`, contents from `layer.info summary`) | typos, wrong names (use the glossary) |
| Work area | `comp.info` | work area shorter than the edit |

## On the rendered file

`qc.py check <render>` -> one line per issue with its time: `BLACK`, `FROZEN`, `SILENCE` (long), `LOUDNESS` (off target), `TRUE_PEAK` (clipping risk), then a verdict line.

Intended black (fade to black at the end) and intended silence are fine - judge by position (start/end) and tell the user only real problems.

## Report

```
Kontrol: 2 sorun
- 00:41 - "SUB_Captions" title-safe dışına taşıyor (alt kenar)
- Ses -17.2 LUFS (hedef -14) -> normalize edeyim mi?
```

Fix what is mechanical (loudness, safe-area offsets) after one confirmation; spelling and content fixes are shown and asked.
