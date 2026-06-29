"""Room description on entry (SPEC 2026-06-29, room-description-on-entry).

The snapshot's `room.description` is the full stored description the first
time a session enters a room, and a short "you return to ..." line on
re-entry. Pre-baked stored text (`rooms.description_cached`); no GPU/LLM."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
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


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303), f"login failed: {r.status_code} {r.text}"


def _recv_until_snapshot(ws) -> dict:
    """Receive until a state_snapshot, skipping move/narrate/image events."""
    for _ in range(12):
        msg = ws.receive_json()
        if msg.get("kind") == "state_snapshot":
            return msg
    raise AssertionError("no state_snapshot received")


def test_full_description_first_visit_then_abbreviated_on_reentry():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            meadow = ws.receive_json()
            assert meadow["kind"] == "state_snapshot"
            assert meadow["room"]["slug"] == "meadow"
            meadow_full = meadow["room"]["description"] or ""
            assert meadow_full and "return to" not in meadow_full.lower()  # full

            ws.send_json({"kind": "input", "text": "go north"})
            forge = _recv_until_snapshot(ws)
            assert forge["room"]["slug"] == "forge"
            forge_desc = forge["room"]["description"] or ""
            assert forge_desc and "return to" not in forge_desc.lower()  # full, new room

            ws.send_json({"kind": "input", "text": "go south"})
            back = _recv_until_snapshot(ws)
            assert back["room"]["slug"] == "meadow"
            # Re-entry into the meadow this session -> abbreviated line.
            assert "return to" in (back["room"]["description"] or "").lower()


def test_effect_resnapshot_does_not_shrink_first_visit_description(monkeypatch):
    """A non-move re-snapshot of the same room keeps the full first-visit
    description (the verdict is sticky for the duration of the visit)."""
    from daydream.api import ws as ws_mod

    full = "A wide quiet meadow under a dimming sky."

    class _Room:
        id = "r-x"
        slug = "x"
        title = "X"
        description_cached = full

    view = {"visited": set(), "room_id": None, "first_visit": True}
    assert ws_mod._room_description(_Room(), view) == full  # entry -> full
    # same room again (effect re-snapshot) -> still full, not abbreviated
    assert ws_mod._room_description(_Room(), view) == full
    assert view["first_visit"] is True
