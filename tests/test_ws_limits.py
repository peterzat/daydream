"""WebSocket limits (SPEC 2026-09-27 criteria 2 and 7): an over-long line and
a flood of frames are refused with no effect, and a revoked session loses an
open socket on its next frame."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from daydream import accounts, db, events, inputs
from daydream.api import ws as ws_module
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _enter(client) -> None:
    authhelp.login(client, "wren-player")
    assert client.post("/api/slots/1/kick").status_code == 200
    assert client.post("/api/slots/1/claim").status_code == 200


def _logged_lines() -> int:
    return len(inputs.fetch())


def _next_notice(ws) -> dict:
    for _ in range(20):
        msg = ws.receive_json()
        if msg.get("kind") == "notice":
            return msg
    raise AssertionError("no notice frame")


def test_an_overlong_line_is_refused_without_effect():
    with TestClient(app) as client:
        _enter(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            before = _logged_lines()
            ws.send_json({"kind": "input", "text": "a" * (ws_module.MAX_INPUT_CHARS + 1)})
            notice = _next_notice(ws)
            assert str(ws_module.MAX_INPUT_CHARS) in notice["text"]
            assert _logged_lines() == before


def test_a_flood_of_frames_is_rate_limited(monkeypatch):
    monkeypatch.setattr(ws_module, "RATE_PER_SECOND", 0.0)  # no refill during the test
    handled = []

    async def fake_handle(text, toon_id, conn):
        handled.append(text)
        return None

    monkeypatch.setattr(ws_module, "_handle_input", fake_handle)
    with TestClient(app) as client:
        _enter(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            for i in range(ws_module.RATE_BURST + 5):
                ws.send_json({"kind": "input", "text": f"look {i}"})
            notice = _next_notice(ws)
            assert "slow down" in notice["text"]
    assert len(handled) == ws_module.RATE_BURST


def test_revoking_a_session_closes_an_open_socket_on_its_next_frame():
    with TestClient(app) as client:
        _enter(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            accounts.revoke_sessions("wren-player")
            ws.send_json({"kind": "input", "text": "look"})
            with pytest.raises(WebSocketDisconnect) as closed:
                for _ in range(20):
                    ws.receive_json()
            assert closed.value.code == 4401


def test_a_command_frame_is_capped_like_a_typed_line(monkeypatch):
    """SECURITY WARN 2026-09-27: a `command` frame's args used to skip the cap
    (a 20,000-character `say` was broadcast and stored)."""
    handled = []

    async def fake_command(msg, toon_id):
        handled.append(msg)

    monkeypatch.setattr(ws_module, "_handle_command", fake_command)
    with TestClient(app) as client:
        _enter(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "command", "verb": "say", "args": "x" * 20000})
            notice = _next_notice(ws)
            assert "at once" in notice["text"]
            ws.send_json({"kind": "command", "verb": "say", "args": "hello"})
            ws.send_json({"kind": "ping"})
            ws.send_json({"kind": "input", "text": "a" * (ws_module.MAX_INPUT_CHARS + 1)})
            _next_notice(ws)
    assert [m["args"] for m in handled] == ["hello"]


def test_an_idle_socket_of_a_revoked_account_is_closed(monkeypatch):
    """SECURITY WARN 2026-09-27: revocation used to bite only on the next
    inbound frame, so a listening tab kept receiving room chat."""
    monkeypatch.setattr(ws_module, "SESSION_RECHECK_S", 0.2)
    with TestClient(app) as client:
        _enter(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            accounts.set_disabled("wren-player", True)
            with pytest.raises(WebSocketDisconnect) as closed:
                for _ in range(50):
                    ws.receive_json()
            assert closed.value.code == 4401


def test_the_spa_sends_a_keepalive_ping():
    js = (Path(__file__).resolve().parent.parent / "web" / "assets" / "main.js").read_text()
    assert 'JSON.stringify({ kind: "ping" })' in js and "clearInterval(pingTimer)" in js
