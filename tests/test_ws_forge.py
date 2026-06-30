"""End-to-end WS integration for the `forge` showcase data skill.

Covers SPEC criterion 2: skills/forge.json installs via the admin CLI,
appears in state_snapshot.skills only when the player is at r-forge,
and — when the player types `forge <something>` — dispatches through
the full safety + LLM + effects pipeline with a mocked LLM, producing
at least one effect beyond narrate (an item lands in the forge room).

The forge.json prompt_template is non-trivial (WHIMSY tone, refusal
guidance, role-separator contract); the LLM is mocked here for
determinism. The drift tier covers real-LLM behavior separately."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from daydream import admin, db, events, items
from daydream.server import app

pytestmark = pytest.mark.tier_medium


FORGE_JSON = Path(__file__).resolve().parent.parent / "skills" / "forge.json"


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _login(client: TestClient) -> None:
    """Log in and claim the seeded Wren (slot 1) as this session's toon.
    Picker-first entry (SPEC 2026-06-30) dropped the default-toon fallback,
    so a WS connection resolves a toon only when the session has claimed one.
    Kick-then-claim because the seed marks Wren human-controlled; the id stays
    `t-wren` so id-pinned assertions hold."""
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)
    assert client.post("/api/slots/1/kick").status_code == 200
    rc = client.post("/api/slots/1/claim")
    assert rc.status_code == 200 and rc.json()["id"] == "t-wren", rc.text


def test_forge_json_installs_from_authored_file():
    """The checked-in skills/forge.json must satisfy the CLI's
    validation gate. A regression here means the showcase file
    drifted out of the author-schema contract."""
    with TestClient(app):
        rc = admin.main(["skill", "add", str(FORGE_JSON)])
    assert rc == 0


def test_forge_absent_from_meadow_snapshot():
    """Context predicate gate: forge's predicate is
    {"room_slug": "forge"}; it must not appear in the meadow."""
    with TestClient(app) as client:
        admin.main(["skill", "add", str(FORGE_JSON)])
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert snap["room"]["slug"] == "meadow"
    skill_names = [s["name"] for s in snap["skills"]]
    assert "forge" not in skill_names


def test_forge_present_in_forge_snapshot_after_go_north():
    """After moving to r-forge, forge appears alongside core skills."""
    with TestClient(app) as client:
        admin.main(["skill", "add", str(FORGE_JSON)])
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # meadow snapshot
            ws.send_json({"kind": "input", "text": "go north"})
            ws.receive_json()  # move event
            forge_snap = ws.receive_json()  # refreshed snapshot
    assert forge_snap["room"]["slug"] == "forge"
    skill_names = [s["name"] for s in forge_snap["skills"]]
    assert "forge" in skill_names
    # Core skills still available too — data skills extend, don't replace.
    assert {"look", "say", "examine", "go"}.issubset(set(skill_names))


def test_forge_happy_path_end_to_end():
    """SPEC criterion 2 happy path: at r-forge, `forge a ring` dispatches
    through the pipeline, the (mocked) LLM returns narrate + add_item,
    both events fan out to the client, AND the broadcast loop re-pushes
    a state_snapshot after the mutation so the SPA's items panel
    reflects the new item without a navigation round-trip."""
    canned = {
        "effects": [
            {"kind": "narrate",
             "text": "The embers brighten; a small ring cools in your palm, warm and slightly uneven."},
            {"kind": "add_item",
             "name": "bronze ring",
             "seed": "a small bronze ring, warm from the embers, slightly uneven where the tongs held it"},
        ]
    }
    with TestClient(app) as client:
        admin.main(["skill", "add", str(FORGE_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=canned)):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # meadow snapshot
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move event
                ws.receive_json()  # forge snapshot (post-move)
                ws.receive_json()  # Rook presence narrate (2026-04-24 spec)
                ws.send_json({"kind": "input", "text": "forge a ring"})
                # The LLM returns narrate + add_item. The item_added
                # event triggers a fresh state_snapshot from the broadcast
                # loop so the SPA's items panel picks up the new item.
                # Criterion 3 regression guard: the mutation snapshot
                # refresh must NOT re-fire Rook's presence narrate;
                # a 4th message would indicate it did.
                msg_a = ws.receive_json()
                msg_b = ws.receive_json()
                msg_c = ws.receive_json()
        event_kinds = [msg_a["event"]["kind"], msg_b["event"]["kind"]]
        assert set(event_kinds) == {"narrate", "item_added"}
        # The narrate text is the forge's, not Rook's greeting.
        narrate_text = next(
            m["event"]["payload"]["text"]
            for m in (msg_a, msg_b)
            if m["event"]["kind"] == "narrate"
        )
        assert "embers" in narrate_text.lower() or "ring" in narrate_text.lower()
        assert "bellows" not in narrate_text.lower()  # not Rook's greeting
        assert msg_c["kind"] == "state_snapshot"
        # The refreshed snapshot includes the freshly-forged item.
        snap_names = {it["name"] for it in msg_c["items"]}
        assert "bronze ring" in snap_names
        # And the DB reflects the same truth (belt + suspenders).
        names = {i.name for i in items.get_items_in_room("r-forge")}
        assert "bronze ring" in names


def test_forge_does_not_dispatch_in_wrong_room():
    """Defensive: a player at r-meadow who types `forge a ring` must NOT
    dispatch the forge data skill (its predicate scopes it to r-forge).
    The bypass uses the room-filtered candidate list, so it sees no
    match; input falls through to the interpreter with core-only
    candidates. The interpreter returns 'none'; the player sees the
    chat-fallback narrate. Critically, the forge skill's own LLM call
    never happens — only the interpreter's single round-trip."""
    interpreter_response = {"skill": "none", "args": "forge a ring"}
    with TestClient(app) as client:
        admin.main(["skill", "add", str(FORGE_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=interpreter_response)) as mock_llm:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # meadow snapshot
                ws.send_json({"kind": "input", "text": "forge a ring"})
                msg = ws.receive_json()
        assert msg["event"]["kind"] == "narrate"
        # No item was forged — the forge skill was never dispatched.
        names = {i.name for i in items.get_items_in_room("r-forge")}
        assert "bronze ring" not in names
        # Exactly one LLM call: the interpreter. A second call would
        # indicate the forge skill ran after the bypass misrouted.
        assert mock_llm.call_count == 1


def test_forge_set_mood_refreshes_snapshot_with_new_mood():
    """Parallel to the add_item path: a mood_set effect should also
    trigger a snapshot refresh so the SPA's toons panel picks up the
    new mood without a navigation round-trip."""
    canned = {"effects": [{"kind": "set_mood", "mood": "kindled"}]}
    with TestClient(app) as client:
        admin.main(["skill", "add", str(FORGE_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=canned)):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # meadow snapshot
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move event
                ws.receive_json()  # forge snapshot
                ws.receive_json()  # Rook presence narrate (2026-04-24 spec)
                ws.send_json({"kind": "input", "text": "forge a thing"})
                mood_msg = ws.receive_json()
                snap = ws.receive_json()
    assert mood_msg["event"]["kind"] == "mood_set"
    assert snap["kind"] == "state_snapshot"
    wren = next((t for t in snap["toons"] if t["name"] == "Wren"), None)
    assert wren is not None and wren["mood"] == "kindled"


def test_forge_refusal_short_circuits_effects():
    """The LLM can refuse; the player sees a narrate with the reason, and
    no items are forged."""
    refused = {
        "refused": True,
        "reason": "the forge is too cool for that tonight",
        "effects": [{"kind": "add_item", "name": "should-not-appear", "seed": "x"}],
    }
    with TestClient(app) as client:
        admin.main(["skill", "add", str(FORGE_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=refused)):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move
                ws.receive_json()  # forge snapshot
                ws.receive_json()  # Rook presence narrate (2026-04-24 spec)
                ws.send_json({"kind": "input", "text": "forge something"})
                msg = ws.receive_json()
        assert msg["event"]["kind"] == "narrate"
        assert "cool" in msg["event"]["payload"]["text"]
        names = {i.name for i in items.get_items_in_room("r-forge")}
        assert "should-not-appear" not in names
