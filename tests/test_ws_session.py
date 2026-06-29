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
