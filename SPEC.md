## Spec — 2026-04-23 — first NPC

**Goal:** Populate the world with its first hand-authored NPC so a player walking the five rooms is not entirely alone, and extend the `examine` core skill to match toons as well as items so the new NPC is a first-class interactable. This is the prerequisite turn for three deferred BACKLOG entries — `npc-drift-loop`, `voice-samples-capture`, and `qwen-2.5-7b-rp-ink-trial` — all of which gate on at least one NPC existing in the world.

### Acceptance Criteria

- [ ] **A new migration seeds one hand-authored NPC into an existing room.** A migration file at `migrations/005_*.sql` (or the next sequential number) INSERTs one new row into `toons` with `is_human_controlled=0`, a WHIMSY-toned `seed` + `appearance_seed`, and a `current_room_id` that places the NPC in one of the five existing rooms. The migration is idempotent (re-running via `db.init_live` leaves exactly one row for that NPC) and does not clobber Wren (`t-wren`) or any existing room.
- [ ] **The NPC appears in `state_snapshot.toons` when and only when the player is in the NPC's room.** The WS snapshot's `toons` list includes an entry for the NPC (id, name, mood) when the controlled toon is co-located with the NPC. When the player is in any other room, the snapshot's `toons` list does NOT include the NPC. This criterion is a regression guard on the existing `get_toons_in_room` behavior extended to cover a non-human toon.
- [ ] **`examine <npc-name>` narrates the NPC.** At a room where the NPC is present, typing `examine <name>` emits a `narrate` event whose text describes the NPC using both the `seed` and `appearance_seed` fields so a human reader can distinguish this NPC from any other toon. Match is case-insensitive and article-tolerant (`examine the <name>` / `examine <NAME>` / `examine <name>` all work). If the current room contains both a toon and an item with matching names, the toon takes priority; the item is only considered when no toon matches. A name that matches neither emits the existing "you don't see X here" narration — failure behavior unchanged.
- [ ] **NPC presence does not regress existing skills.** `go`, `look`, `say`, and the existing `forge` data skill behave identically whether or not the NPC is in the current room. No new NPC-specific branches in core-skill handlers beyond the `examine` extension above. The whole existing test suite (short + medium) stays green both before and after the migration runs.
- [ ] **Tests cover the new flow without GPU or network.** New unit tests cover: `examine` on the NPC (happy path, case-insensitive, article-tolerant), `examine` name-collision (toon-wins when a room hosts both a matching toon and item), `examine` outside the NPC's room (falls through to the not-seen narration). A WS-level test verifies `state_snapshot.toons` reflects the NPC when the player is in the NPC's room and doesn't when the player is elsewhere. Existing tests adjust to the new seeded NPC where their assertions on toon counts or names are affected. All new tests run in `tier_short` except the WS test (`tier_medium`); `bin/game test short` passes before and after the change.

### Context

**Adopted from proposal (2026-04-23 turn-close).** The proposal named three candidate next slices; this spec takes the narrowest form of the top-named direction ("first NPC + toon-slot-management") — just the NPC half. `toon-slot-management` stays in BACKLOG for a later turn: hand-authoring an NPC via migration doesn't need the slot picker UI or the `kicked_at`-promotes-to-NPC machinery, and splitting the slice makes each turn cleanly closable.

**Prior art already in place (no schema changes needed).**
- `toons` table already supports `is_human_controlled=0` (migration 001). An NPC is just a toon row with that flag set and `controller_session=NULL`.
- `toons.get_toons_in_room` already returns all toons (human or not) whose `current_room_id` matches AND `kicked_at IS NULL`. An NPC with those fields will automatically flow into `state_snapshot.toons`.
- `daydream.skills.core.examine` currently uses `items.find_item_in_room_by_name`. The extension adds a `toons.find_toon_in_room_by_name` lookup and checks it first.

**Where things live.**
- `migrations/005_first_npc.sql` (new). Hand-authored NPC row. WHIMSY-toned seed + appearance_seed. The forge room (`r-forge`) is a natural choice — the authored `skills/forge.json` prompt already hints at "someone has stepped away from the anvil" — so the first NPC could be that keeper returning. Implementer's judgment on which room; the criterion is satisfied in any of the five.
- `daydream/toons.py` — add `find_toon_in_room_by_name(room_id, name) -> Toon | None` alongside the existing `get_toons_in_room`. Same case-insensitive / article-stripped matching shape as `items.find_item_in_room_by_name` (keeps the two lookups symmetric).
- `daydream/skills/core.py` — extend `examine`: strip article, try toons first, then items, then fall through to "you don't see X here." Compose the toon narration from seed + appearance_seed in a readable form.
- `tests/test_skills.py` — add `examine`-on-NPC cases (happy path, case-insensitive, article-tolerant, name-collision).
- `tests/test_ws.py` — add a snapshot-includes-NPC case; adjust existing assertions if any break.
- `tests/test_db.py` — if the existing row-count assertion covers toons, bump it.

**Out of scope for this spec** (deferred; do NOT build):
- **Slot management UI and `kicked_at` promotion.** `toon-slot-management` BACKLOG entry stays deferred.
- **Reactive NPC dialogue.** No LLM response when the player `say`s near the NPC; no drift-driven NPC narration. `npc-drift-loop` stays deferred.
- **`say to <npc>` or `talk to <npc>` skill.** Data-skill targeting of NPCs is a later turn. The proposal mentioned it; it's not strictly required for the "feels alive" minimum (presence + examine gets most of the value).
- **Multiple NPCs.** One is the minimum. Populating other rooms is content work, not infrastructure.
- **NPC memory / per-NPC narration voice A/B.** `npc-memory-retrieval`, `voice-samples-capture`, `qwen-2.5-7b-rp-ink-trial` all stay deferred; they become natural follow-ups once this lands.

**zat.env conventions to respect.**
- Work in small committable increments; paired tests in the same commit as the code.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- Before adding code, re-run `bin/game test short` to confirm a clean baseline.
- Per zat.env "Spec is code": `/codereview` will check the implementation against these criteria before push.

**Critical files to create or modify:**

- `migrations/005_first_npc.sql` (new)
- `daydream/toons.py` (modify; add `find_toon_in_room_by_name`)
- `daydream/skills/core.py` (modify; `examine` checks toons first, then items)
- `tests/test_skills.py` (modify; examine-on-NPC coverage)
- `tests/test_ws.py` (modify; snapshot-includes-NPC coverage, adjust existing assertions if they break)
- `tests/test_db.py` (modify if any row-count assertion needs updating)

---
*Prior spec (2026-04-23): data skills + safety baseline shipped 9/9 — safety.py banlist/wrap/refusal primitives, effects.py allowlist dispatcher, data.py DB-backed loader with Jinja sandbox, `bin/game world skill add` CLI, `skills/forge.json` showcase, WS bypass uses the room-filtered candidate list, snapshot refresh after item_added/mood_set.*

<!-- SPEC_META: {"date":"2026-04-23","title":"first NPC","criteria_total":5,"criteria_met":0} -->
