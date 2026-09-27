"""Entering the dream with an account (SPEC 2026-09-27 criteria 5 and 8): a
returning friend lands straight in their toon, a session that left sees
"your dreamer", and a second tab of the same account takes over while the
first is told, calmly, that it is dreaming elsewhere."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from daydream import config, db, events
from daydream.api import ws as ws_module
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium

MIRA = {"name": "Mira", "appearance_seed": "a fox in a wool hat"}


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _fresh_login(client, username="friend") -> str:
    """Log in as a NEW session of `username`; return its raw cookie value."""
    client.cookies.clear()
    authhelp.login(client, username)
    return client.cookies[config.cookie_name()]


def _ws(client, cookie):
    return client.websocket_connect("/ws", headers={"cookie": f"{config.cookie_name()}={cookie}"})


def test_a_returning_friend_lands_straight_in_their_toon():
    with TestClient(app) as client:
        _fresh_login(client)
        assert client.post("/api/dreamer/create", json=MIRA).status_code == 200
        later = _fresh_login(client)  # another day, another session
        client.cookies.clear()
        with _ws(client, later) as ws:
            snap = ws.receive_json()
    assert snap["kind"] == "state_snapshot"
    assert snap["self"]["name"] == "Mira"


def test_no_toon_yet_means_your_dreamer():
    with TestClient(app) as client:
        cookie = _fresh_login(client)
        client.cookies.clear()
        with _ws(client, cookie) as ws:
            assert ws.receive_json() == {"kind": "needs_toon"}


def test_after_leaving_the_next_connect_is_your_dreamer_not_the_toon():
    with TestClient(app) as client:
        _fresh_login(client)
        client.post("/api/dreamer/create", json=MIRA)
        assert client.post("/api/session/leave").status_code == 200
        cookie = client.cookies[config.cookie_name()]
        client.cookies.clear()
        with _ws(client, cookie) as ws:
            assert ws.receive_json() == {"kind": "needs_toon"}


def test_a_second_tab_takes_over_and_the_first_is_told():
    with TestClient(app) as client:
        first = _fresh_login(client)
        client.post("/api/dreamer/create", json=MIRA)
        second = _fresh_login(client)
        client.cookies.clear()
        with _ws(client, first) as ws1:
            assert ws1.receive_json()["kind"] == "state_snapshot"
            with _ws(client, second) as ws2:  # the second tab takes Mira
                assert ws2.receive_json()["self"]["name"] == "Mira"
                # The first tab learns on its next frame (or next event).
                ws1.send_json({"kind": "input", "text": "look"})
                seen = []
                with pytest.raises(WebSocketDisconnect) as closed:
                    for _ in range(30):
                        seen.append(ws1.receive_json())
                assert closed.value.code == ws_module.ELSEWHERE
                assert {"kind": "elsewhere"} in seen


def test_an_admin_with_several_toons_chooses():
    with TestClient(app) as client:
        client.cookies.clear()
        authhelp.login(client, "keeper", role="admin")
        client.post("/api/dreamer/create", json=MIRA)
        client.post("/api/dreamer/create", json={"name": "Ivo", "appearance_seed": "a heron"})
        cookie = _fresh_login(client, "keeper")
        client.cookies.clear()
        with _ws(client, cookie) as ws:
            assert ws.receive_json() == {"kind": "needs_toon"}
