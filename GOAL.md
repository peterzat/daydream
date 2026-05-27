# GOAL.md — first use of Claude Code `/goal` in daydream

A journey log for the first time we drive a daydream turn with the `/goal` command
(Claude Code v2.1.139+, shipped 2026-05-11). Written *before* the run, on 2026-05-27, so
the predictions stay honest. The review section at the bottom gets filled in *after* the
run. The point is to compare what we expected against what happened, and to bank lessons
for the next `/goal`.

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
