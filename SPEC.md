## Spec — 2026-05-07 — NPC drift loop (v0: pre-canned narrates)

**Goal:** Add a background drift loop in `daydream/drift.py` that periodically emits soft narrate events from each NPC, integrated into FastAPI's lifespan. v0 pulls drift lines from a pre-canned per-NPC pool (no LLM call) so the loop never contends for the GPU arbiter, leaving the "drift uses LLM → must yield arbiter on player input" question for a future spec. Realizes the BACKLOG `npc-drift-loop` entry's gentle-drift cadence requirement (~5 min idle, ~30 min when humans present) and unblocks `npc-memory-retrieval` (gated on drift-loop landing).

### Acceptance Criteria

- [x] **`daydream/drift.py` ships an asyncio drift loop with FastAPI lifespan integration.** New module exposes `start_drift_loop()` (returns a handle the lifespan can later stop) and `stop_drift_loop(handle)` (cancels the task and awaits cleanup). `daydream/server.py`'s `lifespan` calls these symmetrically: `start` after `db.init_live()`, `stop` before `db.close_db()`. The loop is a single `asyncio.Task`; cancellation handled gracefully (`CancelledError` caught, task exits cleanly within ~1 s, no resource leaks). Each tick body is wrapped in a try/except that logs and continues, so one bad tick does not kill the loop.

- [x] **Cadence rule.** The loop sleeps `DAYDREAM_DRIFT_IDLE_SECONDS` (default 300, i.e., 5 min) when zero WS subscribers are connected; sleeps `DAYDREAM_DRIFT_BUSY_SECONDS` (default 1800, i.e., 30 min) when >=1 subscriber. The cadence decision is made at each wake-up (NOT at task start), so a connection that arrives mid-sleep takes effect on the next iteration. Subscriber count is read via `daydream.events` (currently `_subscribers` is a module-private list — implementer can add a small public `events.subscriber_count() -> int` accessor or read the existing API; the public/private call is the implementer's). The cadence calc is unit-testable with a mocked subscriber count.

- [x] **Each tick emits exactly one soft narrate event** via `daydream.events.append`, addressed to the chosen NPC's current room. Behavior: (a) select an NPC at random from the world's NPCs (toons with `is_human_controlled=0`); (b) draw a drift line from a per-NPC pool of >=3 lines for that NPC (where the pool lives is the implementer's call — `daydream/drift.py` constant dict, a new `toons.drift_lines_json` column, or per-NPC `skills/<npc>-drift.json` — picking the cheapest path that reads cleanly); (c) emit one `narrate` event for the NPC's `current_room_id`, broadcast to in-room WS subscribers via existing machinery. Empty pool for an NPC: skip and try the next NPC. World with zero NPCs (or all NPCs have empty pools): tick is a no-op, no events appended. NO LLM CALL — drift ticks are pre-canned text so the v0 loop never takes the GPU arbiter, satisfying the BACKLOG entry's "yield arbiter on player input" requirement vacuously. Pool size for the two existing NPCs (Rook, Iris) is at least 3 distinct lines each, in WHIMSY tone matching their voices.

- [x] **Tests cover cadence, tick emission, empty-world no-op, cancellation, and pool quality.** New `tests/test_drift.py` (`tier_short` where possible; `tier_medium` for the lifespan integration if needed):
   - Cadence: with subscriber count = 0, next-sleep-interval == idle default; with count >= 1, == busy default. Env-var override of either default takes effect.
   - Tick: with Rook and Iris seeded, one tick produces exactly one narrate event whose `room_id` matches the chosen NPC's `current_room_id` and whose text is from the NPC's drift pool. Random selection covered with a seeded `random` (or by stubbing the picker).
   - Empty-world: with no NPCs (or all pools empty), tick produces no events.
   - Cancellation: starting the loop, cancelling it, awaiting the task completes within ~1 s without unhandled exceptions.
   - Pool quality: each NPC's pool has >=3 distinct strings; no string is empty or whitespace-only. (Lightweight content-shape check, not WHIMSY-tone assertion.)

- [x] **Existing test suite stays green.** `bin/game test short` and `bin/game test medium` pass. Drift loop's default sleep interval (300 s idle) is far above any test's wall-clock budget, so the first tick never fires inside a test run by accident; if any test does run long enough or timing-sensitive enough that drift events leak in, the implementer adds an opt-out (e.g., `DAYDREAM_DRIFT_ENABLED=0` with a default of `1` and the tests' `conftest.py` setting it to `0`). `tests/test_ws_rook.py` and `tests/test_ws_iris.py` continue green; their event-draining helpers are not perturbed by drift events arriving during the short test windows. No new tier_long tests; no GPU-dependent tests added.

### Context

**Adopted from `### Proposal (2026-05-07)` option 1** (NPC drift loop). User explicitly chose this direction over the also-surfaced `watercolor-lora-ab` revisit candidate. BACKLOG manifest at consume: `npc-drift-loop` annotated ACTIVE in spec 2026-05-07 via `spec-backlog-apply.sh`'s adopt op (no deletes).

**Why now and what's actually possible.** The BACKLOG `npc-drift-loop` entry called for "APScheduler-driven background ticks (weather, NPC mood, in-world calendar) on the gentle drift cadence." For v0 we narrow to NPC narrate emissions only — the simplest tick that's recognizable as "the world is alive." Weather and in-world calendar are not currently modeled in the schema; adding them is a separate scope. NPC mood drift (`toons.mood` UPDATE) is also feasible but invisible without a snapshot refresh; narrate emission is more directly demonstrable and reuses the existing room-broadcast machinery. APScheduler is heavier than v0 needs: a single `asyncio.Task` with a sleep loop is sufficient and adds no new dependency.

**Two NPCs are the activating signal.** Iris joined Rook in the just-shipped second-NPC spec (commit `8de1713`), satisfying the BACKLOG entry's `>=2 NPCs in the world` revisit gate. With a single NPC the drift loop would feel like a soliloquy; with two NPCs in different rooms (Rook at `r-forge`, Iris at `r-attic`), drift emits give the world a sense of activity even while the player is somewhere else.

**No GPU arbiter contention by design (v0).** The BACKLOG entry's "drift loop must yield the GPU lock immediately on player input" requirement assumes drift ticks use the LLM. v0 ticks pull pre-canned text from a per-NPC pool, so they never call `daydream.gpu.arbiter.acquire()`; player input contention is impossible. When a future spec wants LLM-driven drift (richer voice, generated reactions, mood-aware narration), the arbiter-yielding requirement re-activates and lands as a separate increment.

**Subscriber count is the cadence signal.** The events module has `_subscribers: list[asyncio.Queue]` (line 54 of `daydream/events.py`); reading `len(events._subscribers)` gives the current count. The implementer either uses that directly or adds a small public `events.subscriber_count() -> int`. The choice doesn't change the contract; only the internal call site.

**Pool location** is a tradeoff the implementer picks:
- A constant dict in `daydream/drift.py` (e.g., `DRIFT_POOLS = {"t-rook": [...], "t-iris": [...]}`) is cheapest. Lives close to the loop. Editing means a code change.
- A new `toons.drift_lines_json` column (migration 009) puts the data with the NPC; editing means a migration or admin-CLI update. Heavier but more authorable.
- Per-NPC `skills/<npc>-drift.json` follows the data-skill pattern; admin CLI handles install. Heaviest but matches how `skills/rook.json` and `skills/iris.json` are managed.

For v0 the constant-dict path is a defensible default. If the implementer picks a column or skill file, that's also acceptable; the test for criterion 3 "draws from the pool" doesn't care where the pool lives.

**zat.env conventions to respect.**
- Small committable increments. Natural split: drift module + lifespan + tests as C1; pool-content polish (e.g., adding more lines or tone-tuning) as C2 if needed.
- Commits attribute to `user.name` only; no Co-Authored-By trailers.
- Verify build + tests pass before each commit.
- Do not introduce abstractions for v0. No APScheduler, no plugin registry for tick types; one tick type (narrate emission), one cadence rule, one Task.
- Do NOT take the GPU arbiter in v0 drift code. The arbiter wraps LLM and image-gen calls only; drift ticks don't do either.

**Out of scope for this spec** (deferred):
- LLM-driven drift ticks (richer voice; would need GPU arbiter yielding + a different concurrency model). Separate future spec.
- Weather and in-world calendar tick types. The BACKLOG entry references them; v0 ships the narrate emission tick only.
- Mood transitions driven by drift (UPDATE `toons.mood`). Future spec.
- Drift across multiple worlds. Single-world for v0.
- Authoring UI for drift pools. Implementer picks the pool location; editing is operator-side.
- Per-NPC cadence overrides. All NPCs drift at the same global cadence in v0.
- Drift sensitivity to room state (e.g., suppress drift when player is in the NPC's room and just talked). Future polish.
- Updating `npc-memory-retrieval` BACKLOG status note to reflect the drift-loop landing. Implicit when this spec ships; no entry-text edit required.

**Critical files to create:**
- `daydream/drift.py` (criterion 1)
- `tests/test_drift.py` (criterion 4)

**Critical files to modify:**
- `daydream/server.py` (criterion 1; lifespan hook)
- Possibly `daydream/events.py` (small public `subscriber_count()` accessor; implementer's call)

### Findings (2026-05-07)

All five criteria met in one pass; drift loop ships in v0 shape with the design constraints from the spec held intact.

- **C1 (`daydream/drift.py` + lifespan):** New module with `start_drift_loop()` / `stop_drift_loop(handle)`; the loop body is a `while True: sleep → tick → loop`, with `asyncio.CancelledError` propagation handled via try/except patterns that re-raise the cancel signal but swallow normal tick exceptions. `daydream/server.py:lifespan` wires it: `start` after `db.init_live()`, `stop` in a `finally` block before `db.close_db()`. The disabled-via-env-var path returns `None` so `stop_drift_loop(None)` is a clean no-op.
- **C2 (cadence rule):** `_compute_next_interval(subscriber_count)` is a pure function reading the env var on each call; tests cover both branches at default and with overrides.
- **C3 (tick behavior):** `_tick(rng=None)` picks a random eligible NPC (filtered to those with non-empty pools), draws a line, emits one `narrate` via `events.append`. Pool location: constant dict at module top (`_DRIFT_POOLS`) — the cheapest of the three documented options. Rook + Iris each have 4 pre-canned lines in their voice register (matching the prompt-template variety lessons: kind-specific anchors, no shared opener phrases). Empty-world is a no-op (`_tick` returns False without appending).
- **C4 (tests):** `tests/test_drift.py` with 8 tests (3 cadence pure-function, 2 tick DB-interaction, 1 pool-quality, 2 cancellation/disabled). Cadence + pool-quality + cancellation tests are `tier_short`; tick tests are `tier_medium` (touch the DB).
- **C5 (tests stay green):** `bin/game test short` 277 passed (was 271; +6 new tier_short drift tests). `bin/game test medium` 376 passed (was 368; +8 new tier_medium drift tests + the tier_short ones run too). Drift is OFF in tests by default via `tests/conftest.py:42` setting `DAYDREAM_DRIFT_ENABLED=0`; tests that exercise drift (the cancellation test, `test_drift.py:test_drift_loop_cancels_cleanly`) opt in explicitly via `monkeypatch.setenv`.

**Side effects.** Added `events.subscriber_count() -> int` (3-line public accessor) so drift doesn't reach into module-private state. No other API changes.

**Unblocked.** BACKLOG `npc-memory-retrieval` revisit gate (`npc-drift-loop landed`) now satisfied. Natural next-turn candidate.

---
*Prior spec (2026-05-07): Second NPC (Iris, the attic archivist) closed 5/5. `migrations/008_second_npc.sql` adds `t-iris` at slot 101 in `r-attic` (mood `thoughtful` to differentiate from Rook); `skills/iris.json` authors voice differentiated from Rook on role + topical anchors + register, with the 2026-05-06 prompt-template-variety lessons baked in from version 1; `tests/test_ws_iris.py` mirrors `test_ws_rook.py` with 8 tests covering install + happy path + scoping + safety + refusal. No `daydream/api/ws.py` or `daydream/skills/data.py` changes — the data-skill pipeline + snapshot machinery generalize across NPCs as predicted.*

<!-- SPEC_META: {"date":"2026-05-07","title":"NPC drift loop (v0: pre-canned narrates)","criteria_total":5,"criteria_met":5} -->
