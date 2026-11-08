# Edit styles

An edit style is a recipe for a whole video. Once it exists, *"edit this in my Kerem style"* is enough: Claude finds your footage, shows you the settings it's about to use, asks if you want anything changed, and does the edit.

## What goes into a style

| Part | Example |
|---|---|
| **Inputs** | a camera recording, a separate voice-over, an optional screen recording — and how to recognise each file |
| **Structure** | "Split the camera after a sentence like *let's look at the screen*, play the voice-over, then continue the camera." Phrases are examples of a pattern, not exact strings. |
| **Formats** | vertical and horizontal sizes, with any differences between them |
| **Cutting** | how tight each input is cut |
| **Subtitles** | words per line, lines, sentence rules, highlight rules, font, colors, position per part of the video |
| **Look** | font pairings, a named palette, transitions, interstitials, motion presets, UI elements per part |
| **Screen recording** | when and how it appears: size, corners, shadow, entrance |
| **Sound effects** | which events get which sounds, at what level |
| **Rules** | anything else, one sentence each |

A full annotated example is in [`examples/style.example.json`](../examples/style.example.json).

## Creating a style

Pick whichever is easiest:

1. **Talk it through.** "Let's create a style called Kerem." Claude asks only about what you haven't said yet.
2. **From the edit you just made.** "Turn what we did in this chat into a style." Every correction you made becomes a rule.
3. **From a finished project.** "Build a style from `final_v3.aep`." Claude exports the project, summarises fonts, colors, layer roles and effects locally, drafts the style and asks only about things a project can't show — like how tight you cut.

## Running a style

Before it starts, Claude shows a short summary — style version, format, which file plays which role, cut presets, subtitle rules, fonts, palette, transitions, sound effects, render settings — and asks:

> I'm starting the whole operation with these settings. Do you have any other preferences beyond these?

Answer with changes ("no sound effects this time") or just "go". Changes are one-off unless you say to keep them.

If a split point is ambiguous, you'll get two or three candidates to pick from instead of a guess.

## Styles that learn

When an edit is done, Claude asks once whether to save what it learned. If the whole edit happened in one conversation, it uses your corrections. If the work was spread over several chats or you finished it by hand, it compares the final project with the style and proposes only real differences.

## Versions

Decide how old versions are kept the first time a style changes: every change, only big changes, only certain kinds (colors, fonts…), or never. Archived versions keep the instruction that changed them, so "go back to the version before the yellow captions" works.

## Vertical and horizontal

A style can carry several formats with small differences (subtitle position, sizes). If vertical should look genuinely different, make it a separate style and link the two.
