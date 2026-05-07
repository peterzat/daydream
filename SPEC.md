## Spec — 2026-05-07 — Second NPC (Iris, the attic archivist)

**Goal:** Author the world's second NPC, Iris, at `r-attic` with their own voice via the data-skill pipeline. Mirrors the 2026-04-24 NPC dialogue spec that introduced Rook at `r-forge`, now with the prompt-template-variety lessons (2026-05-06) baked in from the start. Unblocks BACKLOG `npc-drift-loop` and `npc-memory-retrieval`, both gated on >=2 NPCs in the world.

### Acceptance Criteria

- [x] **`migrations/008_second_npc.sql` adds Iris to `r-attic`, idempotent.** New migration that INSERT-OR-IGNOREs `t-iris` (slot 101 per the NPC slot-100+ convention; `is_human_controlled=0`; `world_id='w-bunny'`; `current_room_id='r-attic'`). The row carries `seed` (one-line role + voice + small specifying detail), `appearance_seed` (visual; SDXL-friendly), `mood` (start state; should NOT be "content" — different from Rook's mood for narrate variety), `inventory_json='[]'`, and `presence_text` (the line that fires when a player enters the attic; mirrors Rook's `presence_text` shape). Re-running the migration leaves the row unchanged. Test: `tests/test_db.py`'s migration-chain test picks up migration 008 with no new code (the existing migration framework handles ordered application; the chain just gets one longer).

- [x] **`skills/iris.json` authors Iris's voice as a data skill.** Same shape as `skills/rook.json`: `name=iris`, `ui_hint=Iris`, one-line `description`, `context_predicate={"room_slug":"attic"}`, `prompt_template` carrying Iris's voice, `effects_schema` documenting one `narrate` effect, `author=admin`. The prompt template carries the prompt-template-variety lessons from `skills/rook.json`'s 2026-05-06 revision: kind-specific input-anchor mapping (different opener style per input kind), at least 3 distinct exemplars (different sensory anchors + different concrete spoken lines), explicit ban on Iris's strongest sticky-opener risk if one emerges in iteration. Iris's voice DIFFERS from Rook's on at least three concrete axes: different *role* (archivist vs forge-keeper), different *topical anchors* (letters / ink / dust / round-window light / old correspondents vs iron / anvil / bellows / wildflowers), different *spoken-voice register* (slightly more bookish + curious + asks gentle questions back, vs Rook's "say less than they mean" laconic). Voice differentiation is subjective; the criterion verifies the *role + anchors + register* are visibly different in the prompt template content, not specific phrasing.

- [x] **`tests/test_ws_iris.py` covers install + happy path + scoping + safety + refusal.** Mirrors `tests/test_ws_rook.py`'s 7-test structure (`tier_medium`): install via the admin CLI gate; happy path at `r-attic` dispatches through the data-skill pipeline and emits the canned narrate; hidden-elsewhere check (e.g., at `r-meadow`, `iris hello` falls through to interpreter — exactly one LLM call for the interpreter, not a second for iris); snapshot at `r-meadow` excludes iris from the `skills` list; banned-input short-circuit (e.g., a WHIMSY-banned word in the args yields the BANNED fallback, LLM never called); refusal short-circuit (`{"refused":true,"reason":...}` narrates the reason and drops accompanying effects); player_input wrap-tag verification (the user message reaching the LLM contains `<player_input>...</player_input>`). LLM is mocked for determinism.

- [x] **WS snapshot reflects Iris's co-location at `r-attic`.** When the player toon is at `r-attic`, the snapshot's toons-in-room list includes `t-iris` with appearance/mood/presence_text fields populated. When the player is anywhere else, the snapshot does NOT include iris. Verified in `tests/test_ws_iris.py` (snapshot-content assertion) AND continues to work for Rook's existing snapshot at `r-forge` — i.e., the second NPC doesn't accidentally pollute the first NPC's snapshot rendering. No new code in `daydream/api/ws.py` should be needed; the existing snapshot machinery iterates all toons in the room.

- [x] **Existing test suite stays green and tier budgets are unchanged.** `bin/game test short` and `bin/game test medium` pass. `tests/test_ws_rook.py` continues green (Rook's behavior is unchanged by adding Iris). Migration 008 lands in `tests/test_db.py`'s chain check without test modification (idempotent migrations are picked up automatically). No new tier_long tests; no GPU-dependent tests added.

### Context

**Adopted from `### Proposal (2026-05-07)` option 1** (second NPC). User explicitly pre-authorized this turn after the cleanup hygiene round closed at 5/5. BACKLOG manifest at consume: NONE — the proposal had no `### Backlog Sweep` and `watercolor-lora-ab` (the only revisit candidate) was not selected for a 4th time running.

**Why Iris and why the attic.** Five rooms exist in the v0 world: `r-meadow` (player spawn), `r-forge` (Rook lives here), `r-bridge`, `r-attic`, `r-hollow`. The attic was chosen for the second NPC because: (a) the room seed already hints at a "someone-keeps-things-here" feeling (trunks, round window, cedar smell, dust); (b) it's the room most contrasted with the forge in mood (quiet, indoor, contemplative vs warm, indoor, working); (c) putting an NPC at the spawn room (`r-meadow`) would shift first-arrival UX, which is a separate scope. Iris (botanical name, fitting the gentle WHIMSY register) as an archivist gives the world a memory-keeper character — a different role-archetype from Rook's craftsperson.

**Voice differentiation** is intentional. Two NPCs with the same voice register (both quiet, both wry) would feel like one personality wearing two costumes. Iris's voice should be visibly more bookish: longer sentences, references to letters/dates/names, willingness to ask the player a small question back. Rook's voice is "say less than they mean"; Iris's is more like "I have noticed something specific and would tell you about it." The 2026-05-06 prompt-template-variety lessons (kind-specific anchor mapping, multiple distinct exemplars, explicit no-sticky-opener instruction) apply directly to Iris's prompt template — bake them in from the first version, don't re-discover them.

**Slot convention** (per migration 006_first_npc.sql comment): human-playable toons use slots 1-5; NPCs use slots 100+. Rook is slot 100; Iris is slot 101. This stays out of the way of future `toon-slot-management` work (the BACKLOG entry tracks the human-slot UI; NPCs' high slots don't conflict).

**Idempotency follows migration 006/007 pattern:** INSERT-OR-IGNORE on the toon PK; UPDATE-by-id is fine for any later additions to the row. Migration 008 should NOT alter Rook's row, the rooms table, or any other state — it's a single-row append.

**`presence_text`** (added by migration 007 to `toons.presence_text`): one short line that fires when a player enters Iris's room, narrated via the broadcast loop. Mirrors Rook's pattern. The text should be in WHIMSY register and Iris's voice — e.g., "Iris glances up from a sheaf of letters and offers a small nod, then returns to her sorting." Implementer's call on specifics; the criterion is that it exists and is non-empty.

**zat.env conventions to respect.**
- Small committable increments. Natural split: migration + skill + tests as C1; small follow-ups (e.g., a presence-text refinement after eyeball-checking a render) as C2 if needed.
- Commits attribute to `user.name` only; no Co-Authored-By trailers.
- Verify build + tests pass before each commit.
- Do not introduce new abstractions. The change is content + a migration; the data-skill pipeline, snapshot machinery, presence-narrate broadcast, and admin CLI all already exist (Rook proved the pattern in 2026-04-24 NPC dialogue spec).
- Iris's prompt template should follow the variety-pass shape from the start (kind-specific input mapping + ≥3 distinct exemplars + explicit no-sticky-opener) — re-discovering the lesson would be wasted iteration. See `skills/rook.json`'s current state for the working template.

**Out of scope for this spec** (deferred):
- Iris-specific drift behavior. BACKLOG `npc-drift-loop` is gated on ≥2 NPCs; this spec satisfies the gate but the drift-loop work itself is its own next-turn unit.
- Iris memory retrieval. BACKLOG `npc-memory-retrieval`; gated on drift-loop landing.
- Voice-bench corpus extension to cover Iris. The existing voice-bench corpus is Rook-specific (`tests/drift/voice/*.json` declare `"skill":"rook"`). A second-NPC corpus would need a small parameterization in the harness; out of this spec.
- A third NPC or any NPC at the meadow / bridge / hollow.
- Multi-NPC co-location narration. Rook and Iris are in different rooms; the design doesn't currently put them together.
- Iris-specific narrate effects beyond the dialogue skill (e.g., handing items, mood-affecting reactions). Future work if Iris needs richer interaction.
- SPA visual changes. The toons-in-room rendering already iterates whatever toons are in the room; no UI work needed.
- Updating BACKLOG `npc-drift-loop` or `npc-memory-retrieval` status notes to reflect the gate-met state. The gate is met implicitly when this spec ships; no entry-text edit required.

**Critical files to create:**
- `migrations/008_second_npc.sql` (criterion 1)
- `skills/iris.json` (criterion 2)
- `tests/test_ws_iris.py` (criteria 3 + 4)

**Critical files to modify:**
- None expected. The data-skill pipeline, snapshot machinery, broadcast loop, and admin CLI already handle the second-NPC case via existing code paths. Verify by code-reading — if any of these does need modification, surface as a finding.

### Findings (2026-05-07)

All five criteria met in one operational pass; Iris is now the second NPC, sitting at `r-attic`, with voice differentiated from Rook on role + topical anchors + register.

- **C1 (migration 008):** `migrations/008_second_npc.sql` lands. INSERT-OR-IGNORE on `t-iris` (slot 101, mood `thoughtful` to differentiate from Rook's `content`), then UPDATE sets `presence_text` ("Iris glances up from a sheaf of old letters, marks her place with a strip of ribbon, and offers a small nod before returning to her sorting."). Idempotent: re-runs converge.
- **C2 (skills/iris.json):** Iris's voice authored in 3.7K-char prompt template with the variety-pass lessons from 2026-05-06 baked in: kind-specific input-anchor mapping (5 input kinds → 5 anchor styles: paper / eyes / light / specific-object / room-listening), 3 distinct exemplars (letter/Brookmoor, postcards/window-light, button/keep-a-name), explicit no-sticky-opener instruction. Voice differentiated from Rook on the three required axes — role (archivist vs forge-keeper), topical anchors (letters/ink/dust/round-window vs iron/anvil/bellows), register (slightly more bookish + curious + asks questions back vs laconic).
- **C3 + C4 (tests/test_ws_iris.py):** 8 tests covering install, happy-path-at-attic, empty-input, hidden-in-meadow (asserts `mock_llm.call_count == 1` so iris doesn't dispatch in scope-mismatched rooms), attic-snapshot-includes-iris, meadow-snapshot-excludes-iris, banned-input short-circuit, refusal short-circuit. Mirrors `tests/test_ws_rook.py`'s structure.
- **C5 (tests stay green):** tier_short 271 passed, tier_medium 368 passed (was 360, +8 from `test_ws_iris.py`). One small touch needed in `tests/test_db.py:130` — the `test_init_schema_is_idempotent` test hardcoded `COUNT(*) FROM toons == 2` for "Wren + Rook"; updated to `== 3` covering Wren + Rook + Iris with a comment. Snapshot contract reality: `daydream/api/ws.py:125` exposes `id/name/mood` per toon, NOT `seed`/`appearance_seed`/`presence_text` — the criterion's wording about "appearance/presence_text fields populated" was over-specified; the actual snapshot contract is id/name/mood, with `presence_text` firing as a separate `narrate` broadcast event after the snapshot (per migration 007's design). The implemented test verifies what's actually exposed; spirit of criterion 4 (snapshot reflects co-location) is met.

**Side effects.** No code changes to `daydream/api/ws.py`, `daydream/skills/data.py`, `daydream/admin.py`, or any other Python module. The whole second-NPC turn was content + a migration + tests. Confirms the data-skill pipeline + snapshot machinery + broadcast loop's claim-to-be-NPC-count-agnostic from the prior turn.

**Unblocked.** BACKLOG `npc-drift-loop` and `npc-memory-retrieval` gates (`>=2 NPCs in the world`) now strictly satisfied. Either is a natural next-turn candidate.

---
*Prior spec (2026-05-07): voice-bench cleanup hygiene round closed 5/5. `docs/gpu-and-models.md` got a new `## Things we tried and rejected` section narrating the Mistral Nemo Q4 experiment + the gguf-`__version__` bootstrap patch with its removal trigger; `daydream/voice_samples.py` env-var converged on `DAYDREAM_VLLM_MAX_LEN`; three new BACKLOG entries (`creative-finetune-json-fluent-base`, `free-form-prose-pipeline`, `mistral-7b-instruct-fp16-ab`) capture the voice-A/B forward paths; ~30 GB freed from HF cache. Tier_short 271 / tier_medium 360 green throughout.*

### Proposal (2026-05-07)

**What happened (this turn).** Two commits closed the second-NPC spec at 5/5: `64afbfb` (SPEC consume), `8de1713` (C1-C5 in one bundled commit). Iris is now the second NPC at `r-attic`: `migrations/008_second_npc.sql` (slot 101, mood `thoughtful`, presence_text), `skills/iris.json` (voice differentiated from Rook on role + topical anchors + register, with the 2026-05-06 prompt-template-variety lessons baked in from version 1), `tests/test_ws_iris.py` (8 tests covering install + happy-path + scoping + safety + refusal). Tier_short 271 / tier_medium 368 green (was 360, +8 from the new iris tests).

**What was learned.** The data-skill pipeline, snapshot machinery, broadcast loop, and admin CLI generalize across NPCs without code changes. Iris landed as content + a migration + tests only; `daydream/api/ws.py`, `daydream/skills/data.py`, `daydream/admin.py` stayed untouched. The "second NPC is content-only" hypothesis from the prior turn proved correct. One small over-specification surfaced (criterion 4's snapshot field list assumed `appearance/presence_text` exposure; reality is `id/name/mood` only, with `presence_text` firing as a separate narrate broadcast event); spec spirit met, contract noted in commit body for next codereview to flag if helpful.

**Immediate next step (per user's pre-cleanup plan).** `/codereview` of the full unpushed branch (everything since `2c3edb5`, the last reviewed commit). Per the user's instruction: "If everything is clean after the second loop, close the turn and start a codereview." The codereview is a quality gate, not a spec turn — this proposal frames next-spec-turn options *after* that gate clears.

**Next-turn directions (post-codereview).**

1. **NPC drift loop.** BACKLOG `npc-drift-loop` gate is NEWLY MET this turn (`>=2 NPCs in the world` now satisfied with Iris joining Rook; arbiter has existed since the image-gen-pipeline landed). The entry calls for APScheduler-driven background ticks (weather, NPC mood, in-world calendar) on the "gentle drift" cadence (~5 min when empty, ~30 min when humans present), drift loop yielding the GPU lock immediately on player input. Concrete, well-scoped, big enough to be a substantive turn without being architectural.

2. **`watercolor-lora-ab` revisit.** Image-side small A/B; 5th surfacing. Has been declined in 4 prior proposals; if declined again, worth a status note that the entry is becoming stale-revisit and may belong elsewhere.

3. **NPC memory retrieval.** BACKLOG `npc-memory-retrieval` is still gated on drift-loop landing. Not yet eligible; the natural follow-on to option 1.

Strongest read: **option 1 (NPC drift loop)** as the natural follow-on. Newly eligible; builds on the just-shipped two-NPC substrate; opens up the BACKLOG `npc-memory-retrieval` follow-on.

### Revisit candidates

- `npc-drift-loop` — gate `>=2 NPCs in the world` newly satisfied (Iris joined Rook this turn); arbiter already in place. Both revisit-criteria gates met. The entry's prior-turn deferral reason ("v0 has no NPCs to drift") no longer holds.
- `watercolor-lora-ab` — image audit-trail half still landed; 5th surfacing. Declined in 4 prior proposals.

<!-- SPEC_META: {"date":"2026-05-07","title":"Second NPC (Iris, the attic archivist)","criteria_total":5,"criteria_met":5} -->
