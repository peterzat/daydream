"""DB initialization, WAL config, and migration runner."""

from pathlib import Path

import pytest

from daydream import config, db

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def reset_db_singleton():
    db.close_db()
    yield
    db.close_db()


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def test_open_db_sets_wal_mode(temp_db_path: Path):
    conn = db.open_db(temp_db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        sync = conn.execute("PRAGMA synchronous").fetchone()[0]
        assert sync == 1  # NORMAL
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_init_schema_creates_all_tables(temp_db_path: Path):
    conn = db.open_db(temp_db_path)
    try:
        applied = db.init_schema(conn, config.MIGRATIONS_DIR)
        assert "001_initial.sql" in applied
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        expected = {
            "worlds", "rooms", "toons", "items", "skills", "seeds", "events",
            "generated_assets",
            "_migrations",
        }
        assert expected.issubset(tables), f"missing tables: {expected - tables}"
    finally:
        conn.close()


def test_init_schema_seeds_starter_world(temp_db_path: Path):
    conn = db.open_db(temp_db_path)
    try:
        db.init_schema(conn, config.MIGRATIONS_DIR)
        world = conn.execute("SELECT slug, aesthetic_seed FROM worlds").fetchone()
        assert world["slug"] == "bunny-world"
        assert "painterly" in world["aesthetic_seed"]

        # Meadow is the player's starting room; other rooms land via 004.
        meadow = conn.execute(
            "SELECT slug, title FROM rooms WHERE id = 'r-meadow'"
        ).fetchone()
        assert meadow["slug"] == "meadow"
        # 004_multi_room extends the world to 5 connected rooms with
        # bidirectional exits. Keep this count in sync with the migration.
        room_count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
        assert room_count == 5
        # Every room has a non-empty exits_json (at minimum the reverse
        # of whatever points to it), so navigation can't dead-end on
        # load. '{}' is the DEFAULT from the schema; any row still at
        # '{}' means 004 missed it.
        orphans = conn.execute(
            "SELECT id FROM rooms WHERE exits_json = '{}'"
        ).fetchall()
        assert not orphans, f"rooms with no exits: {[r['id'] for r in orphans]}"

        toon = conn.execute("SELECT name, slot FROM toons").fetchone()
        assert toon["name"] == "Wren"
        assert toon["slot"] == 1

        item = conn.execute("SELECT name, seed FROM items").fetchone()
        assert item["name"] == "lantern"
        # SPEC criterion 5 sentinel: examine output must include this string.
        assert "hairline crack" in item["seed"]
    finally:
        conn.close()


def test_init_schema_is_idempotent(temp_db_path: Path):
    conn = db.open_db(temp_db_path)
    try:
        first = db.init_schema(conn, config.MIGRATIONS_DIR)
        second = db.init_schema(conn, config.MIGRATIONS_DIR)
        assert "001_initial.sql" in first
        assert second == []
        # And re-running did not duplicate seed rows.
        assert conn.execute("SELECT COUNT(*) FROM worlds").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM toons").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    finally:
        conn.close()


def test_init_live_returns_singleton(tmp_path: Path):
    path = tmp_path / "live.db"
    c1 = db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    c2 = db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    assert c1 is c2
    db.close_db()
    c3 = db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    assert c3 is not c1  # closed and reopened


def test_get_conn_raises_before_init():
    db.close_db()
    with pytest.raises(RuntimeError, match="not initialized"):
        db.get_conn()
