## Spec — 2026-04-23 — first NPC

**Goal:** Populate the world with its first hand-authored NPC so a player walking the five rooms is not entirely alone, and extend the `examine` core skill to match toons as well as items so the new NPC is a first-class interactable. This is the prerequisite turn for three deferred BACKLOG entries — `npc-drift-loop`, `voice-samples-capture`, and `qwen-2.5-7b-rp-ink-trial` — all of which gate on at least one NPC existing in the world.

### Acceptance Criteria

- [x] **A new migration seeds one hand-authored NPC into an existing room.** A migration file at `migrations/006_*.sql` (005 is now held by the `skills.description` column added during the codereview of the data-skills turn) INSERTs one new row into `toons` with `is_human_controlled=0`, a WHIMSY-toned `seed` + `appearance_seed`, and a `current_room_id` that places the NPC in one of the five existing rooms. The migration is idempotent (re-running via `db.init_live` leaves exactly one row for that NPC) and does not clobber Wren (`t-wren`) or any existing room.
- [x] **The NPC appears in `state_snapshot.toons` when and only when the player is in the NPC's room.** The WS snapshot's `toons` list includes an entry for the NPC (id, name, mood) when the controlled toon is co-located with the NPC. When the player is in any other room, the snapshot's `toons` list does NOT include the NPC. This criterion is a regression guard on the existing `get_toons_in_room` behavior extended to cover a non-human toon.
- [x] **`examine <npc-name>` narrates the NPC.** At a room where the NPC is present, typing `examine <name>` emits a `narrate` event whose text describes the NPC using both the `seed` and `appearance_seed` fields so a human reader can distinguish this NPC from any other toon. Match is case-insensitive and article-tolerant (`examine the <name>` / `examine <NAME>` / `examine <name>` all work). If the current room contains both a toon and an item with matching names, the toon takes priority; the item is only considered when no toon matches. A name that matches neither emits the existing "you don't see X here" narration — failure behavior unchanged.
- [x] **NPC presence does not regress existing skills.** `go`, `look`, `say`, and the existing `forge` data skill behave identically whether or not the NPC is in the current room. No new NPC-specific branches in core-skill handlers beyond the `examine` extension above. The whole existing test suite (short + medium) stays green both before and after the migration runs.
- [x] **Tests cover the new flow without GPU or network.** New unit tests cover: `examine` on the NPC (happy path, case-insensitive, article-tolerant), `examine` name-collision (toon-wins when a room hosts both a matching toon and item), `examine` outside the NPC's room (falls through to the not-seen narration). A WS-level test verifies `state_snapshot.toons` reflects the NPC when the player is in the NPC's room and doesn't when the player is elsewhere. Existing tests adjust to the new seeded NPC where their assertions on toon counts or names are affected. All new tests run in `tier_short` except the WS test (`tier_medium`); `bin/game test short` passes before and after the change.

### Context

**Adopted from proposal (2026-04-23 turn-close).** The proposal named three candidate next slices; this spec takes the narrowest form of the top-named direction ("first NPC + toon-slot-management") — just the NPC half. `toon-slot-management` stays in BACKLOG for a later turn: hand-authoring an NPC via migration doesn't need the slot picker UI or the `kicked_at`-promotes-to-NPC machinery, and splitting the slice makes each turn cleanly closable.

**Prior art already in place (no schema changes needed).**
- `toons` table already supports `is_human_controlled=0` (migration 001). An NPC is just a toon row with that flag set and `controller_session=NULL`.
- `toons.get_toons_in_room` already returns all toons (human or not) whose `current_room_id` matches AND `kicked_at IS NULL`. An NPC with those fields will automatically flow into `state_snapshot.toons`.
- `daydream.skills.core.examine` currently uses `items.find_item_in_room_by_name`. The extension adds a `toons.find_toon_in_room_by_name` lookup and checks it first.

**Where things live.**
- `migrations/006_first_npc.sql` (new). Hand-authored NPC row. WHIMSY-toned seed + appearance_seed. The forge room (`r-forge`) is a natural choice — the authored `skills/forge.json` prompt already hints at "someone has stepped away from the anvil" — so the first NPC could be that keeper returning. Implementer's judgment on which room; the criterion is satisfied in any of the five.
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

- `migrations/006_first_npc.sql` (new)
- `daydream/toons.py` (modify; add `find_toon_in_room_by_name`)
- `daydream/skills/core.py` (modify; `examine` checks toons first, then items)
- `tests/test_skills.py` (modify; examine-on-NPC coverage)
- `tests/test_ws.py` (modify; snapshot-includes-NPC coverage, adjust existing assertions if they break)
- `tests/test_db.py` (modify if any row-count assertion needs updating)

---
*Prior spec (2026-04-23): data skills + safety baseline shipped 9/9 — safety.py banlist/wrap/refusal primitives, effects.py allowlist dispatcher, data.py DB-backed loader with Jinja sandbox, `bin/game world skill add` CLI, `skills/forge.json` showcase, WS bypass uses the room-filtered candidate list, snapshot refresh after item_added/mood_set.*

### Proposal (2026-04-23)

**What happened.** First NPC shipped 5/5 across three increments: migration 006 seeds Rook, the forge-keeper, at r-forge (slot 100, NPC convention; WHIMSY-toned seed + appearance_seed; idempotent INSERT OR IGNORE); `daydream/toons.find_toon_in_room_by_name` mirrors the items helper for case-insensitive lookup; `daydream/skills/core.examine` now tries toons first then items, with toon-wins on name collision. Two new WS tests pin the snapshot-NPC contract (NPC appears in `state_snapshot.toons` only when co-located); six new skill tests cover the examine path (happy + case + article + collision + absent-room + item-fallback). No schema change — the v0 toons table already supported `is_human_controlled=0`, and `get_toons_in_room` already returned NPCs alongside humans. Test surface: 247 -> 255 short, 84 -> 86 medium; 333/333 total green.

**Questions and directions.**
- *NPC greeting on room entry* (cheapest, highest immediate feel). When the controlled toon enters a room that contains an NPC, emit a one-line scripted narrate ("Rook looks up from the bellows and nods"). Either hand-authored per-NPC or generated once via a tiny LLM call with the NPC seed. Low scope, big charm gain; makes Rook feel alive without designing a dialogue protocol.
- *`say to <npc>` + reactive NPC response*. A bigger slice: add a core `say_to` skill (or extend `say` with a target parse), have the NPC respond via an LLM data skill bound to the NPC's seed. Unblocks `voice-samples-capture` and `qwen-2.5-7b-rp-ink-trial` directly. The safety baseline already covers the prompt-injection + banlist surfaces this would introduce.
- *Testing debt: `gameplay-scenario-tests` + `security-tests-tier`*. Both have been revisit-candidates for two turns. Grouped as a "testing tier bump" turn they'd be modest scope and plug regression surfaces before they drift.
- *`toon-slot-management`*. The 5-slot picker UI + `kicked_at`-promotes-to-NPC path. One of its revisit criteria is now met ("first NPC authored"); the other ("second human player wants in") is still soft.

**Revisit candidates** (BACKLOG sweep; criteria now plausibly hold):
- `toon-slot-management` — "first NPC needs to be authored" half of the revisit criteria just triggered.
- `security-tests-tier` — still not picked up after two turns; the banlist / refusal / tag-wrap surfaces are concrete regression targets.
- `gameplay-scenario-tests` — multi-room-nav has been stable for three turns; `test_ws_forge.py` + `test_ws.py` navigation tests are already partial scenarios to formalize.

<!-- SPEC_META: {"date":"2026-04-23","title":"first NPC","criteria_total":5,"criteria_met":5} -->
