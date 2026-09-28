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


def test_a_reconnect_replays_a_bounded_history(monkeypatch):
    monkeypatch.setattr(ws_module, "RESUME_DEPTH", 5)
    with TestClient(app) as client:
        _enter(client)
        for i in range(20):
            events.append("system", None, "narrate", {"text": f"old {i}"}, room_id="r-meadow")
        with client.websocket_connect("/ws?since=0") as ws:
            snap = ws.receive_json()
    assert len(snap["events"]) <= 5


def test_walking_into_a_room_replays_only_its_recent_history():
    """First prod evening, 2026-09-28: in a quiet village a room's last 50
    events span hours, and a resident seemed to do four things at once on
    meeting a player (two ambient lines from hours before, the greeting, the
    answer). A move replays the last twenty minutes, without ambient beats."""
    with TestClient(app) as client:
        _enter(client)
        old = events.append("system", None, "narrate", {"text": "an old line"},
                            room_id="r-forge")
        db.get_conn().execute(
            "UPDATE events SET created_at = datetime('now', '-2 hours') WHERE seq = ?",
            (old.seq,))
        events.append("system", None, "narrate", {"text": "a recent line"}, room_id="r-forge")
        events.append("system", None, "narrate",
                      {"text": "a recent ambient beat", "ambient": True}, room_id="r-forge")
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # the meadow
            ws.send_json({"kind": "input", "text": "go north"})
            for _ in range(10):
                msg = ws.receive_json()
                if msg["kind"] == "state_snapshot":
                    break
    assert msg["room"]["id"] == "r-forge"
    texts = [e["payload"].get("text") for e in msg["events"]]
    assert "a recent line" in texts
    assert "an old line" not in texts
    assert "a recent ambient beat" not in texts


def test_the_arrivals_cut_holds_for_later_snapshots_in_the_room():
    """Codereview 2026-09-28c: the cut held only for the move's own snapshot,
    so the next one in the room (a face painted, which arriving itself sets
    off, or a take) replayed the old and ambient lines. Ambient beats seen
    live since arriving stay."""
    with TestClient(app) as client:
        _enter(client)
        old = events.append("system", None, "narrate", {"text": "an old line"},
                            room_id="r-forge")
        db.get_conn().execute(
            "UPDATE events SET created_at = datetime('now', '-2 hours') WHERE seq = ?",
            (old.seq,))
        events.append("system", None, "narrate", {"text": "a recent line"}, room_id="r-forge")
        events.append("system", None, "narrate",
                      {"text": "a recent ambient beat", "ambient": True}, room_id="r-forge")
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # the meadow
            ws.send_json({"kind": "input", "text": "go north"})
            stage = "arriving"
            for _ in range(30):
                msg = ws.receive_json()
                if stage == "arriving" and msg["kind"] == "state_snapshot":
                    assert msg["room"]["id"] == "r-forge"
                    events.append("system", None, "narrate",
                                  {"text": "a beat after arriving", "ambient": True},
                                  room_id="r-forge")
                    events.append("system", None, "toon_image_ready",
                                  {"toon_id": "t-someone", "image_url": None},
                                  room_id="r-forge")
                    ws.send_json({"kind": "ping"})  # wakes the server loop for the appends
                    stage = "painting"
                elif (stage == "painting" and msg["kind"] == "event"
                      and msg["event"]["kind"] == "toon_image_ready"):
                    stage = "painted"
                elif stage == "painted" and msg["kind"] == "state_snapshot":
                    break
            else:
                raise AssertionError(f"no snapshot after the face was painted ({stage})")
    texts = [e["payload"].get("text") for e in msg["events"]]
    assert msg["room"]["id"] == "r-forge"
    assert "a recent line" in texts and "a beat after arriving" in texts
    assert "an old line" not in texts
    assert "a recent ambient beat" not in texts


def _snapshot_after_painting(ws, room_id: str, beat: str) -> dict:
    """Live, after the first snapshot: an ambient beat, then a face painted in
    the room. Returns the re-snapshot the painting sets off."""
    events.append("system", None, "narrate", {"text": beat, "ambient": True}, room_id=room_id)
    events.append("system", None, "toon_image_ready",
                  {"toon_id": "t-someone", "image_url": None}, room_id=room_id)
    ws.send_json({"kind": "ping"})  # wakes the server loop for the appends
    painted = False
    for _ in range(30):
        msg = ws.receive_json()
        if msg["kind"] == "event" and msg["event"]["kind"] == "toon_image_ready":
            painted = True
        elif painted and msg["kind"] == "state_snapshot":
            return msg
    raise AssertionError("no snapshot after the face was painted")


def test_a_fresh_loads_empty_log_holds_for_later_snapshots_in_the_room():
    """Codereview 2026-09-28c, cycle 2: the cut was recorded only on a move, so
    after a fresh page load (an empty log) the next re-snapshot in the room (a
    face painted, which connecting itself sets off, or a take) replayed its
    last 50 events however old, ambient beats included."""
    with TestClient(app) as client:
        _enter(client)
        old = events.append("system", None, "narrate", {"text": "an old line"},
                            room_id="r-meadow")
        db.get_conn().execute(
            "UPDATE events SET created_at = datetime('now', '-2 hours') WHERE seq = ?",
            (old.seq,))
        events.append("system", None, "narrate",
                      {"text": "an ambient beat before the load", "ambient": True},
                      room_id="r-meadow")
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
            assert snap["room"]["id"] == "r-meadow" and snap["events"] == []
            msg = _snapshot_after_painting(ws, "r-meadow", "a beat since the load")
    texts = [e["payload"].get("text") for e in msg["events"]]
    assert msg["room"]["id"] == "r-meadow"
    assert "a beat since the load" in texts
    assert "an old line" not in texts
    assert "an ambient beat before the load" not in texts


def test_a_reconnects_replay_holds_for_later_snapshots_in_the_room():
    """Codereview 2026-09-28c, cycle 2: a reconnect rebuilds the log from the
    lines it replays, so a later re-snapshot in the room keeps those and adds
    nothing older."""
    with TestClient(app) as client:
        _enter(client)
        events.append("system", None, "narrate", {"text": "a line before the drop"},
                      room_id="r-meadow")
        shown = events.append("system", None, "narrate", {"text": "the last line shown"},
                              room_id="r-meadow")
        events.append("system", None, "narrate", {"text": "a line while away"},
                      room_id="r-meadow")
        events.append("system", None, "narrate",
                      {"text": "a beat while away", "ambient": True}, room_id="r-meadow")
        with client.websocket_connect(f"/ws?since={shown.seq}") as ws:
            snap = ws.receive_json()
            replayed = [e["payload"].get("text") for e in snap["events"]]
            assert "a line while away" in replayed and "a beat while away" in replayed
            assert "the last line shown" not in replayed
            msg = _snapshot_after_painting(ws, "r-meadow", "a beat since reconnecting")
    texts = [e["payload"].get("text") for e in msg["events"]]
    assert msg["room"]["id"] == "r-meadow"
    assert {"a line while away", "a beat while away", "a beat since reconnecting"} <= set(texts)
    assert "a line before the drop" not in texts
    assert "the last line shown" not in texts

