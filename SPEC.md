## Spec — 2026-05-07 — Drift instrumentation: voice-bench harness + outcome observability

**Goal:** Two complementary drift instrumentation pieces. (1) A drift voice-bench harness that renders the LLM-driven drift path against a small fixed corpus and writes a dated markdown file under `docs/pretty/drift-voice-samples/`, mirroring the existing dialogue voice-bench so tone drift in drift-narrate output is eyeball-diffable across model swaps. (2) Module-level outcome counters in `daydream/drift.py` (LLM-emit, canned-fallback, no-op) surfaced via `bin/game status` so an operator can answer "how often is drift falling back to canned?" without reading logs. Realizes proposal items 3 + 4 from the prior turn.

### Acceptance Criteria

- [x] **Drift voice-bench corpus at `tests/drift/drift-voice/` (5 JSON prompts).** Each corpus file specifies `{name, npc_id, mood, memories: [str], doc}` where `memories` is a list of strings (each becomes the `text` field of a synthetic `Memory` injected into the drift prompt). The 5 prompts collectively vary three axes: (a) populated memories vs. empty memories list; (b) Rook (`t-rook`, mood `content`) vs. Iris (`t-iris`, mood `thoughtful`) — at least one each; (c) at least one prompt with a non-default mood (e.g., Rook with `mood = "weary"`) so a mood-only drift bias is captured. Files mirror the layout of `tests/drift/voice/*.json`. The corpus is git-tracked and stable; refreshing it is a review event by design.

- [x] **`daydream/drift.py` extracts a pure `_render_drift_prompt(npc, memories) -> str` helper.** The existing `_llm_narrate` is refactored so prompt rendering is callable without a DB connection. Signature: `_render_drift_prompt(npc: dict, memories: list[Memory]) -> str` returns the user-prompt string ready to send to `acompletion_json`. The function signature accepts any dict-shaped npc with the same keys `_llm_narrate` already uses (`name`, `seed`, `mood`) and any iterable of `Memory`-shaped objects (uses `.text`). `_llm_narrate` keeps its existing fail-closed contract; only the rendering step is extracted.

- [x] **New `bin/game drift-samples` entry point + harness module.** `bin/game` adds a `drift-samples` subcommand that delegates to a new module (e.g., `daydream/drift_samples.py` mirroring `daydream/voice_samples.py`). The harness probes vLLM via the existing pattern (2 s timeout against `<base>/models`) and fails with a clear actionable error if vLLM is unreachable. For each corpus file it builds a synthetic NPC dict + `Memory` list from the JSON, calls `_render_drift_prompt` then `acompletion_json` then `safety.first_banned`, captures the result + per-prompt metrics (wall-time and `llm_client.get_last_usage` for prompt/completion tokens), and writes the output. The harness does NOT touch the DB and does NOT take the GPU arbiter directly (the arbiter is held inside `acompletion_json`).

- [x] **Output: `docs/pretty/drift-voice-samples/YYYY-MM-DD-<model_slug>.md` deterministic and re-run-overwrite.** Same shape as `docs/pretty/voice-samples/`: front-matter capturing the model slug + vLLM flags + harness version, a metrics table (per-prompt latency + token counts + emit-or-fallback verdict), and per-prompt sections rendering the corpus metadata + the LLM's `narrate` text verbatim. When the parsed `narrate` trips the banlist OR is empty / non-string, the section captures "FALLBACK: <reason>" instead of a narrate so the markdown captures the failure mode for diff. Same model on the same day overwrites; different models on the same day land in distinct files (slug-disambiguated) for git-diff A/B.

- [x] **Module-level outcome counters in `daydream/drift.py`.** Add `_TICK_COUNTS: dict[str, int]` with keys at minimum `llm_emit`, `canned_fallback`, `noop` (initialized to 0 at module import). `_tick` increments exactly one key per call: `llm_emit` when the LLM path succeeded and emitted, `canned_fallback` when the LLM path failed (any reason) and the canned line emitted, `noop` when no narrate fired (no eligible NPCs, all-zero weights, all pools empty). Counters are process-local (asyncio single-thread, no lock needed); reset on process restart. A small accessor `tick_counts() -> dict[str, int]` returns a copy. A `reset_tick_counts()` test helper resets all keys to 0.

- [x] **`bin/game status` surfaces drift outcome counters when non-zero.** When any `_TICK_COUNTS` value is non-zero (i.e., drift has fired at least once since process start), `bin/game status` prints a one-line summary: e.g., `drift: 12 emits / 3 fallback / 1 noop (since boot)`. Zero-state (drift hasn't ticked yet) is silent — no extra line. Status output is fetched from the running daydream process via an existing endpoint or a new lightweight `/status/drift` JSON endpoint (implementer picks; either pattern matches existing project style). Tests pin the status-output format with a counter-injected fixture.

- [x] **Tests cover counter increments + harness rendering; existing 36 drift+toons tests stay green.** New tests in `tests/test_drift.py` (or focused module if it grows): tier_short tests that drive `_tick` through each branch (LLM emit, fallback, no-op) and assert the corresponding counter increments by exactly 1 and the others by 0. Tier_short test for `_render_drift_prompt` correctness (with and without memories). Tier_medium test for the `bin/game status` rendering of the counters (mocked counter values; no live process required). The harness module gets a tier_short smoke test that mocks `acompletion_json` end-to-end and asserts the markdown shape (no real vLLM). All existing 19 drift tests + 3 toons tests + the LLM-driven path tests stay green.

### Context

**Why these two together.** Both are drift-instrumentation, both touch `daydream/drift.py` lightly, both have a similar "fast feedback loop on drift quality" rationale. Bundling keeps the SPEC turn cycle short and the implementer's mental model coherent. The voice-bench captures *qualitative* drift output (does the LLM sound on-tone?) while the counters capture *quantitative* drift health (is the LLM-path actually firing or always falling back?).

**Why not seed memories into a DB instead of synthetic injection.** The voice-bench harness should be hermetic: the captured output should reflect the prompt that the production code would build for the given memories, not whatever ranking comes out of a particular DB state. Refactoring `_llm_narrate` to expose `_render_drift_prompt(npc, memories)` makes the harness independent of memory-store state, mirroring how `voice_samples.py` is independent of the operator's installed `skills/rook.json` (it installs the in-tree file into a tmp DB).

**Counter scope: process-local only.** The counters reset on every `bin/game up`. v0 doesn't try to persist them across restarts because (a) drift is a long-tail observability signal where session-fresh data is what matters; (b) any DB-backed counter would need migration, locking, and another `daydream.gpu.arbiter` consideration, none of which earns its keep yet. If multi-restart trends become useful, that's a separate spec.

**Counter outcome categories.** Three categories cover all `_tick` branches:
- `llm_emit`: LLM path returned a non-None narrate string AND that narrate was emitted via `events.append`.
- `canned_fallback`: LLM path returned None (failure / banlist / empty) AND the canned-pool fallback emitted a narrate via `events.append`.
- `noop`: tick returned False (no eligible NPCs, all-zero weights, empty pool, all rooms occupied, etc.) — nothing emitted.

The categories are mutually exclusive and exhaustive — every tick increments exactly one. With `DAYDREAM_DRIFT_LLM_ENABLED=0`, `llm_emit` stays at 0 and only `canned_fallback` (or `noop`) increment.

**`bin/game status` extension is small.** The existing status output is a few lines (server PID, port, access mode, etc.). Appending one drift-stats line when counters are non-zero is a few lines of code in `bin/game cmd_status` reading a new endpoint. Implementer can either add `/status/drift` (returns `{"emits": N, "fallback": N, "noop": N}`) or extend an existing status endpoint — the spec doesn't pin the wire format.

**Voice-bench output shape parallel to `voice-samples`.** The existing `docs/pretty/voice-samples/*.md` is the prior art. New file follows the same visual conventions (front-matter, metrics table, per-prompt sections) so an operator's mental model from voice-samples carries over. The 5 corpus prompts × 1 model run = 5 narrates per run, takes ~5-10 s on the live stack — same order as voice-samples.

**No GPU arbiter contention from the harness.** `_render_drift_prompt` is pure; `acompletion_json` already takes the arbiter inside. The harness invokes them in sequence per prompt; if both the harness and the running daydream server compete for the GPU, the arbiter serializes them as designed. Operators running the harness against a vLLM serving the live game accept some narrate latency uptick during the run.

**Out of scope for this spec** (deferred):
- Counter persistence across `bin/game up/down` cycles. v0 process-local.
- Per-NPC counter breakdowns (Rook vs. Iris emit rates separately). v0 aggregate.
- Drift voice-bench A/B regression detection (a la `tests/test_voice_baseline.py`). The current voice-bench has the regression-tracker; a parallel one for drift-voice can land once 2+ drift-voice baselines exist to compare.
- LLM-driven mood-drift (LLM picks the new mood). v0 is random pick from buckets.
- Drift narrates captured into `memories` (closed loop). Stays one-way.
- `bin/game drift-stats` standalone command. The status one-liner is enough at v0; a dedicated subcommand earns its keep when the data is rich enough to pivot on.
- Wider mood-vocabulary expansion in `_DRIFT_POOLS`. Stays at content/thoughtful/default per NPC.

**Critical files to modify:**
- `daydream/drift.py` — extract `_render_drift_prompt`, add `_TICK_COUNTS` + accessors + `_tick` increments
- `daydream/drift_samples.py` (new) — voice-bench module mirroring `daydream/voice_samples.py`
- `tests/drift/drift-voice/*.json` (new corpus, 5 files)
- `bin/game` — add `drift-samples` subcommand + status one-liner extension
- `tests/test_drift.py` — counter increment tests + `_render_drift_prompt` test + harness smoke
- `tests/test_drift_samples.py` (new) — harness rendering smoke test
- `README.md` — drift bullet may grow a final clause; tier counts roll forward at end-of-turn

**zat.env conventions to respect.** Small committable increments: natural splits are C1+C2 (corpus + render extraction); C3+C4 (harness + entry point); C5+C6 (counters + status surface); C7 (tests). Bundle if a single commit reads cleanly. Commits attribute to `user.name` only. Verify `bin/game test short` + `medium` pass before each commit. The voice-bench harness mirrors an existing pattern; do not invent a parallel pattern. Counters are simple module-level dict — no metrics framework, no dependencies.

---
*Prior spec (2026-05-07): Drift polish round two: per-NPC cadence, room-occupancy suppression, mood-affecting drift closed 6/6. `daydream/drift.py` adds weighted NPC selection (`_NPC_DRIFT_WEIGHT` + `_pick_npc`), room-occupancy suppression (`_occupied_room_ids` + `_eligible_npcs` filter; toggle `DAYDREAM_DRIFT_SUPPRESS_OCCUPIED`), and probabilistic mood transitions (`_maybe_transition_mood` + new `daydream/toons.py:set_mood` helper; toggles `DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED` + `_PROB`). 17 new drift tests + 3 toons tests; tier_short 297→305, tier_medium 413→430.*

<!-- SPEC_META: {"date":"2026-05-07","title":"Drift instrumentation: voice-bench harness + outcome observability","criteria_total":7,"criteria_met":7} -->
