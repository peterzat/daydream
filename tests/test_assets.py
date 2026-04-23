"""Generated-asset provenance: schema (world_id, pinned, workflow_hash),
record helpers (idempotent on natural key), pin/unpin, list/total filters,
and the unified generate_image API recording on persistent miss but not on
hit or ephemeral."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from daydream import assets, config, db
from daydream.images import cache as image_cache
from daydream.images import client as image_client

pytestmark = pytest.mark.tier_short


@pytest.fixture
def conn(tmp_path: Path):
    """A fresh sqlite connection with all migrations applied."""
    c = db.open_db(tmp_path / "test.db")
    db.init_schema(c, config.MIGRATIONS_DIR)
    yield c
    c.close()


@pytest.fixture
def live_db(tmp_path: Path, monkeypatch):
    """Initialize the global DB singleton against a per-test temp path."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    db.init_live(path=tmp_path / "live.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()


# ---- migration ----------------------------------------------------------


def test_migration_creates_generated_assets_table(conn):
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "generated_assets" in tables


def test_migration_creates_target_index(conn):
    indices = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )}
    assert "idx_generated_assets_target" in indices
    assert "idx_generated_assets_world" in indices


def test_generated_assets_has_world_pinned_workflow_hash_columns(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(generated_assets)")}
    assert {"world_id", "pinned", "workflow_hash"}.issubset(cols)


def test_rooms_table_no_longer_has_image_cache_key(conn):
    """Migration 003 drops the dead column."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(rooms)")}
    assert "image_cache_key" not in cols


def test_unique_constraint_on_natural_key(conn):
    import sqlite3
    conn.execute(
        "INSERT INTO generated_assets (asset_kind, target_kind, target_id, "
        "target_seed, seed_hash, file_relpath, world_id, workflow_hash) VALUES "
        "('image', 'room', 'r-1', 'seed', 'h', 'a.png', 'w-1', 'wh')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO generated_assets (asset_kind, target_kind, target_id, "
            "target_seed, seed_hash, file_relpath, world_id, workflow_hash) VALUES "
            "('image', 'room', 'r-1', 'seed', 'h', 'a.png', 'w-1', 'wh')"
        )


# ---- record_image_generation -------------------------------------------


def _record(conn, **overrides):
    """Helper: record with sensible defaults; tests pass overrides."""
    base = dict(
        world_id="w-bunny",
        target_kind="room",
        target_id="r-meadow",
        target_seed="a quiet meadow at dusk",
        seed_hash=image_cache.seed_hash("a quiet meadow at dusk"),
        file_relpath="images/cache/w-bunny/room/r-meadow/abc.png",
        model="sd_xl_base_1.0.safetensors",
        lora="watercolor_v1_sdxl.safetensors",
        prompt_text="a quiet meadow at dusk soft watercolor",
        file_bytes=12345,
        workflow_hash="wfh1234567890abc",
        conn=conn,
    )
    base.update(overrides)
    assets.record_image_generation(**base)


def test_record_inserts_row(conn):
    _record(conn)
    rows = list(conn.execute("SELECT * FROM generated_assets"))
    assert len(rows) == 1
    row = rows[0]
    assert row["asset_kind"] == "image"
    assert row["target_id"] == "r-meadow"
    assert row["world_id"] == "w-bunny"
    assert row["workflow_hash"] == "wfh1234567890abc"
    assert row["pinned"] == 0
    assert row["file_bytes"] == 12345


def test_record_is_idempotent_on_natural_key(conn):
    _record(conn, model="m1", file_bytes=100)
    _record(conn, model="m2", file_bytes=200)
    rows = list(conn.execute("SELECT * FROM generated_assets"))
    assert len(rows) == 1
    assert rows[0]["model"] == "m2"
    assert rows[0]["file_bytes"] == 200


def test_record_distinguishes_different_seed_hashes(conn):
    _record(conn, target_seed="old", seed_hash="aaaa")
    _record(conn, target_seed="new", seed_hash="bbbb")
    assert conn.execute("SELECT COUNT(*) FROM generated_assets").fetchone()[0] == 2


def test_record_with_pinned_true(conn):
    _record(conn, pinned=True)
    row = conn.execute("SELECT pinned FROM generated_assets").fetchone()
    assert row["pinned"] == 1


# ---- list_assets / assets_for_world / total_bytes ----------------------


def test_list_assets_returns_typed_rows(conn):
    _record(conn)
    out = assets.list_assets(conn=conn)
    assert len(out) == 1
    a = out[0]
    assert isinstance(a, assets.Asset)
    assert a.target_id == "r-meadow"
    assert a.world_id == "w-bunny"
    assert a.pinned is False
    assert a.workflow_hash == "wfh1234567890abc"


def test_list_assets_filter_by_target_kind(conn):
    _record(conn, target_kind="room", target_id="r-1", seed_hash="h1")
    _record(conn, target_kind="toon", target_id="t-1", seed_hash="h2")
    rooms = assets.list_assets(target_kind="room", conn=conn)
    toons = assets.list_assets(target_kind="toon", conn=conn)
    assert len(rooms) == 1 and rooms[0].target_kind == "room"
    assert len(toons) == 1 and toons[0].target_kind == "toon"


def test_list_assets_filter_by_world(conn):
    _record(conn, world_id="w-a", target_id="r-1", seed_hash="h1")
    _record(conn, world_id="w-b", target_id="r-2", seed_hash="h2")
    a = assets.list_assets(world_id="w-a", conn=conn)
    b = assets.list_assets(world_id="w-b", conn=conn)
    assert len(a) == 1 and a[0].world_id == "w-a"
    assert len(b) == 1 and b[0].world_id == "w-b"


def test_assets_for_world_is_alias(conn):
    _record(conn, world_id="w-a")
    out = assets.assets_for_world("w-a", conn=conn)
    assert len(out) == 1


def test_total_bytes_sums(conn):
    for i, n in enumerate([100, 200, 350]):
        _record(conn, target_id=f"r-{i}", seed_hash=f"h{i}", file_bytes=n)
    assert assets.total_bytes(conn=conn) == 650


def test_total_bytes_filtered_by_world(conn):
    _record(conn, world_id="w-a", target_id="r-1", seed_hash="h1", file_bytes=100)
    _record(conn, world_id="w-b", target_id="r-2", seed_hash="h2", file_bytes=200)
    assert assets.total_bytes(world_id="w-a", conn=conn) == 100
    assert assets.total_bytes(world_id="w-b", conn=conn) == 200
    assert assets.total_bytes(conn=conn) == 300


def test_total_bytes_zero_when_empty(conn):
    assert assets.total_bytes(conn=conn) == 0


# ---- pin / unpin --------------------------------------------------------


def test_pin_and_unpin_round_trip(conn):
    _record(conn)
    aid = conn.execute("SELECT id FROM generated_assets").fetchone()["id"]
    assets.pin_asset(aid, conn=conn)
    assert conn.execute(
        "SELECT pinned FROM generated_assets WHERE id = ?", (aid,)
    ).fetchone()["pinned"] == 1
    assets.unpin_asset(aid, conn=conn)
    assert conn.execute(
        "SELECT pinned FROM generated_assets WHERE id = ?", (aid,)
    ).fetchone()["pinned"] == 0


def test_pin_is_idempotent(conn):
    _record(conn)
    aid = conn.execute("SELECT id FROM generated_assets").fetchone()["id"]
    assets.pin_asset(aid, conn=conn)
    assets.pin_asset(aid, conn=conn)
    assert conn.execute(
        "SELECT pinned FROM generated_assets WHERE id = ?", (aid,)
    ).fetchone()["pinned"] == 1


# ---- generate_image (PersistentTarget) records on miss -----------------


@pytest.mark.asyncio
async def test_persistent_records_on_cache_miss(live_db):
    fake_bytes = b"\x89PNG\r\n\x1a\nfake-image-bytes"
    target = image_client.PersistentTarget(
        world_id="w-bunny",
        target_kind="room",
        target_id="r-meadow",
        seed="a meadow at dusk",
        prompt_suffix=image_client.WHIMSY_PROMPT_SUFFIX,
    )

    with patch.object(
        image_client, "_execute_workflow", new=AsyncMock(return_value=fake_bytes)
    ):
        await image_client.generate_image(target)

    rows = assets.list_assets()
    assert len(rows) == 1
    a = rows[0]
    assert a.target_kind == "room"
    assert a.target_id == "r-meadow"
    assert a.target_seed == "a meadow at dusk"
    assert a.world_id == "w-bunny"
    assert a.seed_hash == image_cache.seed_hash("a meadow at dusk")
    assert a.file_bytes == len(fake_bytes)
    assert a.model == "sd_xl_base_1.0.safetensors"
    assert a.lora == "watercolor_v1_sdxl.safetensors"
    assert "watercolor" in a.prompt_text
    # workflow_hash matches the post-override workflow
    expected_wf_hash = image_cache.workflow_hash(image_client.load_workflow())
    assert a.workflow_hash == expected_wf_hash


@pytest.mark.asyncio
async def test_persistent_does_not_record_on_cache_hit(live_db, tmp_path):
    target = image_client.PersistentTarget(
        world_id="w-bunny", target_kind="room", target_id="r-x",
        seed="already cached scene",
    )
    wf = image_client.load_workflow()
    p = image_cache.cache_path(target.world_id, target.target_kind, target.target_id, target.seed, wf)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"already cached")

    exec_mock = AsyncMock()
    with patch.object(image_client, "_execute_workflow", new=exec_mock):
        await image_client.generate_image(target)

    exec_mock.assert_not_awaited()
    assert assets.list_assets() == []


@pytest.mark.asyncio
async def test_persistent_requires_db_no_fail_open(tmp_path, monkeypatch):
    """The persistent path REQUIRES recording. If the DB isn't initialized,
    the call must raise — silent fail-open would lose provenance."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    fake_bytes = b"\x89PNG\r\n\x1a\nfake"
    target = image_client.PersistentTarget(
        world_id="w-1", target_kind="room", target_id="r-1", seed="seed",
    )
    with patch.object(
        image_client, "_execute_workflow", new=AsyncMock(return_value=fake_bytes)
    ):
        with pytest.raises(RuntimeError, match="not initialized"):
            await image_client.generate_image(target)


# ---- generate_image (EphemeralTarget) never records --------------------


@pytest.mark.asyncio
async def test_ephemeral_writes_file_no_record(live_db):
    fake_bytes = b"\x89PNG\r\n\x1a\nephemeral-bytes"
    target = image_client.EphemeralTarget(
        name="quick test",
        prompt="a stone bridge over a slow stream",
    )
    with patch.object(
        image_client, "_execute_workflow", new=AsyncMock(return_value=fake_bytes)
    ):
        path = await image_client.generate_image(target)

    assert path.exists()
    assert path.read_bytes() == fake_bytes
    assert "ephemeral" in str(path)
    # No DB row recorded.
    assert assets.list_assets() == []


@pytest.mark.asyncio
async def test_ephemeral_works_without_db(tmp_path, monkeypatch):
    """Ephemeral generation must work even when the DB isn't initialized
    (the image-test CLI path doesn't init a DB)."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    fake_bytes = b"\x89PNG\r\n\x1a\nfake"
    target = image_client.EphemeralTarget(name="x", prompt="anything")
    with patch.object(
        image_client, "_execute_workflow", new=AsyncMock(return_value=fake_bytes)
    ):
        path = await image_client.generate_image(target)
    assert path.exists()
