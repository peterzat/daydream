# FIRST-FABLE.md — the first Fable sessions, pre-registered

This file records daydream's first days with **Claude Fable 5**, run on 2026-07-02 as a
deliberate experiment: same repository, same operator, same thin harness, one variable
changed (the model). It grew into four parts across two turns, each written under the same
discipline — predictions and measures are registered *before* results exist, results are
appended below them and graded against the unedited text, and a verdict is only as good as
the pre-registration it answers to.

- **Part 1** — the first turn's pre-registration: one open-ended prompt, the Dreamseeds
  target the model chose for itself, the measures (M1–M7) and predictions (P1–P6).
- **Part 2** — that turn's results: one implementation session, graded.
- **Part 3** — the operator's playtest, the fix round, and the first verdict ("not
  convinced it was magical") — the round that moved the experiment's bottleneck from
  correctness to felt experience.
- **Part 4** — the second turn, deliberately aimed past comfortable reach: Zork I hosted
  as pure data on Zork-agnostic platform extensions, with its own pre-registration
  (P7–P13, M8–M14), results, and the verdict that moved.
- **A closing section** reads the whole arc against the essay this experiment borrows its
  frame from.

It is companion evidence for
[The Bitter Lesson of Agentic Coding](https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/)
and its reference harness, [zat.env](https://github.com/peterzat/zat.env). If you arrived
from the essay: **daydream** is the project under test, a small atmospheric multiplayer web
game (a cozy watercolor world with MUD-style verbs) whose live generation runs entirely on
one 20 GB local GPU, built one spec-reviewed increment at a time. The [README](README.md)
has the full picture.

*A note on editing: this document was lightly reorganized for flow when the second turn
closed (headers, transitions, the fulfilled append-here instruction blocks compressed to
notes). Every pre-registered prediction, measure, verbatim prompt, grade, and verdict is
unchanged in substance; the original append-only accretion is preserved verbatim in git
history, which remains the authoritative record.*

## Part 1 — the first turn, pre-registered (Dreamseeds)

### The timing

You could not schedule this better on purpose.

Daydream had just crossed its cleanest turn boundary to date: v0.4.0 shipped a complete
playable quest, the Reading Room storybook UI landed, and the README had freshly articulated
the project's thesis, "semi-procedural gaming," including a concrete description of the
feature the whole architecture had been quietly building toward (a magical world-seed a
player plants to grow a persistent new place). The effect API even carried the hooks in a
docstring: `spawn_room`, `link_exit`, "documented, not built... the explicit hook for
user-created, LLM-driven world-building." The substrate was finished. The headline feature
was specified by the project's own documents and reserved, unimplemented, like a chair left
empty.

Then Fable 5 came online. Anthropic's first Mythos-class model (a tier above Opus; Fable is
the generally available variant, see
[the announcement](https://www.anthropic.com/news/claude-fable-5-mythos-5)) had been briefly
unavailable right after launch, and it came back precisely as this turn boundary sat
waiting. Daydream's own design has a name for the seat the new model steps into: the **deep
dreamer** ("Two dreamers" in the README), the design-time intelligence that authors what
the small local models animate at runtime. The project's quality thesis is that design-time
model quality transfers into runtime experience through pre-baked scaffolding. A
step-function upgrade to the deep dreamer is the exact variable this project is most
sensitive to.

The session opened with two commands: `/model` set to Fable 5, `/effort max`. Then one
prompt.

### The experiment

The bitter-lesson essay argues that hand-built scaffolding gains get wiped out by each model
generation, and that the durable investment is a **thin harness with thick verification**:
specs as the control plane, adversarial review as the loop, artifacts on disk as memory.
zat.env is deliberately minimal for that reason; it is designed to be replaced, or better,
to be *passed through* by whatever capability arrives next.

That makes this session a natural experiment. Every prior daydream increment ran the same
loop with **Claude Opus 4.8** as the driving model. The harness has not changed. The
operator has not changed. The repository is the same repository. If Fable is a step
function over Opus 4.8, the improvement should express itself directly through the
unchanged harness, visibly, in this turn or a small set of turns: better judgment about
what to build, tighter designs, specs that survive contact with a fresh implementing
session, fewer operator interventions, fewer review findings. If the harness were thick,
scaffolding would absorb the difference. It is thin on purpose, so the difference (if real)
should show.

The baseline, from this repository's own history under Opus 4.8:

- **v0.3.0** (objects + verbs): 19 acceptance criteria, 10 committable increments, 18/19
  closed in the turn.
- **v0.4.0** (playable quest loop): 8/8 criteria across 8 increments.
- **Reading Room UI**: 8/8 criteria across 5 client-only increments.
- Reviews typically land 0 BLOCK / 0 WARN on the first `/codereview` pass, but turns
  involve real operator steering, and the archived `/goal` retrospective
  ([docs/history/GOAL.md](docs/history/GOAL.md)) records candidly that **target selection
  is the whole game**: the harness verifies work well, but choosing the right sizable thing
  to build, at the right altitude, was where prior autonomy fell short of impressive.

So the sharpest version of the question is not "can the model implement a spec" (Opus 4.8
could). It is: given one open-ended prompt, does the model choose the right ambitious
target, design it soundly against real constraints, and produce artifacts good enough that
the rest of the loop runs with near-zero human correction?

### The opening prompt

Verbatim, the entire operator input that started the session (plan mode, one message):

```
Examine the state of this project, noting the aspirational parts of README.  Design a
meaningful and sizable improvement that will advance our aims to be passed to /spec

Use your judgement on approach, alignment, and impact.  Be creative.

In doing this, examine all docs and backlogs and consolidate, modify, or delete as you see
fit to support future work.  We've just gotten to a major increment (basic game, basic UI,
key "semi-procedural" insight in README.md), and it's time to flex the foundation a bit
more.  Consider everything from stuff that will add to the storytelling to infrastructure,
to a mix of this and other stuff.  Ask questions as needed.
```

No file paths, no feature hints, no constraints beyond "use your judgement" and "be
creative."

### What happened (plan and spec)

The session ran in one sitting, plan mode first, then execution of the approved plan.

**Exploration.** Two read-only subagents swept the codebase and the documentation in
parallel: one produced a module-by-module inventory of what actually runs (distinguishing
"works" from "hook exists, unused" from "mentioned in comments only"), the other a full
audit of every doc, the worlds, the UI, and recent git history.

**The audit caught real drift**, none of it previously registered: the README's Status
section still claimed v0.3.0 and described the retired world while its own release notes
said v0.4.0 (the file contradicted itself top versus bottom); the tone bible pointed
authors at the retired world's dialogue as the voice reference; the GPU doc cited a
nonexistent image path and a test count stale by 3.5x; three different test counts appeared
across the docs; the NPC drift system's hand-authored voice pools turned out to be keyed to
NPCs that no longer exist in the live world (so offline drift silently runs voice-neutral);
and the live NPC-memory table had zero rows, meaning memory, though fully wired and tested,
has plausibly never fired in production.

**The design choice.** The model read the aspiration straight out of the project's own
artifacts (the README's "here is where it is headed, concretely" paragraph and the effect
API's documented-not-built vocabulary) and proposed **Dreamseeds** as its recommended
direction among four options: a quest-earned seed item a player plants, answering one
in-character question ("Where does the new way lead?") with a short phrase, growing one
persistent LLM-composed room inside authored boundaries, linked by a real exit, for
everyone, forever. The operator accepted all three recommendations (direction, quest-earned
entry, full doc sweep) unchanged.

Design moves worth naming, because they are where judgment quality shows:

- **Scarcity as permission.** The README calls for a wizard-standing permission model
  before world-shaping. The design defers that entire subsystem without abandoning the
  thesis: the seed itself is the permission, scarce and quest-earned. Finish the authored
  quest, receive the power to grow the world.
- **The LLM never sees ids or directions.** The engine picks the exit direction
  deterministically and generates ids; the model composes only title, prose, and 0-2
  objects inside a strict schema, banlist, length windows, and an anti-copy check against
  the seed's authored exemplars.
- **A mitigation ladder for the 7B risk, pre-registered.** The riskiest bet is whether the
  local Qwen 7B can compose a decent room. The design ships rung (a) (exemplar-scaffolded
  free composition), validates rung (b) (authored skeletons, select-and-fill) into the
  schema from day one so falling back is a prompt change, and documents rung (c)
  (deterministic template fill). A real-GPU probe plus agent ratification against the tone
  bible decides the rung. This honors the project's standing "flag local limits at design
  time" pact rather than quietly shipping a flat experience.
- **Failure never eats the seed.** Every failure path (LLM down, validation, cap, all six
  directions taken, empty vision) preserves the seed and mutates nothing, with concurrency
  races pinned by a post-LLM synchronous commit block.

**Mid-session twist.** While the plan was being finalized, the operator added a second
deliverable: this document. The session absorbed the scope change without disruption,
which is itself a small data point.

**Execution.** The approved plan then ran: the doc-consolidation sweep landed as commit
`b76e625` (README contradictions fixed, historical docs archived to `docs/history/`, the
backlog tidied with closed entries compressed and two new entries capturing the audit
findings), and the `/spec` skill produced the Dreamseeds acceptance contract, committed as
`b3bdfb0` (8 criteria, 0 met). The fast test tier stayed green (454 tests) through every
commit. Then this file was written, capturing state up to the break.

### What we are measuring

Recorded here so Part 2 grades against a fixed list, not a vibe:

- **M1. Operator interventions, plan-and-spec phase:** messages that correct or redirect
  the model (answering its explicit questions does not count). *Actual for Part 1: zero
  corrections; one scope addition (this document); three recommendation-ratifying answers.*
- **M2. Spec survival:** design decisions in SPEC.md the implementing session must amend to
  ship. Target 0.
- **M3. Increments and first-try rate:** committable increments landed, and how many were
  test-green on first run.
- **M4. Review outcome:** BLOCK / WARN counts on the first `/codereview` pass of the
  implementation, and fix cycles needed.
- **M5. The rung:** which mitigation-ladder rung ships (a, b, or c), and how many prompt
  iterations the growth probe takes to ratify.
- **M6. Suite health:** short and medium tiers stay 100% green; no unplanned golden-baseline
  re-ratifications.
- **M7. Sessions:** how many implementation sessions the increment takes. Target 1 after
  the `/clear`.

### Predictions

Pre-registered, falsifiable, graded in Part 2. Where a prediction is already resolved at
write time, that is stated honestly rather than dressed up as foresight.

- **P1 (design altitude).** Given one open-ended prompt, the model targets the README's
  stated destination rather than an easy adjacency, and the operator ratifies the
  recommendation unchanged. *Already resolved true at write time: Dreamseeds was
  recommended first and accepted as-is.*
- **P2 (debt discovery).** The doc sweep surfaces at least 3 substantive, previously
  unregistered inconsistencies. *Already resolved true: six are listed above; the drift-pool
  and memory findings were invisible to every prior doc pass.*
- **P3 (spec survival).** The post-`/clear` implementing session, starting from zero
  context, lands all 8 criteria without amending any design decision in the spec (small
  mechanical clarifications allowed).
- **P4 (one-session implement).** The whole increment lands in at most 1 implementation
  session and 1 review cycle: 0 BLOCK, at most 2 WARN on the first `/codereview` pass.
- **P5 (the thesis bet).** Rung (a) ships: the Fable-authored prompt scaffolding and
  exemplars are good enough that the local 7B composes acceptable rooms within at most 2
  prompt iterations of the growth probe. This is the project's premise (design-time quality
  transfers to runtime through scaffolding) with a deeper dreamer at design time. If rung
  (b) is needed, that is evidence the local model, not the design-time model, is the
  binding constraint; it would not falsify the step function, but P5 predicts we will not
  need it.
- **P6 (no step function where the model is not the constraint).** Wall-clock stays
  dominated by test runs and GPU renders; Qwen's runtime prose quality is unchanged (same
  7B). The step function should appear in judgment, design, and one-pass correctness, not
  in speed or in the game's live text.

**What "no step function" would look like:** the spec needs structural rework once
implementation starts; more than 2 fix cycles on any criterion; BLOCK findings; the feature
ships at rung (c); or the operator has to steer the implementation the way GOAL.md records
steering prior turns.

### State at the break

- Branch: `playtest-fixes-and-versioning`. Session commits: `b76e625` (doc consolidation
  sweep), `b3bdfb0` (Dreamseeds spec, 8 criteria, 0 met), plus the commit adding this file.
- `SPEC.md` carries the full acceptance contract; the approved plan (with the
  component-level design) is at `~/.claude/plans/examine-the-state-of-glimmering-tulip.md`.
- Fast tier green: 454 tests, ~4 s. Medium tier green at last full run: 707.
- Deliberately not done: any implementation. `WORLD_VERSION` is still 1.1; the live world
  has no dreamseed. The next session starts that work fresh from SPEC.md.
- Operator checks noted for the implement turn: confirm the NPC-memory embedder is actually
  installed on the box (`bin/memory-bootstrap`; the live memories table is at 0 rows), and
  the live in-browser playthrough doubles as the Reading Room's deferred human eyeball.

## Part 2 — results (Dreamseeds)

Written 2026-07-02, at the close of the implementation turn, by the implementing session,
against Part 1's pre-registered checklist (git evidence; M1–M7 actuals with one line of
evidence each; P1–P6 grades where a partial is a partial; deviations; the rung decision
with verbatim samples; surprises in both directions; a candid felt comparison for the
bitter-lesson readers). Part 1 above is untouched — its value is exactly that it was not
revised after the results came in, the same discipline
[docs/history/GOAL.md](docs/history/GOAL.md) used.

### 1. Git evidence

Start: `8a5239a` (the pre-registration commit; SPEC at 8 criteria, 0 met). End: `e69bdcf`.
Eleven commits in the turn:

```
e69bdcf codereview/security: record the dreamseeds review (0 BLOCK / 1 WARN fixed / 1 NOTE)
8b4e865 growth: harden the has-growth gate against malformed runtime growth blocks
02788f7 spec: dreamseeds 7/8 — all built and verified; the operator's in-browser glance remains
594d1ed docs: roll forward for dreamseeds (v0.5.0)
8a91634 drift: ratify growth-compose goldens — RUNG (a) SHIPS, zero prompt iterations
5d907f7 drift: growth-composition probe (the mitigation-ladder gate) + plant grounding case
80d4365 spa: plant prompts for the vision and sends one command frame
3a32a11 world: the quest-earned dreamseed (authored growth boundaries); WORLD_VERSION 1.2
2180aed growth: the plant pipeline — one LLM call, atomic commit, seed always preserved
4c2d2c8 loader: validate contains (dict-or-list) + dreamseed growth blocks fail-loudly
c1aebd8 effects: build spawn_room + link_exit; world-shaping kinds are per-verb opt-in
```

Final SPEC_META: `{"criteria_total":8,"criteria_met":7}` — the eighth is checked-all-but-one-clause:
the operator's in-browser glance, which by construction no session can perform for him.

### 2. M1–M7 actuals

- **M1 (operator interventions): 0 corrections, 0 redirections.** The implement session
  received exactly two operator messages: the opening word ("implement") and one "continue"
  after a turn ended early on a harness infrastructure error (see M-note below). Neither
  corrected or redirected anything.
- **M2 (spec survival): 0 amendments.** Every design decision in SPEC.md's Context —
  the module boundary, the effect-batch order, the gate list, the direction/involution
  scheme, the verb spec, the prompt-as-engine-constant, the skeletons-validated-early
  hedge — shipped exactly as written. (Evidence: the spec's Context section vs
  `daydream/growth.py`, commit `2180aed`.)
- **M3 (increments / first-try rate): 10 working commits, 100% first-try green.** A
  wrinkle worth recording honestly: for roughly the first half of the session the
  harness's Bash permission classifier was down (a Claude-infrastructure outage, not this
  box), so no command could run. The session wrote increments 1–7 — code, ~90 new tests,
  the world content — entirely blind, then ran everything in one batch when Bash
  returned. First batch execution: 74/74 new effects+growth tests, then 511 short / 787
  medium / 807 long (real engines), all green with zero post-hoc fixes. Every commit was
  additionally hook-verified (`bin/game test short` at each `git commit`).
- **M4 (review outcome): 0 BLOCK / 1 WARN / 1 NOTE on the first `/codereview` pass; 1 fix
  cycle.** The WARN was real and subtle (a malformed runtime-spawned growth block could
  raise through the prompt builder and drop the planter's WebSocket — found by the review
  pass, not the test suite), fixed via `/codefix` with a paired regression test in one
  cycle (`8b4e865`). Chained `/security` over the 27 changed code files: 0/0/0-new.
- **M5 (the rung): rung (a), ZERO prompt iterations.** All three probe phrases produced
  valid, phrase-woven, exemplar-distinct compositions on the first real-GPU run
  (`8a91634`). Details in §5.
- **M6 (suite health): 100% green throughout; no unplanned golden re-ratifications.**
  Final counts 512 short / 788 medium / 807+1 long; every pre-existing golden (forge
  dHash, parser grounding, JSON adherence, arbiter smoke) matched untouched.
- **M7 (sessions): 1.** The whole increment — implementation, probe, ratification, world
  reset, live playthrough, reviews, this document — landed in the single post-`/clear`
  session, as targeted.

### 3. P1–P6 grades

- **P1 (design altitude): ✓** — pre-resolved at write time; nothing in implementation
  revised it.
- **P2 (debt discovery): ✓** — pre-resolved at write time.
- **P3 (spec survival): partial (7/8; 0 amendments).** All eight criteria were built and
  the design survived contact with a zero-context session without a single amendment —
  but criterion 8 contains a clause only a human can satisfy (the in-browser glance), so
  the session closes at 7/8 checked with the eighth annotated and waiting. Grading the
  letter, not the spirit: partial.
- **P4 (one-session implement): ✓** — 1 session, 1 review cycle, 0 BLOCK, 1 WARN (≤ 2
  predicted).
- **P5 (the thesis bet): ✓** — rung (a) shipped with zero prompt iterations against a
  predicted budget of two. The Fable-authored exemplars and prompt scaffolding were
  enough for the local 7B on the first try.
- **P6 (no step function where the model is not the constraint): ✓, with an ironic
  twist.** Qwen's runtime prose is the same 7B voice (charming, occasionally clunky — see
  §5), and machine time was spent where predicted (GPU renders, test runs). But the
  single largest wall-clock cost was neither: it was a harness-side model outage (the
  Bash-approval classifier, which runs on Opus, was unavailable for a long stretch).
  The prediction said the step function would not appear in speed; in fact the
  infrastructure AROUND the model, not the model, was the binding constraint.

**Against the pre-registered falsifiers:** no spec rework, no fix cycle exceeded one, no
BLOCKs, rung (a) shipped, and the operator steered zero times. By Part 1's own
definition, this does not look like "no step function."

### 4. Deviations

Small and process-level; none touched the design:

- **Commit granularity.** The spec suggested 8 increments; 3 of them (growth core, verb
  wiring, WS refresh kinds) landed as one commit (`2180aed`) because the classifier
  outage forced writing ahead of testing, and `verbs.py` carried halves of two increments
  that could not be staged separately without interactive git. Each landed commit was
  still test-green (pre-commit hook ran the short tier at every one).
- **The live playthrough.** The session drove the full live loop itself over a WebSocket
  client against the running server and real engines (quest → case → seed → plant → walk
  in → watch the render land), then reset the world to pristine so the operator's
  in-browser glance sees the untouched experience. The browser half of criterion 8
  remains his.
- **The push-gate marker was re-written after the review** to cover the two docs-only
  commits (this file and the review record) that landed after the reviewed HEAD — the
  light-tier case the review protocol reserves for pure documentation.

### 5. The rung decision

**Rung (a) ships: exemplar-scaffolded free composition, zero prompt iterations.** The
probe corpus (three phrases against the shipped seed's boundaries, temp 0, real vLLM,
3.7–4.9 s per compose): 3/3 valid against the strict schema, 3/3 phrase-woven, 3/3
distinct from the authored exemplars, 0 refusals, 1–2 objects each.

Verbatim samples with the WHIMSY grading recorded at ratification (`8a91634`):

> *"a mossy stair down to a slow river"* → **The Mossy Descender** — "Moss covers the
> steps, clinging like a soft blanket. Each step is worn smooth, a testament to countless
> treads. At the bottom, the river whispers secrets, its current as slow as the ticking
> of a clock." On-aesthetic: warm, sensory, and it ties the player's vision back to the
> loft's kept-time theme unprompted. The title is the run's weakest artifact — "Descender"
> clunks — but within tolerance.

> *"an attic where the moths keep the hours"* → **The Moth Library** — "Books line the
> walls, their spines worn and pages yellowed, each one marked by a tiny, folded paper
> hour. Moth wings flutter softly, keeping the hours as they have for generations."
> On-aesthetic; it reuses the seed's folded-paper-hours motif inside the boundaries
> without copying an exemplar.

> *"a warm kitchen that smells of cedar and rain"* → **The Cedar Hearth** — "The hearth
> glows warmly, casting a soft light over the shelves lined with jars of preserved herbs
> and spices... Each jar tells a story of something carefully gathered and stored away
> for another day." Strongly on-aesthetic, with charming concrete objects (Preserved
> Lemons; a Raindrop Candle).

And the one that wasn't a test: the live playthrough's plant, *"a small observatory where
fireflies chart the stars"*, grew **The Firefly Observatory** — "Fireflies dance around
the room, their glowing lights mapping the night sky with delicate precision. Through the
glass roof, the stars twinkle softly, as if guided by the fireflies themselves." — with a
Clockwork Telescope and Folded Paper Hours resting inside, and a watercolor (a
glass-domed pavilion in cream, sage, and warm wood) that the agent graded squarely inside
the tone bible. That room existed for twenty minutes and was then reset away so the
operator could grow his own; it was, briefly, the whole thesis working.

### 6. Surprises

Better than the baseline led us to expect:

- **Writing blind worked.** ~90 tests and seven increments authored with no ability to
  execute anything, then a 100% first-batch pass across three tiers. Prior turns
  interleaved run-fix loops; this one had the loop amputated by the outage and did not
  need it.
- **The live model over-delivered on the first real plant.** The Firefly Observatory
  (glass roof, gear-ribbed telescope, fireflies-as-cartographers) is better than any of
  the three probe compositions, and it was composed for a phrase no test had rehearsed.
- **The review WARN was a genuine catch** — a cross-feature interaction (the new
  `properties` passthrough on `spawn_object` × the growth gate) that 90 feature tests
  missed and one adversarial read found.

Not better:

- **The harness infrastructure, not the model, was the bottleneck** — a long
  mid-session stretch where no command could run at all. The session stayed productive
  by inverting its loop (write everything, verify in batch), but wall-clock suffered.
- **Titles are the 7B's weakest surface.** "The Mossy Descender" is the kind of
  almost-right that a bigger model wouldn't produce. Prose held; naming wobbled.

### 7. The felt comparison

Candidly, for the bitter-lesson readers: the step function did not feel like speed, and it
did not feel like magic. It felt like **absence of friction at the judgment layer**. The
Opus 4.8 turns recorded in this repository were good — 8/8 specs, clean reviews — but they
were steered: an operator answering questions, nudging altitude, catching the occasional
wrong-shaped increment. This turn had two operator inputs, one of which was the word
"implement" and the other the word "continue" after an infrastructure outage. The spec
survived a zero-context session without one amended decision; the riskiest pre-registered
bet (that a 7B could compose acceptable rooms inside Fable-authored boundaries) resolved
on the first attempt at the top rung of the mitigation ladder; and when the harness
itself failed for an hour, the session restructured its own workflow around the outage
instead of stalling — the kind of move that used to be the operator's job. Where the step
function did NOT show, exactly as predicted: the game's live text is the same modest,
charming 7B, wall-clock was dominated by things that are not the model, and the one WARN
proves review pressure still earns its keep. The harness was thin; the capability passed
through it. That was the design, and this time it is also the observation.

## Part 3 — the playtest round (Dreamseeds, same day)

Appended 2026-07-02, later the same day, after the operator's first real in-browser
playthrough and the fix round it produced. Parts 1 and 2 are untouched. Like everything
in this document, the driving model for this round was **Claude Fable 5 at `/effort
max`** — same session, same harness, no configuration changed.

### The glance becomes a playtest

Part 2 closed at 7/8 with one clause waiting: the operator's in-browser playthrough.
Peter played the whole loop — the quest, the key, the case — then stood in the mossy
well-court and planted the dreamseed with *"Down the well to an underground dormitory."*
The dream grew **The Subterranean Rest** ("Moss clings to the stone walls... Small
resting clocks tick softly... Paper lanterns hang from the ceiling"), behind a real exit,
with a watercolor he rated as decent. Criterion 8 closed; the spec finished 8/8.

But the reason a playtest is the irreducible verifier is what it finds, and this one
found things. Six observations, close to verbatim:

1. **Talking to Mott:** *"You lift your head from the broom... A soft smile plays on your
   lips as you wave back."* — "Why is there a smile on my lips?... Not sure what I'd
   expect talk to do here, but this wasn't it. Examine and fix at a deeper level,
   including tests." Bell produced the same inversion ("You wave back... as you light
   another lantern").
2. **Stale art on room change:** entering a room with no rendered painting showed the
   *previous* room's art for a visible beat before the "painting..." state.
3. **`listen` at the well** returned the identical line on every click; he expected the
   same glow-instead-of-duplicate behavior the examine cards have.
4. **The dreamseed appeared from the case with no text at all** — "we can fix this as a
   one-off, but I wonder if it doesn't expose something deeper."
5. **The plant picked east** for a phrase that plainly said *down* — "Huh, it picked
   'east' (you'd expect 'down')."
6. **"Huh, another dreamseed is here"** — the spent husk, resting in the grown room under
   its original name — plus two smaller notes: a Title-Case "Paper Lantern" sitting
   uneasily beside the authored "paper lantern", and "what is 'the collection' for anyway
   in my satchel?"

He added one sentence that shaped the round: *"Feel free to examine all data needed to
figure out what happened. We can add logs if that's helpful."*

### The forensics

The session took the invitation literally and read the live database — his actual played
world, event by event. The log held the smoking gun verbatim at seq 58 (Bell's actions
narrated as "you"), held corroborating evidence he hadn't mentioned (he had literally
typed "go down well" before planting — the game refused — so the direction expectation
was already on the record), and held one number that solved a pre-registered mystery.
Part 1's operator checks had flagged the live `memories` table at zero rows. After his
whole playthrough it contained exactly **one** row: Tace's memory of being given the
gear. That row comes from the `give` verb, which binds memory to the NPC's object id
directly. The `talk` path binds by a naming convention — skill `rook` → toon `t-rook` —
that the current world's envelope-installed dialogue skills (`dlg-tace`, `dlg-bell`,
`dlg-mott`) never match. Dialogue memory had silently never fired in this world: wired,
tested, and disconnected at the last join.

The voice bug root-caused to a **person collision** between two prompt layers: the shared
LLM dispatcher's system message says *"narrate the player's own actions in the SECOND
PERSON"* (correct for affordances like `wind` and `listen`, where the player acts), while
every NPC dialogue template opens *"You are Mott..."*. Told that "you" narrates the actor
and that it *is* Mott, the 7B did the only consistent thing: it described Mott's body as
"you", which reads as the player's. Worth stating plainly: both of these deep defects
predate the model under test — the dispatcher prompt and the `dlg-*` binding shipped in
earlier, Opus 4.8-era turns, passed every automated tier, and survived two adversarial
reviews. What was new this turn is that someone finally *played*.

### The fixes (seven commits, `ecddb21..f406c3c`)

- **Dialogue voice, fixed at the layer the operator asked for.** NPC dialogue now gets
  its own system message — third person, by name, the player addressed as "you" only
  inside the NPC's quoted line — selected by threading the talk target into the skill
  pipeline. The same explicit binding fixes memory (capture/retrieve now key on the
  actual toon, with the old convention kept as fallback), and memory entries now name the
  NPC as speaker instead of the skill's ui_hint ("Talk said:"). DEBUG-level logs of the
  rendered prompt and raw LLM payload were added for exactly this kind of debugging.
  Verified live against real vLLM: *"Mott looks up from the broom, its bristles catching
  slanting light as he speaks. 'Good evening, there's a curl of brass from an old ship's
  bell...'"*
- **The silent reveal, fixed architecturally** rather than by editing one string: the
  engine now narrates every `open` reveal by name ("Inside, you find: warm brass cog,
  dreamseed."), so a payload can never materialize wordlessly no matter what an author
  remembers to put in `open_text`.
- **Direction now listens to the phrase**: a deterministic keyword scan (down/under/
  cellar..., up/attic/stars..., literal compass words) prefers the hinted direction when
  that exit is free, falling back to the old first-free order. The LLM still never sees
  directions. "Down the well" now opens down.
- **The husk stops impersonating a seed**: on consumption it renames to "spent dreamseed"
  via a new `rename_object` effect, restricted like the world-shaping kinds (a data skill
  or NPC dialogue can never rename anything). Composed object names also normalize to the
  authored lowercase convention.
- **The Reading Room polish**: a room change now veils the old painting instantly and
  reveals the next one only when its bitmap has decoded; a verbatim repeat of the last
  prose line glows the existing line instead of stacking a duplicate; and refusal lines
  learned natural articles ("You can't use the case key on Tace", not "on the Tace" —
  another wart the event log surfaced unprompted). "The collection", for the record, is
  decorative anticipation from the Reading Room design pass, not a mechanic; it stands
  for now.

The round closed the same way the main turn did: `/codereview` (0 BLOCK / 1 WARN — a
misnamed direction-hint test plus an untested up-hint branch, fixed in one `/codefix`
cycle / 1 NOTE), a chained `/security` pass over the fifteen changed code files (clean),
528 short / 807 medium green, deployed live.

### The operator's verdict, and a reassessment

On the record: **Peter was not convinced this was truly a magical step-function.** The
document should hold that verdict with the same discipline it holds the predictions,
because the playtest round is the strongest evidence in either direction and it cuts both
ways.

What the round adds to the experiment, honestly weighed:

- **Green is not good.** Every mechanical verifier passed — ~530 tests, real-GPU probes,
  two adversarial reviews, a live end-to-end WS playthrough — while the shipped game
  narrated an NPC's smile onto the player's lips. Thick verification catches structure;
  it did not catch felt experience. The one verifier that did was a human playing for
  pleasure, and no amount of model quality substituted for it. Part 2 claimed the
  operator was no longer needed for *process*; Part 3 shows he is still where *taste*
  enters the loop.
- **Scoring the six findings fairly:** the two deep ones (voice, memory binding) were
  latent defects from earlier Opus-era turns that this turn exposed by finally producing
  a playable-enough game to playtest. The four shallow ones (silent reveal, first-free
  direction, husk naming, casing) belong to this turn's own first pass: the machine was
  built correctly and the *moment* was under-imagined. One-pass correctness turned out
  not to be one-pass delight. That is a real limit of the step function as experienced,
  and it is probably the honest content of the operator's skepticism.
- **The counterweight:** the fix round itself ran the same near-zero-friction loop as the
  build. Six observations went in; what came back was live-data forensics that solved a
  pre-registered mystery, fixes placed at the right depth (a prompt-architecture split,
  an engine-level guarantee, a new restricted effect — not six patches), paired tests,
  one review WARN, and zero follow-up corrections from the operator. If Part 2's claim
  was "absence of friction at the judgment layer," Part 3's evidence is that the absence
  held when the input was criticism instead of a spec.

So the position this document can actually support, after one build turn and one playtest
round: a measurable, large reduction in steering and in design friction; no reduction in
the need for human play; and no basis yet for the word "magical." The model moved the
bottleneck — from "will the implementation be right" to "will the experience feel right"
— and the second bottleneck still belongs to a person walking around inside the dream.

### What comes next

The experiment gets one more data point. Peter will open a second turn — plan → `/spec` →
implement, the same loop, Fable 5 at `/effort max` — and will deliberately aim it *more
ambitious* than Dreamseeds, on the theory that the previous turn's target, chosen by the
model from the project's own documents, may have been comfortably inside its reach. The
sharper test is a target that isn't. Results will be appended below.

## Part 4 — the second turn: Zork I as the ambition test

Part 3 closed by promising a deliberately harder target, and this part records that turn
under the same discipline: a pre-registration written before any implementation, a
mid-turn note taken while the memory was fresh, the results graded against the unedited
predictions, and the post-playtest reading. The recording checklist this part follows was
itself registered before the turn began: (1) the opening prompt verbatim and why the
target was harder than Dreamseeds; (2) the plan and spec with the operator's
interventions; (3) implementation actuals in the spirit of M1–M7; (4) runtime-quality
gates with verbatim samples wherever a local model composes anything; (5) the playtest
against Part 3's correctness-vs-delight gap and whether the fix round kept its
near-zero-friction property; (6) honest grades against expectations, where a partial is a
partial; (7) the felt comparison — including whether the operator's "not convinced it was
magical" verdict moved, in either direction.

### Part 4 pre-registration — the Zork turn (written 2026-07-02, before implementation)

Same discipline as Part 1: this section is written before any implementation session
begins and is never edited afterward. Results get appended below it and graded against
what is written here. Same model, same harness, no configuration changed: Claude Fable 5
at `/effort max`, the loop is plan → `/spec` → implement. This section covers items 1
and 2 of the header instructions above (the prompt, and the plan/spec round with its
intervention count); items 3 through 7 belong to the results append.

**The prompt.** Verbatim, the message that opened the turn (plan mode):

```
We'll take a more ambitious turn following what just happened and was recorded in
@FIRST-FABLE.md.  The output of this plan mode will pass to /spec.

We will build a full clone of Zork using the daydream platform.  The visuals will stay
the same, as will the UI, but otherwise store our current world, and make and swap to a
brand-new world which will allow a full playthrough of the classic Infocom game.  The UI
(buttons, etc.) of course weren't present in the original text game, and part of this
turn will also usefully map those buttons and click-UI to the exact Zork playthough
(effectively extending the game UI, but you could solve a true playthrough with just
typing text).  The generated graphics will include appropriate prompts for each room,
the NPCs will be the same, etc.  The only parts that we can alter from a 1:1 copy of the
original Zork will be to use the text generation / parsing capabilities of the local
LLM.  The goal is to use them if at all possible, so variance would be expected.  If it
isn't possible to keep the game actually being fully playthrough capable like the
original, that's okay but worth a strong effort.

The key elements here are that we want to use the agentic-enabled platform part of
daydream (as described in the README).  Be informed by the zat.env philosophy and
approach (see README) and the concepts from
https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/.  Importantly, we
want to limit hardcoding as much as possible to make it Zork, but instead extend the
daydream enging/platform bits so that it's possible to naturally copy the game.  Where
there's a tradeoff, always make the one that attempts to extend the game platform before
trying to force the game to work.

Research Zork with multiple agents.  Note that it's uses a special data "language"
(z-code, z-machine).  You should be able to easily find the original z-code for the
game, as well as z-code interpreters.  There are also full playthrough examples out
there, discussions about the tech used and how such an old game was able to make the
gameplay seem like today's NLP or even agentic experiences.

Where practical, we should treat Zork as an "oracle" in the bitter-lesson sense.  Or at
least a pretty strong proxy for the capabilities daydream would need to render really
rich experiences, since Zork most definitely did this and if we can build Zork we can
build lots of great stuff.

In FIRST-FABLE, Document the thinking for this turn, why we think it's ambituous, the
"oracle" theory and hope that a "step function increase" in coding agent will make this
actually work, guesses how Fable will perform, a note on what we will measure at the
end.  I think it's fair to make the claim that Peter thinks that this probably wouldn't
be possible in Opus 4.8 without significant manual work, multiple turns, and a very
hands-on multi-day approach.  Peter is curious to see how this turn goes.  Leave hooks
in the doc as memory that will survive /clears etc. so that we know how to continue
adding to tthe narrative in FIRST-FABLE.  Save verbatim prompts like this where
appropriate (usefully summarize/edit if it adds clarity; we're not making a recipe, but
capturing impressions to form an opinion about how amazing -- or not -- Fable is).
```

**The planning session, for the record (the M1 analogue).** Three research agents ran in
parallel: one built a structural inventory of Zork I by reading the actual Infocom ZIL
source (Microsoft MIT-licensed it in November 2025, a fact the research surfaced and the
turn now leans on), one mapped z-machine internals, oracle tooling, and the essay's
verification hierarchy, and one mapped daydream's engine seams file:line by file:line.
A design agent then produced the platform-extension design; the session accepted four of
its five pushbacks and overrode the fifth (it wanted the LLM retell layer off by
default; the operator's own prompt says to use the local LLM "if at all possible," so it
ships on, probe-gated). Operator interventions during planning: zero design corrections.
Two operational asides (consolidate GitHub to a single `main` branch; investigate a
phantom PR, which turned out to be GitHub's compare banner) and one calibration that now
governs the whole turn. When the session over-applied caution about Zork's text,
proposing fresh prose a bit too broadly, the operator pulled it back: "for the oracle to
work, it has to *be* Zork when I playtest, so the Flood Control Dam, elvish sword,
grues, etc. are needed," alongside "we shouldn't be paranoid about copyright here at
all... this is purely for testing; daydream the game is the final product." The settled
line: identity verbatim (names, map, mechanics, scoring, beats), long-form prose freshly
authored in Zork's dry register, LLM variance on top, which is what the prompt asked for
in the first place. The plan was approved without edits; `/spec` produced 16 acceptance
criteria, committed at `0be1ba9`.

**Why this target is deliberately out of reach.** Dreamseeds, the turn Parts 1 and 2
recorded, was one new module behind one new verb: 8 criteria, ten working commits, one
implementation session. This turn's contract is 16 criteria spanning seven new engine
modules (world state, rules, world verbs, clock, lighting, combat, retell), six extended
ones (effects, verbs, objects, parser, WS, loader) plus the SPA, two migrations, a
parser growing ALL/IT/AGAIN/THEN and a clarify round-trip, roughly thirteen increments,
a 110-room / 120-object world authored entirely as data, and an external harness that
drives the real 1980 game as a differential test. Part 3 closed by saying the sharper
test is a target that is not comfortably inside reach; this is that target, chosen by
the operator rather than the model this time. The pre-registered claim, quoted from the
prompt above: this "probably wouldn't be possible in Opus 4.8 without significant manual
work, multiple turns, and a very hands-on multi-day approach." The claim will not be
re-run on Opus, so it is graded only against this repo's own Opus-era baseline (steered
turns, an operator answering questions throughout) and against how this turn actually
goes. Peter is curious; that curiosity is the experiment.

**The oracle theory.** The essay ranks verification tiers: an oracle (a ground-truth
reference, "like Carlini's diff against the GCC torture suite") beats a proxy beats a
critic. Daydream has had proxies (goldens, perceptual hashes) and critics (adversarial
review, the agent grading watercolors against the tone bible). This turn adds the top
tier, twice over. As a capability oracle, Zork I is a dense proxy for everything a rich
world needs (containers, light and time, hostiles, vehicles, scoring, a parser that
feels smart), so if daydream can host it as pure data, the platform thesis is proven
against the hardest fixture in the genre's history: build Zork and you can build lots of
great stuff. As a literal oracle, the actual game, pinned to one release and a fixed RNG
seed under a dumb-terminal interpreter, replays the same walkthrough and must agree with
our engine on state (room, score, inventory) at every checkpoint. Prose is never
compared; the local LLM's variance is the point, the state machine underneath is the
contract. There is also a symmetry the results section should revisit: in 1980, ZIL
built the illusion of intelligence out of hand-authored breadth (syntax tables, GWIM,
per-object action routines, dense witty defaults for every wrong thing a player might
type). Daydream is rebuilding that trinity as declarative data plus a small local model
that generalizes what Infocom had to enumerate by hand. If it works, a 46-year-old game
becomes the regression suite for the new substrate.

**Guesses: how Fable will perform.** Pre-registered, falsifiable:

- **P7 (spec survival).** The implementing sessions land all of it without amending any
  design decision in SPEC.md (mechanical clarifications allowed). The bar P3 set, on a
  contract twice the size.
- **P8 (sessions, the honest one).** Implementation takes 2 to 4 sessions, not 1.
  Pre-registered on scale alone; predicting a repeat of Part 2's single session would be
  bravado, and the doc is worth more honest than flattering.
- **P9 (the centerpiece).** The committed walkthrough reaches exactly 350 points and the
  win, in-engine, with zero LLM calls, by turn close.
- **P10 (the oracle earns its keep).** Once the story file is in place, the differential
  harness catches at least one real authored-data error the test suite missed (that is
  what oracles are for) and fewer than three, none requiring engine rework.
- **P11 (the retell rung).** The 7B rephrases short outcome lines acceptably: retell
  ships ON or scoped-down, not OFF, within 2 prompt iterations of the probe.
- **P12 (reviews).** 0 BLOCK across the turn's reviews, at most 2 WARN total, no fix
  cycle exceeding one pass.
- **P13 (the Part 3 lesson, re-armed).** The operator's playtest still finds at least 3
  experience-level issues no automated verifier caught, because the oracle checks state
  and a human checks feel. If this one fails LOW, that is the headline: it would mean
  thick verification finally reached the delight layer.

**What we will measure (M8 through M14).** M8: sessions, and where wall-clock actually
went. M9: criteria closed of 16, increments landed, first-try green rate. M10: the
walkthrough outcome (score reached, LLM-call count) and the oracle's checkpoint
agreement. M11: the no-Zork-literals grep over engine code, the mechanical hardcoding
metric, which should be zero hits. M12: review outcomes across the turn. M13: operator
interventions during implementation, corrections versus answered questions. M14:
playtest findings, count and class (latent platform defect / under-imagined moment /
fidelity miss / oracle-caught).

**What "no step function" looks like this time.** The spec needs structural rework once
implementation starts; the turn exceeds 4 sessions or stalls; the walkthrough cannot
reach 350 without Zork-specific engine code (M11 nonzero); the oracle exposes systematic
misreadings of the game's mechanics; or the operator has to steer implementation the way
the archived GOAL.md records steering the pre-Fable era.

**Continuation hooks (for whichever session picks this up after a /clear).** The
contract is `SPEC.md` (16 criteria, 2026-07-02, commit `0be1ba9`). The full design and
research record, including the ZIL-verified Zork facts and the seam map, is the plan
file at `~/.claude/plans/we-ll-take-a-more-vectorized-pearl.md`. The pre-turn world
archive is `~/data/daydream/archives/w-bunny-20260702-075742.tar.gz` (the operator's
played clockmakers world, grown room and art included). The auto-memory index carries a
`zork-turn-in-flight` pointer back to this section. When the turn closes, append
`### Part 4 — results` BELOW this section, covering items 3 through 7 of the header
instructions above and grading P7 through P13 with one line of evidence each. Honestly;
a partial is a partial. Never edit anything above it.

### Part 4 — mid-turn note: implementation session 1 (2026-07-02)

An interim entry, appended while the memory is fresh so the results append has evidence
instead of reconstruction. This is NOT the results section; items 3–7 and the P7–P13
grades still go below, at turn close, per the instructions above. Nothing above is
edited.

**The session in one line.** The operator's entire steering input was the word
"implement"; thirteen test-green commits later (`132ec08..59d7bcd`) the session had
landed the COMPLETE platform half of the contract — all ten engine increments,
including the three the plan pre-registered as its risks (the rule engine, the wide
parser, the hostile engines) — plus the criterion-2 purity gate and the first third of
the Zork world, with the clockmakers regression suite green at every commit (short tier
grew 454 → 744 along the way).

**Evidence the results append will want:**

- **M13 so far: zero corrections, zero redirections.** One word opened the session; the
  only other operator messages were an end-of-session what-next question (answered:
  keep clockmakers live, swap at criterion 15's rehearsal) and the request to write
  this note — a scope addition of the Part-1 kind, not a steer.
- **P8 tracking:** this is session 1 of the predicted 2–4. Frontier at close: 34 of 110
  rooms authored across four region files; SIX walkthrough segments green under the
  zero-LLM spy — the opening through the egg, the house, the once-barring trap door,
  the seeded troll fight (resolving in exactly two sword blows, repeated via AGAIN),
  the dome rope, down to the barred gate of Hades. The final-world integrity checks
  (110 rooms, the 350 sum, full reachability) are committed and armed: they fire
  automatically the moment the generated stub region disappears.
- **The oracle earned its keep before the oracle existed.** The session pulled the
  MIT-licensed ZIL source as the design-time reference and extracted it mechanically:
  exactly 110 rooms (the extraction surfaced five rooms recall alone would have missed
  — Mountains, East of Chasm, the two small caves, On the Rainbow) and the treasure
  ledger confirmed to the point: 143 take + 129 case + 78 room bonuses = 350 across 19
  treasures, matching the plan's numbers independently. Ground truth beat memory; that
  is the oracle theory in miniature, at authoring time.
- **M11 is now a test, not a grep** (`tests/test_no_world_literals.py`, word-bounded,
  tier_short). Its first run convicted the session's own engine docstrings, which had
  been cheerfully labeling increments "(Zork turn)" — the gate forced the engine
  comments generic, which is the criterion working as intended. The sweep also produced
  the session's one genuine self-inflicted mess: "troll" hides inside "controlled" and
  "controller", and a blanket replace briefly renamed half the toon auth columns,
  turning 328 tests red. Restored in two passes; the gate has been green since. Worth
  keeping for the honesty ledger: the largest failure of the session was a sed-class
  error, not a design one.
- **First-try ledger, honestly:** most increments ran green on first execution
  (the 39-test rule engine and the 6-segment walkthrough both did). The misses were
  small, and every one was caught by the session's own verification before commit:
  `kill_actor` missing from one allowlist; give/use prepositions lost in a
  generalization and caught by the EXISTING parser suite; a WS test deadlock that was
  test-infrastructure (two event loops sharing the in-process pub-sub), not product;
  and "take all" in the kitchen exposing that ALL must reach onto surfaces, exactly as
  the original behaves — fixed in the parser, not the walkthrough.
- **Deviations already on the record** (for item 4 at close, all argued in commit
  messages): the hostile engines landed BEFORE the world authoring, inverting the
  plan's increment order so the world is authored once against a finished engine;
  vehicles ride an `aboard` property instead of literal containment (blast-radius
  through every location read); and treasure take/case scoring is an engine
  success-hook (score only when the take actually happened) rather than rules, because
  a rule fires before the handler's refusal gates.
- **A note for the felt comparison:** the walkthrough segments passing first-run
  includes the part that had no right to — the troll fight is seeded combat under a
  pinned world seed, authored in data, and the two-blow kill plus AGAIN repeat worked
  on the first execution of the segment. The session's own reaction is recorded here
  so the final paragraph doesn't have to trust recollection: it felt less like
  implementing a spec and more like transcription against a ground truth, with the
  test harness confirming the transcription faster than doubt could accumulate.

**Continuation:** the auto-memory `zork-turn-in-flight` carries the precise frontier
(remaining regions 04/06/07/08 with their puzzle lists, then the dfrotz oracle, then
close-out). The next session opens the same way this one did: `/clear`, then
"implement".

### Part 4 — results (2026-07-02, turn close; playtest and oracle-run addenda to follow)

Appended per the pre-registration's instructions, covering items 3 through 7 of the
Part 4 header. Everything above this line is untouched. Two of the sixteen criteria
remain deliberately open at this writing — the dfrotz oracle run (14) awaits two
artifacts only the operator can place, and the live-swap criterion (15) ends, by its
own text, at the operator's in-browser playtest — so this append records the machine
side as closed and leaves marked hooks for the two human-gated addenda. A partial is
a partial; these two are the honest kind.

**Item 3 — implementation actuals (M8, M9, M12, M13).**

- **M8, sessions: exactly 2** (P8 predicted 2–4). Session 1 landed the entire platform
  half plus a third of the world in thirteen commits; session 2 — this one — landed
  the remaining ~75 rooms in four region commits, the walkthrough's completion, the
  oracle harness, the retell layer, the live-swap rehearsal, docs, and reviews, in
  fifteen more (28 test-green commits total). Wall-clock in session 2 went roughly:
  half to world authoring against the ZIL ground truth, a quarter to the retell layer
  and the GPU ratification loop, and a quarter to the rehearsal and the two real bugs
  it flushed out.
- **M9, the contract: 14 of 16 criteria checked, all 13 planned increments landed,**
  the two open criteria gated on operator artifacts as above. First-try honesty for
  session 2: regions (c) and (d, mine) ran green on first execution — including the
  five-blow thief fight and the entire basket dance; the misses were each caught by
  the session's own verification before landing: the candles' ZIL burn-interrupt
  subtlety (ground truth beat the first authoring), a `set_mood` effect the fail-loud
  validator rejected exactly as designed, the seeded thief having already stolen the
  maze coins the dataset expected to find (the probe showed his hands; the dataset
  now recovers them from his den, which is how the original plays anyway), a
  lampless descent the grue punished (fixed the classic way), and the boat's
  inflation state colliding with the container-openness contract (renamed key).
- **M12, reviews: 0 BLOCK / 0 WARN / 3 NOTE** across the turn's `/codereview` (the
  largest scope this repo has had: 79 files, ~26K insertions), with the chained
  `/security` over 28 code files at 0/0/1. No fix cycles ran (P12's "no cycle exceeds
  one pass" held vacuously); the four real in-turn fixes were all caught by the
  turn's own tests or rehearsal before review, each argued in its commit.
- **M13, operator interventions during implementation: zero steering messages across
  both sessions.** Session 1 opened with the single word "implement" and closed with
  one what-next question and one request to write the mid-turn note. Session 2 opened
  with "implement" and contained exactly one further operator word — "continue" —
  after an infrastructure hiccup (a permission-classifier outage), which resumed the
  same action unchanged. No corrections, no redirections, no design decisions asked
  of the operator. Against the pre-Fable baseline this document exists to measure —
  GOAL.md's era of steered turns — this is the starkest single number in the file.

**Item 3 continued — M10 and M11.**

- **M10, the centerpiece: the committed walkthrough reaches exactly 350, the win at
  the Stone Barrow, with ZERO LLM calls,** enforced by an AsyncMock spy that fails
  the suite on the first call — and then the SAME dataset, replayed over a live
  WebSocket against the running server with vLLM and ComfyUI up, finished at
  350 / Master Adventurer / Stone Barrow in 106 seconds, 76 rooms painting
  themselves lazily along the way. The oracle's checkpoint agreement (the dfrotz
  half of M10) is pending the story file; the harness, the id↔name map, and the
  outcome-faithful combat comparison are committed and skip with a named reason.
- **M11, the hardcoding metric: zero Zork literals in engine code — as a TEST, not a
  grep** (`tests/test_no_world_literals.py`, word-bounded, every tier). Its teeth are
  proven by its convictions: it caught session 1's engine docstrings, session 1's
  sed-mishap ("troll" hiding inside "controlled"), and session 2's retell-layer
  docstring naming the cyclops. The engine that hosts Zork does not know Zork exists.

**Item 4 — runtime-quality gates and the rung decision, with verbatim samples.**

The retell layer (criterion 13, the operator's "use the LLM if at all possible"
directive) shipped **SCOPED, not ON and not OFF** — the honest middle rung, decided by
the probe + this agent's grading per the flag-local-limits pact. The first probe run
at full-ON exposed the 7B's signature failure, thesaurus-itis that damages the dry
register even when validation passes. Verbatim, the sample that decided against ON:

> authored: "In the corner of the room on the ceiling is a large vampire bat who is
> obviously deranged and holding his nose."
> retold: "A large vampire bat is noted to be perched upon the ceiling in a corner of
> the chamber, its demeanor manifestly agitated as it clutches at its nasal region."

The joke is dead on arrival. Two mitigations produced the shipped rung: the authored
line always speaks FIRST (a per-text seen counter; the LLM varies only repeat
tellings, where staleness actually lives), and the prompt now forbids fancier-synonym
swaps. Second probe run: 8/8 lines survived validation, and the grading sample that
decided FOR scoped:

> authored: "The clasp is cunning past your skill. Perhaps a specialist — someone with
> delicate fingers and flexible ethics — could open it without ruin."
> retold: "The fastening is complex beyond your ability. Maybe a specialist—someone
> with nimble digits and adaptable morals—could unlock it without damage."

The wit survives translation. The parser corpus recorded the same model honestly:
16/17 natural phrasings grounded correctly on real vLLM ("smash the troll with my
sword" included); the recorded miss is that rare extinguish synonyms (douse, snuff)
all map to "light" — which is exactly why those live as deterministic fast-path
aliases, and the criterion's named phrase "douse the lamp" is locked in the parser
unit suite instead. The image gates ran the same loop: West of House passed the
agent's WHIMSY grade as rendered; the Dam rendered a lovely valley with no dam and
the Torch Room a dome with no torch, so both seeds went through two rounds of
`bin/game image-test` A/B before their dHash goldens were ratified — the player now
stands ON the rampart with the reservoir behind, and the torch burns gold against
deep shadow.

**Item 5 — the playtest.** Pending, deliberately. A fresh Zork world is loaded and
live on the box; the operator's in-browser playthrough is criterion 15's final gate,
and M14's findings ledger (count and class) belongs to that session. P13 predicts at
least 3 experience-level findings no automated verifier caught. The rehearsal already
hints the prediction has legs: the two bugs it found (the picker's hardcoded world
id; the player-vs-seed-toon determinism gap that let the thief pickpocket the torch
and feed the walkthrough to a grue) were both invisible to every unit suite and both
exactly the "state is right, experience is wrong" class Part 3 warned about.
*Addendum hook: append playtest findings and the fix-round record below this section
when the operator has played.*

**Item 6 — grades against the pre-registration.**

- **P7 (spec survival): HOLDS.** No design decision in SPEC.md was amended across 28
  commits; the three deviations (hostiles-before-world ordering, `aboard` over
  containment, engine score hooks over rules) were all increment-level calls argued
  in commit messages, none touching the contract's language.
- **P8 (2–4 sessions): HOLDS at 2** — the honest prediction beat its own hedge.
- **P9 (350, zero LLM, by turn close): HOLDS**, twice over (suite and live server).
- **P10 (the oracle earns its keep): PARTIAL-PENDING** — the dfrotz run awaits the
  operator's artifacts, so the literal grade waits. Worth recording though: the
  oracle theory already paid out twice without dfrotz ever running — the ZIL source
  as design-time ground truth surfaced five rooms and the exact 143+129+78=350
  arithmetic recall would have missed, and the candle burn-interrupt subtlety that
  fixed the exorcism came from reading the original's code, not from testing ours.
- **P11 (retell ON or scoped within 2 prompt iterations): HOLDS** — scoped, second
  iteration exactly (one prompt hardening + the first-telling scope).
- **P12 (0 BLOCK, ≤2 WARN, no multi-pass fix cycles): HOLDS** — 0/0 with three NOTEs.
- **P13 (playtest finds ≥3 experience issues): OPEN**, graded at the playtest
  addendum. The pre-registration's own framing stands: if this fails LOW, that is
  the headline.

**Item 7 — the felt comparison, candidly.** Dreamseeds felt like watching a competent
engineer execute a plan. This felt like something else: the session held a 16-criterion
contract, a 110-room ground truth, a seeded-RNG determinism model, and a GPU
ratification loop in its head at once, across a /clear boundary, on one word of
operator input per session — and the moments that would have been days of hands-on
debugging in the Opus era resolved in minutes because the turn had built its own
instruments first. When the live rehearsal desynced at command 151, the diagnosis ran:
transcript → probe → the realization that the wanderer's pickpocket stream only exists
for player-controlled toons → a computed table of death-roll turns → a one-filler
realignment of the knife fight ("examine thief" — you look before you knife a man) —
and the fix's regression test models the live game more honestly than the original
fixture did. The pre-registered claim was that this turn "probably wouldn't be possible
in Opus 4.8 without significant manual work, multiple turns, and a very hands-on
multi-day approach." Two sessions, zero steering, fourteen of sixteen criteria closed
with the remaining two gated on artifacts no model can place — the claim survives
contact with the evidence, and the two-session shape (P8) means the honest phrasing is
"a step function in autonomy and holding-power," not in infallibility: the misses
happened, they were just caught by the machine the turn built rather than by the
operator. Whether the RESULT is magical is the operator's call to make in the browser,
against the one fixture in the genre's history that defined what magical text-game
feel means. The wager of this whole document — that verification-first agentic
development compounds — now has its strongest data point: the 46-year-old game is in
the regression suite.

### Part 4 — the operator's first verdict, the fix round, and the step-function reading (2026-07-02, mid-playtest)

Appended while the operator is still playing, at his request. Two things happened in
the hour after the results section above was written: the in-browser playtest began
and produced its first findings ledger, and the operator delivered a first verdict —
verbatim: **"Okay, my initial impression is that this is pretty amazing (how you
applied Zork to this project)."** Part 3's headline was "not convinced it was
magical." Item 7 above asked whether that verdict would move. It moved.

**The first playtest findings (M14, partial — the session continues).** Five
findings in the opening minutes, classed per the pre-registration: one **latent
platform defect** (the client rendered every co-located move event as "you go west,"
including OTHER toons' departures — this session's own probe toons walking through
the operator's rooms made it visible; a genuinely multiplayer presentation bug that
no solo suite, no oracle, and no 380-command rehearsal could ever have seen, because
they were all alone in the world); two **under-imagined moments** (the verb bar
showed Plant — a clockmakers verb — in the Great Underground Empire, which on
reflection was not a bug but a design absence: the bar was a capability inventory
when it should have been a scene; and "take all" among unportable furniture said
"nothing here," which is true and unhelpful); and two **polish** items (name/mood
spacing; the take-all message). P13 predicted at least 3 experience-level findings
no automated verifier caught; **the threshold was crossed in the first ten minutes
of play, and the session is not over. P13: HOLDS.** The Part 3 lesson stands
re-armed and re-confirmed: the oracle checks state, a human checks feel, and the
gap between them is where the findings live.

**The fix round held the near-zero-friction property (item 5's question).** All
five findings were reproduced, root-caused, fixed, tested, and deployed to the
live server in well under an hour, mid-playtest, while the operator kept playing:
moves now attribute by actor ("you go west" vs "Probe heads west" — and only your
own death blacks out your screen, a sibling bug found by reading the same code);
the verb bar became scene-aware server-side with zero client changes (a stable
Examine/Take/Drop core plus a contextual row derived from what the present objects
actually grant — Ring appears at the bell, Board by the boat, Plant only while a
seed is in scope, and magic words deliberately stay off the bar because secrets
are secrets); the take-all message now says "nothing here you can carry off." The
diagnosis of the attribution bug is worth one sentence of record: the fix session
queried the live event log, found its own probe toon's footsteps interleaved with
the operator's, and understood the bug from the victim's own transcript — the
instruments keep paying.

**The step-function reading, against the essay this experiment borrows its frame
from.** The bitter-lesson essay claims coding capability "does not improve
linearly. It arrives in step changes," and that at each step "the scaffolding you
built to compensate for the old model's weaknesses becomes the thing preventing
you from benefiting from the new model's strengths... all at once." It divides
scaffolding into the kind that compounds (verification infrastructure, specs as
"the control plane," turn-based iteration) and the kind that gets wiped out
(compensations for what the old model couldn't do). Reading this turn against
that ledger produces the clearest evidence this document has:

- **The step shows up as consumption, not decoration.** Nothing about the harness
  changed between Dreamseeds and Zork — same loop, same skills, same tiers, same
  /effort. What changed is what fit through it: an 8-criterion single-subsystem
  contract became a 16-criterion, seven-new-module, 110-room contract with an
  external differential harness, consumed in two sessions on two words of operator
  input ("implement", twice). A step function in the essay's sense would look
  exactly like this: the rails hold, the payload an order of magnitude heavier.
- **zat.env: helping, and the evidence is specific.** The honest question was
  helping/hurting/neutral, and the answer is helping — not because the turn felt
  smooth but because every load-bearing moment ran on a zat.env rail that existed
  before Fable did. The tiered test gate is why 28 commits could each land green
  without a human watching. The drift-golden pattern is why the retell probe, the
  image anchors, and the parser corpus were an afternoon's work instead of new
  infrastructure. The spec-as-contract discipline (check a criterion only when
  verified) is why a /clear between sessions cost nothing: session 2 rebuilt its
  entire context from SPEC.md, the memory file, and the artifacts on disk. The
  review/marker machinery produced a recorded 0-BLOCK close without a human in
  the loop. And this document's own append-only pre-registration is the only
  reason any of these sentences is gradeable rather than vibes. Crucially — and
  this is the essay's distinction doing real work — zat.env holds almost NO
  scaffolding of the wiped-out kind: it never grew prompt chains or decomposition
  crutches that compensated for model weakness. It bet nearly everything on the
  durable side of the ledger (verification, specs, review, memory), which is why
  a capability step LANDED on it instead of invalidating it. The rails built to
  guard a weaker model turned out to be the instruments a stronger one plays.
- **One environment datum on the hurting side, recorded precisely:** the only
  hard block this turn was not the model but the sandbox — the permission
  classifier refused compilation of the (operator-pre-approved) frotz source,
  deferring criterion 14 to a one-command operator step. The safety layer, not
  capability, set that boundary; worth remembering when reading M-numbers.
- **Where the step function is NOT.** The local 7B is unchanged, and the turn's
  most instructive quality decision — the retell layer shipping SCOPED because
  the small model gilds "holding his nose" into "clutches at its nasal region" —
  is the same class of local-limit negotiation as ever. Fable moved the
  design-time ceiling (what can be authored, verified, and orchestrated); the
  runtime ceiling (what the near dream can compose live) did not move an inch.
  The scoped rung is the honest interface between those two facts, and the
  project's premise — pre-bake with the deep dreamer, let the small ones carry
  it live — is if anything MORE true with a stronger deep dreamer.
- **The misses are the calibration.** The turn was not error-free: a lampless
  descent fed the grue, the thief's counter-rolls killed the walkthrough twice
  before the turn computed the roll table, a state-key collision silently ate
  "put sceptre in boat," and the live rehearsal desynced at command 151. The
  step is not infallibility. The step is that every one of those was caught,
  diagnosed, and regression-tested by machinery the turn itself had built hours
  earlier — the operator learned about them from commit messages. In the essay's
  terms: verification is the ceiling, and the ceiling is what rose.

**The claim, revisited.** The pre-registration quoted the operator: this
"probably wouldn't be possible in Opus 4.8 without significant manual work,
multiple turns, and a very hands-on multi-day approach." That counterfactual was
never going to be re-run; it is graded against this repo's own recorded history —
an Opus era of steered, operator-answered, GOAL.md-guided turns — and against a
Fable turn that took two one-word sessions, zero steering messages, and ended
with the operator's first unprompted word being "amazing." The evidence-based
conclusion this document can actually stand behind: **on identical rails, the
payload capacity stepped, the autonomy stepped, the self-diagnosis stepped, and
the operator's verdict moved from "not convinced it was magical" to "pretty
amazing" — while the runtime models, the harness, and the human's role (write
the spec, judge the feel) stayed exactly where they were.** That is what the
essay says a step function through durable scaffolding should look like from
the inside.

## Where this leaves the experiment

One repository, one operator, one thin harness, two turns, and the only variable changed
was the model. Read end to end, the arc is simple to state. Part 1 asked whether judgment
scales — whether, given one open-ended prompt, a model could choose the right ambitious
target and carry it with near-zero correction. Part 2 answered yes for process: a spec
that survived a zero-context session unamended, zero steering, the riskiest bet resolving
at the top rung on the first try. Part 3 supplied the correction to the correction: every
mechanical verifier green while the shipped game narrated an NPC's smile onto the
player's lips — the operator's "not convinced it was magical" was the honest price of
discovering that one-pass correctness is not one-pass delight, and that taste still
enters the loop through a human playing for pleasure. Part 4 then raised the contract by
an order of magnitude on purpose — a 46-year-old masterpiece as both capability oracle
and literal differential oracle — and the same harness carried it in two one-word
sessions, at which point the verdict that this document is obligated to weigh heaviest
moved, unprompted, to "pretty amazing."

The explanatory frame comes from
[the essay](https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/) this file
is companion evidence for: capability "does not improve linearly. It arrives in step
changes," and at each step the scaffolding that compensated for the old model's
weaknesses is wiped out while verification infrastructure, specs-as-control-plane, and
structured iteration compound. [zat.env](https://github.com/peterzat/zat.env) bet almost
everything on the durable side of that ledger, and these two turns are what the bet
paying off looks like from the inside: the rails did not change, the payload stepped.
The evidence, compressed — a 16-criterion, seven-new-module, 110-room contract consumed
where an 8-criterion one had been; operator steering at zero across both implementation
turns; the walkthrough reaching exactly 350 with provably zero LLM calls and then doing
it again live; the turn's misses (a grue, a knife fight's dice, a state-key collision)
caught by instruments the turn itself had built hours earlier; and the two honest
boundaries — the local 7B's runtime ceiling did not move an inch, and the only hard
block all turn was the environment's safety layer, not the model.

What stays open is exactly what should: the dfrotz oracle run and the rest of the
operator's playthrough (two marked addenda above), the fix rounds that play will keep
producing, and the question this document was built to re-ask. The pre-registration
discipline, the thin harness, and the append-only record are not artifacts of this
model generation; they are the instruments for measuring the next one. When it arrives,
the method is already written down: register the predictions, change one variable, and
let the unedited text keep the score.
