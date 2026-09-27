# WHIMSY.md: the tone bible

This file is the durable source of truth for Daydream's voice and look.
Every image-gen prompt template, every LLM narration call, and every
asset choice should be checked against it. When in doubt, return here.

If you find yourself wanting to add a "dark fantasy", "sci-fi", or
"hard-edged" element, this is not the project for it. Daydream is a
gentle place. Reread this file before drifting.

---

## Touchstones

The two anchors:

- **Spiritfarer**: warm watercolor, soft edges, gentle light. Late-day
  amber. Wood, wool, candleflame. Companionship with a tinge of
  bittersweet, but never cruel.
- **A Short Hike**: chunky low-fidelity 3D and big readable shapes.
  Cozy forests, friendly creatures, small tasks that matter to the
  characters you meet. Curious, not anxious.

Adjacent if-it-helps: *Florence* for color and pacing, *Cocoon* for
slow wonder, *Knytt Stories* for atmospheric solitude.

Explicitly NOT references: anything pixel-art (Undertale included
even though Toby Fox was in the original brief; the user picked
the painterly references over the pixel-art ones), anything
"retrowave" or "neon", anything Soulslike, anything horror.

---

## Palette

Warm, low-saturation, paper-y. Cream, sage, dusty amber. Golden hour
more than noon, twilight more than night. Highlights are warm
(butter-yellow, candle), shadows are soft (sage-green, lavender-grey).
No pure black. No pure white. No bright red. No neon.

Anchor hex values (used in the v0 placeholder PNG and the SPA CSS):

- `#f6f3ec`: paper background
- `#fbf9f3`: paper surface (cards, panels)
- `#5a7a6a`: sage ink (primary type, accent)
- `#3a4a44`: deep ink (body text)
- `#c8a06e`: warm amber (highlights, fireflies, late sun)
- `#d8d2c2`: paper line (borders, dividers)

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

## Stories: soft stakes (SPEC 2026-09-26)

Who writes what: every line that carries story is authored and must pass this file read aloud; local-model lines are reflexes held to the speaker's voice sheet, kept short, and never state a fact the speaker was not given (docs/REFLEXES.md).

The sections above taught gentleness, and the world
learned it too well: every surface banned wanting, and nothing ever changed
(docs/PIVOT.md section 2.5). Gentle is not wantless. The touchstones have
stakes: Spiritfarer is about death and letting go; A Short Hike has a goal
and a climb. Cozy stories carry tension through **soft stakes**:

- **Wants.** Every guest and keeper wants one thing: a lost nap wants the
  quiet it came from, a lamplighter wants to see a dawn. Say so plainly.
- **Something lost, missed, or not yet.** An hour that never came home, a
  letter never sent, a song someone slept through, a goodbye that came too
  soon. These are the engine of every arc.
- **Gentle time.** Things take days. A guest can wait, and if no one helps,
  it is kept, not lost: it falls asleep in a jar, it stays on at the Waiting
  House. Time moves the story without threatening anyone.
- **Bittersweet endings.** Some endings are sad in the way autumn is sad.
  An hour that goes home is also an hour that leaves. A keeper who opens an
  old grief a little is braver, not broken.
- **Strained, mending things.** A friendship gone quiet, a keeper who
  won't talk about one night, a festival that needs getting ready for.

What stays out, always: **cruelty** (no one is mean on purpose; no
mockery), **horror** (no dread, no gore, no nightmares, nothing hunting
anyone), **grimdark** (no hopelessness, no bleak worlds, no one beyond
comfort), **danger** (no one is ever in peril, including the player), and
**urgency** (no deadlines, no "you must", no countdowns: gentle time is
the opposite of a timer). Death may be mentioned the way Spiritfarer does,
softly and past tense (Wend, the old clockmaker), never shown or
threatened.

A soft-stakes line, for calibration:

> The nap yawns so wide it tips over, then sits back up. It misses Pim,
> though it could not tell you how. If no one sings it home, it will fall
> asleep in a jar in the cellar, kept, and a little sad, and safe.

The safety banlist (`daydream/llm/safety.py`) matches this section: a corpus
of soft-stakes lines passes it, and each still-banned category still blocks
(`tests/test_soft_stakes.py`).

---

## Banned moods

The LLM safety filter (`daydream/llm/safety.py`, checked on player input
and on every narrative field before state mutates) treats these as
immediate refusal triggers in any narration or skill output:

- pixel-art, 8-bit, crunchy, retro-game (visual)
- grimdark, dystopian, brutalist, horror (mood)
- sexual, sensual, romantic-explicit (content)
- violence directed at any toon (NPCs included)
- urgency, deadlines, pressure, "you must" framing (a character may
  still hurry across a square; the banned thing is pressure on the player)
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
  small careful drawings"), never grand or systemy. The canonical world's voice
  sheets (`worlds/lost-hours/cast/`) carry this voice; copy their register.

## Prompt suffix

Append this verbatim to every image-gen and narration prompt that
should land in the WHIMSY tone:

```
soft watercolor, painterly, warm late-day light, cozy storybook
illustration, gentle composition, no text, no logos, no people in
modern dress, no machinery, no harsh edges, Spiritfarer-adjacent,
A Short Hike-adjacent, low-saturation cream and sage palette
```

It lives in code as the `WHIMSY_PROMPT_SUFFIX` constant in
`daydream/images/client.py`; `tests/test_whimsy_prompt_suffix.py`
fails if this block and that constant ever drift apart, so update
both together.

## Portrait prompt suffix

Toon portraits (the scene-margin faces and the picker thumbnails)
prepend this framing clause to the shared prompt suffix above:

```
storybook character portrait, head and shoulders, gentle friendly
face, soft features, plain warm background
```

Chosen by A/B on 2026-07-07 (head-and-shoulders vs figure-vignette,
real loft appearance seeds, SDXL + the watercolor LoRA): the closer
framing keeps a face legible at margin-chip size, and when a
character's appearance seed implies equipment or a pose it falls back
gracefully to a small full figure rather than forcing a crop. Faces
held up well under the loose LoRA in both framings; the portrait
workflow's negative prompt carries the anatomy guards.

It lives in code as `PORTRAIT_FRAMING_CLAUSE` in
`daydream/images/client.py` (joined to `WHIMSY_PROMPT_SUFFIX` as
`PORTRAIT_PROMPT_SUFFIX`); the same drift test covers it.

---

## Re-grounding

When you (a future agent or human) feel the project drifting:

1. Read the two voice samples aloud. Does the new narration sound
   like that?
2. Look at `web/assets/placeholder-meadow.png`. Does the new image
   look like a sibling of that?
3. If either is "no", the change is wrong, not the file.
