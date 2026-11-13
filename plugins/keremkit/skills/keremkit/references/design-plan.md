# Design plan - ask before building

Before a design with several parts (an intro, a title card, a video section with a counter and a lower third, a whole edit's graphics), Claude shows a short numbered plan: for each part, what the library already has, what could be built from scratch instead, and what it would cost. The user picks; then Claude builds. Reusing an item costs a few calls; designing one from scratch costs many times more - so the plan usually pays for itself, and it prevents building the wrong thing.

Preference `design.plan`: `big` (default - a plan when the request has 2+ parts or one large part), `always`, `off` (build straight away, as before). Small, single changes ("make that text yellow") never get a plan.

## 0. What already exists

- `keremkit.py find <words>` once for the whole request: library, techniques, downloaded assets, extensions and past sessions in one call. A technique or recipe that exists is used, never rebuilt from scratch.
- Inside an existing project: `keremkit.py map find <project> <words>` in its `_keremkit/brandkit.md` and map (`project-map.md`) - new parts reuse the project's colours, fonts, motion and effect values and its canonical names.

## 1. Split the request into parts

From the request, the active style and `learning/house-style.md`: 2-8 parts, each a few words ("intro: animated title", "counter: gold subscriber count", "background: purple moving gradient", "transition: whoosh slide"). Parts follow the order they appear in the video.

## 2. Search them all at once

`keremkit.py plan "intro: animated title reveal" "counter: subscriber counter gold" "background: purple gradient moving" --n 2`

One line per hit: `good` (all words matched) or `partial`, score, id, name, summary, and `preview: check` when its preview looks broken. Read only these lines; open a `meta.json` only when a hit's fit is unclear.

## 3. Decide per part

| Case | Proposal |
|---|---|
| A `good` hit that does the job | use it (low cost) |
| A `partial` hit, or a good one that could clearly be better | use it, **or** build it from scratch in a stated better way (medium / high cost) |
| No useful hit, but a free stock element fits (footage, overlay, sound, icon, logo) | `assets.py search` - offer it (low cost), or build it (`assets.md`) |
| No useful hit | ask whether to build it from scratch (medium / high cost) |
| A technique rather than an element (a cut, a flash, a zoom) | `techniques.py search`, no library item needed |

Cost words, always the same: **low** = existing item placed and adjusted (a few calls); **medium** = a simple element built new (a few batches); **high** = a complex or animated design built new (many batches, possibly several rounds). Say "from scratch" only with a concrete idea of what would be better ("with a glass card and a count-up instead of a static number").

## 4. Ask - one message, numbered

In the user's language, one line per part, Claude's recommendation first:

```
1 - Intro: elimizdeki TXT-005 (Rise Blur Reveal) ve BG-002 (Cyan Indigo Gradient) uygun olur. [düşük]
2 - Abone sayacı: UI-028 (Fire Slider) kullanılabilir ya da cam kart üzerinde sayan bir sayacı sıfırdan daha iyi tasarlayabilirim. Önerim: sıfırdan. [orta]
3 - Kapanış: elimizde uygun element bulamadım. Sıfırdan tasarlamamı ister misin? [yüksek]

Önizlemeler aşağıda (1: TXT-005, BG-002 · 2: UI-028). "Hepsi önerdiğin gibi" ya da "1 tamam, 2 elimizdekiyle, 3 sen seç" gibi yazabilirsin.
```

- Show the previews of every proposed item in **one** image (`library-use.md` -> Showing options), in plan order. Up to 4 items; for more, the ones with a real choice first.
- One question per part at most; no extra questions after the plan.
- "Sen seç" / "you decide" -> take the recommendation.

## 5. Build

Follow the answers in plan order: library parts with `library-use.md`, new parts with the usual design rules. If something turns out impossible or much more expensive than said, stop and say so in one line before continuing. Afterwards, offer once to save the new parts to the library (`library-save.md`).

## Unattended or "just do it"

When the user says to go ahead without questions, or nobody is there to answer: take the recommendation for every part, write the plan as the first lines of the report, and build.
