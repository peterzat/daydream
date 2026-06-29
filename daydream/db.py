"""SQLite connection management, migrations, WAL setup.

v0 uses a single process-wide connection (single-writer pattern). The full
async write-queue lands in v2; for now sqlite3's own thread-safety with
check_same_thread=False is sufficient at single-user scale."""

import os
import shutil
import sqlite3
from pathlib import Path

from daydream import config

_conn: sqlite3.Connection | None = None


def open_db(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection in WAL mode with sane defaults."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection, migrations_dir: Path) -> list[str]:
    """Apply any unapplied migrations in lexical order. Returns the names of files
    applied this call (empty list if everything was already applied)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations ("
        "  filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    applied = {row["filename"] for row in conn.execute("SELECT filename FROM _migrations")}
    newly_applied: list[str] = []
    for f in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
        if f.name in applied:
            continue
        conn.executescript(f.read_text())
        conn.execute("INSERT INTO _migrations(filename) VALUES (?)", (f.name,))
        newly_applied.append(f.name)
    return newly_applied


def init_live(
    path: Path | None = None, migrations_dir: Path | None = None
) -> sqlite3.Connection:
    """Open the live DB and run any pending migrations. Idempotent: returns the
    existing connection if already initialized."""
    global _conn
    if _conn is not None:
        return _conn
    if path is None:
        path = config.live_db_path()
    if migrations_dir is None:
        migrations_dir = config.MIGRATIONS_DIR
    _conn = open_db(path)
    init_schema(_conn, migrations_dir)
    return _conn


def get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("DB not initialized; call init_live() first")
    return _conn


def close_db() -> None:
    """Close the live connection. For tests and shutdown."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def max_known_migration() -> int:
    """Highest numeric migration prefix this code ships in `migrations/`. A
    swap/restore refuses any DB whose applied-migration max exceeds this (it
    would expect columns this code does not know about)."""
    nums = []
    for f in config.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"):
        try:
            nums.append(int(f.name[:3]))
        except ValueError:
            continue
    return max(nums) if nums else 0


def applied_migration_max(conn: sqlite3.Connection) -> int:
    """Highest migration number actually applied to `conn`'s DB, read from
    its own `_migrations` table. Pair with `max_known_migration()` to reject
    a newer-schema candidate before swapping it in."""
    nums = []
    for r in conn.execute("SELECT filename FROM _migrations").fetchall():
        try:
            nums.append(int(r["filename"][:3]))
        except (ValueError, KeyError, TypeError):
            continue
    return max(nums) if nums else 0


def _unlink_wal_sidecars(db_path: Path) -> None:
    """Remove `-wal` / `-shm` sidecars next to `db_path` if present. Used by
    the swap path so an orphaned WAL from a prior live DB never bleeds into
    the file opened next."""
    for sfx in ("-wal", "-shm"):
        p = db_path.parent / (db_path.name + sfx)
        if p.exists():
            p.unlink()


def swap_live_db(target_path: Path) -> None:
    """Replace the live DB file with `target_path`'s content in-process and
    reopen the connection onto it.

    SYNCHRONOUS by contract: it performs no `await`, so under asyncio's
    single-threaded cooperative model the close -> install -> reopen sequence
    is atomic with respect to every other coroutine. No WS or drift task can
    observe a half-open `_conn` (the `_conn is None` window exists only inside
    this function, where no other coroutine runs).

    Failure-safe: the current live DB is moved aside before the install and
    restored if the copy or reopen fails, so a failed swap leaves the server
    serving the ORIGINAL world over a healthy connection.

    WAL handling: the current connection is `wal_checkpoint(TRUNCATE)`'d
    before close so the outgoing `live.db` is self-contained, and stale
    `-wal`/`-shm` sidecars are cleared before the reopen so no orphaned WAL
    bleeds into the new DB.

    Callers MUST have already validated `target_path` (a readable daydream DB
    whose schema is not newer than this code) and stopped the drift loop.
    """
    global _conn
    target_path = Path(target_path)
    live = config.live_db_path()
    live.parent.mkdir(parents=True, exist_ok=True)

    if _conn is not None:
        try:
            _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        _conn.close()
        _conn = None

    backup = live.parent / (live.name + ".swapbak")
    if backup.exists():
        backup.unlink()
    had_live = live.exists()
    if had_live:
        os.replace(live, backup)
    _unlink_wal_sidecars(live)

    try:
        shutil.copyfile(target_path, live)
        _unlink_wal_sidecars(live)
        init_live()
    except Exception:
        # Roll back to the original world: drop the partial install, restore
        # the backup, reopen. The server is never left without a live DB.
        if _conn is not None:
            _conn.close()
            _conn = None
        _unlink_wal_sidecars(live)
        if live.exists():
            live.unlink()
        if had_live:
            os.replace(backup, live)
            init_live()
        raise
    finally:
        if backup.exists():
            backup.unlink()
