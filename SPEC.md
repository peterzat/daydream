## Spec — 2026-05-07 — drift-bootstrapped-npcs: drift loop covers any NPC, not just `t-rook` / `t-iris`

**Goal:** Bootstrapped NPCs (added via `bin/game world bootstrap`, ids shaped like `t-<slug>-<uuid>`) need to drift. Today `daydream/drift.py:_eligible_npcs` filters out any NPC missing from `_DRIFT_POOLS`, so bootstrapped NPCs are never selected for a tick — even when the LLM-driven branch is enabled. Open eligibility to all NPCs and add a generic mood-bucketed canned pool with `{name}` interpolation so the canned fallback works when vLLM is down. The hand-authored `t-rook` / `t-iris` pools remain the per-NPC voice; the generic pool is the safety net.

### Acceptance Criteria

- [ ] **Eligibility no longer requires per-NPC pool entry.** `daydream/drift.py:_eligible_npcs` returns every NPC that is `is_human_controlled=0` AND `kicked_at IS NULL` AND (when occupancy suppression is on) whose `current_room_id` is not in `_occupied_room_ids()`. The `_DRIFT_POOLS` membership check is removed from this function. Rook / Iris pick up the right per-NPC pool downstream as before; bootstrapped NPCs become eligible for selection.

- [ ] **`_GENERIC_DRIFT_POOL` constant ships in `daydream/drift.py`.** Mood buckets `content`, `thoughtful`, `curious`, `default`, each with ≥ 3 single-sentence WHIMSY-locked lines (third-person body language, no quoted dialogue, no urgency, no modern tech, no harsh / sexual content; soft, painterly, Spiritfarer / A Short Hike-adjacent), totaling ≥ 12 lines. Each line contains the literal token `{name}` at least once.

- [ ] **`_pick_canned_line` falls through to `_GENERIC_DRIFT_POOL` when the NPC has no per-NPC pool entry.** Bucket-selection rule for the generic pool mirrors the per-NPC rule: prefer the bucket matching `mood`; fall back to `default`; then walk all buckets and pick from the first non-empty one. The chosen line has `{name}` substituted with the toon's name via `str.replace("{name}", name)` (NOT `str.format`), so a name containing `{` or `}` does not crash. The function takes a new `name: str | None = None` parameter so call sites pass the toon name through; when `name` is None the substitution is skipped. Returns `None` only when both per-NPC and generic pools are entirely empty (defense in depth; not reachable in practice).

- [ ] **`_maybe_transition_mood` uses generic-pool keys when the NPC has no per-NPC pool.** Transition target is drawn from `_GENERIC_DRIFT_POOL.keys()` minus `default` minus the current mood when `_DRIFT_POOLS.get(npc["id"])` is None. Existing Rook / Iris mood-drift behavior (drawn from their own pool's keys) is unchanged. Returns None when no eligible target remains, same as today.

- [ ] **`_tick` plumbs the toon's name into `_pick_canned_line` without changing the counter contract.** `_TICK_COUNTS["canned_fallback"]` increments on a generic-pool emit (it is the canned path, just generic). `llm_emit` increments only when `_llm_narrate` produced text. `noop` still fires when no eligible NPC exists OR both LLM and canned paths yielded nothing.

- [ ] **Tests cover the bootstrapped-NPC paths.** New / updated tests in `tests/test_drift.py` (tier_short, no GPU, no real LLM): (a) `_pick_canned_line("t-foo", "curious", name="Foo")` returns one of `_GENERIC_DRIFT_POOL["curious"]` with `{name}` replaced by `Foo`; (b) `_pick_canned_line` with `name="Q{x}Q"` returns without crashing and the result contains the literal `Q{x}Q`; (c) a bootstrapped-NPC DB fixture (id `t-test-abc123`, slot 100, mood `curious`, world `w-bunny`) is selected by `_tick` and emits a generic-pool narrate when `_llm_narrate` is patched to return None; (d) same NPC emits the LLM text when `_llm_narrate` is patched to return a string; (e) `_maybe_transition_mood` for the bootstrapped NPC returns one of `_GENERIC_DRIFT_POOL.keys() - {"default", "curious"}` (RNG seeded so the toggle / probability fire); (f) `test_pick_canned_line_returns_none_for_unknown_npc` is replaced or renamed since the new behavior is "returns generic-pool line", not None — its replacement asserts the generic-pool fall-through. At least 5 new tests; the existing Rook / Iris drift tests stay green unchanged.

- [ ] **`bin/game test short` / `medium` stay green; README rolls forward.** No new GPU dependencies, no new real-network tests, no new env toggles. Tier counts roll forward in README at end-of-turn. The drift bullet in README is updated with one phrase noting that bootstrapped NPCs drift via a generic mood-bucketed pool when the LLM is unavailable.

### Context

**Why now.** `world-bootstrap-opus` shipped earlier this same day (uncommitted at this writing). Bootstrapped NPCs have ids shaped `t-<slug>-<uuid>` which are not keys in `_DRIFT_POOLS`. Reading `_eligible_npcs` shows the `_DRIFT_POOLS.get(n["id"])` membership test is on the eligibility hot path — not the canned-fallback hot path — so bootstrapped NPCs are filtered out BEFORE the LLM branch even gets a chance to run. This is a real bug for the bootstrapped-world flow, not the graceful-degradation-only edge the proposal first sketched.

**Why a generic pool over LLM-only.** Two design options were on the table per the proposal: (1) generic-canned-line fallback (this spec); (2) drift becomes LLM-only when the world has no per-NPC canned pool, with a hard vLLM dependency. Option 1 wins because it preserves daydream's existing fail-closed posture: if vLLM is unreachable — first boot before `bin/game vllm-up`, transient OOM, model swap mid-session, fp8-KV regression hunting — bootstrapped worlds keep drifting via the canned path. The cost is one new constant of generic body-language lines.

**Voice trade-off.** Per-NPC pools (Rook's anvil / forge imagery; Iris's letters / postcards) are tone-locked to each character. The generic pool cannot be that specific. It carries voice-neutral body-language beats that work for any name: e.g., `"{name} pauses to listen to the rafters."`, `"{name} runs a thumb along the back of their hand, distracted."` Hand-authored pools remain the preferred voice; the generic pool is the safety net for bootstrapped NPCs, whose voice mostly comes through the LLM path anyway (where `npc.seed` drives composition).

**Substitution mechanism.** `str.replace("{name}", name)` not `str.format(name=name)`. A curly-brace in a generated name would crash `.format()`; `.replace` is a no-op when the line has no `{name}` token, so future generic pools without interpolation still work. The `name=None` arg lets the LLM-output post-processing (which doesn't need substitution) pass through cleanly; today no caller takes this path but the signature is forward-compatible.

**No new env toggles, no schema change.** Eligibility opening is unconditional; the generic pool ships alongside the per-NPC pool; tests keep using `DAYDREAM_DRIFT_LLM_ENABLED=0` to opt into the canned path. No migration. No worlds DB column.

**Counter contract.** Today `canned_fallback` means "per-NPC canned pool emit." After this spec it means "any canned-path emit (per-NPC OR generic)." The metric loses some granularity but stays useful for `bin/game status`. Splitting into two counters (`canned_per_npc` / `canned_generic`) is a separate diagnostics polish; v1 keeps it one bucket.

**Out of scope** (deferred):
- LLM-driven mood transitions (drawn from any seed-aware lookup rather than a fixed bucket set).
- Per-bootstrapped-world generic pools (e.g., a world with a stoic-samurai NPC wants different body-language beats from a shy-cottager NPC). The generic pool is one constant.
- Any change to the LLM-driven path. It already works for any NPC seed; this spec only opens eligibility and adds a canned fallback.
- Dynamic generic-pool generation (e.g., via Opus during bootstrap). v1 ships a hand-authored pool.
- Splitting the `canned_fallback` counter into per-NPC and generic buckets.

**Critical files to modify:**
- `daydream/drift.py` — add `_GENERIC_DRIFT_POOL`; modify `_eligible_npcs`, `_pick_canned_line`, `_maybe_transition_mood`, `_tick`.
- `tests/test_drift.py` — new tests covering generic-pool fall-through, name interpolation, curly-brace safety, bootstrapped-NPC tick, mood transition; replace `test_pick_canned_line_returns_none_for_unknown_npc`.
- `README.md` — drift-bullet phrase update + tier counts at end-of-turn.

---
*Prior spec (2026-05-07): world-bootstrap-opus closed 7/7 (uncommitted at this writing). `bin/game world bootstrap NAME --aesthetic "..."` calls Opus 4.7 via litellm, validates a strict-JSON envelope (5 rooms / 4 toons / items / 2 skills), and writes a fresh `.db` under `~/data/daydream/worlds-dev/` that drops in over `live.db` after `bin/game down`.*

<!-- SPEC_META: {"date":"2026-05-07","title":"drift-bootstrapped-npcs: drift loop covers any NPC, not just t-rook / t-iris","criteria_total":7,"criteria_met":0} -->
