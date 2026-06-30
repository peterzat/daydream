"""End-to-end gameplay-scenario test (SPEC 2026-06-30 C14).

One scripted story through the playable flow against a `world load`ed world
(uuid toon ids, no literal t-wren): connect -> picker -> create -> look ->
take -> go-to-place -> talk -> spawn -> examine -> inventory. Deterministic
verbs make no LLM call; only the talk dialogue does, and it is mocked. This
exercises the picker-first entry, navigation-by-place, the generative
talk->spawn slice, lazy examine, and the inventory affordance as one flow,
not as isolated unit assertions."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.server import app

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _load_bunny_world(tmp_path) -> None:
    """Build worlds/bunny.json as the live DB under the fresh tmp data dir."""
    from daydream import config
    from daydream.llm import bootstrap

    live = config.live_db_path()
    live.parent.mkdir(parents=True, exist_ok=True)
    envelope = json.loads(
        (Path(__file__).resolve().parent.parent / "worlds" / "bunny.json").read_text()
    )
    bootstrap.load_world("bunny world", envelope, live)
    db.close_db()


def _recv_event(ws, kind: str, limit: int = 16) -> dict:
    """Receive frames until an `event` frame of the given event-kind; return it.
    Snapshots and other events along the way are drained."""
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("kind") == "event" and msg["event"]["kind"] == kind:
            return msg["event"]
    raise AssertionError(f"no {kind!r} event within {limit} frames")


def _recv_snapshot(ws, limit: int = 16) -> dict:
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("kind") == "state_snapshot":
            return msg
    raise AssertionError("no state_snapshot received")


def test_full_play_scenario(tmp_path, monkeypatch):
    _load_bunny_world(tmp_path)

    # Rook's talk dialogue: a narrate plus a generative spawn of the papers
    # (the only LLM call in the whole scenario; everything else is fast-path).
    dialogue = {
        "effects": [
            {"kind": "narrate",
             "text": "Rook brushes soot from the anvil and lays out a sheaf of papers, and says, 'every repair, drawn small.'"},
            {"kind": "spawn_object", "name": "a sheaf of papers",
             "seed": "loose pages, soft at the edges, covered in small careful drawings of every repair",
             "aliases": ["papers", "sheaf"], "generated_by": "talk:rook"},
        ]
    }

    with TestClient(app) as client:
        # connect (unclaimed) -> picker.
        assert client.post("/api/login", data={"password": "test-password"}).status_code in (200, 303)
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json() == {"kind": "needs_toon"}

        # create a toon (slot 2 is empty in bunny.json) -> a uuid id.
        r = client.post(
            "/api/slots/2/create", json={"name": "Fern", "appearance_seed": "a wisp of dusk"}
        )
        assert r.status_code == 200, r.text
        fern_id = r.json()["id"]
        assert fern_id and fern_id != "t-wren"

        with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=dialogue)):
            with client.websocket_connect("/ws") as ws:
                snap = ws.receive_json()
                assert snap["kind"] == "state_snapshot"
                assert snap["room"]["slug"] == "meadow"
                assert snap["self"]["id"] == fern_id
                assert any(it["name"] == "brass lantern" for it in snap["items"])

                # look -> room narrate.
                ws.send_json({"kind": "input", "text": "look"})
                assert "meadow" in _recv_event(ws, "narrate")["payload"]["text"].lower()

                # take the lantern -> it leaves the ground and enters inventory.
                ws.send_json({"kind": "input", "text": "take the lantern"})
                _recv_event(ws, "object_moved")
                after_take = _recv_snapshot(ws)
                assert not any(it["name"] == "brass lantern" for it in after_take["items"])
                assert any(it["name"] == "brass lantern" for it in after_take["inventory"])

                # navigate by place name -> the forge (an adjacent room).
                ws.send_json({"kind": "input", "text": "go to forge"})
                move = _recv_event(ws, "move")
                assert move["payload"]["to_room"] == "r-forge"
                forge_snap = _recv_snapshot(ws)
                assert forge_snap["room"]["slug"] == "forge"
                rook = next(t for t in forge_snap["toons"] if t["name"] == "Rook")

                # talk to Rook (click path) -> his dialogue narrates AND spawns
                # the sheaf of papers into the room.
                ws.send_json({
                    "kind": "command", "verb": "talk",
                    "dobj_id": rook["id"], "args": "show me your papers",
                })
                spawned = _recv_event(ws, "object_spawned")
                assert spawned["payload"]["name"] == "a sheaf of papers"
                after_spawn = _recv_snapshot(ws)
                assert any(it["name"] == "a sheaf of papers" for it in after_spawn["items"])

                # examine the spawned papers (by alias) -> deterministic detail.
                ws.send_json({"kind": "input", "text": "examine the papers"})
                examined = _recv_event(ws, "narrate")["payload"]["text"].lower()
                assert "papers" in examined and "loose pages" in examined

                # inventory -> the lantern taken earlier (deterministic, no LLM).
                ws.send_json({"kind": "input", "text": "inventory"})
                inv = _recv_event(ws, "narrate")["payload"]["text"].lower()
                assert "lantern" in inv
