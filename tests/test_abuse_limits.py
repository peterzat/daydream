"""What one signed-in friend with a script can no longer do to everyone else
(security review 2026-09-29): queue a model call per leave, flood leave and
claim, open socket after socket, or send long words in a command frame."""

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import config, db, events, journal, objects, toons
from daydream.api import slots
from daydream.api import ws as ws_mod
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


def _until(sock, pred, tries: int = 30) -> dict:
    for _ in range(tries):
        msg = sock.receive_json()
        if pred(msg):
            return msg
    raise AssertionError("the expected frame never came")


def test_leave_and_claim_share_a_small_budget():
    with TestClient(app) as client:
        _login(client, "loop-player")
        me = client.post("/api/dreamer/create",
                         json={"name": "Loop", "appearance_seed": "a restless one"}).json()
        slot = toons.get_toon(me["id"]).slot
        leaves, claims = [], []
        for _ in range(slots.PRESENCE_RATE[0] // 2 + 2):
            leaves.append(client.post("/api/session/leave").status_code)
            claims.append(client.post(f"/api/slots/{slot}/claim").status_code)
        # A leave always rests the dreamer (past the budget, quietly); only
        # claims past the budget are refused.
        assert leaves == [200] * len(leaves)
        within = slots.PRESENCE_RATE[0] // 2
        assert claims[:within] == [200] * within
        assert 429 in claims[within:]
        assert toons.get_toon(me["id"]).controller_session is None


async def test_one_recap_at_a_time_per_dreamer(monkeypatch, tmp_path):
    """A leave loop queued a journal call per leave over the same events; a
    second recap while one runs does nothing, and recaps never take a
    player's slot."""
    monkeypatch.setenv("DAYDREAM_JOURNAL_ENABLED", "1")
    gate = asyncio.Event()
    calls = []

    async def slow(**kw):
        calls.append(kw)
        await gate.wait()
        return {"entry": "You wandered a while among clocks and lanterns, then rested."}

    monkeypatch.setattr("daydream.llm.client.acompletion_json", slow)
    with TestClient(app) as client:
        _login(client, "recap-player")
        me = client.post("/api/dreamer/create",
                         json={"name": "Recap", "appearance_seed": "a dreamer"}).json()
        t = toons.get_toon(me["id"])
        events.append("system", None, "narrate", {"text": "A lantern flickers."},
                      room_id=objects.get(t.id).location_id, recipient_id=t.id)
        first = asyncio.create_task(journal.write_entry(t.id))
        await asyncio.sleep(0)
        await journal.write_entry(t.id)  # while the first runs: nothing
        await journal.write_entry(t.id)
        gate.set()
        await first
    assert len(calls) == 1
    assert calls[0].get("gate") == "background"


def test_a_session_keeps_at_most_three_sockets():
    with TestClient(app) as client:
        me = _login(client, "many-tabs")
        client.post("/api/dreamer/create", json={"name": "Tabs", "appearance_seed": "a tab"})
        client.cookies.clear()
        hdr = {"cookie": f"{config.cookie_name()}={me}"}
        with client.websocket_connect("/ws", headers=hdr) as s1:
            _until(s1, lambda m: m["kind"] == "state_snapshot")
            with client.websocket_connect("/ws", headers=hdr) as s2, \
                    client.websocket_connect("/ws", headers=hdr) as s3, \
                    client.websocket_connect("/ws", headers=hdr) as s4:
                for s in (s2, s3, s4):
                    _until(s, lambda m: m["kind"] == "state_snapshot")
                # The oldest is told it is dreaming elsewhere.
                assert _until(s1, lambda m: m["kind"] == "elsewhere")


def test_a_sessions_sockets_share_one_budget_that_a_reconnect_does_not_refill(monkeypatch):
    monkeypatch.setattr(ws_mod, "RATE_PER_SECOND", 0.0)  # no refill while the test runs
    long_line = {"kind": "input", "text": "x" * (ws_mod.MAX_INPUT_CHARS + 1)}
    with TestClient(app) as client:
        me = _login(client, "one-budget")
        client.post("/api/dreamer/create", json={"name": "Budget", "appearance_seed": "a steady one"})
        client.cookies.clear()
        hdr = {"cookie": f"{config.cookie_name()}={me}"}
        half = ws_mod.RATE_BURST // 2
        with client.websocket_connect("/ws", headers=hdr) as s1, \
                client.websocket_connect("/ws", headers=hdr) as s2:
            for s in (s1, s2):
                _until(s, lambda m: m["kind"] == "state_snapshot")
            for _ in range(half - 1):
                s1.send_json({"kind": "ping"})
            s1.send_json(long_line)  # answered, so s1's frames are all counted
            _until(s1, lambda m: m["kind"] == "notice" and "keep it under" in m["text"])
            for _ in range(ws_mod.RATE_BURST - half + 1):  # one more than is left
                s2.send_json({"kind": "ping"})
            _until(s2, lambda m: m["kind"] == "notice" and "slow down" in m["text"])
        for _ in range(100):  # both closed and unregistered: the session had no socket
            if not ws_mod._session_sockets:
                break
            time.sleep(0.02)
        assert not ws_mod._session_sockets
        # The session comes back on a new socket, still spent: the ping is
        # refused (a refilled budget would pass it and answer the long line).
        with client.websocket_connect("/ws", headers=hdr) as s3:
            _until(s3, lambda m: m["kind"] == "state_snapshot")
            for b in ws_mod._session_buckets.values():
                b.warned_at = 0.0  # the "slow down" note may speak again at once
            s3.send_json({"kind": "ping"})
            s3.send_json(long_line)
            note = _until(s3, lambda m: m["kind"] == "notice")
            assert "slow down" in note["text"], note


def test_a_command_frame_keeps_to_the_typed_line_cap():
    with TestClient(app) as client:
        me = _login(client, "long-words")
        client.post("/api/dreamer/create", json={"name": "Words", "appearance_seed": "a talker"})
        client.cookies.clear()
        with client.websocket_connect("/ws", headers={
                "cookie": f"{config.cookie_name()}={me}"}) as sock:
            _until(sock, lambda m: m["kind"] == "state_snapshot")
            before = events.max_seq()
            sock.send_json({"kind": "command", "verb": "say", "args": "x" * 600})
            note = _until(sock, lambda m: m["kind"] == "notice")
            assert "keep it under" in note["text"]
            assert not [e for e in events.fetch_since(before) if e.kind == "say"]
