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
        # Migration 011 unified rooms / toons / items into one `objects`
        # table; the three separate tables no longer exist after the chain.
        expected = {
            "worlds", "objects", "skills", "seeds", "events",
            "generated_assets",
            "_migrations",
        }
        assert expected.issubset(tables), f"missing tables: {expected - tables}"
        gone = {"rooms", "toons", "items"}
        assert not (gone & tables), f"old tables still present: {gone & tables}"
    finally:
        conn.close()


def test_init_schema_seeds_starter_world(temp_db_path: Path):
    conn = db.open_db(temp_db_path)
    try:
        db.init_schema(conn, config.MIGRATIONS_DIR)
        world = conn.execute("SELECT slug, aesthetic_seed FROM worlds").fetchone()
        assert world["slug"] == "bunny-world"
        assert "painterly" in world["aesthetic_seed"]

        # Post-011 the seed lives in `objects`: rooms / toons / things are
        # rows discriminated by `kind`; their kind-specific fields (slug,
        # title, seed, exits, presence_text, ...) live in properties_json,
        # read here via json_extract so this stays a pure migration test.
        # Meadow is the player's starting room; other rooms land via 004.
        meadow = conn.execute(
            "SELECT name, json_extract(properties_json, '$.slug') AS slug "
            "FROM objects WHERE id = 'r-meadow'"
        ).fetchone()
        assert meadow["slug"] == "meadow"
        # 004_multi_room extends the world to 5 connected rooms with
        # bidirectional exits. Keep this count in sync with the migration.
        room_count = conn.execute(
            "SELECT COUNT(*) FROM objects WHERE kind = 'room'"
        ).fetchone()[0]
        assert room_count == 5
        # Every room has non-empty exits (at minimum the reverse of whatever
        # points to it), so navigation can't dead-end on load. An empty exits
        # object serializes to '{}'; any room still at '{}' means 004 missed it.
        orphans = conn.execute(
            "SELECT id FROM objects WHERE kind = 'room' "
            "AND json_extract(properties_json, '$.exits') = '{}'"
        ).fetchall()
        assert not orphans, f"rooms with no exits: {[r['id'] for r in orphans]}"

        # Wren is the player's toon (slot 1). Select by id so the test
        # isn't sensitive to insertion order once NPCs land.
        wren = conn.execute(
            "SELECT name, slot, is_human_controlled FROM objects WHERE id = 't-wren'"
        ).fetchone()
        assert wren["name"] == "Wren"
        assert wren["slot"] == 1
        # 006_first_npc adds Rook, the forge-keeper (slot 100, NPC
        # convention). location_id is the unified containment column
        # (was current_room_id); presence_text now lives in properties.
        rook = conn.execute(
            "SELECT name, slot, location_id, is_human_controlled, "
            "       json_extract(properties_json, '$.presence_text') AS presence_text "
            "FROM objects WHERE id = 't-rook'"
        ).fetchone()
        assert rook["name"] == "Rook"
        assert rook["slot"] == 100
        assert rook["location_id"] == "r-forge"
        assert rook["is_human_controlled"] == 0
        assert isinstance(rook["presence_text"], str) and rook["presence_text"].strip()
        # Wren's presence_text stays null (controlled toon is filtered out of
        # the greeting iteration anyway; a greeting here would be dead data).
        wren_presence = conn.execute(
            "SELECT json_extract(properties_json, '$.presence_text') AS p "
            "FROM objects WHERE id = 't-wren'"
        ).fetchone()["p"]
        assert wren_presence is None

        item = conn.execute(
            "SELECT name, json_extract(properties_json, '$.seed') AS seed "
            "FROM objects WHERE kind = 'thing'"
        ).fetchone()
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
        assert conn.execute(
            "SELECT COUNT(*) FROM objects WHERE kind = 'room'"
        ).fetchone()[0] == 5
        # Wren (slot 1, human) + Rook (slot 100, NPC from 006_first_npc)
        # + Iris (slot 101, NPC from 008_second_npc).
        assert conn.execute(
            "SELECT COUNT(*) FROM objects WHERE kind = 'toon'"
        ).fetchone()[0] == 3
        assert conn.execute(
            "SELECT COUNT(*) FROM objects WHERE kind = 'thing'"
        ).fetchone()[0] == 1
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
