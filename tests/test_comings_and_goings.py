"""Comings and goings (first prod evening, 2026-09-28): walking up and down
from the Clocktower left a bare "you go up." / "you go down." in every room
the player had left, and those lines replayed, stacked, on each return. A
move is presence, not story: the mover reads one line in the room they
reach, whoever shares either room reads a line naming the other place, live,
and a room you come back to replays none of it."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import config, db, events, toons
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


# ---- the tellings ----------------------------------------------------------------


@pytest.mark.tier_short
def test_each_move_is_told_three_ways_naming_the_places():
    up = toons.move_texts("Bell", "up", "The Clocktower", "The Clockmaker's Loft")
    assert up == {"you": "You climb up to the Clockmaker's Loft.",
                  "leave": "Bell climbs up to the Clockmaker's Loft.",
                  "arrive": "Bell comes up from the Clocktower."}
    down = toons.move_texts("Bell", "down", "The Clocktower", "The Hour Cellar")
    assert down["you"] == "You go down to the Hour Cellar."
    assert down["arrive"] == "Bell comes down from the Clocktower."
    east = toons.move_texts("Bell", "east", "The Clocktower", "Umber's Stall")
    assert east["you"] == "You head east to Umber's Stall."
    assert east["leave"] == "Bell heads east to Umber's Stall."
    assert east["arrive"] == "Bell comes in from the Clocktower."
    odd = toons.move_texts("Bell", "out", "The Clocktower", "The Lantern Square")
    assert odd["you"] == "You go out to the Lantern Square."
    shift = toons.move_texts("Bell", None, "A", "The Well-Court", teleport=True)
    assert shift["you"] == "You find yourself in the Well-Court."


# ---- over the socket ---------------------------------------------------------------


def _login(client, username: str) -> str:
    client.cookies.clear()
    authhelp.login(client, username)
    return client.cookies[config.cookie_name()]


def _ws(client, cookie):
    return client.websocket_connect("/ws", headers={"cookie": f"{config.cookie_name()}={cookie}"})


def _until(ws, pred, tries: int = 30) -> dict:
    for _ in range(tries):
        msg = ws.receive_json()
        if pred(msg):
            return msg
    raise AssertionError("the expected frame never came")


def _snapshot(msg) -> bool:
    return msg["kind"] == "state_snapshot"


def _presence(kind: str):
    return lambda m: m["kind"] == "event" and m["event"]["kind"] == kind


def _names_here(snap: dict) -> set[str]:
    return {t["name"] for t in snap["toons"]}


def test_a_room_you_return_to_replays_nothing_of_your_going():
    with TestClient(app) as client:
        cookie = _login(client, "mira-player")
        client.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a tall woman"})
        with _ws(client, cookie) as ws:
            start = _until(ws, _snapshot)["room"]["id"]
            back = None
            for step in ("go north", "go south", "go north", "go south"):
                ws.send_json({"kind": "input", "text": step})
                move = _until(ws, _presence("move"))["event"]
                snap = _until(ws, _snapshot)
                assert move["payload"]["you"].startswith("You head ")
                back = snap
    assert back["room"]["id"] == start
    kinds = {e["kind"] for e in back["events"]}
    assert not kinds & set(toons.PRESENCE_KINDS), kinds


def test_others_see_you_leave_and_arrive_and_their_panel_follows():
    with TestClient(app) as client:
        mira = _login(client, "mira-player")
        client.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a tall woman"})
        ivo = _login(client, "ivo-player")
        client.post("/api/dreamer/create", json={"name": "Ivo", "appearance_seed": "a small man"})
        client.cookies.clear()
        with _ws(client, ivo) as watcher, _ws(client, mira) as walker:
            assert "Mira" in _names_here(_until(watcher, _snapshot))
            _until(walker, _snapshot)
            walker.send_json({"kind": "input", "text": "go north"})
            _until(walker, _snapshot)
            left = _until(watcher, _presence("move"))["event"]["payload"]
            assert left["text"].startswith("Mira heads north to ")
            assert "Mira" not in _names_here(_until(watcher, _snapshot))
            walker.send_json({"kind": "input", "text": "go south"})
            _until(walker, _snapshot)
            came = _until(watcher, _presence("arrive"))["event"]["payload"]
            assert came["text"].startswith("Mira comes in from ")
            again = _until(watcher, _snapshot)
    assert "Mira" in _names_here(again)
    # The arrival stays in the watcher's log through that refresh.
    assert any(e["kind"] == "arrive" for e in again["events"])


def test_the_journal_window_counts_a_move_once():
    with TestClient(app) as client:
        cookie = _login(client, "mira-player")
        mira = client.post("/api/dreamer/create",
                           json={"name": "Mira", "appearance_seed": "a tall woman"}).json()
        with _ws(client, cookie) as ws:
            _until(ws, _snapshot)
            ws.send_json({"kind": "input", "text": "go north"})
            _until(ws, _snapshot)
        mine = events.fetch_for_toon(mira["id"])
    assert [e.kind for e in mine if e.kind in toons.PRESENCE_KINDS] == ["move"]
