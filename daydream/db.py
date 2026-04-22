"""SQLite connection management, migrations, WAL setup.

v0 uses a single process-wide connection (single-writer pattern). The full
async write-queue lands in v2; for now sqlite3's own thread-safety with
check_same_thread=False is sufficient at single-user scale."""

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
