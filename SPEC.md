## Spec — 2026-05-07 — LLM-driven drift narrates with mood-aware canned fallback

**Goal:** Replace the pre-canned per-NPC drift pool with reactive narrate ticks composed by the LLM from each NPC's recent memory + mood, with the canned pool retained as a robust fallback for LLM-unavailable cycles. This closes the loop between the v0.1.0 memory subsystem and the drift loop's "world feels inhabited" goal — drifts surface micro-callbacks to recent dialogue instead of repeating from 4 strings — and folds in two small adjacent improvements (expanded mood-aware canned pool, README count drift). Realizes proposal items 1+2+3 from the prior turn.

### Acceptance Criteria

- [x] **`daydream/drift.py` calls the LLM (arbiter-wrapped) when enabled, falls back to the canned pool on any failure path.** A new branch in the per-tick path builds a tight narrate prompt from the chosen NPC's `name`, `seed`, `mood`, and up-to-K recent memories pulled from `memories.retrieve(npc_id, world_id, query_text=npc.seed, k=DAYDREAM_DRIFT_LLM_TOP_K)` (default `k=3`; using the NPC's seed as query text gives character-bias to retrieval and stays robust on empty memory stores). The LLM call uses `daydream.llm.client.acompletion_json` (which already wraps `arbiter.acquire()`). On `LLMUnavailable` (vLLM down, JSON parse failure, timeout), banlist hit on the parsed `narrate` text, or empty / whitespace-only `narrate`, the tick falls back to the canned-pool path. Both paths reach the same final `events.append(actor_type="system", actor_id=None, kind="narrate", payload={"text": ...}, room_id=npc.current_room_id)`. Per-tick exceptions outside `LLMUnavailable` are still caught and logged at the `_drift_loop` top-level handler so one bad tick does not kill the loop. `_list_npcs` is extended (or replaced by a sibling) to return `world_id` and `mood` alongside `id` and `current_room_id` so the LLM path has the data it needs without an extra DB round-trip per tick.

- [x] **`DAYDREAM_DRIFT_LLM_ENABLED` toggle gates the LLM branch independently of drift on/off and memory on/off.** Default `1` in production code, `0` in `tests/conftest.py` so the existing 5 drift tests + the 16 Rook/Iris dialogue tests are not perturbed. When `0`, every tick goes through the canned-pool path unconditionally (which is itself mood-aware per C3); the LLM client is never imported by the drift code path, and no `acompletion_json` call is issued. The toggle is decoupled from `DAYDREAM_DRIFT_ENABLED` (drift loop on/off) and `DAYDREAM_MEMORY_ENABLED` (memory subsystem on/off): with LLM enabled but memory disabled, drift still calls the LLM with empty memories (the prompt template renders cleanly with `memories=[]`); with memory enabled but LLM disabled, drift uses canned-pool. The matrix of `(drift, memory, LLM)` toggles never produces a crash on any combination — the overall guarantee remains "either a narrate fires or the tick is a logged no-op."

- [x] **Canned pool is mood-aware and expanded; ≥6 distinct lines per NPC across ≥3 buckets; selection biased by `toons.mood`.** `_DRIFT_POOLS` is restructured from `dict[str, list[str]]` to `dict[str, dict[str, list[str]]]` keyed by NPC id then by mood bucket. Each NPC has buckets for at least `content`, `thoughtful`, plus a `default` bucket; total distinct lines per NPC is ≥6 across all buckets. A new helper `_pick_canned_line(npc_id, mood, rng)` selects from the bucket matching `mood` exactly when present and non-empty, falling back to `default` when the mood is unknown or its bucket is empty. The existing 4 Rook lines carry forward into Rook's `content` bucket (Rook's mood per `migrations/006_first_npc.sql`); the existing 4 Iris lines carry forward into Iris's `thoughtful` bucket (Iris's mood per `migrations/008_second_npc.sql`); ≥2 new lines per NPC land in other buckets with WHIMSY-locked tone (single-sentence body-language beats in third-person prose, no quoted dialogue — drift remains ambient). The pool-quality test in `tests/test_drift.py` extends to assert the new shape and bucket counts.

- [x] **LLM narrate prompt is tight, JSON-shaped, role-separated, banlist-checked on output.** System prompt: short and tone-locked (cozy watercolor, Spiritfarer/A Short Hike, single-sentence body-language beat in third-person, NO quoted dialogue — same shape as a canned line but generated, distinct from the dialogue prompts which DO carry quoted dialogue). User prompt: rendered via `jinja2.sandbox.SandboxedEnvironment` (a module-level singleton in `drift.py` to keep the call site self-contained; mirrors `daydream/skills/data.py`'s `_jinja`) injecting `npc_name`, `npc_seed`, `npc_mood`, and `memories` (each `Memory.text` wrapped in `<memory>...</memory>` tags exactly as the dialogue templates do, so a stored prompt-injection cannot escape into the system role). Response shape: `{"narrate": "<single sentence>"}` parsed via `acompletion_json`. The parsed `narrate` is run through `daydream.llm.safety.first_banned` before emit; on hit OR empty / whitespace-only string, fall back to the canned-pool path. No `effects`/`refusal`/jsonschema machinery — drift is one narrate or nothing.

- [x] **Tests cover LLM path, fallback paths, mood-aware selection, empty memories, and toggle off.** New tests in `tests/test_drift.py`:
  - **LLM happy path (tier_medium):** mock `acompletion_json` to return `{"narrate": "Rook tilts the lamp's wick a half-turn brighter."}`; with `DAYDREAM_DRIFT_LLM_ENABLED=1` and seeded RNG so Rook is chosen; assert one new narrate event whose text is exactly the LLM's string and whose `room_id` is `t-rook.current_room_id`.
  - **Fallback on LLMUnavailable (tier_medium):** mock `acompletion_json` to raise `LLMUnavailable`; with LLM enabled; assert one narrate is still emitted and its text appears in the chosen NPC's mood bucket (or the `default` bucket) of `_DRIFT_POOLS`.
  - **Fallback on banlist hit (tier_short):** mock `acompletion_json` to return `{"narrate": "the dream feels uncannily pixel-art tonight"}` (hits the WHIMSY banlist on `pixel-art`); assert canned fallback fires (emitted text is from the canned pool, not the mocked LLM string).
  - **Fallback on empty narrate (tier_short):** mock `acompletion_json` to return `{"narrate": "   "}` (whitespace-only); assert canned fallback fires.
  - **Mood-aware canned selection (tier_short):** with LLM disabled, monkeypatch the chosen NPC's mood bucket selection to a non-default mood that has its own bucket (e.g., set Rook's mood to `thoughtful` via a direct DB UPDATE in the test); seed RNG; assert the picked line came from the matching bucket.
  - **Empty-memory LLM call (tier_medium):** with memory disabled OR a fresh world, assert the LLM is still called (its prompt rendered with `memories=[]`) and the LLM's narrate is emitted. Verifies the prompt template handles the empty branch.
  - **Toggle off goes straight to canned (tier_short):** with `DAYDREAM_DRIFT_LLM_ENABLED=0`, assert `acompletion_json` is never called (mock raises if invoked) and one canned line is still emitted.
  - **Pool-quality (tier_short, updated):** assert the new `dict[str, dict[str, list[str]]]` shape; for each NPC, ≥3 buckets present, ≥6 distinct non-empty string lines total; no duplicates across all buckets for one NPC.
  - The existing 5 drift tests (cadence rule x3, single-narrate emission, no-op-when-no-NPCs, cancel-cleanly, returns-none-when-disabled) stay green; cancel-cleanly continues to verify that adding the LLM path doesn't introduce a hang on cancellation.

- [x] **README count drift fixed in the same turn.** `README.md` cites v0.1.0 ship counts at lines ~11, ~105-106, and ~125 (290 / 401 short / medium). Update to current reality at end-of-turn after C5 tests land. The post-C5 counts will be approximately 298-300 short / 408-410 medium depending on how the new tests parametrize; the implementer rounds to the actual numbers from `bin/game test short` / `bin/game test medium` when committing. Bump in place rather than reframing as historical "v0.1.0 ship counts" — keeping the numbers live is cheaper than perpetually annotating them.

- [x] **`bin/game test short` and `bin/game test medium` stay green; no new GPU-required tests; no perturbation of existing 16 Rook/Iris dialogue tests.** All new tests mock `daydream.llm.client.acompletion_json` (typical pattern: `monkeypatch.setattr("daydream.llm.client.acompletion_json", AsyncMock(return_value=...))`); none require vLLM running. `tools/arbiter-smoke.py` is unaffected (it does not import `drift.py`). The 16 existing dialogue tests pass unchanged because they construct the data-skill pipeline directly, not through the drift loop.

### Context

**Why drift now uses memory + mood + LLM.** The v0.1.0 memory subsystem (migration 009 + `daydream/memories.py`) was sized for the dialogue path but is equally usable from drift. The natural payoff: a Rook who has just discussed iron with a visitor drifts about iron a few minutes later, not about a generic anvil tap. With the existing arbiter, this is purely additive — the drift LLM call serializes with player-driven LLM calls behind the same lock, so worst-case contention is "drift waits for player input to finish," which is the desired behavior (player-driven calls never block on drift).

**Why `npc.seed` as the retrieval query.** The seed is a stable, character-tinted description ("the forge-keeper; slow-moving and quiet; hums old songs..."). Using it as the embedding query gives mild semantic bias toward memories that share the NPC's character (work, quietness, hums) without requiring an explicit "topic" tag at capture. Empty memory store still returns `[]` cleanly. Mood-as-query was considered but mood is a single short token whose embedding is noisy compared to the seed's full-sentence character description.

**Why a separate `DAYDREAM_DRIFT_LLM_ENABLED` toggle.** The decision matrix for what should be on/off has three independent axes (drift loop running, memory store running, LLM-driven drift running). Collapsing any two would surface a "but I want X without Y" case the next time someone debugs against vLLM-down. Tests want LLM-driven drift OFF by default (mock-noise-free); production wants it ON; an operator running with vLLM down wants drift to keep emitting canned pool narrates without an extra crash report; all three want the toggle independent of the other two.

**Why a mood-bucketed canned pool.** Mood is a single small lever the canned path can use without LLM cost. Rook is `content`; Iris is `thoughtful`. Adding mood-keyed buckets means a future change like "set Rook's mood to `weary` after a long forging session" automatically tilts Rook's drift toward weary canned lines. The `default` bucket is the safety net for unknown moods (e.g., when v1 toon-slot-management lands and a kicked human's NPC inherits whatever mood it had at kick time).

**Drift narrate shape.** Distinct from dialogue narrates: drift is single-sentence, third-person prose, NO quoted dialogue, ambient body-language only. The existing canned pool establishes this shape ("Rook hums something low and slow under the bellows." vs. dialogue "...says, 'iron's a stubborn one today.'"). The LLM prompt explicitly forbids quoted dialogue so the LLM path can't drift toward dialogue shape.

**Arbiter contention bound.** Drift's LLM call is single-shot per tick (one acquire / one release). At the busy cadence (1 tick per 1800 s = 30 min), the additional arbiter pressure is negligible compared to player-driven inputs. At the idle cadence (1 tick per 300 s = 5 min) there is by definition no player demand, so contention is zero. No new arbiter machinery; the in-process `asyncio.Lock` in `daydream/gpu/arbiter.py` is sufficient.

**Test-architecture conventions to respect.**
- Small committable increments. Natural split: C1 (canned pool restructure to dict-of-dicts + mood-aware selection); C2 (LLM branch + JSON narrate prompt + banlist check); C3 (tests for both branches); C6 (README count fix); C7 (final tier short/medium green). Or bundle C1+C2 if the diff reads cleanly.
- Commits attribute to `user.name` only; no Co-Authored-By trailers (per `~/.claude/CLAUDE.md`).
- `bin/game test short` and `bin/game test medium` must pass before each commit.
- Do not introduce a new arbiter primitive; reuse the existing `daydream.gpu.arbiter.acquire` via `acompletion_json`.
- Drift LLM call uses `acompletion_json`; no direct `litellm.acompletion`.
- WHIMSY tone is load-bearing: drift narrates remain ambient (no urgency, no modern tech, no quoted dialogue, no harsh edges).

**Out of scope for this spec** (deferred):
- Drift-narrate capture into memory. The dialogue path captures memories; drift narrates are read-only from the memory store. v0 keeps drift one-way to avoid a self-amplifying loop where drift narrates dominate retrieval.
- Per-NPC cadence overrides (some NPCs drift faster than others). Single global cadence remains.
- Room-occupancy-based drift suppression (don't drift in a room where the player is). The existing WS broadcast machinery already filters out-of-room subscribers; drift in the player's room is a feature ("the world keeps moving while you're here"), not a bug. If it later feels intrusive, add a "no-drift-when-player-in-room" gate as a future spec.
- Mood-affecting drift (drift can change mood). Mood is read-only here; mood mutation lives in the `set_mood` effect dispatcher already.
- LanceDB swap for memory retrieval. v0 SQLite linear-scan stays sufficient.
- Voice-bench refresh against drift narrates. Existing dialogue voice-bench is unaffected; if drift narrates need their own audit-trail, that's a future spec.

**Critical files to modify:**
- `daydream/drift.py` (C1, C2, C4)
- `tests/test_drift.py` (C5, including pool-quality update)
- `tests/conftest.py` (C2; add `DAYDREAM_DRIFT_LLM_ENABLED=0` default)
- `README.md` (C6; count drift fix)
- `CLAUDE.md` (brief — drift section becomes "v1 LLM-driven, with mood-aware canned fallback"; the test-architecture sections are unchanged)

**Critical files to read (no edits expected):**
- `daydream/llm/client.py` — `acompletion_json` contract, `LLMUnavailable` exception, arbiter usage.
- `daydream/llm/safety.py` — `first_banned` for output check.
- `daydream/memories.py` — `retrieve` signature; module is fail-closed.
- `skills/rook.json`, `skills/iris.json` — `<memory>` role-separator pattern to mirror in the drift prompt.

---
*Prior spec (2026-05-07): NPC memory retrieval (v0: SQLite-blob embeddings) closed 7/7. `daydream/memories.py` ships capture + retrieve APIs (fail-closed, CPU-only, no GPU arbiter); migration 009 adds the per-world `memories` table with float32 BLOB embeddings; BGE-small lazy-loads from the shared HF cache; ranking is `cosine_similarity * exp(-age_hours/24)`; Rook/Iris templates wrap retrieved text in `<memory>` role-separator tags; `bin/memory-bootstrap` is the one-time CPU-torch + model install. Tests: 8 in `tests/test_memories.py` + integration in `test_ws_rook.py`; tier_short 291 / tier_medium 402 green at v0.1.0.*

### Proposal (2026-05-07)

**What happened.** LLM-driven drift narrates landed in `220d4fc` and `cfcd5f1`, closing this turn's spec 7/7. `daydream/drift.py` now runs a two-path tick: when `DAYDREAM_DRIFT_LLM_ENABLED=1` it pulls up to K recent memories via `memories.retrieve(query=npc.seed)`, renders a tight Jinja prompt (npc_name + seed + mood + `<memory>`-wrapped recents), calls `acompletion_json` (which holds the existing GPU arbiter), runs `safety.first_banned` on the parsed `narrate`, and emits; on any failure (`LLMUnavailable`, banlist hit, empty/missing narrate) it falls through to the canned path. The canned pool is now `dict[str, dict[str, list[str]]]` keyed by NPC then mood — Rook's 4 lines + Iris's 4 carried forward into their primary mood buckets, 4 new lines per NPC across `thoughtful`/`content`/`default`. The toggle matrix of `(drift, memory, LLM)` is decoupled (each axis controllable). 14 new tests + 5 carry-forwards, all `await drift._tick(...)`. Tier counts: short 291→297, medium 402→413; both green. README rolled forward at status + tests sections; v0.1.0 release-notes counts kept historical.

**Questions and directions.**

- **Code review the drift work.** Two-commit feature with a moderate-sized rewrite of `drift.py` and a near-rewrite of `tests/test_drift.py`. The natural next move is `/codereview` to surface BLOCK/WARN issues before any v0.2.0 cut. Fast feedback while context is warm.

- **Drift polish round two.** README "What's next" names three: per-NPC cadence overrides (Rook drifts faster than Iris if mood demands), room-occupancy-based suppression (don't drift in the room the player is currently in — could feel intrusive), mood-affecting drift (drift events nudge `toons.mood` over time so the canned-bucket selection drifts with the world). Largest UX impact is room-occupancy-based suppression. Likely 4-6 acceptance criteria.

- **Voice-bench harness for drift narrates.** The voice-bench at `tests/drift/voice/*.json` is dialogue-shaped (5 dialogue prompts, captures third-person + quoted dialogue). Drift narrates have a different shape (single-sentence body language, no dialogue). A separate `tests/drift/drift-narrate/*.json` corpus + `bin/game drift-samples` capture path would catch tone drift in the LLM-composed drift output the same way the existing harness catches it for dialogue.

- **v0.2.0 cut.** v0.1.0 is tagged at `6daea43`. LLM-driven drift + memory subsystem are the two big-ticket items since then. Worth a tag + release-notes pass once drift polish + a code review have landed.

- **Drift LLM observability.** `_llm_narrate` logs at info/warning. With drift now hitting the LLM, an op-visible counter for "how often does the canned-fallback path fire?" would catch regressions early (e.g., if a future Qwen swap starts tripping the banlist or returning malformed JSON). Could be a couple of module-level counters surfaced via `bin/game status` or a new `bin/game drift-stats` subcommand.

<!-- SPEC_META: {"date":"2026-05-07","title":"LLM-driven drift narrates with mood-aware canned fallback","criteria_total":7,"criteria_met":7} -->
