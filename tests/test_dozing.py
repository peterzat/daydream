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


def test_the_margin_names_who_else_is_awake_and_where():
    """Beta rehearsal 2026-09-28: a household on different schedules wants to
    know who is in the village before going to find them. The snapshot
    lists the other players awake at their pages, with their room; never
    yourself, never a dozing or resting dreamer; and a dreamer who leaves
    or comes back re-snapshots the room at once (presence_changed)."""
    from daydream import toons

    with TestClient(app) as client:
        ivo = _login(client, "ivo-player")
        ivo_me = client.post("/api/dreamer/create",
                             json={"name": "Ivo", "appearance_seed": "a small man"}).json()
        ivo_slot = toons.get_toon(ivo_me["id"]).slot
        mira = _login(client, "mira-player")
        client.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a tall woman"})
        client.cookies.clear()
        hdr = lambda c: {"cookie": f"{config.cookie_name()}={c}"}  # noqa: E731
        with client.websocket_connect("/ws", headers=hdr(mira)) as ws:
            snap = _until(ws, lambda m: m["kind"] == "state_snapshot")
            assert snap["dreaming"] == []  # Ivo's page was never open
            with client.websocket_connect("/ws", headers=hdr(ivo)) as ws2:
                first = _until(ws2, lambda m: m["kind"] == "state_snapshot")
                assert [d["name"] for d in first["dreaming"]] == ["Mira"]
                assert first["dreaming"][0]["room"] == snap["room"]["title"]
                ws.send_json({"kind": "input", "text": "go north"})
                moved = _until(ws, lambda m: m["kind"] == "state_snapshot")
                assert [d["name"] for d in moved["dreaming"]] == ["Ivo"]
                assert moved["dreaming"][0]["room"] == snap["room"]["title"]
                # Ivo leaves the dream: Mira's next snapshot no longer lists them.
                client.cookies.set(config.cookie_name(), ivo)
                assert client.post("/api/session/leave").status_code == 200
                client.cookies.clear()
                # Mira is in another room, and the list refreshes there at
                # once (presence_changed is world-scoped; codereview 2026-09-29).
                gone = _until(ws, lambda m: m["kind"] == "state_snapshot" and m["dreaming"] == [])
                assert gone["room"]["title"] != snap["room"]["title"]
                ws.send_json({"kind": "input", "text": "go south"})
                back = _until(ws, lambda m: m["kind"] == "state_snapshot"
                              and m["room"]["title"] == snap["room"]["title"])
                assert back["dreaming"] == []
                assert all(t["name"] != "Ivo" for t in back["toons"])
            # Ivo steps back in: the room reads it, and the margin follows.
            client.cookies.set(config.cookie_name(), ivo)
            assert client.post(f"/api/slots/{ivo_slot}/claim").status_code == 200
            client.cookies.clear()
            with client.websocket_connect("/ws", headers=hdr(ivo)) as ws3:
                _until(ws3, lambda m: m["kind"] == "state_snapshot")
                woke = _until(ws, lambda m: m["kind"] == "event"
                              and m["event"]["kind"] == "narrate"
                              and "drifts back into the dream" in m["event"]["payload"]["text"])
                assert woke["event"]["payload"]["text"] == "Ivo drifts back into the dream."
                again = _until(ws, lambda m: m["kind"] == "state_snapshot"
                               and any(d["name"] == "Ivo" for d in m["dreaming"]))
                assert any(t["name"] == "Ivo" for t in again["toons"])


def test_the_away_note_survives_the_leavers_own_open_page():
    """Codereview 2026-09-29: the browser posts leave before closing its
    socket, and that socket's re-snapshot read and cleared the "while you
    were away" stamp for a dreamer no longer in the dream. The note keeps
    for their return."""
    from daydream import toons, worldclock

    with TestClient(app) as client:
        ivo = _login(client, "ivo-player")
        ivo_me = client.post("/api/dreamer/create",
                             json={"name": "Ivo", "appearance_seed": "a small man"}).json()
        ivo_slot = toons.get_toon(ivo_me["id"]).slot
        mira = _login(client, "mira-player")
        client.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a tall woman"})
        client.cookies.clear()
        hdr = lambda c: {"cookie": f"{config.cookie_name()}={c}"}  # noqa: E731
        try:
            worldclock.set_fake_now("2026-10-01T18:00:00+00:00")
            with client.websocket_connect("/ws", headers=hdr(mira)) as ws, \
                    client.websocket_connect("/ws", headers=hdr(ivo)) as ws2:
                _until(ws, lambda m: m["kind"] == "state_snapshot")
                _until(ws2, lambda m: m["kind"] == "state_snapshot")
                # Ivo leaves while their page's socket is still open.
                client.cookies.set(config.cookie_name(), ivo)
                assert client.post("/api/session/leave").status_code == 200
                client.cookies.clear()
                # Mira dreams on, an hour later; her words reach Ivo's old
                # socket, so it has processed everything the leave emitted.
                worldclock.advance(hours=1)
                ws.send_json({"kind": "command", "verb": "say", "args": "hello"})
                _until(ws2, lambda m: m["kind"] == "event" and m["event"]["kind"] == "say")
            # Ivo comes back: the note is still there to be told, once.
            client.cookies.set(config.cookie_name(), ivo)
            assert client.post(f"/api/slots/{ivo_slot}/claim").status_code == 200
            client.cookies.clear()
            with client.websocket_connect("/ws", headers=hdr(ivo)) as ws3:
                back = _until(ws3, lambda m: m["kind"] == "state_snapshot")
                note = back["while_you_slept"]
                assert note and "Mira was here while you rested." in note["text"]
        finally:
            worldclock.set_fake_now(None)
