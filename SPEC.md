## Spec — 2026-05-07 — toon-slot-management: 5-slot picker + create/claim/kick + WS session resolution

**Goal:** Replace the v0 "Wren is hardcoded as the player" assumption with a 5-slot toon picker. Players see 5 slots in the SPA, can create a fresh toon in any empty slot, claim a kicked-NPC slot to step into that toon's life, or kick their own slot to release it (the kicked toon stays in-world as a non-drifting NPC carrying its inventory and memories). The WS layer derives the controlled toon from the session's claim, with a legacy `t-wren` fallback so existing tests + the single-session flow keep working through v1. Realizes BACKLOG `toon-slot-management` (ACTIVE in spec 2026-05-07); the gateway to v2 multi-user.

### Acceptance Criteria

- [x] **`GET /api/slots` returns the 5 slots' state.** Response shape: `{"slots": [{"slot": N, "toon": {...} | null}, …]}` for slots 1-5 in order. The `toon` field, when populated, includes at minimum `id`, `name`, `appearance_seed`, `current_room_id`, `is_human_controlled`, `kicked_at`, and a derived `claimed_by_me` boolean (true when the toon's `controller_session` equals the requesting session id). Hand-authored NPCs in slots 100+ are NOT listed (the picker is human-slot only). The endpoint is loopback/tailnet-gated by `AccessMiddleware` like every other API route; session auth via the existing middleware (no new auth surface).

- [x] **`POST /api/slots/{slot}/create` creates a fresh toon in an empty slot.** Body: `{"name": str, "appearance_seed": str}`. On success: creates a new toon row with the chosen slot, `is_human_controlled=1`, `controller_session=<requester's session id>`, `kicked_at=NULL`, starting at `r-meadow`, with empty inventory, default mood (`curious`). Returns 200 with the created toon. Errors: 404 if `slot` is not in 1-5; 400 on missing / non-string / whitespace-only name or appearance_seed; 409 if the slot already has a non-kicked toon. Toon id is implementation choice (e.g., `t-slot{N}-<short-uuid>` or similar — must be unique and stable). Atomic against concurrent creates: two simultaneous POSTs against the same slot result in one 200 and one 409, never both 200.

- [x] **`POST /api/slots/{slot}/claim` adopts an existing kicked-NPC toon.** On success: sets the slot's toon `controller_session=<requester's session id>`, `is_human_controlled=1`, `kicked_at=NULL`. Returns 200 with the toon. Errors: 404 if slot is not in 1-5 or is empty; 409 if the slot's toon is currently controlled (`is_human_controlled=1` and `kicked_at IS NULL`) — caller must kick it first. The endpoint is the only path to flip a kicked-NPC back to human control via the slot system.

- [x] **`POST /api/slots/{slot}/kick` releases a slot to a non-drifting NPC.** On success: sets the slot's toon `controller_session=NULL`, `is_human_controlled=0`, `kicked_at=<UTC ISO timestamp>`. Returns 200 with the kicked toon. The toon's `current_room_id`, `inventory_json`, `mood`, and accrued memories are preserved (it stays in-world). Errors: 404 if slot is empty or out of range. v1 friend-scope: any authenticated session can kick any slot (no per-session ownership check); multi-user differentiation lands with v2 multi-user-shared-world.

- [x] **WS layer resolves the controlled toon from the session, with `t-wren` legacy fallback.** When `daydream/api/ws.py` needs the actor for input dispatch, it queries `toons` for a row where `controller_session = <ws session id>` AND `kicked_at IS NULL` AND `is_human_controlled = 1`. If found, that's the actor and `_current_room_id` reads its `current_room_id`. If no row matches, fall back to `HUMAN_TOON_ID = "t-wren"` (the existing v0 default). Effects dispatch (`actor_id` everywhere it's passed) uses the resolved id, not the constant. The `_current_room_id()` helper takes a session-id parameter or reads it from the same WS context. The `state_snapshot` `toons` field continues to include all toons in the current room regardless of who controls them (no behavior change in the snapshot). Existing 18 `tests/test_ws_*.py` tests stay green by hitting the t-wren fallback path.

- [x] **SPA exposes a slot picker.** The web UI under `web/` adds a clickable affordance (panel, modal, or button-opens-overlay — implementer picks the layout that matches the existing watercolor aesthetic) showing the 5 slots with state: empty / occupied-by-me / kicked-NPC / occupied-by-other. An empty slot click prompts the user for `name` + `appearance_seed` (a simple `prompt()` is fine for v1) and POSTs to `/api/slots/{N}/create`. A kicked-NPC slot has a "claim" button that POSTs to `/api/slots/{N}/claim`. The currently-claimed slot has a "kick" affordance that POSTs to `/api/slots/{N}/kick`. After any successful POST the UI re-fetches `/api/slots` and re-renders. The picker does not auto-open at first connection (legacy fallback is enough); the player can open it explicitly to switch toons. Tone-locked: copy is soft and watercolor-compatible (no urgency, no modern-tech metaphors).

- [x] **Tests cover all four endpoints + the WS resolution change + the SPA structure.** New `tests/test_slots.py` (tier_medium, TestClient-based) covers: list returns 5 slots; create with valid input creates toon and sets claim; create on populated slot returns 409; create with invalid input returns 400; claim on kicked NPC clears `kicked_at` + sets `controller_session`; claim on non-kicked controlled slot returns 409; kick clears claim + sets `kicked_at`; concurrent-create atomicity (two POSTs, one wins). New WS test (tier_medium, in `tests/test_ws.py` or a sibling) verifies that a session that claims slot 2 then sends an input has its event recorded with the claimed toon's id, not `t-wren`. Existing tier_short / tier_medium suites stay green at default (the WS fallback covers them). Test count target: ≥6 new tests; tier_medium total grows by ~6-10.

- [x] **`bin/game test short` / `medium` stay green.** No new GPU dependencies; no new migration (schema already has `slot`, `controller_session`, `is_human_controlled`, `kicked_at`, `inventory_json`, `mood`). README test counts roll forward at end-of-turn to match `bin/game test short` / `medium` reality.

### Context

**v1 scope: human slots only.** Slots 1-5 are the human-toon namespace; NPCs in slots 100+ (Rook at 100, Iris at 101) are unaffected by the picker — they don't appear in `/api/slots` and can't be created/claimed/kicked through this surface. The convention from migration 006 / 008 ("slots 100+ for hand-authored NPCs, slots 1-5 for human-playable toons") becomes a hard contract here.

**Why a `t-wren` fallback instead of a hard cutover.** Removing the hardcoded `HUMAN_TOON_ID = "t-wren"` from `daydream/api/ws.py` would break every existing `tests/test_ws*.py` test that hits the WS layer without claiming a slot first — that's ~16 tests across `test_ws.py`, `test_ws_rook.py`, `test_ws_iris.py`, `test_ws_forge.py`, `test_ws_images.py`. The fallback keeps those green and lets the new test surface focus on the new behavior. v2 multi-user-shared-world removes the fallback (multiple sessions can't share one default toon).

**Concurrency story.** Two sessions hitting `/api/slots/3/create` at the same moment: SQLite is single-writer; one query lands first. The second sees a populated slot via a `WHERE slot = ? AND world_id = 'w-bunny' AND kicked_at IS NULL` precheck and returns 409. Implement as a single `INSERT OR IGNORE` on a uniqueness constraint, OR a SELECT-then-INSERT under an explicit transaction. The existing schema doesn't have a `(slot, world_id) WHERE kicked_at IS NULL` partial index — implementer's call whether to add one or rely on the SELECT-first guard.

**Kicked NPC behavior.** A kicked toon's drift behavior is intentionally minimal at v1: the drift loop's `_eligible_npcs` filter excludes NPCs without a `_DRIFT_POOLS` entry, so kicked toons stay silent (no auto-narrate). They show up in `state_snapshot.toons` for their current room and can be examined / spoken to via the existing core skills (`look`, `examine`, `say`). Adding a generic-NPC drift path is a future spec under the BACKLOG `npc-drift-loop` family.

**Stale claims / orphaned sessions.** v1 doesn't garbage-collect stale `controller_session` values when a WS disconnects without explicitly kicking. A session that reconnects with the same session id re-owns its toon; a fresh-login session sees an "occupied-by-other" slot for an unreachable old claim. Operator escape hatch: kick the slot manually via the API (admin-y). Auto-cleanup on disconnect is a v2 concern when it actually causes friction.

**Auth surface.** `AccessMiddleware` is the gate (loopback / tailnet only); same as every other API route. Friend-scope means any auth'd session can create / claim / kick any slot. Per-session ownership-of-slot is a v2 question that needs the multi-user threat model first.

**Out of scope** (deferred):
- Generic-NPC drift for kicked toons. Future work after BACKLOG `npc-drift-loop` extensions.
- Session GC / stale-claim cleanup on WS disconnect. v2 concern.
- Per-session ownership enforcement (only your-claimed-slot can be kicked). v2 multi-user.
- Toon transfer between worlds. v1 single-world.
- Slot picker UX polish (transitions, hover states, sound effects). MVP for v1.
- Auto-open-picker-at-first-connection. Player can open it explicitly when they care.
- Removing the `t-wren` fallback. v2 multi-user-shared-world.
- Frontend JS testing via Playwright/Selenium. v1 sticks with structural HTML assertions; the JS event handlers are tested implicitly via the API layer they call.

**Critical files to modify:**
- `daydream/api/slots.py` (new) — the four endpoints
- `daydream/server.py` (mount the new router)
- `daydream/api/ws.py` (session→toon resolution, replace `HUMAN_TOON_ID` constant uses with a per-session lookup)
- `daydream/toons.py` (helper for resolving by session_id; helper for `create_toon_in_slot`)
- `web/index.html` and `web/assets/main.js` / `web/assets/style.css` (slot picker)
- `tests/test_slots.py` (new) — endpoint tests
- `tests/test_ws.py` (new test for the claim flow)
- `tests/test_frontend.py` (slot picker DOM presence)
- `README.md` (test counts at end of turn)

---
*Prior spec (2026-05-07): v0.2.0 cut closed 6/6. README's "Latest stable cut" now reads v0.2.0 with a "second inhabited dream" release-notes section above v0.1.0 capturing the deltas (LLM-driven drift, drift polish, drift instrumentation, tooling). TESTING.md tier counts rolled forward (290/401/411 → 320/451/460). Local annotated tag `v0.2.0` at `541d6c7`, pushed to origin in `97698ea..627c7f4`.*

<!-- SPEC_META: {"date":"2026-05-07","title":"toon-slot-management: 5-slot picker + create/claim/kick + WS session resolution","criteria_total":8,"criteria_met":8} -->
