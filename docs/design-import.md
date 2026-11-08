# Copying a look

Show Claude something you like — a screenshot, a web page, a CSS file, an SVG, a Lottie animation or an After Effects project — and ask for that look in your edit.

```
Use the look of the top poster in this HTML for my captions and stat cards. Ignore the examples at the bottom.
```

## What happens

1. **Tokens first.** The reference is reduced to a small tokens file: palette, fonts and weights, key sizes, tracking, radii, borders, background grid, glows, shadows, easing and durations. Files are read by `tokens.py`; nothing large is pasted into the chat.
2. **You confirm.** Claude shows the tokens in a few lines and asks before building anything. Fix a color or a font here and it's fixed everywhere.
3. **Built in After Effects.** Every value is converted for AE — CSS `letter-spacing` becomes AE tracking, `line-height` becomes leading, `cubic-bezier` becomes keyframe influence, glows become gradient shapes, sizes are scaled to your comp.
4. **Kept.** The look can become a style's theme, a set of library items, or both.

Claude stays inside the reference's theme: only its colors, fonts, radii and effects are used. If the edit needs something the reference doesn't have, it's derived from what's there and you're told.

## Which reference works best

| Reference | Result |
|---|---|
| After Effects project | exact, including motion |
| Lottie JSON | exact, including easing and timing |
| HTML / CSS / SVG | exact for colors, type, shapes; motion only if the page defines transitions |
| Image | close, but sizes and fonts are estimated |

## From an image: HTML first or straight to After Effects?

Images have no exact values, so something has to be estimated. KeremKit can first rebuild the image as a quick HTML preview from the estimated tokens. You check it in a browser, correct anything that's off, and only then does Claude build in After Effects.

- **Worth it** for anything with layout: posters, cards in a grid, multi-part designs, or when the font is uncertain. A browser preview is much cheaper to fix than AE comps.
- **Not worth it** for a single text style, a color palette or one simple element — Claude goes straight to AE.

You choose once (`always`, `never`, `auto`, or ask each time) and KeremKit remembers. You don't need to train or set up anything separately — the preview step is part of the kit.

## Ignoring parts of a reference

Say what to ignore ("only the header", "skip the gallery at the bottom"). For files, Claude passes the matching CSS selectors to `tokens.py --scope`, so unrelated rules never reach the tokens.
