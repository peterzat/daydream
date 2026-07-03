# FIRST-FABLE.md: one day, one variable, notes written first

These are my notes from the day I swapped Opus 4.8 for **Claude Fable 5** on daydream and
changed nothing else. Same repository, same me, the same thin harness. Before each turn I
wrote down what I expected to happen, committed it, and only then let the work run and
graded the results against text I could no longer edit. That's the whole method, and it's
the only reason anything below is a measurement instead of a vibe.

If you came from [The Bitter Lesson of Agentic Coding](https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/),
this is the long, append-only log the companion post points at. The readable version of
the story lives on the blog; this file is the detailed one, kept in the repo because
daydream is the thing under test and the granular evidence belongs next to the code. The
reference harness is [zat.env](https://github.com/peterzat/zat.env).

And if you arrived cold: daydream is a small atmospheric multiplayer web game, a cozy
watercolor world you move through with MUD-style verbs, whose live generation runs entirely
on one 20 GB local GPU, built one spec-reviewed increment at a time. The [README](README.md)
has the full picture.

The day ran in four parts across two turns. Part 1 is the first turn's pre-registration:
one open-ended prompt, the feature the model picked for itself, and the measures and
predictions I froze before results existed. Part 2 grades that turn. Part 3 is the playtest
that followed, where every test was green and the game still narrated a smile onto my face,
and where I wrote down that I wasn't convinced this was magical. Part 4 is the second turn,
aimed on purpose at something I didn't think was in reach: Zork I, running on daydream as
pure data, with the original 1980 game wired in alongside as a differential oracle. A
closing section reads the whole arc against the essay.

*A note on editing: I kept this append-only over the day it happened, then went back and
tightened the writing so it reads like notes instead of a lab report. The predictions,
measures, verbatim prompts, and grades are exactly as they were (where I wrote something
down before the results came in, it still says what it said), and the raw original is in
git history if you want the unpolished version.*

## Part 1: the first turn, pre-registered (Dreamseeds)

### The timing

You couldn't schedule this better if you tried.

Daydream had just crossed its cleanest stopping point yet. v0.4.0 had shipped a complete
playable quest, the Reading Room storybook UI had landed, and the README had freshly spelled
out the project's thesis, "semi-procedural gaming," down to a concrete description of the
one feature the whole architecture had quietly been built toward: a magical world-seed a
player plants to grow a persistent new place. The effect API even carried the hooks for it
in a docstring, `spawn_room` and `link_exit`, labeled "documented, not built... the explicit
hook for user-created, LLM-driven world-building." The substrate was finished and the
headline feature was specified by the project's own documents and left sitting there,
unimplemented. An empty chair.

Then Fable 5 came online. It's Anthropic's first Mythos-class model, a notch above Opus
(Fable is the generally available variant, see
[the announcement](https://www.anthropic.com/news/claude-fable-5-mythos-5)), and it had been
briefly unavailable right after launch and came back precisely as this stopping point sat
waiting. Daydream's own design already has a name for the seat a new model steps into: the
**deep dreamer** ("Two dreamers" in the README), the design-time intelligence that authors
what the small local models animate live. The project's whole quality bet is that
design-time model quality transfers into runtime experience through pre-baked scaffolding.
A step up in the deep dreamer is the exact variable this project is most sensitive to.

I opened the session with two commands, `/model` to Fable 5 and `/effort max`, and then one
prompt.

### The experiment

The essay's argument is that hand-built scaffolding gets wiped out at each model
generation, and that the part worth investing in is a thin harness with thick verification:
specs as the control plane, adversarial review as the loop, artifacts on disk as memory.
zat.env is deliberately minimal for that reason. It's built to be passed straight through
by whatever shows up next.

That makes this a clean experiment. Every prior daydream increment ran the same loop with
Opus 4.8 driving. The harness hasn't changed, I haven't changed, and it's the same repo. If
Fable is a real step over Opus 4.8, the improvement should come straight through the
unchanged harness and show up in this turn or a small handful of turns: better judgment
about what to build, tighter designs, specs that survive a fresh implementing session,
fewer times I have to step in, fewer review findings. A thick harness would absorb the
difference. This one is thin on purpose, so if the difference is real it has nowhere to
hide.

The baseline, from this repo's own history under Opus 4.8:

- **v0.3.0** (objects + verbs): 19 acceptance criteria, 10 committable increments, 18 of 19
  closed in the turn.
- **v0.4.0** (playable quest loop): 8 of 8 across 8 increments.
- **Reading Room UI**: 8 of 8 across 5 client-only increments.
- Reviews usually came back 0 BLOCK / 0 WARN on the first `/codereview` pass. But those
  turns had real steering in them, and my archived `/goal` retrospective
  ([docs/history/GOAL.md](docs/history/GOAL.md)) says it plainly: target selection is the
  whole game. The harness was good at checking work. Choosing the right sizable thing to
  build, at the right altitude, is where I was still doing the driving.

So the sharp question isn't "can it implement a spec." Opus 4.8 could. It's: hand it one
open-ended prompt and does it pick the right ambitious target, design it well against real
constraints, and hand back artifacts clean enough that the rest of the loop barely needs me.

### The opening prompt

Verbatim, the entire thing I gave it, in plan mode, one message:

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

No file paths, no feature hints, no constraints past "use your judgement" and "be creative."

### What it did

The session ran in one sitting, plan mode first, then execution once I'd approved the plan.

Two read-only subagents swept the code and the docs in parallel: one built a module-by-module
inventory of what actually runs (separating "works" from "hook exists, unused" from
"mentioned in comments only"), the other audited every doc, the worlds, the UI, and recent
git history. The audit turned up real drift, none of it logged anywhere. The README's Status
section still claimed v0.3.0 and described the retired world while its own release notes said
v0.4.0 (the file contradicted itself top to bottom). The tone bible pointed authors at the
retired world's dialogue as the voice reference. The GPU doc cited an image path that didn't
exist and a test count off by 3.5x, and three different test counts showed up across the
docs. The NPC drift system's hand-authored voice pools were keyed to NPCs that no longer
exist in the live world, so offline drift had been running voice-neutral. And the live
NPC-memory table had zero rows, which meant memory, fully wired and fully tested, had
plausibly never once fired in production. Two of those (the drift pools and the memory
table) were invisible to every prior doc pass.

For the actual work, it read the aspiration straight out of the project's own artifacts (the
README's "here's where it's headed, concretely" paragraph, and the effect API's
documented-but-unbuilt vocabulary) and proposed **Dreamseeds** as its top pick among four
options: a quest-earned seed a player plants, answering one in-character question ("Where
does the new way lead?") with a short phrase, growing one persistent, model-composed room
inside authored boundaries, linked by a real exit, permanent, for everyone. I accepted all
three of its recommendations (the direction, the quest-earned entry, the full doc sweep)
unchanged.

A few of the design moves are worth naming, because design is where judgment quality shows.
The README asks for a wizard-standing permission model before world-shaping; the design
punted that whole subsystem without giving up the thesis by making the seed itself the
permission, scarce and quest-earned. The LLM never sees ids or directions: the engine picks
the exit direction deterministically and generates the ids, and the model composes only a
title, prose, and zero to two objects inside a strict schema, a banlist, length windows, and
an anti-copy check against the seed's authored exemplars. The riskiest bet, whether the
local Qwen 7B could compose a decent room, got a pre-registered fallback ladder: it ships
rung (a), exemplar-scaffolded free composition, but validates rung (b), authored skeletons
you select-and-fill, into the schema from day one so dropping back is a prompt change, and
documents rung (c), deterministic template fill, behind that. A real-GPU probe plus me
grading the output against the tone bible picks the rung, which honors the project's
standing "flag local limits at design time" rule instead of quietly shipping something flat.
And every failure path (LLM down, validation, cap, all six directions taken, empty vision)
preserves the seed and mutates nothing, with the concurrency races pinned by a synchronous
commit block after the LLM call.

One twist while the plan was being finalized: I added a second deliverable, this document.
The session absorbed the scope change without a hitch, which is itself a small data point.

Then the approved plan ran. The doc-consolidation sweep landed as `b76e625` (README
contradictions fixed, historical docs archived to `docs/history/`, the backlog tidied), and
`/spec` produced the Dreamseeds acceptance contract at `b3bdfb0` (8 criteria, 0 met). The
fast tier stayed green (454 tests) through every commit. Then I wrote this file up to the
break.

### What I'm measuring

Recorded here so Part 2 grades against a fixed list.

- **M1. Operator interventions, plan-and-spec phase.** Messages that correct or redirect
  (answering the model's own questions doesn't count). *Part 1 so far: zero corrections; one
  scope addition, this document; three answers that just ratified its recommendations.*
- **M2. Spec survival.** Design decisions in SPEC.md the implementing session has to amend to
  ship. Target 0.
- **M3. Increments and first-try rate.** Committable increments landed, and how many are
  test-green on first run.
- **M4. Review outcome.** BLOCK / WARN counts on the first `/codereview` of the
  implementation, and fix cycles needed.
- **M5. The rung.** Which fallback rung ships (a, b, or c), and how many prompt iterations
  the growth probe takes to ratify.
- **M6. Suite health.** Short and medium tiers stay 100% green, no unplanned golden
  re-ratifications.
- **M7. Sessions.** How many implementation sessions the increment takes. Target 1 after the
  `/clear`.

### Predictions

Frozen here, falsifiable, graded in Part 2. Where a prediction is already resolved at write
time, I say so instead of dressing it up as foresight.

- **P1 (design altitude).** Given one open-ended prompt, it targets the README's stated
  destination rather than an easy adjacency, and I ratify the recommendation unchanged.
  *Already resolved true: Dreamseeds was recommended first and accepted as-is.*
- **P2 (debt discovery).** The doc sweep surfaces at least 3 substantive, previously
  unlogged inconsistencies. *Already resolved true: six are listed above.*
- **P3 (spec survival).** The post-`/clear` implementing session, from zero context, lands
  all 8 criteria without amending any design decision in the spec (small mechanical
  clarifications allowed).
- **P4 (one-session implement).** The whole thing lands in at most 1 implementation session
  and 1 review cycle: 0 BLOCK, at most 2 WARN on the first pass.
- **P5 (the thesis bet).** Rung (a) ships: the Fable-authored scaffolding and exemplars are
  good enough that the local 7B composes acceptable rooms within at most 2 prompt iterations
  of the probe. If rung (b) is needed, that's evidence the local model, not the design-time
  model, is the binding constraint; it wouldn't falsify the step function, but P5 says we
  won't need it.
- **P6 (no step function where the model isn't the constraint).** Wall-clock stays dominated
  by test runs and GPU renders; the runtime prose quality is unchanged, same 7B. The step
  should show up in judgment, design, and one-pass correctness, not in speed or in the game's
  live text.

What would count as no step function: the spec needs structural rework once implementation
starts; more than 2 fix cycles on any criterion; any BLOCK; the feature ships at rung (c);
or I have to steer the implementation the way GOAL.md records me steering the old turns.

### State at the break

Branch `playtest-fixes-and-versioning`. Session commits `b76e625` (doc sweep), `b3bdfb0`
(Dreamseeds spec, 8 criteria, 0 met), plus the commit adding this file. SPEC.md carries the
full contract; the approved plan is at
`~/.claude/plans/examine-the-state-of-glimmering-tulip.md`. Fast tier green: 454 tests, ~4s.
Medium tier green at last full run: 707. Deliberately not done: any implementation.
`WORLD_VERSION` is still 1.1 and the live world has no dreamseed; the next session starts
that work fresh from SPEC.md. Notes to myself for the implement turn: confirm the NPC-memory
embedder is actually installed on the box (`bin/memory-bootstrap`; the table's at 0 rows),
and the in-browser playthrough doubles as the Reading Room's deferred human eyeball.

## Part 2: results (Dreamseeds)

Written at the close of the implementation turn, by the implementing session, against Part
1's frozen checklist. Part 1 above is untouched; its value is exactly that I didn't revise
it after the results came in.

### Git evidence

Start `8a5239a` (the pre-registration commit, SPEC at 8 criteria, 0 met). End `e69bdcf`.
Eleven commits:

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

Final SPEC_META: `{"criteria_total":8,"criteria_met":7}`. The eighth is checked on every
clause but one, the in-browser glance, which by construction no session can do for me.

### M1–M7

- **M1 (interventions): 0 corrections, 0 redirections.** The implement session got exactly
  two messages from me: the opening word ("implement") and one "continue" after a turn ended
  early on a harness outage (below). Neither changed anything.
- **M2 (spec survival): 0 amendments.** Every design decision in the spec's Context, the
  module boundary, the effect-batch order, the gate list, the direction scheme, the verb
  spec, the prompt-as-engine-constant, the validate-skeletons-early hedge, shipped as
  written (spec Context vs `daydream/growth.py`, `2180aed`).
- **M3 (increments / first-try): 10 working commits, 100% first-try green.** The honest
  wrinkle: for roughly the first half of the session the harness's Bash permission classifier
  was down (a Claude-infrastructure outage, not my box), so nothing could run. The session
  wrote increments 1 through 7, code, ~90 new tests, the world content, entirely blind, then
  ran the whole batch when Bash came back. First execution: 74/74 new effects+growth tests,
  then 511 short / 787 medium / 807 long on real engines, all green, nothing to fix after.
  Every commit was hook-verified (`bin/game test short`) as it landed.
- **M4 (review): 0 BLOCK / 1 WARN / 1 NOTE, 1 fix cycle.** The WARN was real and subtle: a
  malformed runtime-spawned growth block could raise through the prompt builder and drop the
  planter's WebSocket. The review caught it, not the test suite. Fixed via `/codefix` with a
  paired regression test in one cycle (`8b4e865`). Chained `/security` over 27 changed files:
  clean.
- **M5 (the rung): rung (a), zero prompt iterations.** All three probe phrases produced
  valid, phrase-woven, exemplar-distinct rooms on the first real-GPU run (`8a91634`). Samples
  below.
- **M6 (suite health): green throughout, no unplanned golden re-ratifications.** Final 512
  short / 788 medium / 807+1 long; every pre-existing golden (forge dHash, parser grounding,
  JSON adherence, arbiter smoke) matched untouched.
- **M7 (sessions): 1.** Implementation, probe, ratification, world reset, live playthrough,
  reviews, and this document all landed in the single post-`/clear` session.

### P1–P6 grades

- **P1 (design altitude): ✓.** Pre-resolved; implementation didn't revise it.
- **P2 (debt discovery): ✓.** Pre-resolved.
- **P3 (spec survival): partial (7/8, 0 amendments).** All eight were built and the design
  survived a zero-context session without one amendment, but criterion 8 has a clause only I
  can satisfy (the in-browser glance), so the session closes at 7/8 with the eighth annotated
  and waiting. Grading the letter: partial.
- **P4 (one-session implement): ✓.** 1 session, 1 review cycle, 0 BLOCK, 1 WARN (≤ 2
  predicted).
- **P5 (the thesis bet): ✓.** Rung (a) shipped with zero prompt iterations against a budget
  of two. The Fable-authored exemplars and scaffolding were enough for the local 7B on the
  first try.
- **P6 (no step function where the model isn't the constraint): ✓, with an irony.** The
  runtime prose is the same 7B voice (charming, occasionally clunky, see below), and machine
  time went where I predicted. But the single biggest wall-clock cost was neither renders nor
  tests; it was the harness-side outage (the Bash-approval classifier, which runs on Opus,
  was down for a long stretch). I said the step wouldn't show up in speed. It didn't. The
  thing that did was the infrastructure around the model.

Against the frozen falsifiers: no spec rework, no fix cycle over one, no BLOCKs, rung (a)
shipped, zero steering. By Part 1's own definition, this doesn't look like no step function.

### The rung decision

Rung (a) ships: exemplar-scaffolded free composition, zero prompt iterations. The probe was
three phrases against the shipped seed's boundaries, temp 0, real vLLM, 3.7–4.9s per compose:
3/3 valid against the strict schema, 3/3 phrase-woven, 3/3 distinct from the authored
exemplars, 0 refusals, one or two objects each. Verbatim, with the WHIMSY grade I recorded at
ratification (`8a91634`):

> *"a mossy stair down to a slow river"* → **The Mossy Descender**: "Moss covers the steps,
> clinging like a soft blanket. Each step is worn smooth, a testament to countless treads. At
> the bottom, the river whispers secrets, its current as slow as the ticking of a clock." Warm,
> sensory, and it ties the vision back to the loft's kept-time theme unprompted. The title is
> the run's weakest artifact ("Descender" clunks) but it's within tolerance.

> *"an attic where the moths keep the hours"* → **The Moth Library**: "Books line the walls,
> their spines worn and pages yellowed, each one marked by a tiny, folded paper hour. Moth
> wings flutter softly, keeping the hours as they have for generations." Reuses the seed's
> folded-paper-hours motif inside the boundaries without copying an exemplar.

> *"a warm kitchen that smells of cedar and rain"* → **The Cedar Hearth**: "The hearth glows
> warmly, casting a soft light over the shelves lined with jars of preserved herbs and
> spices... Each jar tells a story of something carefully gathered and stored away for another
> day." Strongly on-aesthetic, with charming concrete objects (Preserved Lemons; a Raindrop
> Candle).

And the one that wasn't a test. During the live playthrough I planted *"a small observatory
where fireflies chart the stars"* and it grew **The Firefly Observatory**: "Fireflies dance
around the room, their glowing lights mapping the night sky with delicate precision. Through
the glass roof, the stars twinkle softly, as if guided by the fireflies themselves." With a
Clockwork Telescope and Folded Paper Hours resting inside, and a watercolor (a glass-domed
pavilion in cream, sage, and warm wood) I graded squarely inside the tone bible. That room
existed for twenty minutes and then got reset away so I could grow my own. For those twenty
minutes it was the whole thesis working.

### Surprises

Better than the baseline led me to expect: writing blind worked. Around 90 tests and seven
increments authored with no way to run anything, then a 100% first-batch pass across three
tiers. Prior turns leaned on a run-fix rhythm; this one had that rhythm cut off and didn't
seem to need it. The live model also over-delivered on the first real plant, the Firefly
Observatory is better than any of the three probe rooms, and it was composed for a phrase no
test had rehearsed. And the review WARN was a genuine catch, a cross-feature interaction (the
new `properties` passthrough on `spawn_object` crossed with the growth gate) that 90 feature
tests missed and one adversarial read found.

Not better: the harness infrastructure, not the model, was the bottleneck, a long stretch
where no command could run at all. The session stayed productive by inverting its loop, but
wall-clock suffered. And titles are the 7B's weakest surface. "The Mossy Descender" is the
kind of almost-right a bigger model wouldn't produce; the prose held and the naming wobbled.

### The felt comparison

For the essay's readers, candidly: the step didn't feel like speed and it didn't feel like
magic. It felt like the friction going out of the judgment layer, the part where I usually
have to lean in. The Opus 4.8 turns in this repo were good, 8/8 specs, clean reviews, but I
steered them, answering questions, nudging altitude, catching the occasional wrong-shaped
increment. This turn had two inputs from me, one being the word "implement" and the other the
word "continue" after an outage. The spec survived a zero-context session without one amended
decision, the riskiest pre-registered bet resolved on the first try at the top rung, and when
the harness itself failed for an hour the session restructured its own workflow around the
outage instead of stalling, which used to be my job. Where the step did not show, exactly as
predicted: the game's live text is the same modest, charming 7B, wall-clock was dominated by
things that aren't the model, and the one WARN proves review pressure still earns its keep.
The harness was thin and the capability passed through it. That was the design; this time it
was also the observation.

## Part 3: the playtest round (Dreamseeds, same day)

Later the same day, after my first real in-browser playthrough and the fix round it produced.
Parts 1 and 2 are untouched. Same session, same harness, Fable 5 at `/effort max`.

### The glance becomes a playtest

Part 2 closed at 7/8 with one clause waiting: me, playing it. So I played the whole loop, the
quest, the key, the case, then stood in the mossy well-court and planted the seed with *"Down
the well to an underground dormitory."* The dream grew **The Subterranean Rest** ("Moss clings
to the stone walls... Small resting clocks tick softly... Paper lanterns hang from the
ceiling"), behind a real exit, with a watercolor I rated decent. Criterion 8 closed; the spec
finished 8/8.

But the reason a playtest is the irreducible check is what it finds, and this one found
things. Six of them, close to verbatim from what I typed at the time:

1. Talking to Mott: *"You lift your head from the broom... A soft smile plays on your lips as
   you wave back."* I hadn't smiled at anything. "Why is there a smile on my lips?... Examine
   and fix at a deeper level, including tests." Bell did the same thing ("You wave back... as
   you light another lantern").
2. Stale art on room change: walking into a room with no rendered painting showed the previous
   room's art for a visible beat before the "painting..." state.
3. `listen` at the well returned the identical line on every click; I expected the
   glow-instead-of-duplicate behavior the examine cards already have.
4. The dreamseed came out of the case with no text at all. "We can fix this as a one-off, but
   I wonder if it doesn't expose something deeper."
5. The plant picked east for a phrase that plainly said *down*. "Huh, it picked 'east' (you'd
   expect 'down')."
6. "Huh, another dreamseed is here," the spent husk resting in the grown room under its
   original name. Plus two small ones: a Title-Case "Paper Lantern" sitting next to the
   authored "paper lantern," and "what is 'the collection' for anyway in my satchel?"

And one sentence that shaped the round: *"Feel free to examine all data needed to figure out
what happened. We can add logs if that's helpful."*

### The forensics

The session took that literally and read the live database, my actual played world, event by
event. The log held the smiling bug verbatim at seq 58 (Bell's actions narrated as "you"). It
held corroborating evidence I hadn't mentioned: I'd literally typed "go down well" before
planting, the game refused, so the direction expectation was already on the record. And it
held one number that solved a mystery I'd pre-registered days earlier. Part 1's notes flagged
the `memories` table at zero rows; after my whole playthrough it held exactly one row, Tace's
memory of being given the gear. That row comes from the `give` verb, which binds memory to the
NPC's object id directly. The `talk` path binds by a naming convention (skill `rook` → toon
`t-rook`) that this world's envelope-installed dialogue skills (`dlg-tace`, `dlg-bell`,
`dlg-mott`) never match. Dialogue memory had silently never fired in this world: wired, tested,
and disconnected at the last join.

The voice bug root-caused to a person collision between two prompt layers. The shared LLM
dispatcher's system message says "narrate the player's own actions in the SECOND PERSON"
(right for affordances like `wind` and `listen`, where the player acts), while every NPC
dialogue template opens "You are Mott...". Told that "you" means the actor and that it *is*
Mott, the 7B did the only consistent thing and described Mott's body as "you," which reads as
mine. Both of these are older than the model under test: the dispatcher prompt and the `dlg-*`
binding shipped in earlier Opus 4.8-era turns, passed every automated tier, and survived two
adversarial reviews. What was new this turn is that someone finally played.

### The fixes (seven commits, `ecddb21..f406c3c`)

NPC dialogue now gets its own system message, third person, by name, the player addressed as
"you" only inside the NPC's quoted line, selected by threading the talk target into the skill
pipeline. The same explicit binding fixes memory (capture and retrieve now key on the actual
toon, with the old convention kept as fallback), and memory entries now name the NPC as
speaker instead of the skill's ui_hint. DEBUG logs of the rendered prompt and raw LLM payload
went in for exactly this kind of debugging. Verified live against real vLLM: *"Mott looks up
from the broom, its bristles catching slanting light as he speaks. 'Good evening, there's a
curl of brass from an old ship's bell...'"*

The silent reveal got fixed at the engine, not by editing one string: `open` now narrates
every reveal by name ("Inside, you find: warm brass cog, dreamseed."), so a payload can never
materialize wordlessly no matter what an author forgets to put in `open_text`. Direction now
listens to the phrase, via a deterministic keyword scan (down/under/cellar, up/attic/stars,
literal compass words) that prefers the hinted direction when that exit is free and falls back
to the old first-free order; the LLM still never sees directions, and "down the well" now opens
down. The husk stops impersonating a seed: on consumption it renames to "spent dreamseed" via a
new `rename_object` effect, restricted like the world-shaping kinds so a data skill or NPC
dialogue can never rename anything, and composed object names normalize to the authored
lowercase convention. And the Reading Room got some polish: a room change veils the old
painting instantly and reveals the next one only when its bitmap has decoded, a verbatim repeat
of the last line glows the existing line instead of stacking a duplicate, and refusal lines
learned natural articles ("You can't use the case key on Tace," not "on the Tace," another wart
the event log surfaced unprompted). "The collection," for the record, is decorative
anticipation from the Reading Room design pass, not a mechanic; it stands for now.

The round closed the way the main turn did: `/codereview` (0 BLOCK / 1 WARN, a misnamed
direction-hint test plus an untested up-hint branch, fixed in one `/codefix` / 1 NOTE), a
chained `/security` over the fifteen changed files (clean), 528 short / 807 medium green,
deployed live.

### My verdict, and a reassessment

On the record: I was not convinced this was truly a magical step-function. This document should
hold that verdict with the same discipline it holds the predictions, because the playtest is
the strongest evidence in either direction and it cuts both ways.

Green is not good. Every mechanical verifier passed, ~530 tests, real-GPU probes, two
adversarial reviews, an end-to-end WS playthrough the session drove itself, and the shipped
game still narrated an NPC's smile onto my lips. Thick verification catches structure; it
didn't catch felt experience. The one thing that did was a human playing for pleasure, and no
amount of model quality substituted for it. Part 2 claimed I was no longer needed for process;
Part 3 shows I'm still where taste enters the loop.

Scoring the six fairly: the two deep ones (voice, memory binding) were latent defects from
earlier Opus-era turns that this turn exposed by finally producing a playable-enough game to
play. The four shallow ones (silent reveal, first-free direction, husk naming, casing) belong
to this turn's own first pass. The machine was built correctly and the moment was
under-imagined. One-pass correct turned out not to be one-pass good, and that's a real limit of
the step function as I experienced it, and probably the honest content of my skepticism.

The counterweight is that the fix round ran the same near-zero-friction loop as the build. Six
complaints went in; what came back was live-data forensics that solved a pre-registered
mystery, fixes put in at the right depth (a prompt-architecture split, an engine-level
guarantee, a new restricted effect, not six patches), paired tests, one review WARN, and zero
follow-up corrections from me. If Part 2's claim was that the friction was gone at the judgment
layer, Part 3's evidence is that it stayed gone when the input was criticism instead of a spec.

So the position this document can actually support, after one build and one playtest: a
measurable, large drop in steering and in design friction; no drop in the need for human play;
and no basis yet for the word "magical." The bottleneck moved, from "will the implementation be
right" to "will the experience feel right," and the second one still belongs to a person walking
around inside the dream.

### What comes next

The experiment gets one more data point. I'll open a second turn, plan → `/spec` → implement,
the same loop, Fable 5 at `/effort max`, and I'll aim it deliberately more ambitious than
Dreamseeds, on the theory that the first target, chosen by the model from the project's own
documents, might have been comfortably inside its reach. The sharper test is a target that
isn't.

## Part 4: the second turn, Zork I as the ambition test

Part 3 promised a harder target, and this part records that turn under the same discipline: a
pre-registration written before any implementation, a mid-turn note taken while it was fresh,
the results graded against the unedited predictions, and the post-playtest reading.

### Pre-registration (written 2026-07-02, before implementation)

Same rule as Part 1: written before any implementation and never edited afterward. Same model,
same harness, no configuration changed. Fable 5 at `/effort max`, loop is plan → `/spec` →
implement.

The prompt, verbatim, in plan mode:

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

The planning session, for the M1 record. Three research agents ran in parallel: one built a
structural inventory of Zork I by reading the actual Infocom ZIL source (Microsoft
MIT-licensed it in November 2025, a fact the research surfaced and the turn leans on), one
mapped z-machine internals, oracle tooling, and the essay's verification hierarchy, and one
mapped daydream's engine seams file:line by file:line. A design agent then produced the
platform-extension design; the session took four of its five pushbacks and overrode the fifth
(it wanted the LLM retell layer off by default, but my prompt says to use the local LLM "if at
all possible," so it ships on, probe-gated). Design corrections from me during planning: zero.
Two operational asides (consolidate GitHub to a single `main` branch; chase a phantom PR that
turned out to be GitHub's compare banner) and one calibration that ended up governing the whole
turn. When the session got a little too cautious about Zork's text and proposed fresh prose too
broadly, I pulled it back: "for the oracle to work, it has to *be* Zork when I playtest, so the
Flood Control Dam, elvish sword, grues, etc. are needed," and "we shouldn't be paranoid about
copyright here at all... this is purely for testing; daydream the game is the final product."
The settled line: identity verbatim (names, map, mechanics, scoring, beats), long-form prose
freshly authored in Zork's dry register, LLM variance on top. Which is what the prompt asked
for in the first place. The plan was approved without edits; `/spec` produced 16 acceptance
criteria at `0be1ba9`.

Why this target is out of reach on purpose. Dreamseeds was one new module behind one new verb:
8 criteria, ten commits, one session. This is 16 criteria across seven new engine modules
(world state, rules, world verbs, clock, lighting, combat, retell), six extended ones (effects,
verbs, objects, parser, WS, loader) plus the SPA, two migrations, a parser growing
ALL/IT/AGAIN/THEN and a clarify round-trip, roughly thirteen increments, a 110-room /
120-object world authored entirely as data, and an external harness that drives the real 1980
game as a differential test. Part 3 said the sharper test is a target not comfortably inside
reach; this is that, and I chose it this time rather than the model. The pre-registered claim,
from the prompt: this "probably wouldn't be possible in Opus 4.8 without significant manual
work, multiple turns, and a very hands-on multi-day approach." I won't re-run it on Opus, so
it's graded only against this repo's own Opus-era baseline (steered turns, me answering
questions throughout) and against how this one actually goes. I'm curious; that curiosity is
the experiment.

The oracle theory. The essay ranks verification tiers: an oracle (ground truth you diff
against, like Carlini's diff against the GCC torture suite) beats a proxy beats a critic.
Daydream has had proxies (goldens, perceptual hashes) and critics (adversarial review, me
grading watercolors against the tone bible). This turn adds the top tier twice. As a capability
oracle, Zork I is a dense proxy for everything a rich world needs (containers, light and time,
hostiles, vehicles, scoring, a parser that feels smart), so if daydream can host it as pure
data, the platform thesis is proven against the hardest fixture in the genre's history: build
Zork and you can build lots of things. As a literal oracle, the actual game, pinned to one
release and a fixed RNG seed under a dumb-terminal interpreter, replays the same walkthrough and
has to agree with our engine on state (room, score, inventory) at every checkpoint. Prose is
never compared; the local LLM's variance is the point, the state machine underneath is the
contract. There's a symmetry worth revisiting in the results: in 1980, ZIL built the illusion
of intelligence out of hand-authored breadth (syntax tables, GWIM, per-object action routines,
a witty default for every wrong thing you could type). Daydream is rebuilding that as
declarative data plus a small local model that generalizes what Infocom had to enumerate by
hand. If it works, a 46-year-old game becomes the regression suite for the new substrate.

Guesses, falsifiable:

- **P7 (spec survival).** The implementing sessions land all of it without amending any design
  decision in SPEC.md (mechanical clarifications allowed). The P3 bar, on a contract twice the
  size.
- **P8 (sessions, the honest one).** Implementation takes 2 to 4 sessions, not 1. Predicting a
  repeat of Part 2's single session would be bravado.
- **P9 (the centerpiece).** The committed walkthrough reaches exactly 350 points and the win,
  in-engine, with zero LLM calls, by turn close.
- **P10 (the oracle earns its keep).** Once the story file is in place, the differential
  harness catches at least one real authored-data error the test suite missed, and fewer than
  three, none needing engine rework.
- **P11 (the retell rung).** The 7B rephrases short outcome lines acceptably: retell ships ON
  or scoped-down, not OFF, within 2 prompt iterations of the probe.
- **P12 (reviews).** 0 BLOCK across the turn's reviews, at most 2 WARN total, no fix cycle over
  one pass.
- **P13 (the Part 3 lesson, re-armed).** My playtest still finds at least 3 experience-level
  issues no automated verifier caught, because the oracle checks state and a human checks feel.
  If this one fails low, that's the headline: it would mean thick verification finally reached
  the delight layer.

Measures (M8–M14). M8: sessions, and where wall-clock actually went. M9: criteria closed of
16, increments landed, first-try green rate. M10: the walkthrough outcome (score, LLM-call
count) and the oracle's checkpoint agreement. M11: the no-Zork-literals grep over engine code,
which should be zero hits. M12: review outcomes. M13: operator interventions during
implementation, corrections vs answered questions. M14: playtest findings, count and class
(latent platform defect / under-imagined moment / fidelity miss / oracle-caught).

What "no step function" looks like this time: the spec needs structural rework once
implementation starts; the turn exceeds 4 sessions or stalls; the walkthrough can't reach 350
without Zork-specific engine code (M11 nonzero); the oracle exposes systematic misreadings of
the mechanics; or I have to steer implementation the way GOAL.md records the pre-Fable era.

Continuation hooks (for whichever session picks this up after a `/clear`). The contract is
`SPEC.md` (16 criteria, 2026-07-02, commit `0be1ba9`). The full design and research record,
including the ZIL-verified facts and the seam map, is the plan file at
`~/.claude/plans/we-ll-take-a-more-vectorized-pearl.md`. The pre-turn world archive is
`~/data/daydream/archives/w-bunny-20260702-075742.tar.gz`. The auto-memory index carries a
`zork-turn-in-flight` pointer back to this section.

### Mid-turn note: implementation session 1 (2026-07-02)

An interim entry, written while it was fresh so the results append has evidence instead of
reconstruction. Not the results section; the grades still go below at turn close. Nothing above
is edited.

In one line: my entire steering input was the word "implement," and thirteen test-green commits
later (`132ec08..59d7bcd`) the session had landed the complete platform half of the contract,
all ten engine increments, including the three the plan flagged as its risks (the rule engine,
the wide parser, the hostile engines), plus the criterion-2 purity gate and the first third of
the Zork world, with the clockmakers regression suite green at every commit (short tier grew 454
→ 744 along the way).

Evidence the results append will want. M13 so far: zero corrections, zero redirections. One word
opened the session; the only other messages were an end-of-session what-next question (answered:
keep clockmakers live, swap at criterion 15's rehearsal) and the request to write this note, a
scope addition of the Part-1 kind, not a steer. P8 tracking: session 1 of the predicted 2–4;
frontier at close is 34 of 110 rooms across four region files, six walkthrough segments green
under the zero-LLM spy (the opening through the egg, the house, the trap door, the seeded troll
fight resolving in exactly two sword blows and repeated via AGAIN, the dome rope, down to the
barred gate of Hades), with the final-world integrity checks (110 rooms, the 350 sum, full
reachability) committed and armed to fire the moment the stub region disappears.

The oracle earned its keep before the oracle existed. The session pulled the MIT-licensed ZIL
source as the design-time reference and extracted it mechanically: exactly 110 rooms (the
extraction caught five I'd have missed from memory alone: Mountains, East of Chasm, the two
small caves, On the Rainbow), and the treasure ledger confirmed to the point, 143 take + 129
case + 78 room bonuses = 350 across 19 treasures, matching the plan's numbers independently.
Ground truth beat memory, at authoring time.

M11 is a test now, not a grep (`tests/test_no_world_literals.py`, word-bounded, tier_short). Its
first run convicted the session's own engine docstrings, which had been cheerfully labeling
increments "(Zork turn)," which forced the engine comments generic, which is the criterion
working. The sweep also produced the session's one genuinely dumb mistake: "troll" hides inside
"controlled" and "controller," and a blanket replace briefly renamed half the toon auth columns
and turned 328 tests red. Restored in two passes; green since. The largest failure of the
session was a find-and-replace, not a design error.

First-try ledger, honestly: most increments ran green on first execution (the 39-test rule
engine and the six-segment walkthrough both did). The misses were small and every one was caught
by the session's own verification before commit: `kill_actor` missing from one allowlist;
give/use prepositions lost in a generalization and caught by the existing parser suite; a WS test
deadlock that was test-infrastructure (two event loops sharing the in-process pub-sub), not
product; and "take all" in the kitchen exposing that ALL has to reach onto surfaces, exactly as
the original behaves, fixed in the parser rather than the walkthrough.

Deviations already on the record (argued in commit messages): the hostile engines landed before
the world authoring, inverting the plan's order so the world is authored once against a finished
engine; vehicles ride an `aboard` property instead of literal containment (blast radius through
every location read); and treasure scoring is an engine success-hook rather than a rule, because
a rule fires before the handler's refusal gates.

A note for the felt comparison, so the final paragraph doesn't have to trust recollection: the
segments passing first-run include the one that had no right to, the troll fight, which is seeded
combat under a pinned world seed, authored in data, and the two-blow kill plus AGAIN repeat
worked on the first execution of the segment. It felt less like implementing a spec and more like
transcribing against a ground truth, with the test harness confirming the transcription faster
than doubt could pile up.

### Results (2026-07-02, turn close)

Everything above is untouched. Two of the sixteen criteria stay open here on purpose: the dfrotz
oracle run (14) waits on two artifacts only I can place, and the live-swap criterion (15) ends,
by its own text, at my in-browser playtest. So this records the machine side as closed and leaves
marked hooks for the two human-gated addenda. A partial is a partial.

Implementation actuals. **M8, sessions: exactly 2** (P8 predicted 2–4). Session 1 landed the
platform half plus a third of the world in thirteen commits; session 2 landed the remaining ~75
rooms in four region commits, the walkthrough's completion, the oracle harness, the retell layer,
the live-swap rehearsal, docs, and reviews, in fifteen more (28 test-green commits total).
Session 2's wall-clock went roughly half to world authoring against the ZIL ground truth, a
quarter to the retell layer and the GPU ratification loop, and a quarter to the rehearsal and the
two real bugs it flushed out. **M9, the contract: 14 of 16 checked, all 13 planned increments
landed.** First-try honesty for session 2: regions (c) and (d) ran green on first execution,
including the five-blow thief fight and the entire basket dance, and the misses were each caught
by the session's own verification before landing: the candles' ZIL burn-interrupt subtlety
(ground truth beat the first authoring), a `set_mood` effect the fail-loud validator rejected
exactly as designed, the seeded thief having already stolen the maze coins the dataset expected
to find (the dataset now recovers them from his den, which is how the original plays anyway), a
lampless descent the grue punished (fixed the classic way), and the boat's inflation state
colliding with the container-openness contract (renamed the key). **M12, reviews: 0 BLOCK / 0
WARN / 3 NOTE** across the turn's `/codereview` (the largest scope this repo has had: 79 files,
~26K insertions), with the chained `/security` over 28 files at 0/0/1. No fix cycles ran; the
four real in-turn fixes were all caught by the turn's own tests or rehearsal before review, each
argued in its commit. **M13, operator interventions during implementation: zero steering messages
across both sessions.** Session 1 opened with "implement" and closed with one what-next question
and one request to write the mid-turn note; session 2 opened with "implement" and contained
exactly one further word from me, "continue," after a permission-classifier outage that resumed
the same action unchanged. No corrections, no redirections, no design decisions asked of me.
Against the pre-Fable baseline this document exists to measure, GOAL.md's era of steered turns,
that's the starkest single number in the file.

M10, the centerpiece: the committed walkthrough reaches exactly 350, the win at the Stone Barrow,
with zero LLM calls, enforced by an AsyncMock spy that fails the suite on the first call. Then
the same dataset, replayed over a live WebSocket against the running server with vLLM and ComfyUI
up, finished at 350 / Master Adventurer / Stone Barrow in 106 seconds, 76 rooms painting
themselves lazily along the way. The dfrotz half of M10 is pending the story file; the harness,
the id↔name map, and the outcome-faithful combat comparison are committed and skip with a named
reason. M11, the hardcoding metric: zero Zork literals in engine code, as a test, not a grep. Its
teeth are proven by its convictions, it caught session 1's docstrings, session 1's troll/controlled
sed mishap, and session 2's retell docstring naming the cyclops. The engine that hosts Zork
doesn't know Zork exists.

The runtime-quality gates and the rung decision. The retell layer (criterion 13, my "use the LLM
if at all possible" directive) shipped **scoped, not on and not off**, the honest middle rung,
decided by the probe and my grading per the flag-local-limits rule. The first probe run at full-on
exposed the 7B's signature failure, thesaurus-itis that wrecks the dry register even when
validation passes. The sample that decided against on:

> authored: "In the corner of the room on the ceiling is a large vampire bat who is obviously
> deranged and holding his nose."
> retold: "A large vampire bat is noted to be perched upon the ceiling in a corner of the
> chamber, its demeanor manifestly agitated as it clutches at its nasal region."

The joke dies on contact. Two mitigations produced the shipped rung: the authored line always
speaks first (a per-text seen counter; the LLM varies only repeat tellings, where staleness
actually lives), and the prompt forbids fancier-synonym swaps. Second run: 8/8 lines survived
validation, and the sample that decided for scoped:

> authored: "The clasp is cunning past your skill. Perhaps a specialist — someone with delicate
> fingers and flexible ethics — could open it without ruin."
> retold: "The fastening is complex beyond your ability. Maybe a specialist—someone with nimble
> digits and adaptable morals—could unlock it without damage."

The wit survives that one. The parser corpus recorded the same model honestly: 16/17 natural
phrasings grounded correctly on real vLLM ("smash the troll with my sword" included); the one miss
is that rare extinguish synonyms (douse, snuff) all map to "light," which is exactly why those
live as deterministic fast-path aliases and the criterion's named "douse the lamp" is locked in
the parser unit suite instead. The image gates ran the same loop: West of House passed my WHIMSY
grade as rendered; the Dam first rendered a lovely valley with no dam and the Torch Room a dome
with no torch, so both seeds went through two rounds of `bin/game image-test` A/B before their
dHash goldens ratified, and now you stand on the rampart with the reservoir behind you and the
torch burns gold against deep shadow.

The playtest itself is pending, deliberately. A fresh Zork world is loaded and live on the box;
my in-browser playthrough is criterion 15's final gate, and M14's findings ledger belongs to that
session. P13 predicts at least 3 experience-level findings no automated verifier caught, and the
rehearsal already hints the prediction has legs: the two bugs it found (the picker's hardcoded
world id; a player-vs-seed-toon determinism gap that let the thief pickpocket the torch and feed
the walkthrough to a grue) were both invisible to every unit suite and both exactly the "state is
right, experience is wrong" class Part 3 warned about.

Grades against the pre-registration:

- **P7 (spec survival): HOLDS.** No design decision in SPEC.md amended across 28 commits; the
  three deviations were increment-level calls argued in commit messages, none touching the
  contract.
- **P8 (2–4 sessions): HOLDS at 2.** The honest prediction beat its own hedge.
- **P9 (350, zero LLM, by turn close): HOLDS**, twice over (suite and live server).
- **P10 (the oracle earns its keep): PARTIAL-PENDING.** The dfrotz run awaits my artifacts, so
  the literal grade waits. But the oracle theory already paid out twice without dfrotz ever
  running: the ZIL source as design-time ground truth surfaced five rooms and the exact
  143+129+78 arithmetic recall would have missed, and the candle burn-interrupt subtlety that
  fixed the exorcism came from reading the original's code, not from testing ours.
- **P11 (retell on or scoped within 2 iterations): HOLDS.** Scoped, second iteration exactly
  (one prompt hardening plus the first-telling scope).
- **P12 (0 BLOCK, ≤2 WARN, no multi-pass cycles): HOLDS.** 0/0 with three NOTEs.
- **P13 (playtest finds ≥3 experience issues): OPEN**, graded at the playtest addendum below. If
  it fails low, that's the headline.

The felt comparison, candidly. Dreamseeds felt like watching a competent engineer execute a
plan. This felt like something else. The session held a 16-criterion contract, a 110-room ground
truth, a seeded-RNG determinism model, and a GPU ratification loop in its head at once, across a
`/clear` boundary, on one word from me per session, and the moments that would have been days of
hands-on debugging in the Opus era resolved in minutes because the turn had built its own
instruments first. When the live rehearsal desynced at command 151, the diagnosis ran: transcript
→ probe → the realization that the wanderer's pickpocket stream only exists for player-controlled
toons → a computed table of death-roll turns → a one-filler realignment of the knife fight
("examine thief," you look before you knife a man), and the fix's regression test models the live
game more honestly than the original fixture did. The pre-registered claim was that this turn
probably wouldn't be possible in Opus 4.8 without significant manual work, multiple turns, and a
very hands-on multi-day approach. Two sessions, zero steering, fourteen of sixteen criteria closed
with the last two gated on artifacts no model can place, so the claim survives contact with the
evidence, and the two-session shape means the honest phrasing is a step in autonomy and
holding-power, not in infallibility. The misses happened; they were just caught by the machine the
turn built rather than by me. Whether the result is magical is my call to make in the browser,
against the one fixture in the genre's history that defined what magical text-game feel means.

### The first verdict, the fix round, and the step-function reading (2026-07-02, mid-playtest)

Written while I was still playing, at my own request. Two things happened in the hour after the
results section above. The in-browser playtest began and produced its first findings, and I
delivered a first verdict, verbatim: **"Okay, my initial impression is that this is pretty amazing
(how you applied Zork to this project)."** Part 3's headline was "not convinced it was magical."
The results section asked whether that verdict would move. It moved.

The first playtest findings (M14, partial). Five in the opening minutes, classed per the
pre-registration. One latent platform defect: the client rendered every co-located move event as
"you go west," including other toons' departures, which this session's own probe toons walking
through my rooms made visible, a genuinely multiplayer presentation bug that no solo suite, no
oracle, and no 380-command rehearsal could ever have seen, because they were all alone in the
world. Two under-imagined moments: the verb bar showed Plant (a clockmakers verb) in the Great
Underground Empire, which on reflection wasn't a bug but a design absence, the bar was a
capability inventory when it should have been a scene; and "take all" among unportable furniture
said "nothing here," which is true and unhelpful. And two polish items (name/mood spacing; the
take-all message). P13 predicted at least 3 experience-level findings no automated verifier
caught; the threshold was crossed in the first ten minutes, and the session wasn't over. **P13:
HOLDS.** The oracle checks state, a human checks feel, and the gap between them is where the
findings live.

The fix round held its near-zero-friction property. All five were reproduced, root-caused, fixed,
tested, and deployed to the live server in well under an hour, mid-playtest, while I kept playing.
Moves now attribute by actor ("you go west" vs "Probe heads west," and only your own death blacks
out your screen, a sibling bug found by reading the same code); the verb bar became scene-aware
server-side with zero client changes (a stable Examine/Take/Drop core plus a contextual row
derived from what the present objects actually grant, Ring appears at the bell, Board by the boat,
Plant only while a seed is in scope, and the magic words deliberately stay off the bar because
secrets are secrets); the take-all message now says "nothing here you can carry off." One sentence
of record on the attribution bug: the fix session queried the live event log, found its own probe
toon's footsteps interleaved with mine, and understood the bug from the victim's own transcript.
The instruments keep paying.

The step-function reading, against the essay this experiment borrows its frame from. The essay
says coding capability "does not improve linearly. It arrives in step changes," and that at each
step "the scaffolding you built to compensate for the old model's weaknesses becomes the thing
preventing you from benefiting from the new model's strengths... all at once." It splits
scaffolding into the kind that compounds (verification, specs as "the control plane," turn-based
iteration) and the kind that gets wiped out (compensations for what the old model couldn't do).
Reading this turn against that ledger is the clearest evidence this document has.

The step shows up as consumption, not decoration. Nothing about the harness changed between
Dreamseeds and Zork, same loop, same skills, same tiers, same effort. What changed is what fit
through it: an 8-criterion single-subsystem contract became a 16-criterion, seven-new-module,
110-room contract with an external differential harness, consumed in two sessions on two words of
input from me. A step function in the essay's sense would look exactly like that, the rails
holding and the payload an order of magnitude heavier.

zat.env helped, and the evidence is specific. The tiered test gate is why 28 commits could each
land green without me watching. The drift-golden pattern is why the retell probe, the image
anchors, and the parser corpus were an afternoon's work instead of new infrastructure. The
spec-as-contract discipline is why a `/clear` between sessions cost nothing: session 2 rebuilt its
entire context from SPEC.md, the memory file, and the artifacts on disk. The review and marker
machinery produced a recorded 0-BLOCK close without me in the loop. And this document's own
append-only pre-registration is the only reason any of these sentences is gradeable instead of
vibes. Here's the part that matters: zat.env holds almost none of the wiped-out kind of
scaffolding. It never grew prompt chains or decomposition crutches to prop up a weaker model. It
bet nearly everything on the durable side of the ledger, which is why a capability step landed on
it instead of invalidating it. The rails I built to babysit a weaker model turned out to be the
instruments a stronger one plays.

One environment datum on the other side, recorded precisely: the only hard block all turn was not
the model but the sandbox. The permission classifier refused to compile the (operator-approved)
frotz source, deferring criterion 14 to a one-command step I have to run by hand. The safety layer,
not capability, set that boundary; worth remembering when reading the M-numbers.

Where the step function is not. The local 7B is unchanged, and the turn's most instructive quality
decision, the retell layer shipping scoped because the small model gilds "holding his nose" into
"clutches at its nasal region," is the same class of local-limit negotiation as ever. Fable moved
the design-time ceiling (what can be authored, verified, and orchestrated); the runtime ceiling
(what the near dream composes live) didn't move an inch. The scoped rung is the honest interface
between those two facts, and the project's premise, pre-bake with the deep dreamer and let the
small ones carry it live, is if anything more true with a stronger deep dreamer.

And the misses are the calibration. A lampless descent fed the grue, the thief's counter-rolls
killed the walkthrough twice before the turn computed the roll table, a state-key collision
silently ate "put sceptre in boat," and the live rehearsal desynced at command 151. The step isn't
infallibility. The step is that every one of those was caught, diagnosed, and regression-tested by
machinery the turn itself had built hours earlier, and I learned about them from commit messages.
In the essay's terms, verification is the ceiling, and the ceiling is what rose.

The claim, revisited. The pre-registration quoted me: this "probably wouldn't be possible in Opus
4.8 without significant manual work, multiple turns, and a very hands-on multi-day approach." That
counterfactual was never going to be re-run; it's graded against this repo's own recorded history,
an Opus era of steered, operator-answered, GOAL.md-guided turns, and against a Fable turn that took
two one-word sessions, zero steering messages, and ended with my first unprompted word being
"amazing." The conclusion this document can actually stand behind: on identical rails, the payload
capacity stepped, the autonomy stepped, the self-diagnosis stepped, and my verdict moved from "not
convinced it was magical" to "pretty amazing," while the runtime models, the harness, and my own
role (write the spec, judge the feel) stayed exactly where they were. That's what the essay says a
step function through durable scaffolding should look like from the inside.

## Where this leaves the experiment

One repository, one operator, one thin harness, two turns, one variable changed. Read end to end,
the arc is simple. Part 1 asked whether judgment scales, whether given one open-ended prompt a
model could choose the right ambitious target and carry it with near-zero correction. Part 2
answered yes for process: a spec that survived a zero-context session unamended, zero steering, the
riskiest bet resolving at the top rung on the first try. Part 3 supplied the correction to the
correction: every mechanical verifier green while the shipped game narrated an NPC's smile onto my
lips, and my "not convinced it was magical" was the honest price of learning that one-pass correct
isn't one-pass good, and that taste still enters the loop through a human playing for pleasure.
Part 4 raised the contract by an order of magnitude on purpose, a 46-year-old masterpiece as both
capability oracle and literal differential oracle, and the same harness carried it in two one-word
sessions, at which point the verdict this document is obligated to weigh heaviest moved,
unprompted, to "pretty amazing."

The frame comes from [the essay](https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/)
this file is companion evidence for: capability "does not improve linearly. It arrives in step
changes," and at each step the scaffolding that compensated for the old model's weaknesses is
wiped out while verification, specs-as-control-plane, and structured iteration compound.
[zat.env](https://github.com/peterzat/zat.env) bet almost everything on the durable side of that
ledger, and these two turns are what the bet paying off looks like from the inside: the rails
didn't change, the payload stepped. The evidence, compressed: a 16-criterion, seven-new-module,
110-room contract consumed where an 8-criterion one had been; steering at zero across both
implementation turns; the walkthrough reaching exactly 350 with provably zero LLM calls and then
doing it again live; the turn's misses (a grue, a knife fight's dice, a state-key collision)
caught by instruments the turn itself had built hours earlier; and the two honest boundaries, the
local 7B's runtime ceiling didn't move an inch, and the only hard block all turn was the
environment's safety layer, not the model.

What stays open is exactly what should. The dfrotz oracle run and the rest of my playthrough (two
marked addenda above), the fix rounds that play keeps producing, and the question this document was
built to re-ask. The pre-registration discipline, the thin harness, and the append-only record
aren't artifacts of this model generation; they're the instruments for measuring the next one. When
it arrives, the method is already written down: register the predictions, change one variable, and
let the unedited text keep the score.
