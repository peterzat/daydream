"""Session start behavior (SPEC 2026-06-29, session-presence-polish).

A fresh page load starts with an empty event log; a reconnect (signaling its
last-seen seq via ?since) resumes the room's missed history."""

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


def test_fresh_session_empty_log_reconnect_resumes():
    with TestClient(app) as client:
        _login(client)
        # Seed prior room history (meadow is t-wren's starting room).
        events.append(
            "system", None, "narrate", {"text": "an old whisper"}, room_id="r-meadow"
        )
        events.append(
            "system", None, "narrate", {"text": "another old whisper"}, room_id="r-meadow"
        )

        # Fresh page load: empty log even though the room has history.
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
            assert snap["kind"] == "state_snapshot"
            assert snap["room"]["slug"] == "meadow"
            assert snap["events"] == []

        # Reconnect (resume from seq 0): replays the missed room history.
        with client.websocket_connect("/ws?since=0") as ws2:
            snap2 = ws2.receive_json()
            texts = [e["payload"].get("text") for e in snap2["events"]]
            assert "an old whisper" in texts
            assert "another old whisper" in texts


def test_leave_releases_toon_and_routes_next_connect_to_picker():
    with TestClient(app) as client:
        _login(client)
        # Claim a toon (create in slot 2); the WS then resolves it normally.
        r = client.post(
            "/api/slots/2/create", json={"name": "Fen", "appearance_seed": "a wisp"}
        )
        assert r.status_code == 200, r.text
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["kind"] == "state_snapshot"

        # Leave the dream: releases the toon (rests it) + marks the session.
        r = client.post("/api/session/leave")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        slot2 = next(s for s in client.get("/api/slots").json()["slots"] if s["slot"] == 2)
        assert slot2["toon"] is not None
        assert slot2["toon"]["claimed_by_me"] is False  # released
        assert slot2["toon"]["kicked_at"] is not None  # rested, claimable

        # The next WS connect routes to the picker, not the toon or t-wren.
        with client.websocket_connect("/ws") as ws2:
            assert ws2.receive_json() == {"kind": "needs_toon"}

        # Re-picking clears 'left'; the WS resolves a toon again.
        assert client.post("/api/slots/2/claim").status_code == 200
        with client.websocket_connect("/ws") as ws3:
            assert ws3.receive_json()["kind"] == "state_snapshot"
