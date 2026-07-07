"""Full archive -> delete -> restore -> diff roundtrip (BACKLOG
archive-restore-roundtrip-test).

test_admin.py::test_restore_round_trip proves the happy path on one
asset count; this is the disaster-recovery drill: cascade-delete the
world, lose the live DB file itself, restore from the tarball, and diff
the ENTIRE world state (object rows, asset rows, cache file bytes)
against the pre-archive snapshot. Runs in ~1s with no GPU, so it lives
in the medium tier and CI covers it."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from daydream import admin, assets, config, db
from daydream.images import cache as image_cache

pytestmark = pytest.mark.tier_medium

WORLD = "w-bunny"


@pytest.fixture()
def live_world(tmp_path: Path, monkeypatch):
    """A live DB with the migration-seeded world plus one recorded asset
    and its cache file on disk (mirrors test_admin.py's fixture)."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    db.init_live(
        path=tmp_path / f"worlds-{config.env()}/live.db",
        migrations_dir=config.MIGRATIONS_DIR,
    )
    seed = "a small grassy meadow at dusk, fireflies just beginning"
    h = image_cache.seed_hash(seed)
    cache_file = image_cache.cache_dir() / WORLD / "room" / "r-meadow" / f"{h}.png"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"roundtrip" * 64)
    assets.record_image_generation(
        world_id=WORLD,
        target_kind="room",
        target_id="r-meadow",
        target_seed=seed,
        seed_hash=h,
        file_relpath=str(cache_file.relative_to(tmp_path)),
        model="sd_xl_base_1.0.safetensors",
        lora="watercolor_v1_sdxl.safetensors",
        prompt_text=seed,
        file_bytes=cache_file.stat().st_size,
        workflow_hash="wfh-roundtrip",
    )
    yield tmp_path
    db.close_db()


def _world_fingerprint(data_dir: Path) -> dict:
    """Everything that must survive the roundtrip: every object row,
    every asset row, and the bytes of every cache file."""
    conn = db.get_conn()
    objects = [
        tuple(r)
        for r in conn.execute(
            "SELECT id, kind, name, location_id, prototype_id, properties_json "
            "FROM objects WHERE world_id = ? ORDER BY id",
            (WORLD,),
        )
    ]
    asset_rows = [
        (a.target_kind, a.target_id, a.seed_hash, a.file_relpath, a.file_bytes)
        for a in assets.list_assets()
    ]
    cache_root = data_dir / "images" / "cache" / WORLD
    files = {
        str(p.relative_to(cache_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(cache_root.rglob("*.png"))
    }
    return {"objects": objects, "assets": asset_rows, "files": files}


def test_archive_delete_restore_full_diff(live_world, monkeypatch, capsys):
    before = _world_fingerprint(live_world)
    assert before["objects"] and before["assets"] and before["files"]

    assert admin.main(["archive", WORLD]) == 0
    archive = next((live_world / "archives").iterdir())

    # Disaster: cascade-delete the world, then lose the live DB file too.
    assert admin.main(["delete", WORLD, "--yes"]) == 0
    conn = db.get_conn()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM objects WHERE world_id = ?", (WORLD,)
    ).fetchone()[0]
    assert remaining == 0
    assert not (live_world / "images" / "cache" / WORLD).exists()
    db.close_db()
    live = config.live_db_path()
    for p in (live, live.with_name(live.name + "-wal"), live.with_name(live.name + "-shm")):
        if p.exists():
            p.unlink()

    assert admin.main(["restore", str(archive), "--yes"]) == 0
    db.init_live()
    after = _world_fingerprint(live_world)
    assert after == before
