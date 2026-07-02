# FIRST-FABLE.md — the first Fable session, pre-registered

This file records daydream's first-ever session with **Claude Fable 5**, run on 2026-07-02
as a deliberate experiment: same repository, same operator, same thin harness, one variable
changed (the model). It is written in two parts. Part 1 (this section, written at the
session's natural break point) captures what happened, what we are measuring, and what we
predict, before the results exist. Part 2 gets appended after the implementation turn and
grades the predictions against what actually happened. Part 1 is never edited after the
fact; that discipline is the point.

It is companion evidence for
[The Bitter Lesson of Agentic Coding](https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/)
and its reference harness, [zat.env](https://github.com/peterzat/zat.env). If you arrived
from the essay: **daydream** is the project under test, a small atmospheric multiplayer web
game (a cozy watercolor world with MUD-style verbs) whose live generation runs entirely on
one 20 GB local GPU, built one spec-reviewed increment at a time. The [README](README.md)
has the full picture.

## The timing

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

## The experiment

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

## The opening prompt

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

## What happened (Part 1: plan and spec)

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

## What we are measuring

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

## Predictions

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

## State at the break

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

## Part 2 — to be written after the implementation turn

*Instructions to the session (or human) that continues this document. Append below this
section; never edit anything above it. Part 1 is a pre-registration, and its value is
exactly that it was not revised after the results came in (the same discipline
`docs/history/GOAL.md` used).*

After the Dreamseeds increment closes (all criteria checked or the turn abandoned, reviews
recorded), append a `## Part 2 — results` section covering:

1. **Git evidence:** start and end commits, `git log --oneline` for the turn, final
   SPEC_META line.
2. **M1-M7 actuals**, each with one line of evidence (commit hashes, review footers, test
   output). For M1, count operator messages in the implement session that corrected or
   redirected, versus answered questions.
3. **P1-P6 grades:** ✓ / ✗ / partial, one sentence of evidence each. Grade honestly;
   a partial is a partial.
4. **Deviations:** anything the implementation changed from SPEC.md or the plan, however
   small, and why.
5. **The rung decision:** which rung shipped, probe results (validity, phrase-woven,
   distinctness), how many prompt iterations, and 2-3 verbatim samples of grown-room prose
   with the agent's WHIMSY grading.
6. **Surprises**, both directions: things that went better than the baseline led us to
   expect, and things that did not.
7. **The felt comparison:** one candid paragraph, written for the bitter-lesson post's
   readers, comparing this turn's experience against the Opus 4.8 turns recorded in this
   repository's history. Was it a step function? Where exactly did it show, and where
   didn't it?

Keep the register of this file: plain, specific, storytelling over checklist where the two
conflict. If the implement turn spans multiple sessions, say so plainly in M7 and grade P4
accordingly.

## Part 2 — results

Written 2026-07-02, at the close of the implementation turn, by the implementing session.
Part 1 above is untouched.

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
