"""`bin/game prebake` (SPEC 2026-09-26 criterion 20): every room and every
portrait of the world renders through the production pipeline into the
same cache the live snapshot reads, recorded in generated_assets; a re-run
is all cache hits; --force re-renders one. ComfyUI mocked at its single seam."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, prebake
from daydream.images import cache, client
from daydream.llm import bootstrap

pytestmark = [pytest.mark.tier_medium, pytest.mark.real_image_gen]

ROOT = Path(__file__).resolve().parent.parent
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


@pytest.fixture()
def lost_hours_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    events.reset_subscribers()
    path = tmp_path / "live.db"
    bootstrap.load_world("lh", json.loads((ROOT / "worlds/lost-hours.json").read_text()), path)
    render = AsyncMock(return_value=PNG)
    monkeypatch.setattr("daydream.images.client._execute_workflow", render)
    yield path, render
    db.close_db()
    events.reset_subscribers()


async def test_prebake_paints_every_room_and_face_once(lost_hours_db):
    path, render = lost_hours_db
    env = json.loads((ROOT / "worlds/lost-hours.json").read_text())
    n_rooms = len(env["rooms"])
    n_faces = sum(1 for t in env["toons"] if (t.get("appearance_seed") or "").strip())
    results = await prebake.prebake(path)
    assert sum(r["kind"] == "room" for r in results) == n_rooms
    assert sum(r["kind"] == "toon" for r in results) == n_faces
    assert all(r["status"] == "rendered" for r in results)
    assert render.await_count == n_rooms + n_faces
    # The live snapshot's cache path for the start room is the file we wrote.
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    tower = next(r for r in env["rooms"] if r["id"] == "r-clocktower")
    assert cache.cache_path("w-lost-hours", "room", "r-clocktower", tower["seed"],
                            client.load_workflow()).exists()
    rows = db.get_conn().execute("SELECT COUNT(*) FROM generated_assets").fetchone()[0]
    assert rows == n_rooms + n_faces
    db.close_db()
    again = await prebake.prebake(path)
    assert all(r["status"] == "cached" for r in again)
    forced = await prebake.prebake(path, force={"r-loft"})
    assert [r["id"] for r in forced if r["status"] == "rendered"] == ["r-loft"]
