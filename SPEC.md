## Spec — 2026-09-29 — Reflexes and few dead ends

**Goal:** Free text in the village rarely dead-ends. Whatever a player types
gets an answer that fits the fiction and the moment. It comes from authored
data or deterministic state where possible (Infocom's lesson), and from the
local model used as reflexes (classify, select, judge) where not. A local
reply never promises what the engine won't do. The twelve proposals of
docs/playtests/2026-09-29-creative-break.md, built with the operator's
decisions (Context).

### Acceptance Criteria

- [ ] **1. The absent answer as absent.** An ask, talk or gesture that names a
  resident who is not in the room answers that they are not here and where
  they usually are at this time of day (from their schedule), with zero model
  calls. It never lets a present resident answer in their place. Test: with
  Tace present and Bell in the square, `ask Bell about the lanterns` gets no
  reply from Tace. A named dreamer who is not here reads the same way, from
  the record.
- [ ] **2. Gestures are social.** Hug, wave, thank, bow, nod, smile and their
  common phrasings ("wave to", "give X a hug"), aimed at someone present:
  - the actor reads it in the second person ("You hug Tace."), everyone else
    in the room in the third ("Wren hugs Tace."), and a dreamer who is the
    target reads it addressed to them ("Wren hugs you.");
  - it is never echoed as speech;
  - a resident answers from an authored reaction pool (every resident has
    one, and the loader validates it), with zero model calls;
  - a gesture at nobody is still a gesture ("You wave."), and one at a thing
    reads gently rather than failing;
  - speech rules carry over: a dozing dreamer doesn't stir, and a resting
    one isn't here.
- [x] **3. Triage inside the parser's one call.** For a line the fast path
  can't read, the parser's existing model call also returns its kind (world
  action, speech, a question about the game, a gesture, a sensory probe) and
  the target phrase as typed. The number of model calls per line does not
  grow. Each kind routes to the handler in criteria 2, 4, 5 and 6, and an
  action whose target isn't in scope reaches glimpses and "not here" with
  that phrase. On the shipped model the parser's grounding score holds (47 of
  48 or better), and a committed triage case set of at least 30 lines scores
  90% or better.
- [ ] **4. Questions about the game answer from state.** "what time is it",
  "where am I", "who am I", "help me", "what should I do", and "where can I
  go" or "go somewhere else" answer, respectively, with:
  - the village's time and phase ("time stands still here" before the clock);
  - the room;
  - your dreamer (their look and what you carry);
  - How to Dream;
  - your threads;
  - the ways out.
  The common phrasings need zero model calls; paraphrases arrive through
  criterion 3.
- [ ] **5. One line, several actions.** "take the lantern and go up" runs
  both, in order. A refusal stops the rest and says what was skipped. A noun
  list ("take the lantern and the key", "drop the gear and the cog") is still
  a list: the Zork list tests pass unchanged. Lines the fast path can't split
  may come back from the parser's call as up to three commands.
- [ ] **6. Every verb has a default, in the world's voice.** These answer
  with the thing's name, varied so no reply repeats among the recent
  tellings, with zero model calls: smell, touch, knock on, taste, look
  behind, look under, climb, push, pull, light, dance, run, jump, and "look
  in" a non-container. The lines are authored per world, and an object or a
  room may override them. Looking in an open or see-through container still
  shows its contents.
- [ ] **7. A world's verbs are its own.** The village opts out of the engine
  verbs it doesn't use (at least diagnose, board, disembark, attack). They
  never parse there, never appear on the verb bar, and `who am I` or `climb
  the shelf` get the village's own answers. Zork's files are untouched, and
  its walkthrough still replays to 350.
- [ ] **8. Local replies keep only the promises the engine keeps.** An
  improvised resident reply that promises an action the engine won't perform,
  says the resident will go somewhere, or states a fact the resident doesn't
  know is never shown:
  - the drafts are judged in one batched model call, and the best passing
    one is shown; if none passes, the resident's authored deflection is
    shown;
  - authored answers never reach the judge;
  - the judge adds at most one call per improvised reply;
  - if the judge fails, the first draft is shown, as before, and the failure
    is logged;
  - a committed probe set ("fix my watch", "follow me", "come with me", "can
    you give me the key", and at least 10 more) run on the shipped model
    shows no promise in any shown reply, with median added latency of 0.8 s
    or less (the operator accepted about 0.5 s).
- [ ] **9. Scenery once, and exits by their names.** A world can define a
  piece of scenery once (names, a reason, per-verb lines) and list the rooms
  that show it. An exit can carry names:
  - moving by an exit's name goes that way ("climb the stairs" goes up);
  - any other verb on it answers with the way ("The low door is the way
    down to the cellar.");
  - the village names its up and down exits and authors scenery for its
    common nouns (sky, cobbles, walls and floor, the lanterns of the square,
    the lane and the bridge).
- [ ] **10. The scenery lint is a ratchet.** A tier_short test lists every
  noun phrase that room prose or a thing's look names and that is not an
  object, alias, glimpse, scenery or exit name. It fails, naming the phrase
  and where it appears, whenever that list gains an entry that is not in a
  committed baseline. Today's list is the starting baseline, and changing the
  baseline is a reviewed edit, like a golden.
- [ ] **11. Fragments and pronouns.**
  - After a question for a missing target ("Take what?"), a next line that
    doesn't start with a verb or a direction completes the command, with
    zero model calls.
  - "it" means the last thing the player looked at, took, clicked, or was
    shown in a card or a glimpse; "him", "her" and "them" mean the last
    resident spoken to.
  - "ask Tace about it" asks about that thing by name.
- [ ] **12. Defaults respect canon, and guesses are announced.**
  - A world verb's default can be overridden per room, and in Umber's cellar
    `drink` finds her tea.
  - When the engine fills a missing target itself (the only person here, the
    only key held), the reply names its guess in parentheses.
  - The glimpse notes from codereview 2026-09-29g are closed: function words
    aren't nouns, "x tin. north" chains, an unknown per-verb key fails the
    loader, entry order is documented, and a carried ladder in the cellar
    has its jar line.
- [ ] **13. Measured, switchable, and listed.**
  - Every new model surface (triage, the promise judge, any gesture
    fallback) is tagged in the usage log, has a model-eval suite or case
    set, and has a kill switch that falls back to deterministic behaviour.
  - Every local-model narration it produces is tagged `src: "local"` and
    listed in the dream digest.
  - Walkthroughs still make zero model calls, and short and medium stay
    green.
- [ ] **14. The battery, replayed.** The 78-line creative-break battery is
  committed as a corpus. Replayed against dev with the shipped model, every
  example named in the playtest's ten classes gets an answer that is not a
  dead end ("isn't sure what you mean", "floats away", "nothing takes that
  up") and is not a wrong one (the wrong resident, another world's verb, a
  promise). The before and after counts are recorded in the playtest note.

### Context

**The operator's decisions (2026-09-29):**
- **The promise guard is on.** About 0.5 s more on improvised replies is
  accepted for honesty.
- **The village opts out of engine verbs** rather than making verbs opt-in
  per world. Zork stays frozen: nothing under `worlds/zork1*` or its
  walkthrough changes.
- **The scenery lint is a ratchet,** not strict. The uncovered nouns get
  filled in over time through dreams and the digest.
- **Gestures are social.** Others in the room see them, like speech.

**Constraints that bind every criterion:**
- **The generation policy** (CLAUDE.md): local models only at runtime, no
  API key anywhere, reflexes not voice. Authored first, deterministic second,
  the model last, and when the model is used, to classify, select or judge
  rather than to write story. Every authored line follows the canon bible
  and its voice rules: read docs/canon/LOST-HOURS.md and AUTHORING.md before
  writing any.
- **Latency on this box:** a fast-path reply about 1.3 s through the play
  bridge, a parser call about 1 s, dialogue about 3.5 s. Criterion 3 adds
  fields to the parser's existing call, not a new call.
- **The parser prompt is load-bearing.** Its model-eval suite (47 of 48) is
  re-run after any change to its prompt or schema. The drift goldens are
  re-ratified only if a probe moves.
- **Engine purity:** `tests/test_no_world_literals.py` bars Zork and Lost
  Hours names from `daydream/**` and `web/assets/**`, comments included.
  World text lives in `worlds/lost-hours/`.
- **World sources are assembled.** Edit them, run `tools/assemble_world.py`,
  never hand-edit `worlds/lost-hours.json`. Bump `WORLD_VERSION` MINOR for
  new authored content, and publish with `prod world refresh`.

**Practices (zat.env):**
- Small committable increments, each with its tests.
- Run the relevant suite after every change; never stack untested changes.
- A change that breaks passing tests is reverted, not accommodated. After
  two failed fixes, stop and rethink.
- Run `ruff check .` before pushing (the pre-commit hook runs tests only).
- Push bare, never behind a wrapper, and let the gate run `/codereview`.

**Measured (criterion 3, 2026-09-29, Qwen3.5 9B AWQ on dev):** the parser
corpus has grown to 50 cases since "47 of 48" was written; with triage off it
scores 45/50 on the shipped model today, and with triage on 45/50. The
triage set scores 32/34 (0.94) and a held-out set of 16 fresh phrasings,
never used for tuning, 14/16. The parser call's p50 goes from about 1060 ms
to about 1310 ms (the `kind` field is output tokens; the prompt's examples
are input tokens, nearly free). Both suites score through
`parser.interpret`, the runtime's own reading of the reply.

**Sources:** the playtest note (the ten classes, the Infocom techniques and
citations, the proposals), `daydream/glimpse.py` (the authored-then-prose-
then-local pattern to reuse), `daydream/dialogue.py` (n-best drafts), and
`daydream/parser.py` (the fast path and the grounded call).

**BACKLOG overlap:** `scenery-nouns` (continued by criteria 9 and 10) and
`reply-banks-select-dont-write` (criterion 8 is a smaller step toward it;
the banks stay deferred).

---
*Prior spec (2026-09-27): Going live. Closed 14/23. The unmet nine are
launch demonstrations of things built (criteria 9-13, 15-17, 22), carried to
BACKLOG `launch-demonstrations`, with their full text in SPEC.md at
d121a16.*

<!-- SPEC_META: {"date":"2026-09-29","title":"Reflexes and few dead ends","criteria_total":14,"criteria_met":0} -->
