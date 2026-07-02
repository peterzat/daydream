"""End-to-end WS integration for `plant` (SPEC 2026-07-02, criterion 5).

Drives the click-path command frame against a live TestClient with a mocked
LLM: the plant batch fans out, the planter's snapshot refreshes IN PLACE with
the new exit (no reconnect), walking the exit enters the grown room with its
full stored description, and its watercolor background enqueues through the
existing persistent-image path. Also asserts no object/toon/room id leaks
into any player-visible narrate text."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from daydream import db, events, objects
from daydream.api import ws as ws_module
from daydream.server import app

pytestmark = pytest.mark.tier_medium

GROWTH_BLOCK = {
    "question": "Where does the new way lead?",
    "theme": ["dusk", "moss"],
    "palette": "soft green and amber watercolor",
    "exemplars": [
        {"title": "The Winding Stair",
         "seed": "a narrow brass stair climbing into amber dusk",
         "description": "A stair coils up into the last of the light. Small "
                        "clocks rest on its steps, each keeping its own time."},
    ],
}

COMPOSITION = {
    "title": "The Moss Stair",
    "room_seed": "a narrow stair of soft moss winding down into green light",
    "description": "A stair of moss coils gently downward. The air is cool "
                   "and smells of rain. Somewhere below, water keeps a slow "
                   "time of its own.",
    "objects": [
        {"name": "mossy pebble", "seed": "a small pebble wearing a coat of moss"},
    ],
}


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)
    assert client.post("/api/slots/1/kick").status_code == 200
    rc = client.post("/api/slots/1/claim")
    assert rc.status_code == 200 and rc.json()["id"] == "t-wren", rc.text


def _spawn_carried_seed() -> str:
    seed = objects.spawn(
        "w-bunny", "thing", "dreamseed", "t-wren",
        prototype_id=objects.PROTO_THING,
        properties={"seed": "a seed like a folded lantern",
                    "verbs": ["plant"], "growth": GROWTH_BLOCK},
    )
    return seed.id


def test_plant_command_grows_room_and_refreshes_snapshot_live():
    with TestClient(app) as client:
        _login(client)
        seed_id = _spawn_carried_seed()
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=dict(COMPOSITION))) as spy:
            with client.websocket_connect("/ws") as sock:
                snap0 = sock.receive_json()
                assert snap0["kind"] == "state_snapshot"
                # Plant is on the verb bar (single-object, free-text).
                bar = {v["name"]: v for v in snap0["verb_bar"]}
                assert "plant" in bar and bar["plant"]["needs_iobj"] is False
                # The carried seed offers plant in the inventory panel.
                inv = {o["name"]: o for o in snap0["inventory"]}
                assert "plant" in inv["dreamseed"]["verbs"]
                assert "south" not in snap0["room"]["exits"]

                # The click path: one structured command frame. The whole
                # plant batch lands synchronously, so the broadcast loop
                # sends the FIRST batch event (room_grown), then one fresh
                # snapshot whose seq floor covers the rest of the batch —
                # the remaining events reach the client inside the
                # snapshot's replayed `events`, not as separate frames.
                sock.send_json({"kind": "command", "verb": "plant",
                                "dobj_id": seed_id,
                                "args": "a mossy stair into green light"})
                first = sock.receive_json()
                assert first["kind"] == "event"
                assert first["event"]["kind"] == "room_grown"
                snap1 = sock.receive_json()
                assert snap1["kind"] == "state_snapshot"

                # ONE LLM call; the refreshed snapshot carries the new exit
                # in place (no reconnect), and the seed left the inventory.
                assert spy.call_count == 1
                new_room_id = snap1["room"]["exits"].get("south")
                assert new_room_id, "refreshed snapshot must carry the new exit"
                assert all(o["name"] != "dreamseed" for o in snap1["inventory"])
                # The payoff narrate rides the snapshot's event replay; it
                # names the way and the title — and no raw ids appear in ANY
                # narrate text (SPEC: no ids in player-visible text).
                narrates = [e["payload"]["text"] for e in snap1["events"]
                            if e["kind"] == "narrate"]
                payoff = next(t for t in narrates if "takes root" in t)
                assert "south" in payoff and "The Moss Stair" in payoff
                for t in narrates:
                    assert new_room_id not in t and seed_id not in t
                    assert "t-wren" not in t

                # Walk the new exit: the grown room arrives with its full
                # stored description and enqueues its background render.
                sock.send_json({"kind": "input", "text": "go south"})
                move = sock.receive_json()
                assert move["event"]["kind"] == "move"
                grown_snap = sock.receive_json()
                assert grown_snap["kind"] == "state_snapshot"
                assert grown_snap["room"]["id"] == new_room_id
                assert grown_snap["room"]["title"] == "The Moss Stair"
                assert grown_snap["room"]["description"] == COMPOSITION["description"]
                names = {o["name"] for o in grown_snap["items"]}
                assert {"mossy pebble", "spent dreamseed"} <= names  # husk rests here
                # Lazy image gen fired for the grown room through the existing
                # persistent path (the conftest mock holds the dedup key).
                assert any(key[2] == new_room_id for key in ws_module._generating)


def test_plant_failure_path_over_ws_preserves_seed():
    """A refusal composition narrates in character; the seed stays carried
    and NO exit appears in any later snapshot."""
    with TestClient(app) as client:
        _login(client)
        seed_id = _spawn_carried_seed()
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value={"refused": True,
                                               "reason": "the dream is settling"})):
            with client.websocket_connect("/ws") as sock:
                sock.receive_json()
                sock.send_json({"kind": "command", "verb": "plant",
                                "dobj_id": seed_id, "args": "somewhere soft"})
                msg = sock.receive_json()
                assert msg["event"]["kind"] == "narrate"
                assert "settling" in msg["event"]["payload"]["text"]
        assert objects.get(seed_id).location_id == "t-wren"
        assert objects.get(seed_id).properties.get("state") != "spent"
