## Spec — 2026-04-24 — NPC presence narration

**Goal:** when the controlled toon walks into a room containing an NPC, emit a scripted one-line narrate that describes the NPC's presence (e.g., "Rook is at the bellows, humming quietly"). Makes Rook feel present without designing a dialogue protocol yet. The smallest coherent next step after first-NPC; say-to-NPC and reactive dialogue stay deferred for a later turn.

### Acceptance Criteria

- [ ] **Migration 007 adds `toons.presence_text` (nullable) and sets Rook's value.** A new migration file at `migrations/007_*.sql` runs `ALTER TABLE toons ADD COLUMN presence_text TEXT` (default NULL so existing rows survive) and then `UPDATE toons SET presence_text = '<WHIMSY-toned sentence>' WHERE id = 't-rook'`. Wren's `presence_text` stays NULL. The migration is idempotent: re-applying via `db.init_live` produces the same schema + value (ALTER TABLE ADD COLUMN on an existing column is a no-op in SQLite; UPDATE converges on the same value). Migration 005 is prior art for `ALTER TABLE ADD COLUMN` in this project.

- [ ] **Controlled-toon `move` into a populated room emits one narrate per co-located NPC with non-NULL `presence_text`.** When `_broadcast_loop` handles a controlled-toon `move` event and has sent the post-move `state_snapshot`, it then iterates the toons in the destination room and, for each toon whose id is NOT the controlled toon AND whose `presence_text` is a non-empty string, appends one `narrate` event carrying that text (`room_id` = the destination room). The narrates reach the client through the existing broadcast path and land in chat-log order AFTER the move event + snapshot pair. With one NPC (Rook) in one room (r-forge), moving `north` from the meadow produces exactly one Rook presence narrate; moving into any other room produces none.

- [ ] **Only `move` triggers presence narrates.** Initial WS connect does NOT fire a presence narrate (the snapshot's `events` field already carries prior narrates on reconnect, so firing fresh would create duplicate text in the chat log). Effect-mutation snapshot refreshes (the `item_added` / `mood_set` triggers added in the prior data-skills turn) do NOT fire presence narrates (they would spam the log on every data-skill dispatch in a populated room). Only the controlled-toon `move` branch in the broadcast loop emits them.

- [ ] **Empty / NULL / whitespace-only `presence_text` is a silent skip.** A toon with `presence_text = NULL`, `""`, or only-whitespace contributes no narrate. No error, no placeholder text. This keeps future "add an NPC without authoring a greeting" cheap: just omit the column in the migration and the NPC is silently present.

- [ ] **Tests cover the flow without GPU or network, and existing tests keep passing.** Four coverage surfaces: (a) `tests/test_db.py` asserts the migration landed — column exists, Rook's `presence_text` is non-empty, Wren's is NULL. (b) `tests/test_ws.py` adds a positive case: `go north` from meadow produces move → snapshot → Rook's presence narrate, in that order. (c) `tests/test_ws.py` also adds a negative case: initial connect to meadow + no move produces no presence narrate on the next few receive attempts. (d) `tests/test_ws_forge.py` (the existing forge-at-r-forge tests) is updated to consume the Rook presence narrate that now lands after the post-move snapshot but BEFORE the forge dispatch; those tests also assert NO additional Rook narrate fires on the effect-mutation snapshot refresh (criterion 3's regression guard). All new tests run in `tier_short` or `tier_medium`; short + medium both green before and after the change.

### Context

**Adopted from proposal (2026-04-23 turn-close), direction 1.** The proposal named four candidate directions; this spec is direction 1, "NPC greeting on room entry" — cheapest, highest-charm. The other three directions (say-to-NPC + reactive dialogue, testing debt for `gameplay-scenario-tests` + `security-tests-tier`, `toon-slot-management`) stay deferred for later turns.

**Why fire on move only (not on connect).** A player can reconnect mid-session (Safari disconnect, `bin/game down && up`, etc.). The state_snapshot sent on connect already includes up to 50 recent events via the `events` field, so any prior Rook presence narrate is already in the chat log. Firing a FRESH narrate on every connect would create duplicate text in the chat log on reconnect — confusing for the player. The simplest rule is "only explicit moves greet"; the initial connect that happens once at session start, before the player has moved, is almost always in the meadow (no NPC), so skipping that trigger costs nothing for the default flow.

**Why fire after the snapshot, not before.** The snapshot gives the client the authoritative room state (items, toons panel, exits, image). Seeing "Rook is at the bellows" in the chat log AFTER the toons panel has updated to show Rook is natural narration order; seeing it before would be weirdly prescient. The broadcast loop already sends events in seq order, so appending the narrate after the snapshot send naturally preserves this ordering.

**Where things live.**
- `migrations/007_npc_presence.sql` (new). `ALTER TABLE toons ADD COLUMN presence_text TEXT;` then `UPDATE toons SET presence_text = '...' WHERE id = 't-rook'`. Prior art: migration 005 for the skills table.
- `daydream/toons.py` — add `presence_text: str | None` to the `Toon` dataclass and to `Toon.from_row`.
- `daydream/api/ws.py` — add a small helper `_emit_npc_presence_narrates(controlled_toon_id, room_id)` that appends narrates for qualifying NPCs via `events.append`. Call it from the `_broadcast_loop`'s `is_controlled_move` branch, AFTER the snapshot `send_json` and BEFORE (or alongside) the `_maybe_enqueue_image_gen` call. The new narrates flow back through the same broadcast loop's queue.
- `tests/test_db.py` — extend the existing seeded-state test to assert the column + values.
- `tests/test_ws.py` — positive move-into-forge case; negative initial-connect-to-meadow case.
- `tests/test_ws_forge.py` — update the forge E2E tests to consume the post-move presence narrate; add the effect-mutation negative assertion.

**Out of scope for this spec** (deferred; do NOT build):
- **Reactive NPC dialogue.** No LLM-driven NPC response; `say to <npc>`, `talk to <npc>`, `npc-drift-loop` all stay deferred.
- **Greeting dedup across sessions.** Reconnecting to a room you already greeted fires no new narrate under criterion 3, but if you later move OUT and back IN, the greeting fires again. That's the simple v1 behavior. A "dedup within session" policy is future polish.
- **LLM-generated greetings.** Rook's `presence_text` is author-set in the migration. Generating varied greetings from the seed via LLM is future work.
- **Safety filter on author-set `presence_text`.** The operator / migration author is trusted; the banlist is aimed at LLM-produced text, not migration data. An off-tone value here is an authoring bug to fix in the migration, not a runtime safety surface.
- **Multiple NPCs per room / second NPC.** One NPC exists today (Rook). Adding more is content work, not in this spec.

**zat.env conventions to respect.**
- Small committable increments; tests in the same commit as the code they cover.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- Re-run `bin/game test short` after each functional change; confirm clean baseline before adding new work.
- Per zat.env "Spec is code": `/codereview` will check this implementation against these five criteria before any push.

**Critical files to create or modify:**

- `migrations/007_npc_presence.sql` (new)
- `daydream/toons.py` (modify; `presence_text` field on Toon)
- `daydream/api/ws.py` (modify; presence-narrate helper called from the controlled-move branch)
- `tests/test_db.py` (modify; migration assertion)
- `tests/test_ws.py` (modify; positive + negative presence-narrate cases)
- `tests/test_ws_forge.py` (modify; consume the new narrate in the happy-path test; add the no-emit-on-mutation assertion)

---
*Prior spec (2026-04-23): first NPC shipped 5/5 — migration 006 seeds Rook at r-forge (slot=100, is_human_controlled=0, WHIMSY-toned seed + appearance_seed), `toons.find_toon_in_room_by_name` helper, `examine` core skill now checks toons first then items with toon-wins on name collision, WS snapshot tests pin the NPC co-location contract.*

<!-- SPEC_META: {"date":"2026-04-24","title":"NPC presence narration","criteria_total":5,"criteria_met":0} -->
