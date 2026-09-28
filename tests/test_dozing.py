"""A player with no one at the page is dozing (playtest 2026-09-28b).

Another player's dreamer was still claimed by a session long gone, so it
stood in "here with you" like anyone present, and a hello met silence. Now
their card says they are away, and speaking to them says they are dozing."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import config, db, events
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


def _login(client, username: str) -> str:
    client.cookies.clear()
    authhelp.login(client, username)
    return client.cookies[config.cookie_name()]


def _until(ws, pred, tries: int = 30) -> dict:
    for _ in range(tries):
        msg = ws.receive_json()
        if pred(msg):
            return msg
    raise AssertionError("the expected frame never came")


def test_a_player_whose_page_is_closed_dozes_and_says_so_when_spoken_to():
    with TestClient(app) as client:
        ivo = _login(client, "ivo-player")
        client.post("/api/dreamer/create", json={"name": "Ivo", "appearance_seed": "a small man"})
        mira = _login(client, "mira-player")
        client.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a tall woman"})
        client.cookies.clear()
        hdr = lambda c: {"cookie": f"{config.cookie_name()}={c}"}  # noqa: E731
        with client.websocket_connect("/ws", headers=hdr(mira)) as ws:
            snap = _until(ws, lambda m: m["kind"] == "state_snapshot")
            cards = {t["name"]: t for t in snap["toons"]}
            assert cards["Ivo"]["away"] is True
            assert cards["Mira"]["away"] is False  # never yourself
            ws.send_json({"kind": "command", "verb": "talk", "dobj_id": cards["Ivo"]["id"],
                          "args": "hello!"})
            said = _until(ws, lambda m: m["kind"] == "event" and m["event"]["kind"] == "say")
            assert said["event"]["payload"]["to"] == "Ivo"
            note = _until(ws, lambda m: m["kind"] == "event" and m["event"]["kind"] == "narrate")
            assert "Ivo is dozing" in note["event"]["payload"]["text"]
            # Once Ivo's page is open, Ivo is here, and a hello is just speech.
            with client.websocket_connect("/ws", headers=hdr(ivo)) as ws2:
                _until(ws2, lambda m: m["kind"] == "state_snapshot")
                ws.send_json({"kind": "input", "text": "go north"})
                _until(ws, lambda m: m["kind"] == "state_snapshot")
                ws.send_json({"kind": "input", "text": "go south"})
                again = _until(ws, lambda m: m["kind"] == "state_snapshot"
                               and any(t["name"] == "Ivo" for t in m["toons"]))
                assert {t["name"]: t for t in again["toons"]}["Ivo"]["away"] is False


def test_a_command_that_changes_your_threads_sends_them_at_once():
    """Playtest 2026-09-28c: an ask or a take moved a thread, but the satchel's
    count waited for the next snapshot. A command that changes this player's
    threads is followed by a `threads` frame."""
    from daydream import objects, toons, worldstate

    with TestClient(app) as client:
        mira = _login(client, "mira-player")
        me = client.post("/api/dreamer/create",
                         json={"name": "Mira", "appearance_seed": "a tall woman"}).json()
        client.cookies.clear()
        room = objects.get(me["id"]).location_id
        pebble = objects.spawn(toons.live_world_id(), "thing", "pebble", location_id=room,
                               prototype_id=objects.PROTO_THING, properties={"seed": "a pebble"})
        worldstate.set(toons.live_world_id(), "def:threads", [
            {"id": "pebble", "text": "You carry a pebble.", "if": [{"carried": pebble.id}]}])
        hdr = {"cookie": f"{config.cookie_name()}={mira}"}
        with client.websocket_connect("/ws", headers=hdr) as ws:
            first = _until(ws, lambda m: m["kind"] == "state_snapshot")
            assert first["threads"] == []
            ws.send_json({"kind": "command", "verb": "take", "dobj_id": pebble.id})
            got = _until(ws, lambda m: m["kind"] == "threads")
            assert got["threads"] == ["You carry a pebble."]
