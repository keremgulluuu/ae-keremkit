# Techniques

KeremKit knows a set of editing techniques by name. Ask for a kind of work and it lists the options first:

```
What can you do with the audio?
I want to add some cuts.
Show me the techniques.
```

You get each technique's real name and a one-line explanation, marked automatic or manual, plus a short recommendation. Pick the ones you want.

| Group | Examples |
|---|---|
| Cuts | jump cut, jump-cut zoom, J-cut, L-cut, cutaway / B-roll, match cut, cut on action, smash cut, whip transition, speed ramp, montage |
| Motion | emphasis punch-in, slow push-in, camera shake |
| Audio | loudness normalization, noise reduction, high-pass, de-esser, compression, presence EQ, music ducking, room tone, micro crossfades, breath reduction |
| Formats | multi-format delivery (16:9, 9:16, 1:1) |
| Quality | pre-render check (fonts, footage, safe areas, spelling, black/frozen frames, loudness) |
| Organisation | layer order, names and colour labels; project log |
| Publishing | YouTube chapters, title and description ideas, thumbnail frames, EDL / FCPXML export |

## Your own techniques

```
Add a technique called "glitch cut": RGB split on the frame before every cut, 2 frames.
```

It's saved in `KeremKit/settings/techniques.json`, shows up in the lists next to the built-in ones, and travels with `keremkit.py pack`.

## Audio

Audio is processed with ffmpeg and swapped into the comp: analysis first (loudness, peaks, noise), then the chain you choose. Loudness normalization is two-pass and lands on the target (YouTube −14 LUFS by default). Music can be ducked under speech automatically.

## Layer organisation

After every edit, layers are renamed with role prefixes, ordered by role and colour-labelled. It never reorders in a way that would change the picture (mattes, parents and adjustment layers stay where they matter). Change the order or colours by saying so; turn it off with "don't organise layers automatically".
