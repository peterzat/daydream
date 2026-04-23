"""WS image-gen flow: state_snapshot image_url field, room_image_ready
event emission via the real _generate_and_emit (with the unified
generate_image mocked), /cache StaticFiles mount."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.api import ws as ws_module
from daydream.images import cache as image_cache
from daydream.images import client as image_client
from daydream.server import app

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


@pytest.fixture
def initialized_db(tmp_path: Path):
    """Manually init the DB for tests that don't go through TestClient lifespan
    (e.g., direct calls to ws._generate_and_emit)."""
    from daydream import config

    db.init_live(path=tmp_path / "live.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)


# ---- snapshot.image_url field ------------------------------------------


def test_snapshot_image_url_is_none_on_cold_cache():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["room"]["image_url"] is None


def test_snapshot_image_url_is_set_when_cached(tmp_path: Path):
    """Pre-populate the cache for the seeded meadow; snapshot returns the URL."""
    seed = "a small grassy meadow at dusk, fireflies just beginning, soft watercolor edges"
    wf = image_client.load_workflow()
    p = image_cache.cache_path("w-bunny", "room", "r-meadow", seed, wf)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake-cached-png")
    expected_url = image_cache.cache_url("w-bunny", "room", "r-meadow", seed, wf)

    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["room"]["image_url"] == expected_url


# ---- /cache StaticFiles mount ------------------------------------------


def test_cache_mount_serves_a_real_file(tmp_path: Path):
    seed = "test seed"
    wf = image_client.load_workflow()
    p = image_cache.cache_path("w-x", "room", "r-y", seed, wf)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")
    url = image_cache.cache_url("w-x", "room", "r-y", seed, wf)
    with TestClient(app) as client:
        _login(client)
        r = client.get(url)
    assert r.status_code == 200
    assert r.content == b"\x89PNG\r\n\x1a\nfake-bytes"
    assert r.headers["content-type"] == "image/png"


def test_cache_mount_404_on_missing_path():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/cache/no-such-world/room/no-room/deadbeef.png")
    assert r.status_code == 404


# ---- _generate_and_emit real flow (mocked image client) ----------------


@pytest.mark.real_image_gen
async def test_generate_and_emit_writes_room_image_ready_with_url(tmp_path: Path, initialized_db):
    seed = "a quiet room"
    target = ws_module._room_target("w-bunny", "r-meadow", seed)
    wf = image_client.load_workflow()
    expected_path = image_cache.cache_path(
        target.world_id, target.target_kind, target.target_id, target.seed, wf
    )

    async def fake_gen(t, *, model=None, lora=None, seed=None, base_url=None):
        out = image_cache.cache_path(
            t.world_id, t.target_kind, t.target_id, t.seed, wf
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return out

    with patch.object(image_client, "generate_image", new=AsyncMock(side_effect=fake_gen)):
        await ws_module._generate_and_emit(target, image_client.target_dedup_key(target))

    out = events.fetch_since(0)
    matching = [e for e in out if e.kind == "room_image_ready" and e.room_id == "r-meadow"]
    assert len(matching) == 1
    payload = matching[0].payload
    assert payload["image_url"] == image_cache.url_for_cache_path(expected_path)
    assert "error" not in payload


@pytest.mark.real_image_gen
async def test_generate_and_emit_emits_error_on_comfyui_failure(initialized_db):
    target = ws_module._room_target("w-bunny", "r-meadow", "seed-x")
    with patch.object(
        image_client,
        "generate_image",
        new=AsyncMock(side_effect=image_client.ComfyUIError("comfy unreachable")),
    ):
        await ws_module._generate_and_emit(target, image_client.target_dedup_key(target))

    out = events.fetch_since(0)
    matching = [e for e in out if e.kind == "room_image_ready"]
    assert len(matching) == 1
    payload = matching[0].payload
    assert payload["image_url"] is None
    assert "comfy unreachable" in payload.get("error", "")


# ---- _maybe_enqueue_image_gen dedup ------------------------------------


def test_maybe_enqueue_short_circuits_when_cached():
    """A cache hit at the target's path means no task is created."""
    seed = "cached"
    wf = image_client.load_workflow()
    p = image_cache.cache_path("w-1", "room", "r-1", seed, wf)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")

    spawned = []

    def fake_create_task(coro):
        spawned.append(coro)
        coro.close()  # avoid "coroutine was never awaited"

    with patch.object(asyncio, "create_task", side_effect=fake_create_task):
        ws_module._maybe_enqueue_image_gen("w-1", "r-1", seed)
    assert spawned == []


def test_maybe_enqueue_dedups_in_flight():
    """Two callers within the same event loop for the same key spawn one task."""
    seed = "in-flight"
    spawned = []

    def fake_create_task(coro):
        spawned.append(coro)
        coro.close()

    with patch.object(asyncio, "create_task", side_effect=fake_create_task):
        ws_module._maybe_enqueue_image_gen("w-1", "r-1", seed)
        ws_module._maybe_enqueue_image_gen("w-1", "r-1", seed)
    assert len(spawned) == 1
