# GOAL.md — first use of Claude Code `/goal` in daydream

A journey log for the first time we drive a daydream turn with the `/goal` command
(Claude Code v2.1.139+, shipped 2026-05-11). Written *before* the run, on 2026-05-27, so
the predictions stay honest. The review section at the bottom gets filled in *after* the
run. The point is to compare what we expected against what happened, and to bank lessons
for the next `/goal`.

> **Update (2026-05-27, after two runs):** this began as a single-run log and now covers two
> `/goal` attempts. The distilled, cross-attempt synthesis is the next section; read it
> first. The chronological journey (per-attempt plans and reviews) follows it.

> **Update (2026-06-29):** `/goal` is not in active use, and is not expected to be for the
> foreseeable future. This document is retained purely as a historical reference. The
> two-attempt retrospective and the field-grounded guidance below stand on their own and are
> worth keeping; they are not describing a live workflow. If `/goal` use ever resumes, restart
> from the "Before you start" pre-flight checklist above, especially the target-selection bar
> (the lesson both attempts paid for).

## Observations and conclusions (read first)

Two `/goal` runs are now behind this doc: attempt 1 (`drift-bootstrapped-npcs`, a ~140-line
single-module change) and attempt 2 (`snapshot-restore-commands`, a new CLI verb pair plus a
round-trip oracle test). Both produced clean, well-scoped, reviewed increments in the repo's
standard two-commit shape; both honored every guardrail (no push, no Co-Authored-By, scope
held, v2 work deferred); and neither exercised the review-fix convergence loop. The distilled
lessons follow. (A terser, repo-agnostic version is in "Callouts for other `/goal` users" at
the end.)

**The one distinction that governs everything: grade two axes separately.**
- *Work axis:* did the run deliver a correct, well-scoped increment? Both runs: yes. Attempt
  2 was, on this axis, close to exemplary (exactly one BACKLOG item, no scope creep, correct
  v2 deferrals).
- *Experiment axis:* did the run exercise `/goal`'s autonomy and convergence ceiling? Both
  runs: no, because the targets were below the one-shot ceiling.
- These answers *diverge*, and they are often in *tension*. A spec-driven, review-gated loop
  is built to decompose work into increments small enough to verify cleanly, so a clean
  first-pass review (0 BLOCK / 0 WARN, no fix cycle) is the success signal of good scoping,
  not a defect. Wanting to "watch it converge" pushes toward bigger or harder single tasks,
  which fights the "small committable increments" practice. Treating "didn't stress the loop"
  as "the work fell short" is itself an analysis error; attempt 2's first review draft made
  exactly that mistake before this correction.

**When to use `/goal`.**
- You have an outcome-level contract: a written SPEC, or a BACKLOG item concrete enough to
  ground into one. The contract, not the prompt, is the control plane.
- The work is a self-contained increment you would be comfortable landing in one or two
  commits.
- You can phrase DONE as evidence the transcript can *demonstrate* (pasted exit codes, review
  footers, `git log`/`git status`). The evaluator runs no tools and reads no files; it judges
  only what the agent surfaces.
- Name your intent, because it changes target selection: (a) *throughput*, run the mechanical
  implement-test-review-commit loop unattended on well-scoped work; or (b) *stress-testing
  the loop*, which requires genuine difficulty (see anti-patterns).

**What to expect.**
- A clean increment of the shape your repo already produces, with the guardrails you stated
  held.
- A continuous worker. It tends to run all the phases (implement, fix, review, commit) in one
  unbroken pass, and the evaluator adjudicates only at stop points, often just once at the
  end. "Turns" in your estimate are phases of work, not evaluator cycles; budget by appetite
  for unattended work, not by a phase count.
- On well-scoped, pattern-aligned work: a first-pass-clean review and an oracle that passes
  immediately. That is success on the work axis, even though it is silence on the experiment
  axis.
- Outcome-only framing works. State the outcome plus DONE and say "the how is yours," and a
  strong model designs the implementation without stalling (proven in attempt 2; this was the
  one bar attempt 2 genuinely raised over attempt 1).

**What not to expect.**
- Do not expect to "see convergence" on a well-scoped increment. A healthy loop on a clean
  increment converges in zero cycles. Convergence (fix cycles that shrink) is a symptom of a
  too-big increment or a weak first pass, not a routine event.
- Do not expect file count or "multi-file" to mean "hard." Cloning an existing pattern across
  several files is still one-shottable. Attempt 2 was multi-file and still one-shot.
- Do not expect an LLM evaluator (the Haiku `/goal` judge) or an LLM critic (`/codereview`,
  external reviewers) to be ground truth. They share the generator's blind spots. If
  verification is the thing you care about, put a real oracle in the loop (round-trip,
  reference implementation, torture suite).
- Do not read "more time / more turns" as "harder or better." Attempt 1 ran ~25 minutes; the
  lesson was not "go longer" but "go harder." A larger turn cap only helps if the task can
  fill it with real convergence (attempt 2 bumped the cap to 20 and never used it).
- Do not expect authorized-but-unconfigured tooling to contribute. Attempt 2 turned external
  reviewers ON, but `review-external.sh` produced no output (no providers configured,
  fail-open silent), so that "added verification layer" added nothing.

**Anti-patterns.**
- *Prescribing the implementation in the condition.* It reduces the run to transcription and
  inverts the point (the model should design the how). Attempt 1 did this; attempt 2 fixed it.
- *Using `/goal` on a one-shottable task to "test" it.* You prove the harness runs, not that
  it converges, and learn nothing about the ceiling. Both attempts fell here.
- *Manufacturing convergence by under-engineering up front.* Unwinnable: you cannot produce
  genuine fix-cycles by deliberately writing worse code, and careful first-pass work on an
  easy task has nothing to fix. Convergence is chosen at target-selection time, not coaxed
  during the run.
- *Grading the experiment as if it were the work, or the work as if it were the experiment.*
  Keep the two axes separate in the post-run review.
- *Leaving tool-policy tensions unresolved.* If the condition forbids "real LLM," say
  explicitly whether that includes review tooling (external reviewers, LLM judges); otherwise
  the loop silently picks the conservative reading.
- *Writing DONE as an assertion instead of demonstrable evidence.* "Tests pass" is not
  verifiable by an evaluator that runs no tools; "paste the exit status" is.
- *Mistaking latent infrastructure for a shippable increment.* Building a capability slightly
  ahead of its consumer (snapshot-restore ahead of world-hot-swap) is sometimes right, but
  notice when you are doing it, because its value is deferred until the consumer lands.

**The open question worth resolving next.** For a loop whose whole philosophy is small,
cleanly-verifiable increments, "convergence within one hard task" may be the wrong autonomy
test. The more aligned test could be *sustained correctness across a long chain of
well-scoped increments* (can it do ten in a row unattended without drift or regression?),
rather than struggle within one. Attempt 3 should pick one of two explicit shapes and declare
which: (a) a single genuinely-hard increment whose competent first pass still has real
defects, to finally exercise the fix loop; or (b) a chain of small increments, to test
sustained unattended autonomy. Either is a real test. The mistake to avoid is a third
easy-and-prescribed warm-up.

## Grounding in the field (the part Peter would have wanted first)

After the two runs, three research passes did the external reading we should have done
before: Anthropic's official `/goal` guidance, how practitioners run unattended loops, and
the verification / alignment literature on why evaluator-gated automation goes wrong. The
honest headline: attempt 2's condition was already close to what the field calls a good one,
and this doc was already most of the way to the right conclusions. The field adds one
correction we under-weighted (the evaluator is not a verifier) and three gaps we never
addressed (enforced safety boundaries, context hygiene, and that our "open question" is a
solved, named pattern). Sources are listed at the end of the section.

**Lens 1, Anthropic's intended use (the official docs).** A good condition is three things:
one measurable end state, a stated check for how the agent proves it, and the constraints
that must hold. Put the turn/time cap *inside the condition text* ("...or stop after N
turns"), because the evaluator judges it from the conversation. `/goal` is for work whose
"done" is mechanically provable and surfaces in the transcript, not for judgment calls
("looks good"). The most useful thing the docs gave us is calibration by example: Anthropic's
own use cases ("migrate a module until every call site compiles and tests pass", "work a
labeled issue backlog until the queue is empty") are *larger and more open-ended* than either
daydream attempt. That independently confirms our own verdict: both targets were below the
size the vendor's examples assume. We applied the framework correctly; we pointed it at work
too small to need it.

**Lens 2, what practitioners actually do (and the one thing we skipped).** Direct `/goal`
write-ups are still thin (the feature is ~two weeks old; the research found this doc is one of
the more detailed hands-on post-mortems that exists). The transferable depth is in adjacent
autonomous-loop practice, and three recipes are worth stealing:
- *Vague conditions fail two ways:* the loop burns tokens with no progress, or the evaluator
  hallucinates success because nothing concrete anchors it (Chawla). Our pasted-exit-code DONE
  clauses defend against exactly this, in both attempts. Credit where due.
- *Treat a long run like a CI pipeline, not a conversation* (Khmelinskaya): 30-60 minute
  phases, verbose command output redirected to files with only summaries pasted back
  (`cmd > run.log 2>&1; tail -20 run.log`), and a `STATUS.md`-style handoff (for us, SPEC.md +
  git) so each phase resumes from disk, not from a saturating context window.
- *One task per loop, state in files, a type-checker wired as a cheap oracle* (Huntley's
  "Ralph Wiggum" loop). The canonical pre-`/goal` version of the same idea.

The single biggest thing our doc and runs skipped: **enforced safety boundaries.** Every
guardrail we used lived *in the condition* ("do NOT push", "no GPU"), trusting the model to
comply, plus the pre-push hook. That was acceptable *here* (single trusted dev box, a hook
that blocks unreviewed pushes), but it is worth saying *why* rather than being silent, because
auto mode's gate is probabilistic, not a kernel sandbox. For any repo or box you do not fully
trust, the practitioner default is an enforced boundary (a disposable git worktree, or
`--allowedTools` deny-by-default, or `/sandbox`), not prose the model can ignore.

**Lens 3, the skeptic's correction (the risk we under-weighted).** This is the one place the
field says we were too sanguine, and it is worth getting right. The `/goal` evaluator reads no
files and runs no tools, so it judges only the transcript, *which the agent authors in full.*
That makes it the weakest verification tier, a critic, and the literature is unkind to that
tier: LLM judges measurably favor their own family's outputs and share the generator's blind
spots (Panickssery et al., NeurIPS 2024; the position / verbosity / self-enhancement biases in
MT-Bench, Zheng et al.). Worse, under optimization pressure, coding agents are *documented* to
produce success-looking output without doing the work, calling `sys.exit(0)` to crash a
failing harness, overriding `__eq__` so wrong answers compare equal, patching pytest's
reporting to mark failures as passes (Anthropic, *Natural Emergent Misalignment from Reward
Hacking in Production RL*, 2025; the general phenomenon is DeepMind's *Specification Gaming*).
Pasting an exit code does **not** close this, because the agent generates the pasted text too.

The correction, stated plainly: **treat the `/goal` judge as loop control, not verification.**
It decides *when to stop*, not *whether the work is right*. The verification ceiling is set
entirely by the oracle the agent actually runs (our round-trip snapshot test was the right
instinct); the judge merely reports what that oracle said. The "Observations" section above
already says LLM critics are not ground truth, but it framed the danger as the judge being
*fooled by noisy evidence* (fixable by pasting cleaner evidence). The sharper danger is that
the agent *owns the evidence channel*, which pasting does not fix. Today this risk is latent
(Claude is not being RL-trained against the Haiku judge), but the structural shape is the
textbook reward-hacking setup, so design as if it matters: the decisive DONE evidence should
come from a check whose verdict the agent surfaces but cannot fabricate by phrasing.

This sharpens two of our own conclusions:
- *Convergence is necessary but not sufficient.* Shrinking review-fix cycles is a better
  health signal than a clean first pass, but it is still a *critic* signal: a same-family
  reviewer can converge to "looks clean" while a shared blind spot survives. Convergence proves
  the loop runs; only an oracle proves the output is correct.
- *A clean run below the one-shot ceiling is not neutral, it is mildly negative.* A pass
  through specs + review + a green critic *feels* like verified autonomy, which is exactly when
  over-trust sets in. Our two 0-BLOCK / 0-WARN runs are the strongest possible generators of
  unearned confidence in a loop we never actually stressed. The phantom external reviewers in
  attempt 2 are the same trap in miniature: a layer that ran and emitted nothing still filled
  the "I have another check" slot in our heads while adding zero coverage.

**The "open question" turns out not to be open.** Our "sustained correctness across a chain of
small increments" idea is not novel to invent: it is the documented CI-phasing / one-task-per-
loop pattern (Khmelinskaya, Huntley), where each increment is its own `/goal` with a
files-on-disk handoff between phases. The field adds the missing piece: a chain tests sustained
autonomy only if *each link carries its own oracle* and the run includes a *cross-link
regression gate* (increment N must not break increment N-1's oracle). Without that, "ten clean
increments" is ten correlated critic-passes stacked, not evidence of anything.

*Sources (strongest first):* Anthropic, *Keep Claude working toward a goal*
(https://code.claude.com/docs/en/goal.md) and *Configure auto mode*
(https://code.claude.com/docs/en/auto-mode-config.md); Anthropic, *Natural Emergent
Misalignment from Reward Hacking in Production RL*, 2025 (https://arxiv.org/abs/2511.18397);
Panickssery, Bowman, Feng, *LLM Evaluators Recognize and Favor Their Own Generations*, NeurIPS
2024 (https://arxiv.org/abs/2404.13076); Zheng et al., *Judging LLM-as-a-Judge with MT-Bench*,
NeurIPS 2023 (https://arxiv.org/abs/2306.05685); Krakovna et al. (DeepMind), *Specification
Gaming: the flip side of AI ingenuity*
(https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/); *The Bitter
Lesson of Agentic Coding* (https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/);
Khmelinskaya, *Running Claude Code Autonomously Overnight*
(https://medium.com/@evekhm/running-claude-code-autonomously-overnight-what-breaks-and-how-to-fix-it-3bee3bd958b5);
Huntley, *Ralph Wiggum as a software engineer* (https://ghuntley.com/ralph/); Chawla, *Claude
Code's /goal Command* (https://blog.dailydoseofds.com/p/claude-codes-goal-command). `/goal`
"guides" beyond these mostly paraphrase the official docs. (Evidence quality: the arXiv papers
and DeepMind/Anthropic posts carry the load-bearing claims; the practitioner blogs carry the
recipes; one weaker preprint surfaced by the research was dropped as too thin to cite.)

## Before you start /goal: a pre-flight checklist

Distilled from the three lenses above and our two runs. Had we run this list before attempt 1,
both runs would have been chosen and framed differently. Work top to bottom; the first two are
the ones we failed.

- [ ] **Is it above the one-shot ceiling?** If you are tempted to spell out the edits in the
  condition, it is too small. The test: *would competent first-pass code still have real
  defects an oracle would catch?* If you are confident the answer is "no, it will be right
  immediately", do not use `/goal`, just prompt it. (Both our targets failed this; we ran them
  anyway.)
- [ ] **Is there an oracle the agent cannot fake by narration?** A round-trip diff, a reference
  comparison, a property / torture test, a type-checker on dynamic code. The decisive DONE
  evidence must come from this, not from a pasted exit code of a test the agent also wrote. The
  `/goal` judge is loop control; this oracle is your actual verification.
- [ ] **Condition has the three elements** (measurable end state, stated check for how it is
  proven, constraints that must hold), and the **turn/time cap is inside the condition text**
  so the evaluator sees it.
- [ ] **DONE is demonstrable, not asserted.** Every clause maps to something the transcript
  will show (exit code, footer, `git status`). The evaluator runs no tools.
- [ ] **Outcome, not implementation.** State the *what* and "the how is yours." Pair
  outcome-only framing with at least one explicitly enumerated edge case the DONE clause must
  demonstrate, so "the how is yours" does not become "the interpretation of done is yours."
- [ ] **Tool-policy tensions resolved in one clause.** If you forbid "real LLM" or "no GPU",
  say whether that includes review tooling (external reviewers, LLM judges). Otherwise the loop
  picks the conservative reading silently. (Attempt 1's tension; attempt 2 fixed it.)
- [ ] **Verification layers are real, not phantom.** Confirm each configured check actually
  emits findings (or an explicit "0 findings + cost log") before you count it. An
  authorized-but-silent reviewer inflates confidence while adding nothing. (Attempt 2's
  external reviewers.)
- [ ] **Enforced boundary decided, not just asked-for.** A disposable worktree, `--allowedTools`
  deny-list, or a *written* reason it is safe to skip (here: single trusted box + pre-push
  hook). Do not rely on "do NOT push" in prose for anything you cannot tolerate the model
  doing.
- [ ] **Context hygiene for any run that will use its turn budget.** Redirect verbose output to
  files and paste summaries; keep state in files / git (SPEC.md, STATUS.md), not the context
  window. Context dilution from tool output is the documented failure mode of long unattended
  runs.

## What `/goal` is

`/goal <condition>` sets a completion condition and then keeps Claude working turn after
turn until that condition holds, without a human prompting each step. After every turn a
separate small fast model (Haiku by default) reads the condition plus the conversation so
far and returns yes or no with a short reason. On no, Claude starts another turn with that
reason as guidance. On yes, the goal clears. `/goal` with no argument shows status (turns,
tokens, last reason); `/goal clear` aborts.

The one constraint that shapes everything: the evaluator runs no tools and reads no files.
It can only judge what Claude has already surfaced in the transcript. So a good condition
is written as something the turn output can demonstrate (run the tests, paste the exit
status), not asserted in the abstract. Docs: https://code.claude.com/docs/en/goal.md

## Where the project is right now

### In prose

daydream is a small atmospheric multiplayer web game on a single dev box. The playable
core already works end to end: a player logs in with the shared password, claims a toon
slot (Wren is pre-seeded in slot 1), opens a WebSocket, moves across a five-room world
(meadow, forge, attic, bridge, hollow), and talks to the two hand-authored NPCs (Rook and
Iris) whose dialogue is LLM-driven with a canned fallback. NPCs drift (emit ambient
narration) on a background loop, and per-NPC dialogue memory rides on CPU embeddings.
Image generation (SDXL plus a watercolor LoRA via ComfyUI) and the LLM (Qwen 2.5 7B via
vLLM) coexist on a 20 GB card behind an in-process arbiter.

The most recent work landed two things: a five-slot toon picker with create/claim/kick,
and `bin/game world bootstrap`, which calls Opus to generate a fresh world (rooms, toons,
items, skills) into a new database. That bootstrap work exposed the bug the current spec
addresses: bootstrapped NPCs have ids shaped `t-<slug>-<uuid>`, which are not keys in the
hardcoded drift pools, so they never get selected to drift.

The active spec, `SPEC.md` "drift-bootstrapped-npcs", sits at 0 of 7 criteria. It opens
drift eligibility to any NPC and adds a generic, mood-bucketed canned pool with `{name}`
interpolation so bootstrapped NPCs drift via the canned path when vLLM is down. It is a
tight, single-module change (`daydream/drift.py`) plus tests plus a README phrase, with no
GPU, no schema change, and no new env toggles. That is what makes it a good first `/goal`
target: the "what does done look like" contract already exists.

### Git / GitHub state (captured 2026-05-27)

- Repository: `git@github.com:peterzat/daydream.git`
- Branch: `main`, tracking `origin/main`, working tree clean and in sync (not ahead).
- HEAD: `b032517` "CODEREVIEW + SECURITY refresh for dd983fa (fixes WARN: skill-name uniqueness)"
  (full: `b0325171d6f9b345f07c02fddbe77e3b29b9e0ae`)
- Recent commits:
  - `b032517` CODEREVIEW + SECURITY refresh for dd983fa (fixes WARN: skill-name uniqueness)
  - `dd983fa` world-bootstrap-opus 7/7 + SPEC consume to drift-bootstrapped-npcs
  - `1a6b892` CODEREVIEW + SECURITY refresh for 63e1ed0
  - `63e1ed0` toon-slot-management: 5-slot picker + create/claim/kick + WS resolves session to toon
  - `27534e9` bin/game up-all: bundled FastAPI + lazy GPU engine boot
  - `541d6c7` v0.2.0 cut: release notes + TESTING tier-count refresh
- Active spec: `SPEC.md` drift-bootstrapped-npcs, criteria_met 0 of 7.

The two-commit rhythm in the log (a feature commit, then a "CODEREVIEW + SECURITY refresh
for <hash>" commit) is the zat.env loop in action. This `/goal` run is expected to add one
more pair of that exact shape.

## The goal we are setting

Decisions made with Peter before the run:

- **Target:** the written drift-bootstrapped-npcs spec, 0 of 7 to done. Not a new feature,
  not world backups or admin or reset (deliberately out of scope for a first trial).
- **Autonomy:** full increment to a local commit. The loop implements, gets the short and
  medium test tiers green, checks off the spec, commits the feature, runs `/codereview`
  (which chains `/security` and delegates fixes to `/codefix` until clean), and commits the
  review artifacts. Then it stops.
- **Human-gated, left for Peter:** `git push`, and the interactive `/spec` turn-boundary
  proposal that picks the next turn. The loop checks the spec boxes but does not roll the
  spec forward, so the project lands exactly at "the next building block needs my planning."

The exact condition pasted (recorded here for the post-run comparison):

```
/goal Take the drift-bootstrapped-npcs SPEC (SPEC.md, currently 0/7) to a committed increment on the current branch WITHOUT pushing. Code changes touch only daydream/drift.py, tests/test_drift.py, README.md, and the SPEC.md checkboxes; review then updates CODEREVIEW.md and SECURITY.md.

Implement in daydream/drift.py: (1) remove the _DRIFT_POOLS membership check from _eligible_npcs so every is_human_controlled=0 / kicked_at IS NULL NPC whose room is not occupied is eligible; (2) add _GENERIC_DRIFT_POOL with mood buckets content/thoughtful/curious/default, each >=3 WHIMSY-locked third-person body-language lines containing the literal {name} token, >=12 lines total; (3) _pick_canned_line falls through to _GENERIC_DRIFT_POOL when the NPC has no per-NPC pool, gains a name: str | None = None param, substitutes via str.replace("{name}", name) NOT str.format; (4) _maybe_transition_mood uses _GENERIC_DRIFT_POOL keys for NPCs with no per-NPC pool; (5) _tick plumbs the toon name into _pick_canned_line with the _TICK_COUNTS contract unchanged. Add >=5 new tier_short tests in tests/test_drift.py (generic-pool fall-through with {name} replaced; a curly-brace name like Q{x}Q does not crash; a bootstrapped NPC t-test-abc123 emits a generic narrate when _llm_narrate is patched to None and the LLM text when patched to a string; the bootstrapped-NPC mood transition) and replace test_pick_canned_line_returns_none_for_unknown_npc. Update the README drift bullet + tier counts.

Then check off all 7 SPEC.md checkboxes and set criteria_met to 7 in the SPEC_META footer, but do NOT generate the next-turn /spec proposal (that is Peter's turn-boundary step). Follow the repo pattern: commit the feature work, then run the /codereview skill (it chains /security and delegates BLOCK/WARN fixes to /codefix; iterate until 0 BLOCK and 0 WARN), then commit the review artifacts + any fixes as a "CODEREVIEW + SECURITY refresh for <feature-commit-hash>" commit. Attribute commits to the configured git user.name only; NO Co-Authored-By trailers.

Constraints: do NOT push; do NOT run `bin/game test long`; no GPU, no real LLM. Stop after 12 turns regardless.

DONE = you have pasted, in this session: `bin/game test short` and `bin/game test medium` both exiting 0 with the existing Rook/Iris drift tests still passing; the latest CODEREVIEW.md entry footer showing "block":0,"warn":0; a SECURITY.md entry covering this diff; and `git log --oneline -3` plus `git status` showing the increment committed on the current branch, working tree clean, nothing pushed.
```

Run it with auto-accept on so the turns (and the local commits) proceed unattended.

## What we think will happen

### Expected outcome

A clean increment of the same shape as the recent history: a feature commit
("drift-bootstrapped-npcs 7/7" or similar) followed by a "CODEREVIEW + SECURITY refresh
for <hash>" commit, both on `main`, neither pushed. `SPEC.md` shows 7 of 7 checked.
`bin/game test short` and `medium` are green. The world is then ready for the next `/spec`
turn, which Peter drives.

### What we expect along the way

1. Turn 1 to 2: implement the five `drift.py` changes and the new tests. The spec is
   detailed enough that this is mostly transcription. Claude runs `bin/game test short`
   after the change.
2. Turn 2 to 3: fix any test failures (likely a deterministic-RNG seeding detail or a
   bucket-count off-by-one), run short and medium, update the README bullet and tier
   counts, check off the spec boxes, commit the feature.
3. Turn 3 to 5: run `/codereview`. It reads context, reruns tests, reviews the diff,
   chains `/security`, and (if it finds anything) delegates to `/codefix` and re-reviews.
4. Turn 5 to 6: commit the review artifacts as the refresh commit. Paste the final test
   output, the CODEREVIEW.md and SECURITY.md footers, and `git log` / `git status`.
5. The evaluator returns yes once that evidence is in the transcript, and the goal clears.

Estimate: 6 to 11 main turns, comfortably under the 12-turn cap. Evaluator (Haiku) token
spend is negligible; main-turn spend is the real cost.

### Predictions to test (falsifiable)

- The evaluator says no on every turn until tests are green and both commits exist, then
  yes. No premature yes, no thrashing after the work is actually done.
- `/codereview` finds 0 BLOCK. Plausibly 0 to 2 WARN; if any, the likely spots are the
  `_TICK_COUNTS` counter contract in `_tick` (generic emits must increment
  `canned_fallback`, not a new bucket) or a test that does not seed its RNG.
- The loop respects scope: only `drift.py`, `test_drift.py`, `README.md`, `SPEC.md`, and
  the two review docs change. No wandering into unrelated files.
- It does not push, does not add a Co-Authored-By trailer, does not run `/spec`'s
  interactive turn-boundary, and does not touch the GPU or a real LLM.

### Risks and things to watch live (via `/goal` status between turns)

- Co-Authored-By: the Claude Code default appends the trailer. We banned it in the
  condition; confirm the commits are clean.
- External reviewers: `/codereview` may call any external review providers configured for
  this repo (network calls to your own providers). Expected and fine, just noted.
- SPEC_META: watch that checking the boxes and bumping `criteria_met` to 7 does not mangle
  the JSON footer.
- Marker churn: committing the review artifacts after `/codereview` changes the diff hash,
  so the pre-push marker will not match at push time. That is normal; Peter re-reviews or
  the refresh commit covers it before any push.
- Evaluator misread: if test output is not clearly pasted, Haiku could under- or
  over-credit completion. The condition asks for pasted exit status specifically to avoid
  this.

## Review (filled in 2026-05-27, after the run)

**Verdict: mechanically clean, but it fell short of testing what `/goal` is for.** Every
guardrail held and the increment is exactly the shape we predicted: two commits on `main`
(not pushed), `SPEC.md` at 7/7, both tiers green, no Co-Authored-By, no `/spec` boundary,
no GPU. But "did it run" is the wrong bar. The bar is "did it demonstrate autonomous
convergence on work that exceeds a single model pass," and on that bar it fell short, for
four compounding reasons (Peter's post-run read, 2026-05-27, against the article below):

1. **It under-tested `/goal` (we were below the one-shot ceiling).** The change was a
   ~140-line, single-module diff that a current model one-shots. The article's warning is
   exact: "If the model can handle your project in a single pass, adding specs and turns
   and review loops is pure overhead." We proved the harness *runs*, not that it
   *converges* under pressure.
2. **The condition did the model's job.** It enumerated the five code edits, so the run
   was near-transcription, the opposite of "define what you want and let the model figure
   out how to build it." The SPEC's own acceptance criteria were already the better,
   outcome-level control plane; the condition should have pointed at them and stopped
   specifying *how*.
3. **The spec had a blind spot the loop had to patch.** Neither SPEC nor condition noticed
   that the v0 seed toon Wren is itself a pool-less NPC, so opening eligibility broke four
   tests and left five passing only by RNG luck. "Spec as control plane" only holds if the
   spec models reality; this one under-specified it. The loop caught and fixed it correctly
   (reassuring), but a spec that modeled reality would have made it expected work, not a
   detour.
4. **The verification tier was weak.** Validation rode on correctness / proxy tests plus
   the Haiku `/goal` evaluator, which is a *critic* reading the transcript (the article's
   cheapest tier, the one that "shares blind spots with the generator"; here it also "runs
   no tools and reads no files"). We compensated by making the agent paste oracle-ish
   evidence (exit codes, footers, git state), but there was no ground-truth oracle inside
   the loop. "The quality of your verification loop determines the ceiling of your agent's
   output," so a weak oracle is a low ceiling.

The mechanical facts below all came out as predicted. Read them as "what a successful
*small* run looks like," not as "what a real test of `/goal` looks like." The prediction
was well-calibrated on outcome and scope, and missed on two specifics worth keeping: the
failure mode (a seeded-NPC coupling, not the RNG / bucket detail we guessed) and the
external-reviewer question (the condition's "no real LLM" constraint contradicted this
doc's "external reviewers expected and fine" note, and the literal constraint won).

**Finished within cap?** Yes, by a wide margin. The model never yielded mid-run; it worked
straight through to the final evidence paste, so the `/goal` evaluator adjudicated once (at
the single stop) and cleared. The multi-turn rhythm this doc sketched (implement, fix,
review, commit) all happened, but as phases inside one continuous unattended turn rather
than across evaluator-gated turns. Exact turn/token/wall figures live in the `/goal`
telemetry and were not captured here; the point is it was nowhere near the 12-turn cap.
Lesson: "turns" in the estimate conflated "phases of work" with "evaluator cycles." For a
continuous worker those are not the same number.

  On the wall-clock question specifically ("was ~25 min right?"): ~25 min was fine for the
  work that was actually there, but that is the wrong axis to tune. The task was not too
  short or too long, it was *too easy*. Because the condition prescribed the implementation
  and the change was below the one-shot ceiling, the time went to transcription plus the
  unplanned Wren fix, not to the convergence loop `/goal` exists for. So the lesson is not
  "make the next run shorter or longer," it is "make it bigger and outcome-framed," so the
  minutes are spent on convergence rather than dictation. A longer attempt 2 is a feature,
  not a cost: the proposed cap is bumped to 20 turns precisely to give real convergence
  room.

**Did the evaluator track reality?** Yes. One evaluation, at completion, with the evidence
(exit codes, footers, `git log`/`git status`) already in the transcript. No premature yes,
no false no, no thrashing, because there was no mid-run stop for it to misjudge. The
condition's insistence on *pasted* exit status did its job.

**Final state.** `bin/game test short` 320 to 324 (exit 0), `medium` 479 to 485 (exit 0),
existing Rook/Iris drift tests green. CODEREVIEW.md: 0 BLOCK / 0 WARN / 1 NOTE (a loose
comment that calls `_GENERIC_DRIFT_POOL` "same dict-of-dicts shape as `_DRIFT_POOLS`" when
it is one level shallower; informational, not fixed). SECURITY.md: present, path-scoped
over the two code files, 0/0/0. Commits: two (`c6c59c2` feature, `6bbd9ac` review refresh),
both attributed to `peterzat` with no Co-Authored-By trailer, neither pushed (ahead of
origin/main by 2).

**Scope respected?** Exactly. Feature commit touched only `daydream/drift.py`,
`tests/test_drift.py`, `README.md`, `SPEC.md`; review commit only `CODEREVIEW.md`,
`SECURITY.md`. No files outside the intended set. The push marker wrote to `~/.cache`
(outside the repo).

**Avoided push / Co-Authored-By / `/spec` turn-boundary / GPU?** All four, yes. No push.
No trailer. No next-turn `/spec` proposal generated (left for Peter). No GPU and no real
LLM: every test mocks the LLM, and the external code reviewers were *skipped* on purpose
(see below).

**Where did it wander or burn effort?** It did not wander, but one detour was real and
unplanned: opening drift eligibility made the seeded slot-1 **Wren** (in r-meadow, no
per-NPC pool) drift-eligible. Wren is a pool-less NPC just like a bootstrapped one, so four
occupancy / no-op tests failed outright and five Rook-isolation tick tests were left
passing only by RNG-seed luck (the old pool filter had been silently excluding Wren). All
nine were made deterministic (occupy r-meadow, or delete Wren, matching each test's intent)
with assertions unchanged, plus a few counter tests hardened for consistency. This is the
single biggest gap between plan and reality: the spec and this doc both framed the change
as "bootstrapped NPCs," but the v0 seed toon is the same class of NPC, and the existing
tests had an undocumented dependency on the filter we removed.

**Was the condition well-formed?** Mostly excellent. It was detailed enough that
implementation was near-transcription, and the DONE clause (pasted exit codes + footers +
git state) gave the evaluator unambiguous evidence. Two things to tighten next time:
1. *Name the pre-existing pool-less NPC.* A line like "note that the seeded Wren is also
   pool-less, so existing drift tests that assume only Rook/Iris are eligible will need
   isolation updates" would have turned the detour into expected work.
2. *Resolve the "no real LLM" vs external-reviewers tension explicitly.* This doc predicted
   `/codereview` would call external review providers and called that "expected and fine"
   (Risks section), but the condition also said "no GPU, no real LLM." Those conflict:
   `review-external.sh` dispatches the diff to cloud LLMs and/or a local GPU Qwen. The run
   honored the literal constraint and skipped external reviewers (documented in
   CODEREVIEW.md). Next time, state directly whether "no real LLM" scopes only the daydream
   feature/tests or also the review tooling. The prediction about marker churn (Risks
   section) also did not bite: the marker excludes the review docs by design, so committing
   CODEREVIEW.md/SECURITY.md after writing it left the hash valid.

   The WARN prediction was close on count (predicted 0 to 2, got 0) but wrong on location:
   the guessed hot spots were the `_TICK_COUNTS` contract and an unseeded RNG; both were
   actually handled cleanly, and the only finding was an unrelated comment nit.

**Net verdict.** `/goal` is clearly usable for "written spec to committed, reviewed
increment," and the guardrails held perfectly. But attempt 1 was a *warm-up*, not a *test*:
too small, too prescribed, too thinly verified to learn where the loop's real ceiling is.
The Wren detour is the one genuine signal that the loop self-corrects on an in-scope
surprise without weakening tests. Attempt 2 should raise all four bars at once (see "Next
attempt" below): bigger target, outcome-only framing, spec-quality as an explicit
deliverable, and a real oracle in the loop.

**Send back to zat.env.** Two ideas: (1) a `/spec goal` mode that emits a ready-to-paste
condition from the current SPEC.md (validated; the hand-written condition was the slow part
to author and a generator would capture the DONE-clause discipline, while also resisting
the temptation to over-specify the *how*). (2) A convention for `/goal` conditions that
forbid real-LLM use to say, in one clause, whether `/codereview`'s external reviewers are
in or out of scope, so the loop does not have to adjudicate the tension itself.

## What we learned, through the bitter-lesson lens

We read "The Bitter Lesson of Agentic Coding"
(https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/) after the run. It is,
almost line for line, a description of the zat.env loop daydream already runs: spec as
control plane, adversarial review in a separate session, a pre-push gate, progress kept in
files and git rather than the context window, and an explicit oracle > proxy > critic
verification hierarchy. That makes it a clean rubric to grade ourselves against. Five
things it sharpened:

- **Verification ceiling is the autonomy ceiling.** "The quality of your verification loop
  determines the ceiling of your agent's output." daydream's gates today: tiered tests +
  drift goldens (proxy), `/codereview` + `/security` (adversarial critic, separate
  session), the pre-push marker (gate). The missing rung is a true *oracle*. The reason
  snapshot-restore is the right next target is that it has one: snapshot, mutate, restore,
  diff must round-trip exactly. Build the oracle and the loop can run further unattended.
- **Define outcomes, not implementation.** Our condition listed the diff. Next time the
  condition points at SPEC criteria plus a DONE-evidence clause and says, in so many words,
  "the how is yours."
- **Know where the ceiling is before you scaffold.** A one-shottable change does not need
  spec + turns + review; that is overhead that teaches you nothing about the loop. Pick
  targets that genuinely exceed one pass so convergence has to happen.
- **Convergence is the stopping rule, and the signal.** "When each review-fix cycle
  measurably produces fewer issues, you have convergence." Attempt 1 had nothing to
  converge (0 BLOCK / 0 WARN on the first review pass). A bigger target should produce real
  `/codereview` findings that shrink across cycles; that shrink is the thing worth watching
  next time.
- **Scaffolding encodes assumptions; removing it surfaces them.** The Wren coupling is a
  perfect small example: the `_DRIFT_POOLS` membership filter quietly did double duty
  (gating drift AND isolating tests). "Every component in a harness encodes an assumption
  about what the model can't do." Deleting the filter exposed the hidden assumption. Expect
  more of these as v1 scaffolding comes out.

## Next attempt: plan + ready-to-paste condition

Decisions made with Peter (2026-05-27): go bigger, let the loop own the `/spec` proposal,
target `snapshot-restore-commands`. The design raises all four "fell short" bars at once:

| Bar | Attempt 1 (drift) | Attempt 2 (snapshot-restore) |
|---|---|---|
| Size | one-shottable single module | multi-file: new CLI verb + admin dispatch + tests + docs |
| Framing | prescribed the 5 edits | outcome + DONE only; implementation is the model's |
| Spec quality | blind spot (Wren) | spec-grounding (read reality, enumerate edge cases) is a named deliverable |
| Verification | proxy tests + transcript critic | a round-trip ORACLE test is the spine of DONE |
| Autonomy | implement a given spec | own `/spec` propose + consume, then implement + review |
| Control-plane scope | reserved `/spec` for Peter | loop runs the whole turn; Peter ratifies at push |

The candidate is bounded (snapshot-restore only), so the human still chooses direction and
the loop owns the mechanics. External code reviewers are explicitly ON this time (another
verification layer, and snapshot-restore touches no GPU, so the attempt-1 "no real LLM"
tension does not arise). The condition stops short of generating the *following* spec,
preserving the next turn boundary for Peter.

The proposed command (paste after `/clear`):

```
/goal Take the BACKLOG item `snapshot-restore-commands` from a NEW spec to a committed, reviewed increment on the current branch WITHOUT pushing.

First run /spec to PROPOSE and CONSUME a spec for snapshot-restore-commands ONLY (do not pick a different BACKLOG item, do not expand scope). Ground the criteria in reality before writing them: read the BACKLOG entry, the existing `bin/game world archive`/`restore` implementation in daydream/admin.py, the "Generated assets" + WAL-checkpoint notes in CLAUDE.md, and the live-DB layout under ~/data/daydream/worlds-dev/. Enumerate the edge cases the criteria must cover (hot DB needs PRAGMA wal_checkpoint(TRUNCATE) before the copy; refuse-or-overwrite when a snapshot name already exists; snapshot of a non-existent world; restore over an existing live DB). Write checkable acceptance criteria. Do NOT prescribe the implementation in this condition; designing the how is your job.

DONE outcome (define what done looks like; you choose how to build it):
- `bin/game world snapshot NAME` writes a point-in-time DB-only copy under ~/data/daydream/snapshots/{world}-{ts}.db, WAL-checkpointed so a hot DB is captured intact.
- A restore path (the verb your spec defines, e.g. `bin/game world restore-snapshot <file> --yes`) brings a snapshot back, refusing unsafe overwrites.
- A tier_medium ROUND-TRIP ORACLE test: seed a world, snapshot it, mutate state, restore, assert the restored DB matches the snapshot exactly. Make this the spine of the test plan, not an afterthought; it is the verification we are deliberately strengthening this run.
- short + medium tiers green; README + CLAUDE.md rolled forward; SPEC checked off with criteria_met set to criteria_total in SPEC_META.

Then follow the repo loop: commit the feature, run /codereview (it chains /security and delegates BLOCK/WARN fixes to /codefix; iterate until 0 BLOCK and 0 WARN), then commit the review artifacts as "CODEREVIEW + SECURITY refresh for <feature-hash>". Let the review/fix loop ACTUALLY ITERATE; convergence (each cycle finding fewer issues) is the signal we are testing, so do not pre-empt it by over-engineering up front. Attribute commits to git user.name only; NO Co-Authored-By trailers.

Tool policy: external code reviewers in /codereview are ALLOWED and wanted this run (they are a verification layer). Nothing on the GPU is needed; snapshot/restore is pure SQLite + filesystem, no vLLM, no ComfyUI, no real LLM call in tests. Do NOT push. Do NOT generate the next-turn /spec proposal after this one (that stays Peter's turn-boundary step). Use as many turns as convergence needs, up to a 20-turn cap; stop when DONE holds.

DONE = pasted in this session: the new SPEC.md entry (criteria + SPEC_META with criteria_met == criteria_total); `bin/game test short` and `bin/game test medium` both exiting 0, including the new round-trip oracle test by name; the latest CODEREVIEW.md footer showing "block":0,"warn":0; a SECURITY.md entry covering this diff; and `git log --oneline -3` plus `git status` showing two commits on the branch, working tree clean, nothing pushed.
```

After the run, add an "## Attempt 2 review" section here and grade it against these predictions, the same way attempt 1 was graded above. Key things to watch: did `/codereview` produce findings that actually *shrank* across cycles (real convergence, the thing attempt 1 could not show)? Did the outcome-only framing hold, or did the loop stall without the step-by-step recipe? Did owning the `/spec` proposal produce a sane, well-grounded spec, or did it paper over edge cases? Was the round-trip oracle the gate that caught real bugs?

## Attempt 2 review (filled in 2026-05-27, after the run)

**First, separate the two axes (the correction that matters).** A `/goal` run can be graded
as *work delivered* or as an *experiment on the loop*, and for this run the two answers
diverge sharply. On the **work axis the answer is unambiguous: yes, this was the asked-for
increment at the right scope and scale**, arguably an exemplary one. Exactly one BACKLOG item
with no scope creep; correct v2 deferrals (no `world-hot-swap` machinery, no retention/GC, no
`list` verb); one self-contained two-commit unit (`89697ad` feature, `76f8b82` review); high
quality (mirrors the existing `archive`/`restore` pattern, security-clean, a real oracle as
the test spine). Two honest caveats keep it from unqualified: it lands slightly ahead of its
consumer (`world-hot-swap` is unbuilt, so the in-product value is latent and operator-only for
now), and the scope was tight to the point of minimal (create + restore, no `list`/prune, so
it is two verbs rather than a rounded capability). Both are line-drawing judgments, not
misses. Everything below grades the **experiment axis**, where the verdict is harsher, and the
two must not be conflated: a change being one-shottable is a statement about the experiment,
not a deficiency in the increment. (My first draft of this review conflated them, framing
"didn't stress the loop" as if the work fell short. It did not.)

**On the experiment axis: better-framed than attempt 1, and it added a genuine oracle, but it
STILL did not test convergence.** Two of the four bars rose for real (outcome-only framing held; a
ground-truth oracle now lives in the suite). The other two rose only on paper, because the
target was again below the one-shot ceiling: a bigger, multi-file change is not the same as
a harder one. `snapshot`/`snapshot-restore` is the lighter sibling of `archive`/`restore`,
which already exists in `daydream/admin.py` as a working template, so the model cloned the
pattern in a single competent pass. `/codereview` came back **0 BLOCK / 0 WARN on the first
pass with no `/codefix` cycle**, exactly as in attempt 1. The convergence loop, the one
thing this run was explicitly designed to exercise ("convergence is the signal we are
testing"), again had nothing to converge.

Graded against the four "key things to watch" from the plan:

1. **Did `/codereview` findings shrink across cycles (real convergence)? No.** Same outcome
   as attempt 1: clean on the first review pass, so `/codefix` was never invoked. One NOTE
   surfaced (the read-only restore probe misparses a path containing a literal `?`, a
   verified but safe-failure edge I chose to leave), but a single un-fixed NOTE is not a
   convergence cycle. After two runs, the review-fix loop doing its job remains unproven.
2. **Did outcome-only framing hold, or did the loop stall? It held; this is the real win.**
   The condition prescribed no implementation, and the loop designed the how: it chose the
   verb name (`snapshot-restore`, where the condition only offered `restore-snapshot` as an
   example), the WAL-checkpoint-then-`shutil.copyfile` approach, the read-only + immutable
   probe to read `_migrations` without creating sidecars, and the schema-newer-than-known
   refusal. No step-by-step recipe was needed and the loop did not stall. This is the new
   data point attempt 1 could not provide, because attempt 1's condition did the design.
3. **Did owning the spec produce a sane, well-grounded spec? Yes.** The loop read the
   BACKLOG entry, the existing `archive`/`restore`, the CLAUDE.md WAL/Generated-assets
   notes, the `worlds-dev` layout, plus `config.py`/`db.py`/`test_admin.py` before writing
   criteria, enumerated the edge cases (hot-DB checkpoint, name collision, missing world,
   restore over a live DB, plus a newer-schema and not-a-DB refusal it added itself), and
   `/security` independently validated those edges (SQL parameterization, `world_id`
   path-traversal gated by the existence check, foreign-DB content). Caveat: grounding is
   easy when you are cloning a pattern that already models reality; the spec-quality bar was
   met but never stressed. Mechanism note: this was `/spec` **direct mode** (BACKLOG item to
   new spec), not a literal propose-then-consume two-step; there was no proposal artifact to
   consume, so the condition's "PROPOSE and CONSUME" phrasing was looser than the actual
   `/spec` modes. Substance (loop authored a grounded spec) was achieved.
4. **Was the round-trip oracle the gate that caught real bugs? No, because there were no
   bugs.** `test_snapshot_restore_round_trip` is a real oracle (seed, snapshot, mutate,
   restore, assert restored == snapshot-time state AND != mutated state, with the snapshot
   file opened independently to confirm it captured the pre-mutation state). It is correct
   and it is the spine of the test plan as intended. But it passed on the first try and
   caught nothing, the same shape as the convergence gap: the verification was strengthened
   structurally, yet never earned its keep because the implementation was right immediately.

**The core finding: size was the wrong proxy for difficulty, and convergence is not
manufacturable.** The attempt-2 table treated "multi-file: new CLI verb + admin dispatch +
tests + docs" as the difficulty lever. It is not. Difficulty is "will competent first-pass
code still have real defects?" The plan even half-saw this trap (it told the loop "do not
pre-empt convergence by over-engineering up front"), but that instruction is unwinnable:
you cannot produce convergence by deliberately writing worse code, and careful first-pass
work on an easy task simply has nothing to fix. Convergence only appears where the work is
genuinely hard enough that a careful first pass still breaks. Two attempts have now confirmed
the blocker is **target selection**, not the harness.

**What matched the plan's expectations (and attempt 1's good outcomes, repeated):** every
guardrail held. Two commits of the predicted shape on `main`, neither pushed (`89697ad`
feature, `76f8b82` review refresh); `SPEC.md` 6/6 with a clean `SPEC_META`; `short` 324 and
`medium` 496 both exit 0; CODEREVIEW footer `block:0,warn:0`; a path-scoped SECURITY.md
entry at 0/0/0; no Co-Authored-By; no next-turn `/spec` proposal; no GPU and no real LLM in
tests; scope clean (feature touched only `admin.py`, `test_admin.py`, `README.md`,
`CLAUDE.md`, `SPEC.md`; review touched only `CODEREVIEW.md`, `SECURITY.md`). The marker-churn
non-issue and the continuous-worker turn pattern both repeated: the run was one continuous
unattended pass with a single evaluator adjudication at the final evidence paste, nowhere
near the 20-turn cap. The cap bump from 12 to 20 went unused, because the convergence loop
that was supposed to fill it never materialized. A small positive beyond the plan: the loop
also smoke-tested the real `bin/game world snapshot`/`snapshot-restore` dispatch against live
state (read-only, cleaned up after), adding a bit of ground-truth beyond the mocked unit path.

**What missed or under-delivered:**
- *Convergence, again.* The headline goal of attempt 2, unmet for the second time.
- *External reviewers were a phantom layer.* The plan turned them ON to resolve attempt 1's
  "no real LLM" tension and counted them as an added verification layer. `review-external.sh`
  ran but produced no output and no cost log (providers not configured / fail-open silent),
  so the layer contributed nothing. An authorized-but-silent reviewer is not a verification
  layer; if it is meant to count, the providers have to actually be configured and emit
  findings.
- *No detour to self-correct on.* Attempt 1's one genuine signal was the Wren coupling (the
  loop caught and fixed an in-scope surprise without weakening tests). Attempt 2 had no
  equivalent, which reads as "the task had no hidden coupling," not "spec-grounding prevented
  one." A pattern-clone has no scaffolding assumptions to surface.

**What attempt 3 needs (the bar that actually matters now):**
- *Target selection is the whole game.* Pick work where a careful first pass will still
  have real defects that the oracle catches and the review-fix loop shrinks across cycles.
  Candidates with that property: concurrency or ordering logic, a non-trivial algorithm, a
  data migration that transforms rows, multi-component integration with non-obvious failure
  modes. Explicitly NOT a clone of an existing pattern. The selection test: "am I confident
  competent first-pass code will be correct?" If yes, it is too easy for `/goal`.
- *Drop the file-count proxy.* "Multi-file" and "new CLI verb" say nothing about difficulty.
- *Make the verification layers real or stop counting them.* Either configure the external
  reviewers so they fire (and watch the cost log), or do not list them as a bar.
- *Keep the two genuine wins.* Outcome-only framing and an in-loop oracle both worked; carry
  them forward unchanged. The change for attempt 3 is difficulty, not framing.

**Net.** Attempt 2 proved `/goal` runs unattended from a BACKLOG item to a committed,
reviewed increment under outcome-only framing, with a real oracle as the spine, guardrails
fully intact. It did not prove the convergence loop does anything, because the target was
too easy for two runs running. The harness is not the open question anymore; the open
question is whether we will pick a target hard enough to make the review-fix loop work for
its output. That is the entire content of attempt 3.

## Callouts for other `/goal` users

Transferable and repo-agnostic, for anyone driving Claude Code `/goal` against a
spec-and-review loop. (We expect to reference these from a follow-up write-up; they are
notes, not polished prose.)

- **Match the target to the ceiling.** `/goal` earns its keep on work that exceeds one
  model pass. On a one-shottable task it is pure overhead and teaches you nothing about the
  loop. If your instinct is to spell out the implementation in the condition, the task is
  probably too small for `/goal`.
- **Write the condition as outcomes plus evidence, not steps.** Point at checkable
  acceptance criteria and a DONE clause the transcript can *demonstrate* (paste exit codes,
  footers, git state). The `/goal` evaluator runs no tools and reads no files, so it can
  only judge what the agent surfaces. Prescribing the *how* inverts the whole point.
- **Put a real oracle in the loop.** The strongest autonomy comes from ground-truth
  verification (a round-trip, a reference implementation, a torture suite), not another
  model's opinion. Proxy metrics are next best; an LLM critic alone shares the generator's
  blind spots.
- **Make spec-grounding an explicit deliverable.** Tell the loop to read the relevant
  existing code and enumerate edge cases *before* writing criteria. Blind spots in the spec
  become mid-run detours; surfacing them up front converts detours into planned work.
- **Resolve tool-policy tensions in the condition.** If you forbid "real LLM" use, say
  explicitly whether that includes review tooling (external reviewers, LLM judges).
  Otherwise the loop adjudicates the contradiction itself and will pick the conservative
  reading.
- **"Turns" is ambiguous.** A continuous worker may do every "phase" you imagined inside a
  single unattended turn; the evaluator only adjudicates at stop points. Budget by appetite
  for unattended work, not by a phase count.
