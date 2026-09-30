# Playtest 2026-09-30: a chip nobody introduced, and a name that answered with its own card

The operator's notes from their own dreamer in the prod village (release
791e579, WORLD_VERSION 1.12), early in a playthrough, and what the prod record
showed. Both are the kind of problem the 2026-09-29 passes ("what the page
offers", glimpses, the scenery lint) were built to close, so the question
behind this pass was the operator's: why do we keep missing here?

## What the operator saw

1. **Wend.** In the loft, Tace's ask-about chips offered "Wend". Asked, Tace
   answered well, but story-wise the dreamer did not know who Wend was, and
   the chip had arrived as if they should.
2. **Forget-me-nots.** The resting clocks' card reads "...one painted with
   forget-me-nots...", with "forget-me-nots" underlined as a link. "look at
   forget-me-nots" answered with the resting clocks' card again, word for
   word. "get forget-me-nots" showed the same card and then "You can't take
   the resting clocks."

## What the record showed

**Wend.** `bin/game prod dream digest` lists every input. Nothing authored
that the dreamer read named Wend before the chip appeared. The only line
that did was the one local-model line in the whole session: the reply to
"hi Tace!" the evening before, "...Come, sit by the round window; the dusk is
turning amber just as Wend liked to see it." The model reads Tace's whole
voice sheet (apprenticed to Wend; a sample line quoting Wend) and dropped the
name in passing. `heard.on_event` counted every line told to a player, so
from then on Wend was a chip. (The dreamer has since asked Tace about Wend,
which makes it a legitimate chip for them now; no prod data needs changing.)

**Forget-me-nots.** The 2026-09-26 dream digest had a dead end, "examine
the clock painted with forget-me-nots". The fix then was to add
"forget-me-nots", "painted clock" and two more as aliases of the resting
clocks. That made the name resolve, so every check passed: the parser found
a thing, the scenery lint (2026-09-29) counted the phrase as covered, and
the keeper-welcome walkthrough asserted `examine forget-me-not clock`
answers with text containing "forget-me-nots", which the shelf's own look
does. What the player read was the shelf's look again, and a refusal naming
the shelf.

## Why we keep missing

Not quite "patches where we needed a system". The recent passes built the
right systems. Each system's acceptance check measured a proxy that the
author's side can satisfy while the player's experience stays the same:

| Surface | What the check measured | What the player needed |
|---|---|---|
| chips (`heard.py`) | the name appeared in a line shown to the player | the story introduced the subject |
| details (aliases; the scenery lint) | the name resolves to an object | the answer says something the player hasn't just read |
| the walkthrough step | the answer contains the word | the answer is about the thing asked |
| a refusal | the verb doesn't apply to the object | the refusal names what the player asked for |
| the creative-break battery | dead ends and wrong answers | (an echo is neither, so it went uncounted) |

Each pass closed its instance, and the class as its check defines it; the
next playtest found the neighbouring case the proxy lets through. Two things
made it worse:

- **The model is a second author, and the checks didn't tell them apart.**
  Provenance (`src: "local"`) was recorded on every model-written line but
  read only by the dream digest. The chip gate trusted the model's words as
  much as Opus's, which contradicts the project's own rule (reflexes, not
  voice: story is authored).
- **The fix for a dead end was "make it resolve".** An alias is the cheapest
  way to stop "You don't see that here", and it quietly converts a dead end
  into an echo. The walkthrough then pinned the echo in place.

Some of it is plain iteration: the chip gate and glimpses were a day old and
met their first unscripted play here. But the two misses share the proxy
shape, and more iteration on the same checks would have kept producing it.
The change in approach is to write each surface's check as the player's
question and make the tests ask it, and to treat model text as unauthored
everywhere a check decides what the page offers.

## What changed (dev, not yet published)

- **Chips:** a line the local model wrote introduces no subject
  (`heard.on_event` skips `src: "local"`). Only authored and engine text,
  things seen, and the player's own asks do. (`tests/test_heard.py`)
- **Replies:** among the n-best drafts, one that names a person or place
  this player has not come across ranks below one that doesn't
  (`dialogue.unmet_names`). A live probe of 28 greetings and small
  questions to Tace, Umber and Bell on fresh players found an unmet subject
  in a third of replies (mostly common words such as "tea" or "gear"; once
  "the frost", a story subject); the ranking counts only people and places,
  so small talk is unchanged.
- **Parts:** a glimpse on a thing may be a part (`"part": true`): a detail
  its look names answers a look with its own words and the verbs it
  authors, and every other verb is done to its thing as if named ("wind the
  painted clock" keeps the old custom). The loader refuses a part on a room
  and a part named like its own thing. The forget-me-not clock is the first
  part, with its own look and take; the walkthrough now asserts its words and
  the shelf's absence. WORLD_VERSION 1.13.
- **Refusals** say back the name the player typed ("You can't take the
  clocks", not the object's full name).
- **The detail lint** asks the player's question: an alias that its own
  thing's look names under another head noun fails the build until it is a
  part or is reviewed as a name for the whole thing, with why, in
  `tests/baselines/whole_aliases.json` (sixteen reviewed: the clock case's
  door and lock, Pollen, the pigeonholes' letters, the summer jar's label,
  and the rest).
- **Links:** a card never links the thing (or part) it is the card of; a
  thing's parts link to their own look, and a part's card links back to its
  thing. DESIGN.md: a link is a promise of something new.

## Still open

- **The glimpse fallback for a look is an echo by design.** A look at a name
  the prose says but nothing authors ("the narrow bed" in the Lamp House)
  reads back the sentence that names it. The scenery lint's baseline (125
  noisy phrases) is the backlog. Either author the prologue rooms' details
  as parts and glimpses first (clocktower, loft, cellar, square: what every
  new dreamer sees), or let the local model write a look line for them
  (validated against the sentence, tagged local, listed in the digest), as
  it already does for other verbs. The first is safer; the second closes the
  class.
- **Everyday words as topic labels.** The chip vocabulary includes labels
  such as "tea", "the frost", "waiting" and "hours". An authored line that
  uses the word in passing makes the chip. That is intended for tea; a pass
  over the labels that are everyday words would find any that aren't.
- **Reach.** Glimpses and scenery (not parts) are not links. A verb that
  needs no object ("listen to the forget-me-not clock") does not reach a
  part's thing.
- **The battery counts no echoes.** Adding one (a look whose answer repeats
  the text the name was read in) would make the replayed battery ask the
  player's question too.
- **Improvised canon.** The reply ranking sees names, not events: "the
  frost" in a simile still reaches a new player. The voice sheets' `never`
  lists remain the guard for what the story keeps for later.
