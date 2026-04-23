## Spec — 2026-04-23 — multi-room navigation

**Goal:** Replace the hardcoded one-room meadow with a hand-seeded ≥5-room world the player can walk through. Adds a `go <direction>` core skill, populates `rooms.exits_json` as the source of truth, and renders exits as clickable buttons in the SPA. The image-gen pipeline (v1) renders a fresh background per new room visited; the GPU arbiter and cache need no changes (cache key already includes `room_id`).

### Acceptance Criteria

- [x] **`go <direction>` core skill moves the toon between rooms.** Typing `go north` when the current room has a `north` exit emits a `move` event (with `from_room`, `to_room`, `direction` in the payload), updates the toon's `current_room_id`, and the next `state_snapshot` reflects the new room (title, description, items, exits, image_url). Typing `go <direction>` for a direction not in the current room's `exits_json` emits a `narrate` event ("you can't go that way" or similar) and emits no `move` event.
- [x] **`exits_json` is the single source of truth for navigation.** The `rooms.exits_json` field maps direction names (e.g. `north`, `south`, `east`, `west`, plus `up` / `down` / `in` / `out` if a room uses them) to target `room_id`s. The `go` skill reads it; the WS snapshot includes `room.exits` derived from it. No room adjacency hardcoded outside the SQL migration that seeds it.
- [x] **A new migration seeds ≥5 connected rooms with bidirectional exits.** `migrations/002_*.sql` (or whatever the next number is) extends the v0 meadow into a connected world of at least 5 rooms. Every exit is bidirectional: if room A's `exits_json` maps `north → B`, then B's maps `south → A`. Each room has a meaningful `seed` that the image-gen and LLM pipelines can use. The migration is idempotent (won't double-seed on re-run) and does not destroy the existing meadow row.
- [x] **The SPA renders exits as clickable buttons.** `state_snapshot.room.exits` flows into the SPA, which renders one button per exit alongside the existing skill bar. Clicking an exit button sends `{kind: "input", text: "go <direction>"}` — the canonical-bypass path, no LLM round-trip. When the room changes, the exit button set updates without a page reload.
- [x] **Persistence across restart preserves the player's current room.** After `go north` followed by `bin/game down && bin/game up` and a reconnect, the snapshot reflects the destination room (not the starting meadow). The `move` event is in the events log; the toon's `current_room_id` was updated.
- [x] **Image-gen and cache work per-room with no regression.** Each new room's first visit triggers async image gen (cold cache → SPA shows "painting...") and caches under `~/data/daydream/images/cache/{world}/{room}/{hash}.png`. The meadow's existing cached image continues to serve. No changes to `daydream/images/cache.py` or `daydream/images/client.py` required (the cache key already includes `room_id`); this criterion is a regression guard.
- [x] **Tests cover the navigation contract without GPU.** New unit tests in `tests/test_skills.py` for the `go` skill (happy-path move event + side effect on `toons.current_room_id`; rejection narration for unknown direction; case-insensitive direction). New WS integration test in `tests/test_ws.py` for the navigation flow (connect → snapshot has exits → send `go north` → receive move event → next snapshot has the new room). Updates to `tests/test_db.py` if its existing room-count assertions break under the new migration. All new tests are LLM/GPU/network-free via the existing mocks.

### Context

**Adopted from BACKLOG entry** `multi-room-navigation` (now annotated `(ACTIVE in spec 2026-04-23)` in BACKLOG.md). This is the smallest of the three slices the v1 close-out proposal recommended, and explicitly the suggested first slice ("proves nav, cheap"). The other two — `data-skills-cli` + `safety-baseline-v1`, and `npc-drift-loop` — remain in BACKLOG and become the natural follow-up turns.

**State coming in (since the proposal was written).** Beyond what the proposal's "What happened" describes, this turn also lands on top of: (a) ComfyUI moved into `external/ComfyUI/` with `bin/comfyui-bootstrap`; vLLM on the same external-engines pattern (CLAUDE.md "External engines"). (b) Port hygiene: daydream FastAPI on `54321`, vLLM and ComfyUI on `127.0.0.1` defaults; `DAYDREAM_ACCESS=tailscale|public` toggle with the `AccessMiddleware` enforcing at the HTTP/WS layer. (c) Comprehensive GPU/ML doc pass at `docs/gpu-and-models.md`; drift-catcher tests for the WHIMSY suffix and the workflow LoRA name. (d) 153/153 tests green across all of the above. The new `go` skill should fit cleanly into all of this — no new infrastructure required.

**Where things live.**
- Existing core skills (`look`, `say`, `examine`) in `daydream/skills/core.py`. Add `go` next to them, register in `daydream/skills/registry.py`.
- Room read helpers in `daydream/rooms.py` (already has `get_room`, `get_room_by_slug`); add `move_toon(toon_id, room_id)` or do it inline in `go`. Toon write goes through `daydream/toons.py`.
- WS snapshot composition is in `daydream/api/ws.py:_state_snapshot`; extend the `room` dict with `exits`. The canonical-bypass router (first-word-matches-skill-name → direct dispatch) already handles `go north` without LLM (no change needed).
- SPA shell is `web/index.html`; rendering JS is `web/assets/main.js`; styles in `web/assets/style.css`. Add an exits container alongside the skill bar.

**Migration shape recommendation.** `migrations/002_multi_room.sql` should `INSERT` four new rooms (with seeds matching the WHIMSY anchor — soft, painterly, cozy) and `UPDATE` the meadow's `exits_json` plus each new room's so the world graph is connected. SQL `ON CONFLICT` clauses or `INSERT OR IGNORE` keep the migration idempotent.

**Aesthetic anchor (locked, do not drift).** Spiritfarer / A Short Hike. New room seeds should read like the meadow seed does: small, sensory, unhurried. Examples to match the tone: "the quiet forge with embers drifting like sleepy fireflies"; "a wooden bridge over a slow stream, dragonflies"; "an attic with afternoon dust in slanting light". Avoid grandiose, urgent, or modern-tech language. WHIMSY.md is the authority.

**Out of scope for this spec** (deferred; do not build):
- **Toon slot management.** v1 still has one hardcoded toon (Wren). Movement applies to that toon. `toon-slot-management` BACKLOG entry stays deferred.
- **NPC drift / NPC dialogue.** No NPCs move or speak in this spec. `npc-drift-loop` and `npc-memory-retrieval` stay deferred.
- **World bootstrap via Opus.** Hand-seed the 5 rooms via SQL. `world-bootstrap-opus` stays deferred.
- **Per-room LLM voice or image-gen prompt variation.** The single workflow JSON + WHIMSY suffix is sufficient — each room's seed already differentiates the output.
- **Skill authoring (data skills).** No data-skill registry changes here. `data-skills-cli` + `safety-baseline-v1` stay deferred.
- **Painterly Svelte UI polish.** Vanilla TS SPA stays. Exits rendered as buttons reusing the existing skill-bar styling pattern.

**zat.env conventions to respect** (familiar from v0/v1; carried for the implementing agent's convenience):
- Bind `0.0.0.0` for daydream (port 54321 by default; access middleware filters by source IP).
- HF cache shared at `~/.cache/huggingface`; persistent state under `~/data/daydream/`.
- Python venv at `.venv/`; `PIP_REQUIRE_VIRTUALENV=true` is set globally.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- Work in small committable increments; tests in the same increment as code; re-run pytest after each change. Per zat.env, "Spec is code": `/codereview` will check the implementation against these criteria before any push.

**Critical files to create or modify:**

- `migrations/002_multi_room.sql` (new; 4 rooms + meadow exits update; idempotent)
- `daydream/skills/core.py` (modify; add `go` handler)
- `daydream/skills/registry.py` (modify; register `go`)
- `daydream/rooms.py` and/or `daydream/toons.py` (modify; `current_room_id` update helper)
- `daydream/api/ws.py` (modify; `_state_snapshot` includes `room.exits`)
- `web/assets/main.js` (modify; render exits, route clicks to `go <direction>` input)
- `web/assets/style.css` (modify; exit-button styling, mirrors `#skill-bar button`)
- `tests/test_skills.py` (modify; `go` skill tests)
- `tests/test_ws.py` (modify; navigation flow test)
- `tests/test_db.py` (modify; update room-count assertions if they're now wrong)

---
*Prior spec (2026-04-23): v1 image-gen pipeline shipped 8/8 — WHIMSY tone bible, GPU arbiter (asyncio.Lock, in-process), ComfyUI workflow + bin/game image-test, cache + WS room-image flow, SPA painting state + bg swap, vLLM serving Qwen 2.5 7B Instruct AWQ, live arbiter smoke at 9 s for 5 alternating LLM↔image requests.*

<!-- SPEC_META: {"date":"2026-04-23","title":"multi-room navigation","criteria_total":7,"criteria_met":7} -->
