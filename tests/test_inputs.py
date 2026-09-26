"""Every word a player types is kept (SPEC 2026-09-26 criterion 16).

Raw input (free text and structured clicks) is persisted with actor, time,
and the resolved command; it is never broadcast (a co-located player's
connection never sees it); and a recorded session exports as a walkthrough
dataset that replays."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events, inputs, worldclock
from daydream.server import app

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    worldclock.set_fake_now("2026-10-01T17:00:00+00:00")
    yield
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _claim_wren(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)
    assert client.post("/api/slots/1/kick").status_code == 200
    assert client.post("/api/slots/1/claim").status_code == 200


def _drain_until(ws, pred, limit=40):
    for _ in range(limit):
        frame = ws.receive_json()
        if pred(frame):
            return frame
    raise AssertionError("expected frame never arrived")


def test_typed_and_clicked_inputs_are_recorded_with_resolution():
    with TestClient(app) as client:
        _claim_wren(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"kind": "input", "text": "take the lantern"})
            _drain_until(ws, lambda f: f.get("kind") == "state_snapshot")
            lantern_id = next(
                i.resolved[0]["dobj_id"] for i in inputs.fetch()
                if i.source == "text")
            ws.send_json({"kind": "command", "verb": "drop", "dobj_id": lantern_id})
            _drain_until(ws, lambda f: f.get("kind") == "state_snapshot")
            ws.send_json({"kind": "input", "text": "xyzzy plugh"})
            _drain_until(ws, lambda f: f.get("kind") == "event")
        rows = inputs.fetch()
    assert [r.source for r in rows] == ["text", "command", "text"]
    typed, clicked, gibberish = rows
    assert typed.text == "take the lantern"
    assert typed.toon_id == "t-wren"
    assert typed.created_at == "2026-10-01T17:00:00+00:00"
    assert typed.resolved and typed.resolved[0]["verb"] == "take"
    assert clicked.verb == "drop" and clicked.dobj_id == lantern_id
    # An ungroundable line (the LLM is unreachable in tests) is still kept.
    assert gibberish.text == "xyzzy plugh"


def test_inputs_are_never_broadcast():
    """Raw input is not an event: nothing typed reaches the event log as
    input, so no other connection can ever receive it."""
    with TestClient(app) as client:
        _claim_wren(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "get lantern"})
            _drain_until(ws, lambda f: f.get("kind") == "state_snapshot")
        logged = events.fetch_since(0)
    assert logged
    for e in logged:
        assert "get lantern" not in str(e.payload)


def test_recorded_session_exports_as_a_replayable_walkthrough():
    with TestClient(app) as client:
        _claim_wren(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "take the lantern"})
            _drain_until(ws, lambda f: f.get("kind") == "state_snapshot")
            ws.send_json({"kind": "input", "text": "drop lantern"})
            _drain_until(ws, lambda f: f.get("kind") == "state_snapshot")
        dataset = inputs.export_walkthrough("t-wren")
    steps = dataset["segments"][0]["commands"]
    assert [s["cmd"] for s in steps] == ["take the lantern", "drop lantern"]
    assert all(s["at"].startswith("2026-10-01T17:00") for s in steps)


async def test_an_exported_session_replays_on_a_fresh_world(tmp_path):
    """The raw input log is a regression oracle: a player's recorded
    session, exported as a walkthrough, replays through the real parser on a
    fresh copy of the world, at its original times."""
    import json as _json

    from daydream import walkthrough

    with TestClient(app) as client:
        _claim_wren(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "take the lantern"})
            _drain_until(ws, lambda f: f.get("kind") == "state_snapshot")
            ws.send_json({"kind": "input", "text": "north"})
            _drain_until(ws, lambda f: f.get("kind") == "state_snapshot")
        dataset = inputs.export_walkthrough("t-wren")
    db.close_db()
    events.reset_subscribers()
    from daydream import config

    db.init_live(path=tmp_path / "replay.db", migrations_dir=config.MIGRATIONS_DIR)
    dataset["players"] = [{"as": "A", "name": "Replayer"}]
    dataset["segments"][0]["commands"][-1]["expect"] = {"carrying": ["lantern"]}
    run = await walkthrough.replay(_json.loads(_json.dumps(dataset)))
    assert run.steps == 2
