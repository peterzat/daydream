## Spec — 2026-05-07 — v0.2.0 cut: release notes, TESTING tier-count refresh, tag

**Goal:** Tag v0.2.0 at HEAD with a release-notes pass that captures everything since v0.1.0 (NPC memory subsystem, LLM-driven drift narrates, mood-aware canned fallback, drift polish round two, drift voice-bench harness, drift outcome observability, `bin/install-hooks`, memory salience drift probe). The release-notes update folds into README.md's existing Release notes section; TESTING.md's tier-count contract refreshes from v0.1.0's frozen numbers (290/401/411) to v0.2.0's current reality (320/451/460). Git tag is local-only — pushing is a separate operator action.

### Acceptance Criteria

- [x] **README.md "Latest stable cut" line names v0.2.0.** Line ~11 currently reads `Latest stable cut: **v0.1.0**`; updates to `**v0.2.0**`. The accompanying tier-count phrase already reads "320 fast tests... 451 integration tests" (rolled forward in earlier turns), so no number change there — just the version label.

- [x] **README.md adds a "v0.2.0 — second inhabited dream" (or similarly named) release-notes section** above the v0.1.0 section. Captures the deltas since v0.1.0: NPC dialogue memory subsystem (per-world `memories` table, BGE-small CPU embedder, cosine + 24h recency-decay ranking, fail-closed); LLM-driven drift narrates with mood-aware canned fallback (drift composes via LLM from memories + mood, falls back to mood-bucketed canned pool on banlist hit / vLLM down / empty narrate); drift polish (per-NPC weights, room-occupancy suppression, mood-affecting drift via probabilistic transitions); drift voice-bench harness (`bin/game drift-samples` writes dated markdown under `docs/pretty/drift-voice-samples/`); drift outcome observability (`/status/drift` endpoint + `bin/game status` one-liner); `bin/install-hooks` (idempotent pre-commit + pre-push installer). Also notes any deliberate exclusions / "what we learned." Section length proportional to v0.1.0's section; not a full rewrite.

- [x] **README.md "What works today" bullets at the top remain consistent with the v0.2.0 release notes.** The Status section bullets (lines ~13-23) already reflect the current state (drift bullet mentions LLM + occupancy + mood-drift; NPC dialogue memory bullet present). Spot-check that no bullet contradicts what the v0.2.0 release notes claim shipped. If the bullets are accurate, no edit needed; if not, refresh them in the same change.

- [x] **TESTING.md tier-count references roll forward from v0.1.0 to v0.2.0.** Lines that say "at v0.1.0" with counts 290 / 401 / 411 update to "at v0.2.0" with 320 / 451 / 460 (or whatever the current `bin/game test short / medium / long` reality is at end of turn). Specifically: line 58 ("Cold-open" expected count), lines 117 / 125 / 133 (per-tier "Test count at v0.1.0" annotations), and line 267 ("~401 tests" reference). Verify each by running the corresponding `bin/game test <tier>` (or `--collect-only` for tier_long which needs engines) and substituting the actual count. The `tier_long` count includes engine-up probes; if engines are down at update time, derive the number from `pytest -m 'tier_short or tier_medium or tier_long' --collect-only`.

- [x] **Git tag `v0.2.0` created at HEAD.** Local tag (annotated, with a one-line message naming the release) created via `git tag -a v0.2.0 -m "..."`. Tag is NOT pushed to origin — pushing tags is an operator-explicit action, separate from this spec. The tag's commit must be the commit that lands these README + TESTING updates (operator picks: tag the README/TESTING commit directly, or tag a separate "v0.2.0 release-notes" commit).

- [x] **`bin/game test short` and `bin/game test medium` stay green.** Pure docs + tag turn; no code changes. Tier counts at end-of-turn equal whatever this spec's commit landed with.

### Context

**Why v0.2.0 now.** v0.1.0 was tagged at `6daea43` (NPC drift loop pre-canned, image-gen pipeline, multi-room world, two NPCs). Since then six bundled feature turns landed: NPC memory (`7ae5836`/`7e130ae`), LLM-driven drift (`220d4fc`), drift polish round two + drift instrumentation (`c8f66d4`), plus tooling (`f52a424` install-hooks, `2f9f825` memory probe). Each turn was small and self-contained but their combined surface ("the world remembers, drifts, suppresses in-frame, and is observable") is substantively a release. Cutting now anchors the dialogue + drift + memory triple as the v0.2.0 baseline before further feature work would muddy the boundary.

**TESTING.md ship-count semantics.** The four "at v0.1.0" annotations were written by `/tester design 2026-04-23` to pin the test contract at a specific snapshot. They're useful exactly because they're frozen — they let an operator say "this is what the contract looked like at v0.1.0 ship." For v0.2.0 to be the new reference, those annotations migrate forward. The historical v0.1.0 numbers can be dropped entirely (they live in git history) or briefly noted; implementer's call. Lighter is better.

**Tag-without-push convention.** Local tags are reversible (`git tag -d`); pushed tags are not (`git push origin :refs/tags/v0.2.0` works but conventions discourage tag-rewrites). The spec creates the local tag; pushing it is a separate operator action that should happen after a quick verification (`git show v0.2.0` + maybe a `bin/game test medium` pass on a clean checkout). Pushing the tag mirrors how `git push` itself was a separate explicit step in prior turns.

**No CHANGELOG.md.** v0.1.0 used the README's Release notes section for what shipped. v0.2.0 uses the same surface. A separate CHANGELOG.md becomes worth its keep when the README's section grows past one screen of release notes; not yet.

**Out of scope** (deferred):
- CHANGELOG.md split (defer per above).
- Push the tag to origin (operator action).
- A pre-tag /codereview pass — the most recent codereview at `97698ea` already covers everything in the v0.2.0 cut. Re-running would be busywork.
- Drift voice-bench baseline capture (operator session — separate from the cut).
- TESTING.md `/tester design` full re-review. v0.2.0 just refreshes tier counts; a full strategy review is a separate spec when the test architecture itself changes.
- README "What's next" bullet refresh — already current after this turn's prior edits.

**Critical files to modify:**
- `README.md` (status line + new release-notes section)
- `TESTING.md` (tier-count refresh, ~5 lines)
- New git tag `v0.2.0`

---
*Prior spec (2026-05-07): Drift instrumentation: voice-bench harness + outcome observability closed 7/7. `daydream/drift.py` extracted `_render_drift_prompt(npc, memories)` pure helper + `_TICK_COUNTS` outcome counters (`llm_emit`/`canned_fallback`/`noop`). `daydream/drift_samples.py` voice-bench harness mirroring `voice_samples.py`; 5-prompt corpus at `tests/drift/drift-voice/`. `/status/drift` endpoint + `bin/game status` one-liner. 30 new tests; tier_short 297→320, tier_medium 413→451.*

<!-- SPEC_META: {"date":"2026-05-07","title":"v0.2.0 cut: release notes, TESTING tier-count refresh, tag","criteria_total":6,"criteria_met":6} -->
