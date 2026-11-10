# Troubleshooting

## When an operation fails

1. **Read the error.** Usually a wrong parameter, layer name or property path.
2. **Search known issues** in `learning/known-issues.md` by a keyword from the error (grep / `Select-String`); do not read the whole file. Apply a matching fix.
3. **Fix once and retry.** Check parameters with `ae_catalog <category>` if needed.
4. **Second failure of the same approach: stop.** Tell the user briefly: what was tried, the error, the likely cause, a proposed next step.
5. **Solved something new? Record it** as one entry in `known-issues.md`:
   ```
   ## [tag1, tag2] Short title
   - Symptom: ...
   - Cause: ...
   - Fix: ...
   ```

Something broke and the cause is unclear: `project.undo` (reverts the whole last call) or open the latest checkpoint; say which.

## After Effects not responding

- `NO_INSTANCE` / no running AE: ask the user to open After Effects (normally, not with `-m`), then retry once.
- A dialog is blocking: `instance.dialogs` -> `instance.dismiss_dialog`.
- Long operations: raise `timeoutMs` (render.start, big batches).
- Memory: `project.purge`.

## Tool problems (outside AE)

| Problem | Likely fix |
|---|---|
| `python` not found on Windows | try `py`; save the working command to `tools.python` |
| ffmpeg error mentioning `filter_complex_script` | handled automatically (newer ffmpeg); if it persists, update ffmpeg |
| Whisper gives no word times | use `--word_timestamps True` (openai) / `word_timestamps=True` (faster-whisper) |
| Whisper very slow | smaller model or GPU (`tools.whisper.device`); tell the user the trade-off |
| Cut file out of sync in AE | the source was variable-frame-rate: re-render (cutlist renders CFR) and `footage.reload` |
| Subtitle layer shows nothing | `footage("<name>")` must equal the imported item name exactly; time beyond last cue shows empty by design |
| `keremkit.py` says NOT_SET_UP | run `keremkit.py init` (setup.md) |
| Catalog search finds nothing / catalog was edited by hand | `keremkit.py reindex` rebuilds it from the meta files |
| `ERROR: package rejected` on unpack | the package's manifest points outside the KeremKit folder - don't import it; ask where it came from |
| Whisper JSON without word times | subtitles fall back to even timing per segment (a WARN says so); re-run Whisper with word timestamps |

## Learned in real use (After Effects MCP)

- **One AE call at a time.** Never send two AE tool calls in parallel: the second raises "a second script while another script was already running". Clear it with `instance.dismiss_dialog` and retry.
- **`project.auto_fix_expressions` fails** with "Illegal use of reserved word" - don't use it; rename with `project.rename` or `item.set_props`.
- **`project.rename` with a map can silently skip names** (~20% in a large batch). Always re-check the count afterwards (`item.list` / `comp.info`) and fix the rest with `item.set_props` by id.
- **`project.reduce` + `project.undo`**: undo restores the full project, which is much faster than reopening it. `footage.replace` after a reduce is a second undo step (`project.undo {count: 2}`). Keep `project.reduce` in its own call so a failed reduce never triggers an undo of earlier work.
- **After a save-as loop the open project points at the last saved copy.** Finish with `project.open` on the original so a Ctrl+S can't overwrite a library item.
- **faster-whisper crashes** with `av.open() got an unexpected keyword 'metadata_errors'` (PyAV version mismatch) or `cublas64_12.dll not found`: extract a 16 kHz mono WAV with ffmpeg, load it as a numpy array and pass that to `transcribe()`; run `device="cpu", compute_type="int8"` until CUDA libraries are installed (`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`).
- **Old catalogs**: libraries made with 1.0 use `name_tr`/`name_en` columns. Current tools read them, and `keremkit.py init` rewrites the catalog in the new format.

## Built-in pitfalls

- PostScript font names (`Montserrat-Bold`, not "Montserrat Bold") - verify with `font.list` / `font.info`.
- `project.open` closes without saving - save first.
- `project.reduce` empties the project - only inside the library-save flow, after saving.
- `comp.duplicate` shares nested precomps - keep parameters on top-level layers.
- `egp.export_mogrt` on an unsaved project opens a save dialog - save first.
- Expressions target the JavaScript engine (`project.get_settings`).
- Never open undo groups yourself; `project.undo` cannot go inside a batch.
- An op cannot use an id produced earlier in the same batch - split batches.
