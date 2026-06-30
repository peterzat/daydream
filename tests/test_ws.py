"""Websocket: auth gate, state_snapshot, input dispatch (canonical + LLM).

SPEC criteria 4 (websocket protocol) and parts of 5 (skills end to end via WS).
LLM tests mock daydream.llm.client.acompletion_json so no GPU needed."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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


def _login(client: TestClient) -> None:
    # TestClient follows the 303 to / by default, so accept either status.
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303), f"login failed: {r.status_code} {r.text}"


def test_ws_unauthed_is_rejected():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()


def test_ws_sends_state_snapshot_on_connect():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["kind"] == "state_snapshot"
    assert msg["room"]["slug"] == "meadow"
    assert any(it["name"] == "lantern" for it in msg["items"])
    assert any(t["name"] == "Wren" for t in msg["toons"])
    skill_names = {s["name"] for s in msg["skills"]}
    assert {"look", "say", "examine"}.issubset(skill_names)


def test_ws_snapshot_does_not_include_npc_when_player_is_elsewhere():
    """SPEC 2026-04-23 criterion 2: Rook (migration 006) is at r-forge.
    On initial connect the player starts at r-meadow, so the snapshot's
    toons list must not leak the NPC across room boundaries."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["room"]["slug"] == "meadow"
    toon_names = {t["name"] for t in msg["toons"]}
    assert "Rook" not in toon_names
    assert "Wren" in toon_names


def test_ws_go_into_npc_room_emits_presence_narrate():
    """SPEC 2026-04-24 criterion 2: entering r-forge (where Rook lives)
    emits Rook's presence_text as a narrate event, after the move event
    and the post-move snapshot. Order: move -> snapshot -> narrate."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # meadow snapshot
            ws.send_json({"kind": "input", "text": "go north"})
            move_msg = ws.receive_json()
            snap = ws.receive_json()
            narrate = ws.receive_json()
    assert move_msg["event"]["kind"] == "move"
    assert snap["kind"] == "state_snapshot" and snap["room"]["slug"] == "forge"
    assert narrate["kind"] == "event"
    assert narrate["event"]["kind"] == "narrate"
    assert narrate["event"]["actor_type"] == "system"
    # Greeting text carries Rook-specific vocabulary from migration 007.
    text = narrate["event"]["payload"]["text"]
    assert "Rook" in text
    assert "bellows" in text or "sooty" in text or "humming" in text


def test_ws_initial_connect_to_empty_room_emits_no_presence_narrate():
    """SPEC 2026-04-24 criterion 3: connecting to the meadow (no NPCs)
    does NOT fire a presence narrate, and more broadly, initial connect
    never fires one — the snapshot's `events` field already carries
    prior narrates on reconnect. Verified by sending `say` after the
    snapshot and asserting the FIRST event received is the say event,
    not a stray narrate ahead of it."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
            assert snap["room"]["slug"] == "meadow"
            # Send a `say` to prove the next event we receive is that
            # say, not a queued presence narrate that leaked through.
            ws.send_json({"kind": "input", "text": "say hello"})
            evt = ws.receive_json()
    assert evt["event"]["kind"] == "say"
    assert evt["event"]["payload"]["text"] == "hello"


def test_ws_snapshot_includes_npc_after_entering_npc_room():
    """SPEC 2026-04-23 criterion 2: after `go north` from the meadow
    the player is at r-forge; the refreshed snapshot's toons list
    must include Rook (the NPC) alongside Wren (the player)."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial snapshot (meadow)
            ws.send_json({"kind": "input", "text": "go north"})
            ws.receive_json()  # move event
            snap = ws.receive_json()  # refreshed snapshot (forge)
    assert snap["kind"] == "state_snapshot"
    assert snap["room"]["slug"] == "forge"
    toon_names = {t["name"] for t in snap["toons"]}
    assert {"Wren", "Rook"}.issubset(toon_names)
    # The NPC's mood (from the migration seed) flows into the snapshot.
    rook = next(t for t in snap["toons"] if t["name"] == "Rook")
    assert rook["mood"] == "content"


def test_ws_canonical_look_emits_narrate_event():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"kind": "input", "text": "look"})
            evt = ws.receive_json()
    assert evt["kind"] == "event"
    assert evt["event"]["kind"] == "narrate"
    assert "meadow" in evt["event"]["payload"]["text"]


def test_ws_canonical_say_emits_say_event():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "say hello"})
            evt = ws.receive_json()
    assert evt["event"]["kind"] == "say"
    assert evt["event"]["payload"]["text"] == "hello"
    assert evt["event"]["actor_id"] == "t-wren"


def test_ws_canonical_examine_echoes_seed_sentinel():
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "examine the lantern"})
            evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    assert "hairline crack" in evt["event"]["payload"]["text"]


def test_ws_dispatch_uses_claimed_slot_toon_not_legacy_wren():
    """After claiming a slot, the WS resolves the controlled toon to
    that slot's toon. Subsequent input events have actor_id matching
    the claimed toon, not 't-wren' (the legacy fallback)."""
    with TestClient(app) as client:
        _login(client)
        # Claim slot 2 with a fresh toon.
        r = client.post(
            "/api/slots/2/create",
            json={"name": "Mira", "appearance_seed": "a small fox in a wool hat"},
        )
        assert r.status_code == 200
        claimed_id = r.json()["id"]
        assert claimed_id != "t-wren"
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"kind": "input", "text": "say hello"})
            evt = ws.receive_json()
    assert evt["event"]["kind"] == "say"
    assert evt["event"]["actor_id"] == claimed_id


def test_ws_unclaimed_session_falls_back_to_t_wren():
    """A session that hasn't claimed a slot dispatches as t-wren
    (legacy fallback). Verifies the fallback path explicitly."""
    with TestClient(app) as client:
        _login(client)
        # Do NOT claim a slot.
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"kind": "input", "text": "say hello"})
            evt = ws.receive_json()
    assert evt["event"]["actor_id"] == "t-wren"


def test_ws_llm_routed_input_dispatches_skill():
    """SPEC criterion 6: 'look around' -> look skill via LLM interpreter."""
    canned = {"skill": "look", "args": "around"}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        with TestClient(app) as client:
            _login(client)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "look around"})
                evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    assert "meadow" in evt["event"]["payload"]["text"]


def test_ws_unknown_phrase_produces_chat_fallback():
    """SPEC criterion 6: chatter -> 'none' -> narrate fallback, no skill misfire."""
    canned = {"skill": "none", "args": ""}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        with TestClient(app) as client:
            _login(client)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "sing a song"})
                evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    # The fallback narration includes the original input verbatim.
    assert "sing a song" in evt["event"]["payload"]["text"]


def test_ws_llm_unavailable_produces_foggy_narration():
    """SPEC criterion 7: LLM down -> 'the dream is foggy' narration, no crash."""
    from daydream.llm.client import LLMUnavailable

    with patch(
        "daydream.llm.client.acompletion_json",
        new=AsyncMock(side_effect=LLMUnavailable("vLLM unreachable")),
    ):
        with TestClient(app) as client:
            _login(client)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "what time is it"})
                evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    assert "foggy" in evt["event"]["payload"]["text"].lower()


def test_ws_snapshot_includes_prior_events_after_say():
    """SPEC criterion 8 spine: 'say hello' persists; reconnecting receives it
    in the snapshot's recent-events slice."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "say hello"})
            ws.receive_json()  # the say event
        # Reconnect on the same DB resumes via ?since (a fresh load = empty log).
        with client.websocket_connect("/ws?since=0") as ws2:
            snapshot = ws2.receive_json()
    say_events = [
        e for e in snapshot["events"]
        if e["kind"] == "say" and e["payload"].get("text") == "hello"
    ]
    assert len(say_events) == 1


# ---- multi-room navigation ----------------------------------------------


def test_ws_snapshot_includes_room_exits():
    """SPEC criterion 2: state_snapshot.room.exits is the single source of
    truth for navigation UI. Meadow has north -> forge and east -> bridge
    per 004_multi_room.sql."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert snap["room"]["slug"] == "meadow"
    exits = snap["room"]["exits"]
    assert exits == {"north": "r-forge", "east": "r-bridge"}


def test_ws_go_north_moves_toon_and_refreshes_snapshot():
    """SPEC criterion 1: `go north` emits a move event and the server
    pushes a fresh snapshot pinned to the new room."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial snapshot (meadow)
            ws.send_json({"kind": "input", "text": "go north"})
            # The server sends the move event first, then a fresh
            # state_snapshot for the destination.
            move_msg = ws.receive_json()
            snap2 = ws.receive_json()
    assert move_msg["kind"] == "event"
    move = move_msg["event"]
    assert move["kind"] == "move"
    assert move["payload"] == {
        "from_room": "r-meadow",
        "to_room": "r-forge",
        "direction": "north",
    }
    assert snap2["kind"] == "state_snapshot"
    assert snap2["room"]["slug"] == "forge"
    # The new room's exits are the forge's own — NOT the meadow's.
    assert snap2["room"]["exits"] == {"south": "r-meadow", "up": "r-attic"}


def test_ws_go_unknown_direction_narrates_and_does_not_move():
    """SPEC criterion 1 failure path: a direction not in exits_json emits
    a narrate event and NO move event and NO fresh snapshot."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial snapshot
            ws.send_json({"kind": "input", "text": "go diagonal"})
            evt_msg = ws.receive_json()
    assert evt_msg["kind"] == "event"
    assert evt_msg["event"]["kind"] == "narrate"
    assert "can't go diagonal" in evt_msg["event"]["payload"]["text"]


def test_ws_navigation_persists_across_reconnect():
    """SPEC criterion 5: `go north` then reconnect -> the snapshot the
    new connection receives reflects the destination room, proving the
    toon's current_room_id was written through and survives a session
    boundary (simulating bin/game down && bin/game up)."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "go north"})
            ws.receive_json()  # move event
            ws.receive_json()  # refreshed snapshot (forge)
        # New WS connection on the same DB — current_room_id should
        # now persist as r-forge.
        with client.websocket_connect("/ws") as ws2:
            snap = ws2.receive_json()
    assert snap["room"]["slug"] == "forge"
    assert snap["room"]["exits"] == {"south": "r-meadow", "up": "r-attic"}


# ---- scene objects + verb bar in the snapshot --------------------------


def test_ws_snapshot_carries_scene_objects_verb_bar_and_entities():
    """The snapshot sends clickable scene objects (things with verbs), the
    verb bar (Examine/Take/Drop/Talk), the inventory list, and an entity
    sidecar mapping in-scope names to ids for narration linking."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    # The lantern (previously sent but unrendered) carries its verbs + kind.
    lantern = next(i for i in snap["items"] if i["name"] == "lantern")
    assert lantern["kind"] == "thing"
    assert lantern["verbs"] == ["examine", "take", "drop"]
    # The verb bar is exactly Examine / Take / Drop / Talk.
    assert [v["name"] for v in snap["verb_bar"]] == ["examine", "take", "drop", "talk"]
    # Inventory starts empty; the entity sidecar maps the lantern's name -> id.
    assert snap["inventory"] == []
    assert any(
        e["alias"].lower() == "lantern" and e["object_id"] == "i-lantern"
        for e in snap["entities"]
    )


# ---- structured command frame (the click path) -------------------------


def test_ws_command_take_moves_item_and_refreshes_snapshot():
    """A `{kind:"command", verb:"take", dobj_id}` frame executes the take verb:
    the thing moves into the actor's inventory and the server pushes a fresh
    snapshot where it no longer sits on the meadow floor."""
    from daydream import objects

    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial snapshot
            ws.send_json({"kind": "command", "verb": "take", "dobj_id": "i-lantern"})
            moved = ws.receive_json()  # object_moved event
            snap = ws.receive_json()  # refreshed snapshot
        # Still inside the TestClient lifespan -> the live DB is open.
        assert objects.get("i-lantern").location_id == "t-wren"
    assert moved["event"]["kind"] == "object_moved"
    assert snap["kind"] == "state_snapshot"
    assert not any(it["name"] == "lantern" for it in snap["items"])


def test_ws_command_examine_makes_no_llm_call():
    """SPEC: the UI command path bypasses the parser, so a deterministic verb
    issues ZERO LLM calls. examine echoes the cached seed sentinel directly."""
    spy = AsyncMock(return_value={})
    with patch("daydream.llm.client.acompletion_json", new=spy):
        with TestClient(app) as client:
            _login(client)
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # snapshot
                ws.send_json(
                    {"kind": "command", "verb": "examine", "dobj_id": "i-lantern"}
                )
                evt = ws.receive_json()
    assert evt["event"]["kind"] == "narrate"
    assert "hairline crack" in evt["event"]["payload"]["text"]
    spy.assert_not_called()


def test_ws_skills_include_go_navigation():
    """Criterion 2 corollary: the `go` skill is in the registry and
    therefore appears in the snapshot's skills list so the UI can
    route clicks (though nav clicks actually go through the exit-bar
    path, which sends `go <direction>` as input)."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    skill_names = {s["name"] for s in snap["skills"]}
    assert "go" in skill_names
