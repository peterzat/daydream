"""Websocket: auth gate, state_snapshot, input dispatch (canonical + LLM).

SPEC criteria 4 (websocket protocol) and parts of 5 (skills end to end via WS).
LLM tests mock daydream.llm.client.acompletion_json so no GPU needed."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from daydream import db, events, toons
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


def _login_only(client: TestClient) -> None:
    # TestClient follows the 303 to / by default, so accept either status.
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303), f"login failed: {r.status_code} {r.text}"


def _claim_wren(client: TestClient) -> None:
    """Bind the seeded Wren (slot 1) to the caller's session, keeping its
    literal `t-wren` id so id-pinned assertions hold. The seed marks Wren
    human-controlled, so adopting it requires a prior kick (rest)."""
    assert client.post("/api/slots/1/kick").status_code == 200
    r = client.post("/api/slots/1/claim")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "t-wren"


def _login(client: TestClient) -> None:
    """Log in AND claim the seeded Wren as this session's controlled toon.

    Picker-first entry (SPEC 2026-06-30) removed the legacy auto-control of a
    default toon, so a WS connection resolves a toon only when the session has
    claimed one. Most WS tests act as Wren, so the default login helper claims
    it (preserving the `t-wren` id). Tests that need an unclaimed session
    (picker routing) or create their own toon use `_login_only`."""
    _login_only(client)
    _claim_wren(client)


def test_ws_unauthed_is_rejected():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()


def test_ws_rejects_cross_origin_handshake():
    """The /ws handshake is rejected when a browser sends a cross-origin Origin
    (defense in depth for the state-changing WS channel, since the HTTP-only CSRF
    middleware doesn't gate the GET upgrade). Non-browser clients with no Origin
    still connect -- covered by the other ws tests."""
    with TestClient(app) as client:
        _login(client)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws", headers={"origin": "http://evil.example"}
            ) as ws:
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


def test_ws_snapshot_carries_build_and_world_version():
    """The snapshot carries the server build SHA + WORLD_VERSION so the SPA can
    detect a redeploy under an open tab (stale JS) and reload (web/assets/main.js)."""
    from daydream import version

    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["kind"] == "state_snapshot"
    assert msg["build"] == version.build_sha()
    assert msg["world_version"] == version.WORLD_VERSION


def _two_sessions(client: TestClient) -> tuple[str, str]:
    """Two distinct authed sessions on ONE TestClient (one event loop — the
    in-process pub-sub requires it): session A claims the seeded Wren, session
    B creates Pip in slot 2. Returns their raw session-cookie values; pass
    them as explicit Cookie headers on websocket_connect."""
    _login(client)  # session A claims Wren
    wren_cookie = client.cookies["daydream_session"]
    client.cookies.delete("daydream_session")
    _login_only(client)  # fresh session B
    r = client.post(
        "/api/slots/2/create",
        json={"name": "Pip", "appearance_seed": "a quiet second dreamer"},
    )
    assert r.status_code == 200, r.text
    pip_cookie = client.cookies["daydream_session"]
    client.cookies.delete("daydream_session")  # sockets carry cookies explicitly
    return wren_cookie, pip_cookie


def test_ws_private_events_reach_only_the_actor():
    """Actor-private routing (migration 014, SPEC 2026-07-02 criterion 12):
    one player's `look` self-narration reaches their own log and NOT a
    co-located player's; broadcast events (`say`) still reach both."""
    with TestClient(app) as client:
        wren_cookie, pip_cookie = _two_sessions(client)
        with client.websocket_connect(
            "/ws", headers={"cookie": f"daydream_session={wren_cookie}"}
        ) as wren_ws, client.websocket_connect(
            "/ws", headers={"cookie": f"daydream_session={pip_cookie}"}
        ) as pip_ws:
            assert wren_ws.receive_json()["kind"] == "state_snapshot"
            assert pip_ws.receive_json()["kind"] == "state_snapshot"
            # Wren looks: private. Then Wren says: broadcast. Pip must see
            # ONLY the say — if the look leaked, it would arrive first.
            wren_ws.send_json({"kind": "command", "verb": "look"})
            wren_look = wren_ws.receive_json()
            assert wren_look["kind"] == "event"
            assert wren_look["event"]["kind"] == "narrate"
            assert "meadow" in wren_look["event"]["payload"]["text"].lower()
            wren_ws.send_json({"kind": "command", "verb": "say", "args": "hello"})
            pip_first = pip_ws.receive_json()
            assert pip_first["kind"] == "event"
            assert pip_first["event"]["kind"] == "say"
            assert pip_first["event"]["payload"]["text"] == "hello"


def test_ws_reconnect_replay_excludes_others_private_events():
    """The `since` replay path applies the same recipient filter as live
    delivery: another player's private look never appears in your replayed
    history, while broadcast events do."""
    with TestClient(app) as client:
        wren_cookie, pip_cookie = _two_sessions(client)
        with client.websocket_connect(
            "/ws", headers={"cookie": f"daydream_session={wren_cookie}"}
        ) as wren_ws:
            assert wren_ws.receive_json()["kind"] == "state_snapshot"
            wren_ws.send_json({"kind": "command", "verb": "look"})
            assert wren_ws.receive_json()["event"]["kind"] == "narrate"
            wren_ws.send_json({"kind": "command", "verb": "say", "args": "marco"})
            assert wren_ws.receive_json()["event"]["kind"] == "say"
        # Pip reconnects with since=0: replay carries the say, not the look.
        with client.websocket_connect(
            "/ws?since=0", headers={"cookie": f"daydream_session={pip_cookie}"}
        ) as pip_ws:
            snap = pip_ws.receive_json()
        kinds = [e["kind"] for e in snap["events"]]
        texts = [e["payload"].get("text", "") for e in snap["events"]]
        assert "say" in kinds
        assert not any("meadow" in t.lower() for t in texts)


def test_ws_container_contents_nest_and_reveal_live():
    """Criterion 4 over the wire: a closed opaque container renders
    childless; the `open` click reveals its nested contents in a fresh
    snapshot on the SAME connection (no reconnect)."""
    from daydream import objects

    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
            assert snap["kind"] == "state_snapshot"
            objects.spawn(
                "w-bunny", "thing", "sack", "r-meadow",
                prototype_id=objects.PROTO_THING,
                properties={"container": True, "state": "closed",
                            "verbs": ["open", "close"]},
                object_id="o-sack",
            )
            objects.spawn("w-bunny", "thing", "garlic", "o-sack",
                          prototype_id=objects.PROTO_THING, object_id="o-garlic")
            ws.send_json({"kind": "command", "verb": "look"})  # any event flows
            ws.receive_json()
            ws.send_json({"kind": "command", "verb": "open", "dobj_id": "o-sack"})
            # property_set(state) triggers a re-snapshot; drain frames until
            # it arrives, then check nesting.
            for _ in range(8):
                msg = ws.receive_json()
                if msg["kind"] == "state_snapshot":
                    break
            else:
                pytest.fail("no refreshed snapshot after open")
            sack_card = next(it for it in msg["items"] if it["id"] == "o-sack")
            assert [c["id"] for c in sack_card.get("contents", [])] == ["o-garlic"]


def test_ws_snapshot_carries_world_status():
    """The snapshot carries the world-shared status block (score / rank /
    moves / deaths / lit) from the world_state KV; a world with no authored
    scoring reports zeros and a null rank."""
    with TestClient(app) as client:
        _login(client)
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["kind"] == "state_snapshot"
    assert msg["status"] == {
        "score": 0, "rank": None, "moves": 0, "deaths": 0, "lit": True,
    }


def test_session_liveness_refcounts_multiple_connections():
    """A session with two live WS connections (two tabs on one toon) stays live
    until BOTH close -- is_session_live is backed by a Counter, not a set, so one
    tab closing doesn't free a toon the other tab is still playing."""
    from daydream.api import ws

    ws._live_session_counts.clear()
    try:
        assert ws.is_session_live("s1") is False
        ws._mark_session_live("s1")
        ws._mark_session_live("s1")  # second tab, same session
        assert ws.is_session_live("s1") is True
        ws._unmark_session_live("s1")  # one tab closes
        assert ws.is_session_live("s1") is True  # the other tab is still live
        ws._unmark_session_live("s1")  # second tab closes
        assert ws.is_session_live("s1") is False
        assert "s1" not in ws._live_session_counts  # no zero-count leak
    finally:
        ws._live_session_counts.clear()


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
    """After creating a toon in a slot, the WS resolves the controlled toon
    to that slot's toon. Subsequent input events have actor_id matching the
    created toon (not a default toon — picker-first entry has no fallback)."""
    with TestClient(app) as client:
        _login_only(client)
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


def test_ws_unclaimed_session_routes_to_picker():
    """Picker-first entry (SPEC 2026-06-30): a session that hasn't claimed a
    slot receives a `needs_toon` frame instead of auto-controlling a default
    toon. The legacy `t-wren` fallback is removed, so no input ever silently
    no-ops for lack of a resolved actor."""
    with TestClient(app) as client:
        _login_only(client)
        # Do NOT claim a slot.
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json() == {"kind": "needs_toon"}


def _load_bunny_world(tmp_path, monkeypatch) -> None:
    """Build the canonical reset world (worlds/bunny.json: uuid'd toon ids, no
    literal `t-wren`) as the live DB under a fresh tmp data dir. The next
    TestClient lifespan opens it (migrations already applied -> no reseed)."""
    import json

    from daydream import config
    from daydream.llm import bootstrap

    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    live = config.live_db_path()
    live.parent.mkdir(parents=True, exist_ok=True)
    envelope = json.loads(
        (Path(__file__).resolve().parent.parent / "worlds" / "bunny.json").read_text()
    )
    bootstrap.load_world("bunny world", envelope, live)
    db.close_db()


def test_picker_first_in_world_loaded_world(tmp_path, monkeypatch):
    """C1 canonical (SPEC 2026-06-30): against a `world load`ed world (uuid'd
    toon ids, no literal `t-wren`), an unclaimed session routes to the picker,
    and a created toon enters the dream and acts ("go north" moves). This is
    the production world shape where the removed `t-wren` fallback used to
    resolve a phantom that no-op'd every input."""
    _load_bunny_world(tmp_path, monkeypatch)
    with TestClient(app) as client:
        # A loaded world has uuid toon ids; the literal seed id does not exist.
        assert toons.get_toon("t-wren") is None
        _login_only(client)
        # Unclaimed session -> picker, never a phantom toon.
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json() == {"kind": "needs_toon"}
        # Create a toon (slot 2 is empty in bunny.json) -> a uuid id, not t-wren.
        r = client.post(
            "/api/slots/2/create", json={"name": "Fern", "appearance_seed": "a wisp of dusk"}
        )
        assert r.status_code == 200, r.text
        created_id = r.json()["id"]
        assert created_id and created_id != "t-wren"
        # Now the session enters the dream and "go north" actually moves.
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
            assert snap["kind"] == "state_snapshot"
            assert snap["room"]["slug"] == "meadow"
            ws.send_json({"kind": "input", "text": "go north"})
            move = ws.receive_json()
        assert move["event"]["kind"] == "move"
        assert move["event"]["actor_id"] == created_id


def test_ws_say_attributes_by_name_not_id(tmp_path, monkeypatch):
    """C2 (SPEC 2026-06-30): in a `world load`ed world (uuid'd toon ids), a
    `say` carries the speaker's display NAME in its payload and the speaker's
    raw id appears nowhere in the event — so the client attributes by name,
    never by a leaked id (the playtest's `iris-ed7…` regression class)."""
    _load_bunny_world(tmp_path, monkeypatch)
    with TestClient(app) as client:
        _login_only(client)
        r = client.post(
            "/api/slots/2/create", json={"name": "Fern", "appearance_seed": "a wisp"}
        )
        assert r.status_code == 200, r.text
        created_id = r.json()["id"]
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"kind": "input", "text": "say hello there"})
            evt = ws.receive_json()
    assert evt["event"]["kind"] == "say"
    assert evt["event"]["payload"]["name"] == "Fern"
    assert evt["event"]["payload"]["text"] == "hello there"
    # The raw toon id leaks nowhere in the say payload (name or text).
    assert created_id not in str(evt["event"]["payload"])


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
    assert lantern["verbs"] == ["examine", "take", "drop", "put"]
    # The verb bar is scene-aware (playtest 2026-07-02): the stable core
    # first, then only what the present objects grant. This room holds one
    # lantern and no one else: give needs a recipient, put a container,
    # plant a seed, talk a toon — none apply, so the bar is exactly the
    # core. (Presence cases are unit-tested in test_verbs.py.)
    names = [v["name"] for v in snap["verb_bar"]]
    assert names == ["examine", "take", "drop"]
    bar = {v["name"]: v for v in snap["verb_bar"]}
    assert bar["take"]["needs_iobj"] is False and bar["take"]["valid_iobj_kinds"] == []
    # Inventory starts empty; the entity sidecar maps the lantern's name -> id.
    assert snap["inventory"] == []
    assert any(
        e["alias"].lower() == "lantern" and e["object_id"] == "i-lantern"
        for e in snap["entities"]
    )


@pytest.mark.asyncio
async def test_command_frame_forwards_iobj_to_executor(monkeypatch):
    """C6 (SPEC 2026-07-01): a two-object command frame (the click path for
    give/use) reaches execute_command with BOTH the dobj and the iobj id."""
    from daydream.api import ws

    spy = AsyncMock()
    monkeypatch.setattr("daydream.verbs.execute_command", spy)
    await ws._handle_command(
        {"kind": "command", "verb": "give", "dobj_id": "o-gear",
         "iobj_id": "t-tace", "args": ""},
        "t-actor",
    )
    spy.assert_awaited_once()
    _, kwargs = spy.call_args
    assert kwargs.get("dobj_id") == "o-gear"
    assert kwargs.get("iobj_id") == "t-tace"


def test_ws_snapshot_carries_self_identity():
    """C3 (SPEC 2026-06-30): the snapshot names the controlled toon (WHO YOU
    ARE) so the SPA renders it distinctly and separates it from co-located
    toons. Self is also present in the inclusive `toons` list (client filters)."""
    with TestClient(app) as client:
        _login(client)  # claims Wren
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert snap["self"] is not None
    assert snap["self"]["id"] == "t-wren"
    assert snap["self"]["name"] == "Wren"
    assert any(t["id"] == "t-wren" for t in snap["toons"])


def test_ws_inventory_command_reports_carried_and_empty():
    """C4 (SPEC 2026-06-30): the `inventory` command lists carried things and
    says so when empty, end to end over the WS (deterministic fast-path, no
    LLM)."""
    with TestClient(app) as client:
        _login(client)  # claims Wren at the meadow, empty-handed
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"kind": "input", "text": "inventory"})
            empty = ws.receive_json()
            ws.send_json({"kind": "command", "verb": "take", "dobj_id": "i-lantern"})
            ws.receive_json()  # object_moved
            ws.receive_json()  # snapshot refresh
            ws.send_json({"kind": "input", "text": "inventory"})
            full = ws.receive_json()
    assert empty["event"]["kind"] == "narrate"
    assert "carrying nothing" in empty["event"]["payload"]["text"].lower()
    assert "lantern" in full["event"]["payload"]["text"].lower()


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
