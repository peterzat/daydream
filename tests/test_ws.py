"""Websocket: auth gate, state_snapshot, input dispatch (canonical + LLM).

SPEC criteria 4 (websocket protocol) and parts of 5 (skills end to end via WS).
LLM tests mock daydream.llm.client.acompletion_json so no GPU needed."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from daydream import db, events
from daydream.server import app


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _login(client: TestClient) -> None:
    # TestClient follows the 303 to / by default, so accept either status.
    r = client.post("/api/login", data={"password": "REDACTED"})
    assert r.status_code in (200, 303), f"login failed: {r.status_code} {r.text}"


def test_ws_unauthed_is_rejected():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()


def test_ws_sends_state_snapshot_on_connect():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["kind"] == "state_snapshot"
    assert msg["room"]["slug"] == "meadow"
    assert any(it["name"] == "lantern" for it in msg["items"])
    assert any(t["name"] == "Wren" for t in msg["toons"])
    skill_names = {s["name"] for s in msg["skills"]}
    assert {"look", "say", "examine"}.issubset(skill_names)


def test_ws_canonical_look_emits_narrate_event():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"kind": "input", "text": "look"})
            evt = ws.receive_json()
    assert evt["kind"] == "event"
    assert evt["event"]["kind"] == "narrate"
    assert "meadow" in evt["event"]["payload"]["text"]


def test_ws_canonical_say_emits_say_event():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "say hello"})
            evt = ws.receive_json()
    assert evt["event"]["kind"] == "say"
    assert evt["event"]["payload"]["text"] == "hello"
    assert evt["event"]["actor_id"] == "t-wren"


def test_ws_canonical_examine_echoes_seed_sentinel():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "examine the lantern"})
            evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    assert "hairline crack" in evt["event"]["payload"]["text"]


def test_ws_llm_routed_input_dispatches_skill():
    """SPEC criterion 6: 'look around' -> look skill via LLM interpreter."""
    canned = {"skill": "look", "args": "around"}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        with TestClient(app) as client:
            _login(client)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "look around"})
                evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    assert "meadow" in evt["event"]["payload"]["text"]


def test_ws_unknown_phrase_produces_chat_fallback():
    """SPEC criterion 6: chatter -> 'none' -> narrate fallback, no skill misfire."""
    canned = {"skill": "none", "args": ""}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        with TestClient(app) as client:
            _login(client)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "sing a song"})
                evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    # The fallback narration includes the original input verbatim.
    assert "sing a song" in evt["event"]["payload"]["text"]


def test_ws_llm_unavailable_produces_foggy_narration():
    """SPEC criterion 7: LLM down -> 'the dream is foggy' narration, no crash."""
    from daydream.llm.client import LLMUnavailable

    with patch(
        "daydream.llm.client.acompletion_json",
        new=AsyncMock(side_effect=LLMUnavailable("vLLM unreachable")),
    ):
        with TestClient(app) as client:
            _login(client)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "what time is it"})
                evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    assert "foggy" in evt["event"]["payload"]["text"].lower()


def test_ws_snapshot_includes_prior_events_after_say():
    """SPEC criterion 8 spine: 'say hello' persists; reconnecting receives it
    in the snapshot's recent-events slice."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "say hello"})
            ws.receive_json()  # the say event
        # New websocket connection on the same DB:
        with client.websocket_connect("/ws") as ws2:
            snapshot = ws2.receive_json()
    say_events = [
        e for e in snapshot["events"]
        if e["kind"] == "say" and e["payload"].get("text") == "hello"
    ]
    assert len(say_events) == 1
