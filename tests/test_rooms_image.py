"""Room-image repaint API (dev regen UI): GET image-prompt, POST image, and
the ws.enqueue_room_regen outcomes it maps onto. The async render itself is
mocked/stubbed — these cover auth, prompt hygiene, outcome→status mapping,
and the enqueue dedup/seed contract."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.api import ws as ws_module
from daydream.images import client as image_client
from daydream.server import app

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    ws_module.reset_in_flight()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()
    ws_module.reset_in_flight()


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)


# ---- GET /api/rooms/{id}/image-prompt ----------------------------------


def test_image_prompt_requires_auth():
    with TestClient(app) as client:
        r = client.get("/api/rooms/r-meadow/image-prompt")
        assert r.status_code == 401


def test_image_prompt_returns_canonical_prompt():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/api/rooms/r-meadow/image-prompt")
        assert r.status_code == 200
        body = r.json()
        assert body["room_id"] == "r-meadow"
        # It is exactly the seed + tone-suffix join the render uses.
        from daydream import rooms
        room = rooms.get_room("r-meadow")
        assert body["prompt"] == image_client.canonical_prompt(
            room.seed, image_client.WHIMSY_PROMPT_SUFFIX
        )
        assert body["prompt"].endswith(image_client.WHIMSY_PROMPT_SUFFIX)


def test_image_prompt_404_on_unknown_room():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/api/rooms/r-nowhere/image-prompt")
        assert r.status_code == 404


# ---- POST /api/rooms/{id}/image (outcome mapping) ----------------------


def test_repaint_requires_auth():
    with TestClient(app) as client:
        r = client.post("/api/rooms/r-meadow/image", json={})
        assert r.status_code == 401


def test_repaint_started_no_prompt():
    with TestClient(app) as client:
        _login(client)
        with patch.object(ws_module, "enqueue_room_regen",
                          return_value="started") as enq:
            r = client.post("/api/rooms/r-meadow/image", json={})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "status": "started", "custom_prompt": False}
        enq.assert_called_once_with("r-meadow", prompt_override=None)


def test_repaint_started_with_prompt():
    with TestClient(app) as client:
        _login(client)
        with patch.object(ws_module, "enqueue_room_regen",
                          return_value="started") as enq:
            r = client.post("/api/rooms/r-meadow/image",
                            json={"prompt": "  a stormy version  "})
        assert r.status_code == 200
        assert r.json()["custom_prompt"] is True
        # Whitespace-trimmed, passed through as the override.
        enq.assert_called_once_with("r-meadow", prompt_override="a stormy version")


def test_repaint_blank_prompt_is_treated_as_none():
    with TestClient(app) as client:
        _login(client)
        with patch.object(ws_module, "enqueue_room_regen",
                          return_value="started") as enq:
            r = client.post("/api/rooms/r-meadow/image", json={"prompt": "   "})
        assert r.status_code == 200
        assert r.json()["custom_prompt"] is False
        enq.assert_called_once_with("r-meadow", prompt_override=None)


def test_repaint_409_when_in_flight():
    with TestClient(app) as client:
        _login(client)
        with patch.object(ws_module, "enqueue_room_regen",
                          return_value="in_flight"):
            r = client.post("/api/rooms/r-meadow/image", json={})
        assert r.status_code == 409


def test_repaint_404_on_unknown_room():
    with TestClient(app) as client:
        _login(client)
        with patch.object(ws_module, "enqueue_room_regen",
                          return_value="no_room"):
            r = client.post("/api/rooms/r-nowhere/image", json={})
        assert r.status_code == 404


def test_repaint_400_on_non_string_prompt():
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/rooms/r-meadow/image", json={"prompt": 123})
        assert r.status_code == 400


def test_repaint_400_on_overlong_prompt():
    with TestClient(app) as client:
        _login(client)
        from daydream.api.rooms import MAX_PROMPT_CHARS
        r = client.post("/api/rooms/r-meadow/image",
                        json={"prompt": "x" * (MAX_PROMPT_CHARS + 1)})
        assert r.status_code == 400


def test_repaint_tolerates_empty_body():
    """No JSON body at all == same-prompt regen."""
    with TestClient(app) as client:
        _login(client)
        with patch.object(ws_module, "enqueue_room_regen",
                          return_value="started") as enq:
            r = client.post("/api/rooms/r-meadow/image")
        assert r.status_code == 200
        enq.assert_called_once_with("r-meadow", prompt_override=None)


# ---- ws.enqueue_room_regen contract ------------------------------------


@pytest.fixture
def initialized_db(tmp_path: Path):
    from daydream import config
    db.init_live(path=tmp_path / "live.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()


def test_enqueue_no_room_returns_no_room(initialized_db):
    assert ws_module.enqueue_room_regen("r-nonexistent") == "no_room"


def test_enqueue_schedules_forced_task_with_seed(initialized_db):
    """A valid room schedules a _generate_and_emit task with force=True and a
    random seed; a second call while it's 'in flight' is refused."""
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()  # avoid 'never awaited'
        return None

    with patch.object(image_client, "generate_image", new=AsyncMock()), \
         patch.object(asyncio, "create_task", side_effect=fake_create_task):
        first = ws_module.enqueue_room_regen("r-meadow", prompt_override="x")
        # Key is now in the in-flight set (the task was scheduled but our
        # stub never runs the finally that clears it), so a repeat is refused.
        second = ws_module.enqueue_room_regen("r-meadow")
    assert first == "started"
    assert second == "in_flight"
    assert len(scheduled) == 1
