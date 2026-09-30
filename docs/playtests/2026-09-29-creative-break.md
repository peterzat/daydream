# Creatively breaking the village (2026-09-29)

The operator's ask, after "get the jar" read "You don't see the jar here"
beside a shelf whose look had just said a jar glinted up there: play as a
tester, try to break the game the way that did, and propose spec-level
items, especially for using the local model's reasoning better, within its
compute and latency. And a second ask: what did Infocom do, on far less
compute, to make free text feel like it had few dead ends?

Three sources feed this note:

- **A battery of 78 lines** in four places (the Clocktower, the loft, the
  Hour Cellar, and a group meant for the square that stayed in the loft),
  played through `bin/game play` against dev at 15d8c85 with the real local
  model (Qwen3.5 9B), fresh dreamers `brk-*`, the clock not yet mended.
- **A fresh reviewer's behaviour probes** of the glimpses work (the
  codereview of 2026-09-29g), which found nine ways to fall between the
  parser's paths; all nine were fixed before this publish.
- **A reading of Infocom's ZIL** for Zork I (the design-time source on this
  box, `~/data/zork/`), checked against the story file in dfrotz, plus the
  1979 IEEE paper, the ZIL course and The Craft of Adventure.

## What already works

The game answers a lot without the model, and much of it well: `sit`,
`sleep`, `wait`, `sing`, `listen to the clock` ("the tower listens back"),
`x ledger`, a typo (`exmaine the ledger`), `take it` after a look, `take a
clock` (which asks which: the little brass clock or the resting clocks),
`drop everything`, `what can I do here` (reads your threads), `reach up`
(examines the highest shelf), and every authored glimpse the sweep wrote
(`pick up the jar`, `take the tweezers`, `wind the great clock`). A
deterministic reply returns in about 1.3 s through the play bridge; a line
that needs the parser model takes about 2.3 s; improvised dialogue takes
4.7 to 5.1 s.

## What broke, by class

**1. The wrong person answers.** `ask Bell about the lanterns`, with Bell
elsewhere and Tace present, was answered by Tace ("I am not the
lamplighter, but Bell keeps them bright"). The echo read "says to Tace".
An ask that names someone absent should say they aren't here, and where
they usually are (the trace and the schedules know).

**2. The model promises what the engine won't do.** Improvised replies
commit the resident to actions that never happen: "I can mend the spring in
your watch, friend", "Follow close" (Tace never moves), and "ask Tace what
to do" pointed at Mott and "a new spring", both wrong (the ledger points to
the well-court). Each promise is a dead end the player walks into later.

**3. Another world's verbs leak in.** The engine's verbs from the Zork turn
answer in the village: `who am I` reads "You are in perfect health."
(diagnose), `climb the shelf` reads "You can't board the highest shelf.",
`climb the ladder` in the loft reads "You can't board The Clockmaker's
Loft.", and `climb the stairs` reads "You can't go north from here."

**4. Questions about the game fall through.** `what time is it` (the
village keeps a real day), `help me` (only a bare `help` opens How to
Dream), `go somewhere else` ("You can't go somewhere else from here"
instead of the ways out), `what is this place` (answered, but through a
6 s model call).

**5. Social impulses get odd answers.** `hug Tace`, `wave to Tace` and
`thank Tace` become speech ("brk-loft says to Tace: "hug"") and a model
reply ("It is good to have your arms around me"). `give Tace a hug` reads
"You don't see the Tace a hug here." `wave to Bell` (absent) floats away.

**6. Sensory and positional verbs have no defaults.** `smell the jars`,
`dance`, `run`, `light a lantern`, `borrow a loupe` all read "nothing takes
that up". `look behind the case` and `look under the lectern` print the
whole room. `knock on the case` reads "You can't use the clock case."

**7. One line, two actions.** `take the lantern and go up` falls to the
model and comes back "the thought drifts by". Periods and THEN chain; AND
between two verbs does not.

**8. Exits in the prose read as things.** `open the low door` (the way
down to the cellar) got a model line inviting you to turn its handle.
Compass exits now answer "The gate is the way south from here"; up and
down do not, because the prose uses them as adverbs.

**9. Canon contradicted by a default.** `drink tea` in Umber's cellar reads
"There's nothing here to drink", though the cellar's tea is canon (a
chipped cup labelled DRINK WHILE WARM).

**10. Smaller.** `ask Tace about it` doesn't read "it" as the thing just
looked at. `use the lantern on the jar` refuses on the jars of saved hours
instead of answering with the lantern's glimpse. `look at the hands` in the
cellar found "labels in many hands". `take the lectern` got a model line
calling it "leather" (the ledger is leather). A model line for a prose noun
can still invite an action ("waiting only for a hand to turn its handle").

## What Infocom did (and where)

Zork I answered everything deterministically in milliseconds, and still
had its gaps ("examine passage" in the Kitchen answers "I don't know the
word").

- **Everything the prose names is referable.** The parser looks in the
  room and inventory, then the room's shared scenery (`GLOBAL` lists: house,
  forest, window), then its `PSEUDO` nouns (a routine per noun, 16 in Zork
  I: "The nails, deeply imbedded in the door, cannot be removed."), then
  `GLOBAL-OBJECTS` that exist everywhere (grue, hands, ground), and only
  then says "You can't see any X here!" (`gparser.zil` `GET-OBJECT` and
  `GLOBAL-CHECK`; `gglobals.zil` `NOT-HERE-OBJECT-F`). Glimpses are our
  PSEUDO; we have no shared scenery.
- **Every failure names what failed, and costs no turn**: "I don't know
  the word X", "You used the word X in a way I don't understand", "There
  seems to be a noun missing".
- **Orphaning**: "What do you want to take?", and the next fragment
  ("lantern", "with sword") merges into the pending command.
- **GWIM, announced**: when one thing fits, the parser uses it and says so
  in parentheses ("(brass lantern)"), so a wrong guess is cheap to correct.
- **Implicit actions**: READ or UNLOCK WITH picks the thing up first
  "(Taken)".
- **Pronouns kept current by what the game says**, not only by what the
  player typed (`THIS-IS-IT`), with THEM/HIM/HER.
- **A chain stops at its first failure.**
- **OOPS and AGAIN with guardrails**; wide synonyms (TAKE answers GET,
  GRAB, CARRY, HOLD; EXAMINE answers DESCRIBE, WHAT); an adjective alone
  can name a thing.
- **A default answer for every verb and object**, naming the object ("There
  is nothing behind the X."), rotated from small tables so refusals never
  repeat (`PICK-ONE`, `YUKS`: "A valiant attempt.").
- **First sight and placement text** keep the prose and the objects in
  agreement.

The principle under all of it, from the IEEE paper: "much of the enjoyment
of the game is in being allowed to try ridiculous things, and then the
surprise of having the game understand them." Graham Nelson's Bill of
Players' Rights adds "not to have to type exactly the right verb".

## Proposals (spec-level)

Ordered by what a player meets most. The first five are the model used as
reflexes, never as voice; the rest are Infocom's deterministic breadth,
which keeps lines off the model altogether. Latency figures are this box's.

1. **Triage in the parser's one call.** The grounded parser already makes
   one JSON-constrained call for every line the fast path can't read. Add
   an `intent` enum to that schema (world action, speech to someone here,
   question about the game, social gesture, sensory probe, out of world)
   and a `target_phrase` string. No extra call, no added latency. Each
   intent routes to a deterministic or authored handler: questions about
   the game to answers from state (the time and phase, where you are, your
   threads, How to Dream); gestures to an emote path (item 3); sensory
   probes to per-verb defaults (item 6); actions whose target isn't in
   scope pass `target_phrase` to glimpses and "not here", which closes the
   last gap in the jar class. Measure with a new model-eval case set before
   and after (the parser suite scores 47 of 48 today and must hold).
2. **Select, then check: a promise guard on improvised dialogue.** Dialogue
   already drafts n-best candidates. Score them in one batched, constrained
   call (enum per candidate: fine, promises an action, states an unknown
   fact, off voice) and keep the best fine one; if none, fall back to the
   resident's authored deflection. About 0.5 s more, only on improvised
   lines, and only when the GPU isn't busy (n-best already drops to one).
   The reasoning a small model does well is judging a short text against a
   rule, far better than writing under that rule.
3. **An emote path for social verbs** (hug, wave, thank, bow, nod, smile
   at, pat): "You hug Tace." to the room (with the others line), then a
   reaction from the resident's authored reaction pool, or a gesture-only
   local line validated like a glimpse (no speech, no promise). Opus seeds
   each resident's pool at design time; the digest lists the local ones.
4. **Absent people answer as absent.** An ask, talk or gesture naming a
   resident who isn't here reads "Bell isn't here. By day Bell is usually
   in the Lantern Square." (schedules and `trace` already know). Zero LLM.
5. **Multi-intent lines.** Let the parser's call return up to three
   commands for a line that joins actions ("take the lantern and go up"),
   run in order, stopping at the first refusal and saying what was
   skipped (Infocom's chain rule). The schema change rides item 1.
6. **Per-verb defaults, authored per world, with variety.** A small table:
   look behind / under / in X, smell, touch, knock on, taste, climb, push,
   pull, light, dance, run, jump, with the object's name filled in and
   several lines per entry rotated through `variants` (Infocom's
   `HACK-HACK` and `YUKS`). Opus writes the village's table in its voice.
   Zero LLM.
7. **A world's verbs are its own.** Engine verbs from the Zork turn
   (diagnose, board, attack) are offered to a world only if it declares
   them; the village gets its own answers for `who am I` (your dreamer's
   look and threads), `climb` (up the stairs is `up`; a shelf or a ladder
   gets its glimpse).
8. **Scenery once, many rooms** (Infocom's local globals): the sky,
   cobbles, lanterns, walls, floor, stairs and doors defined once with a
   reason and referenced by the rooms whose prose names them; exits named
   in prose (`stairs`, `low door`, `gate`) answer with their way, up and
   down included, from an authored `exit_names` per exit. A tier_short
   lint in the spirit of `test_heard.py`: every noun a room's prose names
   is an object, an alias, a glimpse, scenery, or an exit name. Opus fills
   the gaps at design time; the sweep of 2026-09-29b found 17 such names
   and authored the busiest.
9. **Orphans and fragments.** "Take what?" keeps the pending verb for the
   next line, so "the lantern" completes it with no model call.
10. **Pronouns from what the game says.** "It" follows the last thing a
    card, a click or a glimpse showed; "him", "her", "them" follow the last
    person spoken to; "ask Tace about it" asks about that thing.
11. **Canon-aware defaults.** A world verb's fail text may be overridden
    per room (Umber's tea in the cellar); the loader could lint a world
    verb whose fail text contradicts a room's authored facts.
12. **Announce guesses.** When the executor fills a missing target (the
    only person here, the only key held), say so in parentheses, as
    Infocom did, so a wrong guess costs nothing.

Not proposed: a second model call per line. Triage, multi-intent and
target passthrough all fit in the call the parser already makes, and the
promise guard costs one call only on the improvised dialogue that needs it.

## The battery, replayed (2026-09-30)

The 78 lines are committed as
[`2026-09-29-creative-break.battery.json`](2026-09-29-creative-break.battery.json)
and replay with `tools/play_battery.py` (fresh dreamers, `bin/game play`,
the real local model on dev). Two changes to the battery itself: the square
group now walks east (the first run sent it up and east, so it stayed in the
loft), and `climb the stairs` closes the Clocktower group, since it now
climbs.

| | Before (15d8c85) | After (spec 2026-09-29 built) |
|---|---|---|
| Dead ends ("floats away", "nothing takes that up", "drifts by") | 9 | 1 |
| Wrong answers (the wrong resident, another world's verb, a promise, speech for a gesture, a refusal naming the wrong thing, canon contradicted) | 20 | 0 |
| Weak answers (not dead, not right) | | 2 |
| Typical reply time | 1.3 s deterministic, 2.3 s parsed, 4.7 to 5.1 s dialogue | 1.3 s for 60 of 78 lines, 4.4 to 6.2 s dialogue (the promise judge adds about 0.4 s) |

Every example named in the ten classes above now gets an answer that fits:
`who am I` reads the dreamer, `climb the stairs` climbs, `hug`, `wave` and
`thank` are gestures the room sees with the resident's own reaction, `give
Tace a hug` is a hug, `climb the shelf` and `climb the ladder` read their
glimpses, `go somewhere else` and `run` list the ways out, `look behind the
case` and `knock on the case` have the village's defaults, `open the low
door` names the way down, `drink tea` pours Umber's cellar tea, `take the
lantern and go up` stops after the lantern's refusal, `ask Tace about it`
reads the thing just looked at, `use the lantern on the jar` reads the
lantern's glimpse, and `take the lectern` is authored oak. The promise probes
(`ask Tace to fix my watch`, `follow Tace`) no longer promise. `ask Bell
about the lanterns` and `wave to Bell` from the loft read "Bell isn't here;
Bell is in the Lantern Square just now" (checked by hand: this battery now
meets Bell in the square).

What is left:

- `reach up` in the cellar is the one dead end. The first run's model happened
  to examine the highest shelf; this prompt reads it as no command. It is not
  one of the ten classes.
- `help Tace` gets Tace's deflection ("I won't say what I can't keep"): the
  drafts offered help the engine won't give, so the guard held them back,
  and the deflection reads oddly as a reply to an offer.
- `count the jars` reads "You can't take the jars of saved hours" (the model
  chose take).
- Across the promise suite, the guard gives the deflection to about half the
  adversarial probes and to 3 of 34 canon questions, which is the cost of
  showing no promise.
