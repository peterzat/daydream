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


def test_resting_the_toon_you_play_is_leaving_not_an_instant_wake():
    """Codereview BLOCK 2026-09-28: kick left the session 'in', so the next
    connect's auto-enter woke the toon at once, in the start room, and the
    room never heard the dreamer go."""
    with TestClient(app) as client:
        _fresh_login(client)
        mira = client.post("/api/dreamer/create", json=MIRA).json()
        assert client.post(f"/api/slots/{mira['slot']}/kick").status_code == 200
        assert any("Mira drifts out of the dream" in e.payload.get("text", "")
                   for e in events.fetch_since(0) if e.kind == "narrate")
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


def test_a_stale_tab_reconnecting_leaves_the_toon_with_the_device_in_use():
    """Codereview WARN 2026-09-28: a laptop wakes and reconnects (?since=)
    while the friend plays on the phone; the phone keeps Mira and the laptop
    is told it is dreaming elsewhere."""
    with TestClient(app) as client:
        laptop = _fresh_login(client)
        client.post("/api/dreamer/create", json=MIRA)
        phone = _fresh_login(client)
        client.cookies.clear()
        with _ws(client, phone) as ws_phone:  # a fresh load takes Mira over
            assert ws_phone.receive_json()["self"]["name"] == "Mira"
            with client.websocket_connect(
                    "/ws?since=5", headers={"cookie": f"{config.cookie_name()}={laptop}"}) as ws_lap:
                assert ws_lap.receive_json() == {"kind": "elsewhere"}
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws_lap.receive_json()
                assert closed.value.code == ws_module.ELSEWHERE
            ws_phone.send_json({"kind": "command", "verb": "look"})
            assert ws_phone.receive_json()["kind"] == "event"  # still hers


def test_a_dreamer_rested_from_another_device_wakes_that_page_and_stays_rested():
    """Codereview WARN 2026-09-29c: a rest from another device (or the shell)
    closed the page's socket like a network drop, and its reconnect took the
    toon straight back. The socket closes with RESTED, and that session has
    left the dream, so a reconnect lands awake."""
    from daydream import toons

    with TestClient(app) as client:
        phone = _fresh_login(client)
        me = client.post("/api/dreamer/create", json=MIRA).json()
        slot = toons.get_toon(me["id"]).slot
        laptop = _fresh_login(client)
        client.cookies.clear()
        with _ws(client, phone) as ws_phone:
            assert ws_phone.receive_json()["kind"] == "state_snapshot"
            client.cookies.set(config.cookie_name(), laptop)
            assert client.post(f"/api/slots/{slot}/kick").status_code == 200
            client.cookies.clear()
            ws_phone.send_json({"kind": "ping"})
            with pytest.raises(WebSocketDisconnect) as closed:
                for _ in range(30):
                    ws_phone.receive_json()
            assert closed.value.code == ws_module.RESTED
        with client.websocket_connect(
                "/ws?since=0", headers={"cookie": f"{config.cookie_name()}={phone}"}) as ws_back:
            assert ws_back.receive_json() == {"kind": "needs_toon"}
        t = toons.get_toon(me["id"])
        assert t.controller_session is None and t.kicked_at is not None


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


def test_an_admin_switches_toons_and_leaving_rests_the_one_in_play():
    """Codereview WARN 2026-09-28: taking a toon lets go of the one the
    session held, so the socket follows the pick, the released toon can be
    taken back, and leaving leaves nothing claimed."""
    with TestClient(app) as client:
        client.cookies.clear()
        authhelp.login(client, "keeper", role="admin")
        mira = client.post("/api/dreamer/create", json=MIRA).json()
        ivo = client.post("/api/dreamer/create",
                          json={"name": "Ivo", "appearance_seed": "a heron"}).json()
        for pick, name in ((mira, "Mira"), (ivo, "Ivo"), (mira, "Mira")):
            assert client.post(f"/api/slots/{pick['slot']}/claim").status_code == 200
            with client.websocket_connect("/ws") as ws:
                assert ws.receive_json()["self"]["name"] == name
        assert client.post("/api/session/leave").status_code == 200
        assert not any(t["claimed_by_me"] for t in client.get("/api/dreamer").json()["toons"])
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json() == {"kind": "needs_toon"}


def test_a_player_makes_only_so_many_dreamers_a_day():
    """Each dreamer paints a portrait on the shared GPU: making and letting go
    in a loop is capped per player per day (codereview/hardening 2026-09-28);
    the operator's admin accounts are exempt."""
    from daydream.api import slots as slots_module

    limit, _ = slots_module.DREAMERS_PER_DAY
    with TestClient(app) as client:
        authhelp.login(client, "looper")
        for i in range(limit):
            r = client.post("/api/dreamer/create",
                            json={"name": f"Loop{i}", "appearance_seed": "a small wren"})
            assert r.status_code == 200, r.text
            slot = r.json()["slot"]
            assert client.post(f"/api/slots/{slot}/delete").status_code == 200
        r = client.post("/api/dreamer/create",
                        json={"name": "LoopMore", "appearance_seed": "a small wren"})
        assert r.status_code == 429
        authhelp.login(client, "keeper-admin", role="admin")
        r = client.post("/api/dreamer/create",
                        json={"name": "Admin", "appearance_seed": "a small wren"})
        assert r.status_code == 200
