## Spec — 2026-05-07 — Second NPC (Iris, the attic archivist)

**Goal:** Author the world's second NPC, Iris, at `r-attic` with their own voice via the data-skill pipeline. Mirrors the 2026-04-24 NPC dialogue spec that introduced Rook at `r-forge`, now with the prompt-template-variety lessons (2026-05-06) baked in from the start. Unblocks BACKLOG `npc-drift-loop` and `npc-memory-retrieval`, both gated on >=2 NPCs in the world.

### Acceptance Criteria

- [ ] **`migrations/008_second_npc.sql` adds Iris to `r-attic`, idempotent.** New migration that INSERT-OR-IGNOREs `t-iris` (slot 101 per the NPC slot-100+ convention; `is_human_controlled=0`; `world_id='w-bunny'`; `current_room_id='r-attic'`). The row carries `seed` (one-line role + voice + small specifying detail), `appearance_seed` (visual; SDXL-friendly), `mood` (start state; should NOT be "content" — different from Rook's mood for narrate variety), `inventory_json='[]'`, and `presence_text` (the line that fires when a player enters the attic; mirrors Rook's `presence_text` shape). Re-running the migration leaves the row unchanged. Test: `tests/test_db.py`'s migration-chain test picks up migration 008 with no new code (the existing migration framework handles ordered application; the chain just gets one longer).

- [ ] **`skills/iris.json` authors Iris's voice as a data skill.** Same shape as `skills/rook.json`: `name=iris`, `ui_hint=Iris`, one-line `description`, `context_predicate={"room_slug":"attic"}`, `prompt_template` carrying Iris's voice, `effects_schema` documenting one `narrate` effect, `author=admin`. The prompt template carries the prompt-template-variety lessons from `skills/rook.json`'s 2026-05-06 revision: kind-specific input-anchor mapping (different opener style per input kind), at least 3 distinct exemplars (different sensory anchors + different concrete spoken lines), explicit ban on Iris's strongest sticky-opener risk if one emerges in iteration. Iris's voice DIFFERS from Rook's on at least three concrete axes: different *role* (archivist vs forge-keeper), different *topical anchors* (letters / ink / dust / round-window light / old correspondents vs iron / anvil / bellows / wildflowers), different *spoken-voice register* (slightly more bookish + curious + asks gentle questions back, vs Rook's "say less than they mean" laconic). Voice differentiation is subjective; the criterion verifies the *role + anchors + register* are visibly different in the prompt template content, not specific phrasing.

- [ ] **`tests/test_ws_iris.py` covers install + happy path + scoping + safety + refusal.** Mirrors `tests/test_ws_rook.py`'s 7-test structure (`tier_medium`): install via the admin CLI gate; happy path at `r-attic` dispatches through the data-skill pipeline and emits the canned narrate; hidden-elsewhere check (e.g., at `r-meadow`, `iris hello` falls through to interpreter — exactly one LLM call for the interpreter, not a second for iris); snapshot at `r-meadow` excludes iris from the `skills` list; banned-input short-circuit (e.g., a WHIMSY-banned word in the args yields the BANNED fallback, LLM never called); refusal short-circuit (`{"refused":true,"reason":...}` narrates the reason and drops accompanying effects); player_input wrap-tag verification (the user message reaching the LLM contains `<player_input>...</player_input>`). LLM is mocked for determinism.

- [ ] **WS snapshot reflects Iris's co-location at `r-attic`.** When the player toon is at `r-attic`, the snapshot's toons-in-room list includes `t-iris` with appearance/mood/presence_text fields populated. When the player is anywhere else, the snapshot does NOT include iris. Verified in `tests/test_ws_iris.py` (snapshot-content assertion) AND continues to work for Rook's existing snapshot at `r-forge` — i.e., the second NPC doesn't accidentally pollute the first NPC's snapshot rendering. No new code in `daydream/api/ws.py` should be needed; the existing snapshot machinery iterates all toons in the room.

- [ ] **Existing test suite stays green and tier budgets are unchanged.** `bin/game test short` and `bin/game test medium` pass. `tests/test_ws_rook.py` continues green (Rook's behavior is unchanged by adding Iris). Migration 008 lands in `tests/test_db.py`'s chain check without test modification (idempotent migrations are picked up automatically). No new tier_long tests; no GPU-dependent tests added.

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

---
*Prior spec (2026-05-07): voice-bench cleanup hygiene round closed 5/5. `docs/gpu-and-models.md` got a new `## Things we tried and rejected` section narrating the Mistral Nemo Q4 experiment + the gguf-`__version__` bootstrap patch with its removal trigger; `daydream/voice_samples.py` env-var converged on `DAYDREAM_VLLM_MAX_LEN`; three new BACKLOG entries (`creative-finetune-json-fluent-base`, `free-form-prose-pipeline`, `mistral-7b-instruct-fp16-ab`) capture the voice-A/B forward paths; ~30 GB freed from HF cache. Tier_short 271 / tier_medium 360 green throughout.*

<!-- SPEC_META: {"date":"2026-05-07","title":"Second NPC (Iris, the attic archivist)","criteria_total":5,"criteria_met":0} -->
