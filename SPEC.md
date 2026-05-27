## Spec — 2026-05-27 — snapshot-restore-commands: fast DB-only world snapshots + restore

**Goal:** Add `bin/game world snapshot <world_id>` (a WAL-checkpointed, DB-only point-in-time copy under `~/data/daydream/snapshots/{world}-{ts}.db`) and an inverse `snapshot-restore` verb that reinstates a snapshot as the live DB while refusing every unsafe overwrite. This is the fast, lightweight sibling to the existing `archive`/`restore` (which bundle DB + per-world image cache + manifest into a tarball for shipping a world off-box). DB-only snapshots are the substrate the deferred `world-hot-swap` flow will build on, but this turn ships the CLI verbs only.

### Acceptance Criteria

- [x] **`bin/game world snapshot <world_id>` writes a WAL-checkpointed, DB-only point-in-time copy.** It runs `PRAGMA wal_checkpoint(TRUNCATE)` on the live DB before copying so the output is self-contained (no `-wal`/`-shm` sidecar required to read it), then writes a single SQLite file to `~/data/daydream/snapshots/{world_id}-{ts}.db` (timestamp format `%Y%m%d-%H%M%S`, mirroring `archive`). It creates `snapshots/` if absent. The output opens as a valid SQLite DB containing the world's rows; no tarball, no `MANIFEST.json`, and no per-world image cache is bundled (bundling is `archive`'s job). It prints a one-line confirmation naming the output path and byte size, and exits 0.

- [x] **Snapshot create-side refusals each exit 2 with a clear stderr message and write no file.** When: (a) no live DB exists (reuses the existing `_require_live_db` guard's message); (b) `<world_id>` is not a row in the live `worlds` table ("no world with id ..."); (c) the computed output path already exists (refuse-on-collision rather than silently overwrite).

- [x] **`bin/game world snapshot-restore <snapshot.db> --yes` reinstates a snapshot as the live DB, refusing every unsafe case.** On success it installs the snapshot file as `config.live_db_path()`, prints a confirmation, and exits 0. It exits 2 and writes nothing when: (a) `--yes` is absent; (b) the snapshot file does not exist; (c) a live DB already exists at the target (refuse-to-overwrite — same posture as archive `restore`); (d) the candidate file's applied-migration max (read from its own `_migrations` table) exceeds this code's max known migration, or the file is not a readable daydream SQLite DB.

- [x] **Round-trip oracle test `test_snapshot_restore_round_trip` (tier_medium) is the spine of the test plan.** It seeds a live world, captures its state (fingerprint F0), takes a snapshot, mutates live so the state differs (F1 ≠ F0), then runs `snapshot-restore --yes` and asserts the restored DB equals F0 and differs from F1. It independently opens the snapshot `.db` with `sqlite3` and confirms the snapshot captured F0 (the pre-mutation state), not F1. No GPU, no real LLM. (May mirror `test_restore_round_trip`'s fresh-data-dir mechanic to avoid `-wal` sidecar carryover.)

- [x] **Edge-case tests cover the refusals and the WAL guarantee (tier_medium, no GPU), in `tests/test_admin.py`.** At minimum: snapshot produces a valid SQLite DB-only file with no tarball; snapshot refuses unknown world; snapshot refuses with no live DB; snapshot refuses on output-path collision; snapshot-restore refuses without `--yes`; snapshot-restore refuses a missing file; snapshot-restore refuses when a live DB exists; snapshot-restore refuses a newer-schema file; and a WAL test confirming a row committed to live before the snapshot is present when the snapshot file is opened independently (proves the checkpoint flushed the WAL into the copied file).

- [x] **`bin/game test short` and `bin/game test medium` exit 0; README + CLAUDE.md rolled forward.** The new verbs are wired into `daydream/admin.py`'s argparse and surfaced in `bin/game`'s usage/help line. README's "World admin" bullet and the Tech-sketch persistence row list `snapshot` / `snapshot-restore`, and the README short/medium test counts are updated. CLAUDE.md's "Generated assets" file-layout block gains `snapshots/{world}-{ts}.db`, its operator-commands block gains the two verbs, and the now-stale "**Distinct from `snapshot-restore-commands` (BACKLOG).**" note is updated to reflect that the feature shipped (snapshot = fast DB-only point-in-time; archive = heavyweight full bundle).

### Context

**Distinction from archive/restore (already shipped, in `daydream/admin.py`).** `archive <world_id>` tars `live.db` (post-WAL-checkpoint) + the per-world image cache + a `MANIFEST.json` into `archives/{world}-{ts}.tar.gz`; `restore <archive> --yes` validates the manifest and untars into the data dir. Snapshots are deliberately lighter: a bare `.db` file, no cache, no manifest — fast point-in-time capture for rollback/hot-swap, not for shipping a world to another box. The two are siblings, not replacements. Reuse the existing helpers (`_require_live_db`, `_max_known_migration`, `_applied_migration_max`, the `datetime.now().strftime` timestamp, `db.init_live()` + `PRAGMA wal_checkpoint(TRUNCATE)` from `cmd_archive`) rather than re-deriving them.

**WAL checkpoint is load-bearing.** The DB runs in WAL mode (`daydream/db.py:open_db`). Recent committed writes can live in `live.db-wal`, not the main file. A naive copy of `live.db` alone would miss them — exactly the bug `cmd_archive` already guards against. Snapshot must checkpoint(TRUNCATE) first so the copied `.db` is a complete, self-contained point-in-time.

**Restore target and non-destructiveness.** `snapshot-restore` installs the file at `config.live_db_path()` (`worlds-{env}/live.db`). It refuses to overwrite an existing live DB (the data-loss guard), so the documented "bring it back" flow is: `bin/game down`, clear/move the current live DB (and its `-wal`/`-shm` sidecars), then `snapshot-restore --yes`. The round-trip test reproduces this precondition. `--yes` is required for symmetry with `restore`/`delete`. Like archive-restore, when the snapshot's schema is older than current code, a one-line note that the next `bin/game up` will migrate forward is a nice-to-have (not gated).

**Verb naming.** `snapshot` is the create verb (matches the BACKLOG command shape `bin/game world snapshot NAME` and the goal). The inverse is a distinct verb (`snapshot-restore`) rather than overloading the existing `restore`, which takes a `.tar.gz` archive and validates a manifest — overloading would make the file-type contract ambiguous.

**Out of scope (do not build scaffolding for these — zat.env: "Do not build scaffolding for features that are not needed yet").**
- `world-hot-swap` (separate v2 BACKLOG entry): the SHELVE broadcast → drain → checkpoint → close-pool → atomic `rename` of a live symlink → reopen-pool → `world_changed` broadcast. This spec ships CLI verbs only; no symlink, no live pool reopen, no WS broadcast.
- Snapshot retention / GC / pruning of old `.db` files. No automatic cleanup; the dir grows until an operator clears it (a future gardening pass, like the `pinned` column comment on assets).
- `bin/game status` / `world list` integration (no snapshot inventory surfaced).
- Restoring a snapshot into a *different* world id or env than it came from (a snapshot is restored as-is into the current env's live slot).

**zat.env practices for this increment.** Work in one committable increment; write the paired tier_medium tests in the same increment as the `admin.py` code (don't stack untested changes). Verify `bin/game test short` + `medium` green before and after. Keep the change minimal — two new `cmd_*` functions + two argparse subparsers + the bin/game usage string + docs; no refactor of the existing archive/restore code beyond extracting a shared helper if one is genuinely warranted.

**Critical files:**
- `daydream/admin.py` — add `cmd_snapshot(world_id)` and `cmd_snapshot_restore(path, yes)`, a `_snapshots_dir()` helper, and the two argparse subparsers + dispatch.
- `tests/test_admin.py` — the round-trip oracle + edge-case tests (all `tier_medium`; the module is already `pytestmark = tier_medium`).
- `bin/game` — extend the `usage:` strings if they enumerate world subcommands (the `cmd_world` shell is already a thin `python -m daydream.admin "$@"` pass-through, so no per-verb wiring needed there).
- `README.md`, `CLAUDE.md` — roll-forward per the last criterion.

---
*Prior spec (2026-05-07): drift-bootstrapped-npcs closed 7/7 — opened drift eligibility to all NPCs and added a generic mood-bucketed canned pool so bootstrapped NPCs (`t-<slug>-<uuid>`) drift on the offline path.*

<!-- SPEC_META: {"date":"2026-05-27","title":"snapshot-restore-commands: fast DB-only world snapshots + restore","criteria_total":6,"criteria_met":6} -->
