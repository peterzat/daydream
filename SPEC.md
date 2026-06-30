## Spec — 2026-06-29 — session & presence: room descriptions on entry, fresh sessions, toon delete, keyless authoring

**Goal:** A session-and-presence pass so stepping into and out of a dream feels intentional — rooms describe themselves on arrival, a new session starts fresh, and toons are yours to make and unmake — plus reconciling world creation with the local-only / no-production-API-key generation policy.

### Acceptance Criteria

*Room description on entry*

- [x] **The room description renders in the SPA.** Each `state_snapshot` already carries `room.description` (`daydream/api/ws.py` `_state_snapshot`); `web/assets/main.js` now displays it in the room view (today it renders only the title). Verifiable by a DOM-level/browser check that a snapshot with a non-empty `room.description` shows that text; existing WS snapshot tests stay green.
- [x] **First arrival into a room this session auto-describes it; re-entry is abbreviated.** Entering a room not yet seen this session surfaces its full description (the stored `description_cached`, the same text the `look` core skill emits — `daydream/skills/core.py`); a later arrival into that same room in the same session surfaces a short/elided line instead. Driven by per-session visited-room memory. No live LLM call (the first-look text is pre-baked stored text, per the generation policy). Verifiable via TestClient: connect → move into room A (full description present) → leave → re-enter A (abbreviated).

*Session & presence*

- [x] **A new session starts with an empty event log; a reconnect still resumes.** A brand-new session's first `state_snapshot` replays no prior room history (its `events` list is empty; only events from then on stream in), while a reconnect re-hydrates as today. The server distinguishes the two. Verifiable via TestClient: a fresh connection's first snapshot has an empty `events` array even when the room has prior events; a reconnect that signals a prior seq still receives catch-up.
- [x] **"Leave the dream" wakes you to the character picker.** The leave control plays a brief "you wake…" beat and returns to the slot/character picker, releasing the session's active toon so you are not silently dropped back into the same toon (you choose again on re-entry) — replacing the tailnet no-op `/api/logout` (`is_authed` ignores logout). The visual transition is browser-manual; the server-side release (the next resolution does not auto-control the prior toon, and does not silently fall back to the seeded `t-wren`) is TestClient-verifiable.
- [x] **Toons can be permanently deleted, freeing the slot.** Alongside the recoverable kick/rest, a new path deletes a human toon outright so its slot reads empty afterward (`GET /api/slots`), reachable from the slot-picker UI and via `admin.main`/an endpoint, refusing cleanly on an empty or out-of-range slot, and handling the toon's dependent rows (events/memories) without leaving the DB inconsistent. Verifiable via TestClient/`admin.main`: create a toon → delete → slot empty and the toon row gone (distinct from kick, which leaves a `kicked_at` row in place).

*World authoring (keyless, per the generation policy)*

- [x] **A keyless, in-session world-authoring path exists.** A world can be built from an Opus-authored world spec (the bootstrap JSON envelope) with NO cloud LLM call and NO `ANTHROPIC_API_KEY` — a loader validates the envelope with the same validator `bootstrap_world` uses and writes a valid world DB, refusing a malformed envelope and an existing output path. Verifiable in `tier_medium`: `admin.main([...])` turns a committed JSON fixture into a world DB that opens with its rooms/toons, no network, no key.
- [ ] **The API-key bootstrap path is reconciled with the policy.** The litellm→Anthropic `world bootstrap` path is removed OR explicitly deprecated/off so the documented default way to make a world is the keyless in-session loader. README + CLAUDE.md present keyless authoring as canonical.

*Cross-cutting*

- [ ] **Tiers green; docs rolled forward.** `bin/game test short` and `bin/game test medium` exit 0 with paired tests for each item above (WS via TestClient; slot-delete + world-load via `admin.main`; all GPU/LLM-free). README + CLAUDE.md updated for the new arrival/leave/delete behaviors and the keyless authoring path. Browser-manual criteria (the "you wake…" transition; the rendered-description styling) are flagged as such and eyeballed once.

### Context

**Built from three BACKLOG "Session & presence" entries** (`room-description-on-entry`, `session-presence-polish`, `world-authoring-in-session`), captured from the 2026-06-29 playtest and marked ACTIVE in BACKLOG. Locked decisions from that design discussion: "leave the dream" = a brief "you wake…" beat then the character picker; a new session = an empty text log; toon removal = keep kick/rest AND add a true delete.

**Generation policy (load-bearing — see CLAUDE.md "Generation policy").** Runtime uses only local models on the RTX 4000; no production API key. Two consequences here: (1) the arrival/first-look description is the pre-baked stored `rooms.description_cached`, NOT a live LLM call — so describe-on-entry is local, instant, and GPU-free to test; the short re-entry line may be a template or an optional cheap local-Qwen call but must NOT be required by any criterion (tests stay LLM-free). (2) World authoring moves off the Anthropic API entirely: Opus authors a world inside a Claude Code session and a keyless loader writes it.

**Code anchors (verify before editing).**
- `daydream/api/ws.py` `_state_snapshot` already includes `room.description` and replays `events` via `fetch_since(last_seq - SNAPSHOT_HISTORY_DEPTH)` (≈50) on every connect; `_broadcast_loop` already sends a fresh snapshot on a controlled `move` (the natural hook for describe-on-entry). WS session→toon resolution is `controller_session` else the seeded `LEGACY_TOON_ID = "t-wren"` fallback — releasing control on "leave" must not silently re-drop you into Wren.
- `web/assets/main.js` `renderSnapshot` renders the title but never `snap.room.description`.
- `daydream/skills/core.py` `look` emits `room.description_cached or "You are in {title}."` — mirror it for auto-describe.
- `daydream/api/auth.py` `is_authed` returns true unconditionally on the tailnet, so `/api/logout` is a no-op; the leave action is a client-side picker + release, not an auth logout.
- `daydream/api/slots.py` + `daydream/toons.py`: create/claim/kick; kick sets `kicked_at` (recoverable). No delete exists; add one that frees the slot and handles the toon's dependent rows (events/memories) coherently.
- `daydream/admin.py` `cmd_world_bootstrap` → `daydream/llm/bootstrap.py` `bootstrap_world` (litellm→Anthropic; exit 2 with no key). The keyless loader reuses that module's JSON-envelope validator + DB writer, minus the LLM call.

**zat.env practices.** Land this as separate committable increments (the room-description render is the lowest-hanging — ship it first), writing paired `tier_medium` tests in the same increment as each piece; don't stack untested changes. Verification is TestClient/`admin.main` oracles (no GPU/LLM). Don't build v2 scaffolding.

**Out of scope.** Multi-user differentiation (any authed session may still act on any slot — v2 `multi-user-shared-world`); the creative authoring of a new world's content (an Opus-in-Claude-Code act, not code this spec ships); elaborate "you wake" animation beyond a simple transition; memory/LanceDB changes.

**Critical files:** `daydream/api/ws.py`, `web/assets/main.js`, `daydream/api/slots.py`, `daydream/toons.py`, `daydream/api/auth.py`, `daydream/admin.py`, `daydream/llm/bootstrap.py`, `tests/test_ws*.py` + `tests/test_admin.py` (or a new `tests/test_slots*.py`), `README.md`, `CLAUDE.md`.

---
*Prior spec (2026-06-29): world-hot-swap closed 6/6 — live in-process world swap (`POST /api/world/swap` + `bin/game world swap`) replacing the running server's live DB without a restart, with connected clients re-snapshotting; failure-safe, with a round-trip + reconnect oracle.*

<!-- SPEC_META: {"date":"2026-06-29","title":"session & presence: room descriptions on entry, fresh sessions, toon delete, keyless authoring","criteria_total":8,"criteria_met":6} -->
