## Spec — 2026-06-29 — world-hot-swap: live in-process world swap without restart

**Goal:** Add a live, in-process world swap so an operator can replace the running server's live DB with a different world DB (a snapshot or a `world bootstrap` output) WITHOUT restarting the FastAPI process, and connected clients converge on the new world. This is the deferred consumer that makes `snapshot`/`snapshot-restore` non-latent: snapshot-restore is the offline (server-down) path; swap is its online counterpart. This turn ships the server-side mechanism with a provable oracle; the graceful SPA transition UX is a named follow-up (out of scope below).

### Acceptance Criteria

- [x] **Live swap, no restart.** With the server running, an admin-gated, in-process swap installs a target world DB as the live DB and the SAME running process begins serving the new world. The process is not restarted (same PID; the FastAPI lifespan does not cycle). The swap is reachable as `bin/game world swap <target.db>` (a thin client to the in-process path), mirroring the `snapshot-restore <file>` argument shape. Verified by a test that boots the app, swaps to a second world DB, and asserts a subsequent state snapshot reflects the new world's rooms/toons while the app instance is unchanged.

- [x] **Connected clients are served the new world.** On swap, every currently-connected WebSocket subscriber receives a fresh `state_snapshot` of the new world (or a control/close signal that drives its reconnect to one) — no socket is left rendering stale world-A state indefinitely. Verified by the oracle: hold an open WS to world A, trigger the swap, and assert that socket receives world B's `state_snapshot` (not stale A state).

- [x] **Atomic, corruption-free, and failure-safe.** After a successful swap the live DB content equals the target DB exactly, with no orphaned `-wal`/`-shm` from the prior live DB bleeding into the new one (the implementation must checkpoint or use indirection to prevent this — mechanism is the implementer's choice). Input arriving during the swap window never serves half-swapped/empty state and never crashes the server. A swap that is refused OR fails partway leaves the server still serving the ORIGINAL world over a healthy connection (never a closed/`None` `_conn` that bricks the running server).

- [x] **The drift loop survives the swap.** The background drift task is stopped before the DB transition and restarted after it against the new world; no drift tick writes to a closed or mid-rename DB during the transition. Verified by a test asserting drift emits against the new world's NPCs after a swap with no exception logged across the boundary, and the `_TICK_COUNTS` contract is intact.

- [x] **Unsafe swaps are refused with a clear message and zero state change.** Each of these refuses without disrupting the live world or any client: no live DB / server not in a swappable state; target file does not exist; target is not a readable daydream SQLite DB; target's applied-migration max (from its own `_migrations` table) exceeds this code's max known migration (newer schema). CLI refusals exit non-zero; the in-process path returns a clear error response.

- [x] **Round-trip + reconnect oracle is the spine; tiers green; docs rolled forward.** A `tier_medium` oracle (seed world A live, open a WS, swap to world B, assert the connected socket converges on world B AND the live DB equals world B and differs from world A, with world B opened independently to confirm) is the spine of the test plan, not an afterthought. Edge-case tests cover the refusals and drift-survival. `bin/game test short` and `bin/game test medium` exit 0. README and CLAUDE.md roll forward: the new `world swap` verb, the live-vs-offline distinction from `snapshot-restore`, and the new on-swap WS behavior (new server→client control/snapshot semantics).

### Context

**This is adopted from the 2026-06-29 turn proposal and consumes BACKLOG `world-hot-swap`.** Prior turn (`snapshot-restore-commands`, shipped `89697ad`) deliberately built latent infrastructure; this turn builds its consumer so the DB-only snapshot/bootstrap outputs become usable against a live server.

**Architecture grounding (from a codebase map; verify against current code before relying on a line number).**
- *DB handle is a single process-global, not a pool.* `daydream/db.py` holds `_conn: sqlite3.Connection | None`; `init_live()` opens+migrates, `get_conn()` returns it, `close_db()` closes and nulls it. The swap primitive is `close_db()` + `init_live()` against a new file. All DB access routes through `get_conn()`, so swapping the global is sufficient — but everything in flight that holds the old handle is a hazard (criterion 3).
- *`live.db` is a plain FILE today — no symlink indirection exists* (`config.live_db_path()` returns `worlds-{env}/live.db`). The BACKLOG's "atomic rename of a `live` symlink" is therefore not free: the implementer either introduces symlink indirection OR does `PRAGMA wal_checkpoint(TRUNCATE)` then swaps the file. Either is fine; the contract is criterion 3 (target content exactly, no orphan-WAL corruption). Do not naively rename `live.db` and leave `-wal`/`-shm` behind.
- *No control-plane WS message exists.* `daydream/api/ws.py` protocol is `state_snapshot` / `event` (server→client) and `input` (client→server); `daydream/events.py` has `_subscribers` + `_broadcast`. Delivering the new world to open sockets (criterion 2) needs either broadcasting a fresh per-socket `state_snapshot` or a new control kind / clean close. There is no client-side reconnect-on-control handler today.
- *Events are synchronous inline; the drift loop is the main async writer.* `daydream/drift.py` is started/stopped in the `daydream/server.py` lifespan, and `drift_handle` is NOT currently exposed outside the lifespan. The swap must be able to stop and restart it (criterion 4), which means plumbing the handle to the swap path or making it module-accessible.
- *THE KEY CONSTRAINT: the offline admin CLI is a separate process and cannot reach the running server's `_conn`/`drift_handle`.* `snapshot`/`restore`/`snapshot-restore` all require the server DOWN for exactly this reason. A LIVE swap must run IN the server process — an admin-gated endpoint in the running app — with `bin/game world swap` as a thin client that calls it. Criterion 1's "same PID, in-process" forces this; do not try to implement swap as a standalone `daydream.admin` subprocess.

**Distinction from snapshot-restore (already shipped, `daydream/admin.py`).** `snapshot-restore <file> --yes` is offline: it refuses when a live DB exists and is run with the server down. `swap` is the online counterpart: server up, replaces the live DB in-process, signals clients. Reuse the existing validation helpers where they fit (`_max_known_migration`, `_applied_migration_max`, the read-only/immutable probe that reads a candidate's `_migrations` without creating sidecars).

**zat.env practices for this increment.** Write the paired `tier_medium` tests in the same increment as the code (the round-trip+reconnect oracle is the verification spine — oracle over proxy over critic). This increment is genuinely multi-component (db, server lifespan, drift, ws/events, a new in-process endpoint, admin/bin wiring, tests); land it as one coherent unit but do not stack untested changes — get the swap mechanism green under the oracle before layering refusals. Change only what is necessary; no unrelated refactor of the archive/restore code. Per the anti-pattern this whole feature exists to avoid: deliver a usable end-to-end live swap, not more latent infrastructure.

**Out of scope (do not build scaffolding for these).**
- *Graceful SPA transition UX* — the "the dream shifts..." overlay, client-side reconnect-on-control handling, and re-selecting a toon that does not exist in the swapped-in world. This is the immediate follow-up increment; this turn's client contract is only "the server delivers the new world to open sockets" (criterion 2), verified server-side via TestClient, not a browser eyeball.
- *Multi-env* (`--env dev|preview|prod`), *per-world / partial swap* (swap is all-or-nothing on the whole live DB), snapshot retention/GC, and migrating a newer-schema target on the fly (newer schema is refused, criterion 5; older schema migrates forward on the next natural `init_live`).

**Critical files (from the map; confirm before editing):**
- `daydream/db.py` — the `_conn` swap primitive (`close_db()` + `init_live()`).
- `daydream/server.py` — lifespan; expose/limit `drift_handle` so the swap can stop+restart drift.
- `daydream/drift.py` — `start_drift_loop` / `stop_drift_loop`.
- `daydream/events.py`, `daydream/api/ws.py` — subscriber fanout; on-swap snapshot/control delivery to open sockets.
- a new admin-gated in-process swap endpoint (under `daydream/api/`).
- `daydream/admin.py` + `bin/game` — thin `world swap` client to the endpoint.
- `tests/` — a `tier_medium` oracle (likely `tests/test_ws_swap.py` or extending `test_admin.py`); WS tests boot via `TestClient(app)` with the stubbed LLM.
- `README.md`, `CLAUDE.md` — roll-forward per the last criterion.

---
*Prior spec (2026-05-27): snapshot-restore-commands closed 6/6 — `bin/game world snapshot` / `snapshot-restore`, WAL-checkpointed DB-only point-in-time copies with refuse-every-unsafe-overwrite restore and a round-trip oracle test.*

<!-- SPEC_META: {"date":"2026-06-29","title":"world-hot-swap: live in-process world swap without restart","criteria_total":6,"criteria_met":6} -->
