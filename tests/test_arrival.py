"""Arriving in a room (playtest 2026-09-28b, a first friend's ten minutes).

Walking into the square, Bell's welcome (a room `enter` rule) landed above
"You head east to the Lantern Square", dimmed as an earlier line, and Bell's
usual greeting came after it, just after Bell had climbed down to shake
hands. The lines a move causes are appended before the arrival snapshot, so
the snapshot now names the move's own seq for the SPA to cut "earlier" at,
and someone those lines already named does not greet the player again."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events, objects
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium

WELCOME = "Rook looks up from the anvil and waves you in, sparks and all."


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _until(ws, pred, tries: int = 30) -> dict:
    for _ in range(tries):
        msg = ws.receive_json()
        if pred(msg):
            return msg
    raise AssertionError("the expected frame never came")


def _walk_into_the_forge(welcome: bool):
    with TestClient(app) as client:
        authhelp.login(client)
        # The seeded Wren (slot 1), kick-then-claim as test_ws_forge does.
        assert client.post("/api/slots/1/kick").status_code == 200
        assert client.post("/api/slots/1/claim").status_code == 200
        if welcome:
            objects.set_property("r-forge", "rules", [
                {"on": "enter", "do": [{"kind": "narrate", "to": "@actor", "text": WELCOME}]}])
        with client.websocket_connect("/ws") as ws:
            _until(ws, lambda m: m["kind"] == "state_snapshot")
            ws.send_json({"kind": "input", "text": "go north"})
            move = _until(ws, lambda m: m["kind"] == "event" and m["event"]["kind"] == "move")
            snap = _until(ws, lambda m: m["kind"] == "state_snapshot")
            ws.send_json({"kind": "input", "text": "look"})
            after = []  # narrates that came between the arrival and the look
            while True:
                msg = ws.receive_json()
                if msg["kind"] != "event" or msg["event"]["kind"] != "narrate":
                    continue
                text = msg["event"]["payload"].get("text", "")
                if text == WELCOME or text.startswith("Rook is at the bellows"):
                    after.append(text)
                    continue
                break  # the look's own line
    return move["event"], snap, after


def test_the_snapshot_cuts_earlier_at_the_move_and_carries_its_welcome():
    move, snap, _after = _walk_into_the_forge(welcome=True)
    assert snap["arrival_seq"] == move["seq"]
    welcome = [e for e in snap["events"] if e["payload"].get("text") == WELCOME]
    assert welcome and welcome[0]["seq"] > snap["arrival_seq"]


def test_someone_the_welcome_named_does_not_greet_again():
    _move, _snap, after = _walk_into_the_forge(welcome=True)
    assert not any(t.startswith("Rook is at the bellows") for t in after), after


def test_without_a_welcome_the_greeting_still_comes():
    _move, snap, after = _walk_into_the_forge(welcome=False)
    assert any(t.startswith("Rook is at the bellows") for t in after), after
    assert snap["arrival_seq"] is not None
