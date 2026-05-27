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

## Notes for review afterwards

Fill in after the run.

- Finished within cap? Turns used: ___ / 12. Wall time: ___. Token spend (main): ___.
  Evaluator spend: ___.
- Did the evaluator's yes/no decisions track reality each turn? Any false yes or false no,
  and what was the stated reason?
- Final state: tests short/medium green? CODEREVIEW.md block/warn counts? SECURITY.md
  entry present? Commits (count, messages, attribution, pushed or not)?
- Scope respected? List any files touched outside the intended set.
- Did it correctly avoid push, Co-Authored-By, the `/spec` turn-boundary, and the GPU?
- Where, if anywhere, did the loop wander or burn a turn unproductively?
- Was the condition well-formed? What would you add or tighten next time (process hints,
  tighter scope, different turn cap)?
- Net verdict: would you reach for `/goal` again for this class of work (a written spec to
  a committed increment)? At what autonomy scope?
- Anything worth sending back to zat.env (for example, a `/spec goal` mode that emits a
  ready-to-paste condition from the current SPEC.md)?
