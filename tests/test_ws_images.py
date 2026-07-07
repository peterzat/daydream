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
    """Log in and claim the seeded Wren (slot 1) as this session's toon.
    Picker-first entry (SPEC 2026-06-30) dropped the default-toon fallback,
    so a WS connection resolves a toon only when the session has claimed one.
    Kick-then-claim because the seed marks Wren human-controlled; the id stays
    `t-wren` so id-pinned assertions hold."""
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)
    assert client.post("/api/slots/1/kick").status_code == 200
    rc = client.post("/api/slots/1/claim")
    assert rc.status_code == 200 and rc.json()["id"] == "t-wren", rc.text


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
    base_url = image_cache.cache_url("w-bunny", "room", "r-meadow", seed, wf)

    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    # Snapshot URL is now ?v=<mtime>-versioned; the path half is unchanged.
    assert msg["room"]["image_url"].split("?")[0] == base_url
    assert "?v=" in msg["room"]["image_url"]


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

    async def fake_gen(t, *, model=None, lora=None, seed=None, base_url=None,
                       force=False, prompt_override=None):
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
    # URL is now ?v=<mtime>-versioned; strip the query to compare the path.
    assert payload["image_url"].split("?")[0] == image_cache.url_for_cache_path(expected_path)
    assert "?v=" in payload["image_url"]
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


# ---- toon portraits (SPEC 2026-07-07 criterion 2) ------------------------

WREN_APPEARANCE = "a soft watercolor toon, dusty cloak, freckles, kind eyes"


def _write_portrait_cache(world_id: str, toon_id: str, appearance: str) -> str:
    """Pre-populate the portrait cache the way a finished render would and
    return the unversioned cache URL."""
    target = image_client.portrait_target(world_id, toon_id, appearance)
    wf = image_client.load_workflow_for(target)
    p = image_cache.cache_path(world_id, "toon", toon_id, appearance, wf)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake-portrait")
    return image_cache.url_for_cache_path(p)


def test_snapshot_toon_cards_carry_portrait_url_cached_only():
    """image_url on toon cards (self included) is None until the portrait is
    cached, then the versioned /cache URL — reads never trigger renders."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
        assert msg["self"]["image_url"] is None
        base = _write_portrait_cache("w-bunny", "t-wren", WREN_APPEARANCE)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
        assert msg["self"]["image_url"].split("?")[0] == base
        assert "?v=" in msg["self"]["image_url"]


def test_connect_enqueues_portraits_for_room_toons():
    """The initial snapshot enqueues a portrait render for every co-located
    toon with a non-empty appearance seed (self included here: Wren)."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            assert any(k[1] == "toon" and k[2] == "t-wren"
                       for k in ws_module._generating), ws_module._generating


def test_portrait_enqueue_skips_empty_appearance_and_cached(monkeypatch):
    """No appearance seed -> no render; cached -> no render. The quiet
    placeholder is the SPA's job, not a render trigger."""
    from daydream import config as config_mod
    from daydream import objects

    db.init_live(
        path=Path(config_mod.data_dir()) / "x.db",
        migrations_dir=config_mod.MIGRATIONS_DIR,
    )
    try:
        # Wren: cache pre-populated -> skipped. Rook: blank appearance -> skipped.
        _write_portrait_cache("w-bunny", "t-wren", WREN_APPEARANCE)
        objects.set_property("t-rook", "appearance_seed", " ")
        objects.move("t-rook", "r-meadow")

        spawned = []

        def fake_create_task(coro):
            spawned.append(coro)
            coro.close()

        with patch.object(asyncio, "create_task", side_effect=fake_create_task):
            ws_module._maybe_enqueue_toon_portraits("r-meadow")
        assert spawned == []
    finally:
        db.close_db()


@pytest.mark.real_image_gen
async def test_generate_and_emit_toon_target_emits_toon_image_ready(initialized_db):
    """A toon target's finish lands as toon_image_ready in the toon's current
    room, carrying toon_id — the re-snapshot trigger co-located players see."""
    from daydream import toons

    t = toons.get_toon("t-wren")
    target = ws_module._toon_target(t)
    wf = image_client.load_workflow_for(target)

    async def fake_gen(tg, *, model=None, lora=None, seed=None, base_url=None,
                       force=False, prompt_override=None):
        out = image_cache.cache_path(
            tg.world_id, tg.target_kind, tg.target_id, tg.seed, wf
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return out

    with patch.object(image_client, "generate_image", new=AsyncMock(side_effect=fake_gen)):
        await ws_module._generate_and_emit(target, image_client.target_dedup_key(target))

    matching = [e for e in events.fetch_since(0) if e.kind == "toon_image_ready"]
    assert len(matching) == 1
    ev = matching[0]
    assert ev.room_id == "r-meadow"  # wren's current room
    assert ev.payload["toon_id"] == "t-wren"
    assert "?v=" in ev.payload["image_url"]
    # And the broadcast loop treats it as a snapshot-refresh trigger.
    assert "toon_image_ready" in ws_module._EFFECT_MUTATION_KINDS


def test_slots_listing_carries_cached_only_portrait_url():
    """GET /api/slots exposes portrait_url: None before the portrait exists,
    the versioned URL after — and listing never triggers a render."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/api/slots")
        slot1 = next(s for s in r.json()["slots"] if s["slot"] == 1)
        assert slot1["toon"]["portrait_url"] is None
        assert not ws_module._generating  # no render started by the listing
        base = _write_portrait_cache("w-bunny", "t-wren", WREN_APPEARANCE)
        r = client.get("/api/slots")
        slot1 = next(s for s in r.json()["slots"] if s["slot"] == 1)
        assert slot1["toon"]["portrait_url"].split("?")[0] == base
        assert not ws_module._generating
