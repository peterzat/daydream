# WHIMSY.md — the tone bible

This file is the durable source of truth for Daydream's voice and look.
Every image-gen prompt template, every LLM narration call, and every
asset choice should be checked against it. When in doubt, return here.

If you find yourself wanting to add a "dark fantasy", "sci-fi", or
"hard-edged" element, this is not the project for it. Daydream is a
gentle place. Reread this file before drifting.

---

## Touchstones

The two anchors:

- **Spiritfarer** — warm watercolor, soft edges, gentle light. Late-day
  amber. Wood, wool, candleflame. Companionship with a tinge of
  bittersweet, but never cruel.
- **A Short Hike** — chunky low-fidelity 3D and big readable shapes.
  Cozy forests, friendly creatures, small tasks that matter to the
  characters you meet. Curious, not anxious.

Adjacent if-it-helps: *Florence* for color and pacing, *Cocoon* for
slow wonder, *Knytt Stories* for atmospheric solitude.

Explicitly NOT references: anything pixel-art (Undertale included
even though Toby Fox was in the original brief — the user picked
the painterly references over the pixel-art ones), anything
"retrowave" or "neon", anything Soulslike, anything horror.

---

## Palette

Warm, low-saturation, paper-y. Cream, sage, dusty amber. Golden hour
more than noon, twilight more than night. Highlights are warm
(butter-yellow, candle), shadows are soft (sage-green, lavender-grey).
No pure black. No pure white. No bright red. No neon.

Anchor hex values (used in the v0 placeholder PNG and the SPA CSS):

- `#f6f3ec` — paper background
- `#fbf9f3` — paper surface (cards, panels)
- `#5a7a6a` — sage ink (primary type, accent)
- `#3a4a44` — deep ink (body text)
- `#c8a06e` — warm amber (highlights, fireflies, late sun)
- `#d8d2c2` — paper line (borders, dividers)

These are starting points, not a hard contract. Drift them within the
warm/painterly band as long as the result still feels like the
touchstones.

---

## Voice samples

Narration should read as if a quiet, slightly amused observer is
describing a small place to a friend. Sentences run short to medium.
Sensory before declarative. No exposition dumps. No second-person
imperatives ("you must"). No urgency. The world is happening; the
player is welcome to notice.

Two anchor samples:

> The meadow is quiet at dusk. Fireflies are just starting up, slow
> and uncertain, like they are not sure they remember how. The grass
> smells like the cooling earth. Somewhere off to the east, a small
> bell rings once, then waits a long while, then rings again.

> The forge is warm in the way a kept room is warm. Embers drift up
> the chimney like they have somewhere gentle to be. The anvil is
> scarred but well-loved, and someone has set a small clay pot of
> wildflowers on the lip of the brick.

Both pass: short concrete sentences, specific sensory detail, a small
unexplained mystery (the bell, the wildflowers), and no urgency.

---

## Banned moods

The LLM safety filter (lands in v1 with `safety-baseline-v1`) treats
these as immediate refusal triggers in any narration or skill output:

- pixel-art, 8-bit, crunchy, retro-game (visual)
- grimdark, dystopian, brutalist, horror (mood)
- sexual, sensual, romantic-explicit (content)
- violence directed at any toon (NPCs included)
- urgency, deadlines, pressure, "you must" framing
- modern-tech, machinery, vehicles, computers (breaks the dream)
- sarcasm, cynicism, irony at the player's expense

A narration that drifts toward any of these should be re-rolled or
replaced with a soft refusal narration ("the dream resists that
thought" or similar in-fiction language).

---

## Object descriptions (examine + spawn)

The object/verb core (2026-06-30) added two new runtime generation surfaces;
both obey this tone bible and the Banned moods above:

- **Lazy-cache examine.** When a player examines a spawned object with no
  cached detail, one local-LLM call writes ONE or two soft, painterly
  sentences (`daydream/verbs.py:_EXAMINE_SYSTEM`), persisted as
  `properties.examined_text` and served from cache after. Tone: a small
  noticed thing, warmly. No urgency, no modern tech, no quoted dialogue. The
  banlist (`daydream/llm/safety.py`) drops an off-tone description before it
  caches.
- **Generative objects (spawn).** A dialogue's `spawn_object` effect names a
  real thing (Rook's "a sheaf of papers"). Author such names + their seeds as
  cozy, specific-sensory nouns ("loose pages, soft at the edges, covered in
  small careful drawings"), never grand or systemy. The reset world's dialogue
  prompts (`worlds/bunny.json`) carry this voice; copy their register.

## Prompt suffix

Append this verbatim to every image-gen and narration prompt that
should land in the WHIMSY tone:

```
soft watercolor, painterly, warm late-day light, cozy storybook
illustration, gentle composition, no text, no logos, no people in
modern dress, no machinery, no harsh edges, Spiritfarer-adjacent,
A Short Hike-adjacent, low-saturation cream and sage palette
```

Use it as the `WHIMSY_PROMPT_SUFFIX` constant in
`daydream/llm/prompts.py` and `daydream/images/client.py`. Update
both call sites if the suffix changes here.

---

## Re-grounding

When you (a future agent or human) feel the project drifting:

1. Read the two voice samples aloud. Does the new narration sound
   like that?
2. Look at `web/assets/placeholder-meadow.png`. Does the new image
   look like a sibling of that?
3. If either is "no", the change is wrong, not the file.
