"""End-to-end WS integration for the `iris` NPC dialogue data skill.

Covers SPEC 2026-05-07 "Second NPC (Iris, the attic archivist)" —
criteria 2-4. skills/iris.json gives Iris a voice via the existing
data-skill pipeline (the same Option B: NPC-as-data-skill that Rook
uses). These tests mock the LLM for determinism; the prompt_template
in iris.json is voice-critical and is checked by inspection rather
than by these tests.

Mirrors tests/test_ws_rook.py's 7-test structure, with two changes:
the skill name, and the room (r-attic instead of r-forge). The
hidden-elsewhere test goes the other direction (iris hidden in the
meadow rather than rook hidden in the meadow) so the two NPCs'
scoping doesn't cross-pollute each other's coverage.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from daydream import admin, db, events
from daydream.server import app
from daydream.skills import registry

pytestmark = pytest.mark.tier_medium


IRIS_JSON = Path(__file__).resolve().parent.parent / "skills" / "iris.json"


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


def _walk_to_attic(ws) -> None:
    """Move the player from r-meadow → r-forge → r-attic, draining the
    snapshot + presence narrate events along the way. Leaves the WS
    ready to receive iris dispatch responses."""
    ws.receive_json()  # meadow snapshot
    ws.send_json({"kind": "input", "text": "go north"})
    ws.receive_json()  # move event meadow→forge
    ws.receive_json()  # forge snapshot
    ws.receive_json()  # rook presence narrate (migration 007)
    ws.send_json({"kind": "input", "text": "go up"})
    ws.receive_json()  # move event forge→attic
    ws.receive_json()  # attic snapshot
    ws.receive_json()  # iris presence narrate (migration 008)


# ---- criterion 2: install via the CLI -----------------------------------


def test_iris_json_installs_and_registry_sees_it():
    """The checked-in skills/iris.json must satisfy the CLI's validation
    gate, and the registry must see the installed row as a kind='data'
    skill. Regression guard: if the author file drifts out of the
    author-schema contract, this test fails."""
    with TestClient(app) as client:
        rc = admin.main(["skill", "add", str(IRIS_JSON)])
        assert rc == 0
        spec = registry.find("iris")
        assert spec is not None
        assert spec.kind == "data"
        assert spec.ui_hint == "Iris"
        assert "archivist" in spec.description.lower()


# ---- criterion 3 (happy path): end-to-end at r-attic --------------------


def test_iris_happy_path_at_r_attic():
    """At r-attic, `iris hello` dispatches through the data-skill
    pipeline; the (mocked) LLM returns one narrate effect, which
    reaches the client as a narrate event with the canned text.
    Also asserts that player_input was wrapped in role-separator
    tags."""
    canned = {
        "effects": [
            {"kind": "narrate",
             "text": "Iris lifts a folded letter to the slanting light, smooths the crease, and says, 'this one is from a town I have never been to.'"}
        ]
    }
    captured: dict = {}

    async def fake_llm(*, system: str, user: str, **kwargs):
        captured["user"] = user
        return canned

    with TestClient(app) as client:
        admin.main(["skill", "add", str(IRIS_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json", new=fake_llm):
            with client.websocket_connect("/ws") as ws:
                _walk_to_attic(ws)
                ws.send_json({"kind": "input", "text": "iris hello"})
                msg = ws.receive_json()
    assert msg["event"]["kind"] == "narrate"
    assert "town I have never been to" in msg["event"]["payload"]["text"]
    assert "<player_input>hello</player_input>" in captured["user"]


def test_iris_empty_input_still_dispatches():
    """`iris` with no args still routes: the template invites Iris to
    acknowledge the player. The canned LLM response stands in for
    Iris's silent acknowledgment."""
    canned = {
        "effects": [
            {"kind": "narrate", "text": "Iris looks up over the spectacles, smiles softly, and returns to her sorting."}
        ]
    }
    with TestClient(app) as client:
        admin.main(["skill", "add", str(IRIS_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=canned)):
            with client.websocket_connect("/ws") as ws:
                _walk_to_attic(ws)
                ws.send_json({"kind": "input", "text": "iris"})
                msg = ws.receive_json()
    assert msg["event"]["kind"] == "narrate"
    assert "spectacles" in msg["event"]["payload"]["text"]


# ---- criterion 3 (scoping): iris hidden outside r-attic ----------------


def test_iris_hidden_in_meadow():
    """At r-meadow, `iris hello` must NOT dispatch the iris skill
    (predicate scopes it to r-attic). The input falls through to the
    LLM interpreter, which with a canned `skill:none` response produces
    the chat-fallback narrate. Exactly one LLM call fires (the
    interpreter), NOT a second call for the iris skill itself."""
    interpreter_response = {"skill": "none", "args": "hello"}
    with TestClient(app) as client:
        admin.main(["skill", "add", str(IRIS_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=interpreter_response)) as mock_llm:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # meadow snapshot
                ws.send_json({"kind": "input", "text": "iris hello"})
                msg = ws.receive_json()
        assert msg["event"]["kind"] == "narrate"
        # The narrate is the chat fallback, not an iris-voice response.
        assert "iris" not in msg["event"]["payload"]["text"].lower() or \
               "you think to yourself" in msg["event"]["payload"]["text"].lower()
        # One LLM call = the interpreter. A second would mean the iris
        # skill dispatched in a room where its predicate hides it.
        assert mock_llm.call_count == 1


# ---- criterion 4: snapshot reflects iris co-location -------------------


def test_iris_in_attic_snapshot_skills_and_toons():
    """Snapshot at r-attic includes iris in the skills list (the SPA
    needs it to render the dialogue button) AND iris appears in the
    room's toons list with appearance + presence_text populated."""
    with TestClient(app) as client:
        admin.main(["skill", "add", str(IRIS_JSON)])
        _login(client)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # meadow snapshot
            ws.send_json({"kind": "input", "text": "go north"})
            ws.receive_json()  # move
            ws.receive_json()  # forge snapshot
            ws.receive_json()  # rook presence
            ws.send_json({"kind": "input", "text": "go up"})
            ws.receive_json()  # move
            attic_snap = ws.receive_json()
    assert attic_snap["room"]["slug"] == "attic"
    skill_names = [s["name"] for s in attic_snap["skills"]]
    assert "iris" in skill_names
    toon_names = [t["name"] for t in attic_snap["toons"]]
    assert "Iris" in toon_names
    iris_toon = next(t for t in attic_snap["toons"] if t["name"] == "Iris")
    # The snapshot exposes id/name/mood per daydream/api/ws.py's
    # current shape; presence_text fires as a separate narrate event
    # (verified implicitly by _walk_to_attic draining it from the WS
    # without the test deadlocking).
    assert iris_toon["id"] == "t-iris"
    assert iris_toon["mood"] == "thoughtful"


def test_iris_not_in_meadow_snapshot_skills_or_toons():
    """Companion to the hidden-in-meadow dispatch test: the snapshot
    `skills` list excludes iris in the meadow (no 'Iris' button on the
    SPA in a room without Iris), AND iris is NOT in the meadow's toons
    list (the controlled toon is at r-meadow; Iris stays at r-attic)."""
    with TestClient(app) as client:
        admin.main(["skill", "add", str(IRIS_JSON)])
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert snap["room"]["slug"] == "meadow"
    skill_names = [s["name"] for s in snap["skills"]]
    assert "iris" not in skill_names
    toon_names = [t["name"] for t in snap["toons"]]
    assert "Iris" not in toon_names


# ---- criterion 3 (safety): banlist + refusal short-circuits ------------


def test_iris_banned_input_short_circuits_before_llm():
    """A banlist hit in the player's args (e.g. 'pixel-art' — WHIMSY
    category 1) short-circuits to the BANNED fallback narrate; the LLM
    is never called. Standard data-skill input-banlist contract; this
    test pins it for the iris path as a regression guard."""
    with TestClient(app) as client:
        admin.main(["skill", "add", str(IRIS_JSON)])
        _login(client)
        mock_llm = AsyncMock()
        with patch("daydream.llm.client.acompletion_json", new=mock_llm):
            with client.websocket_connect("/ws") as ws:
                _walk_to_attic(ws)
                ws.send_json({"kind": "input", "text": "iris a pixel-art letter please"})
                msg = ws.receive_json()
        assert msg["event"]["kind"] == "narrate"
        # Safety fallback text contains "dream"; iris persona-voice would not.
        assert "dream" in msg["event"]["payload"]["text"].lower()
        mock_llm.assert_not_awaited()


def test_iris_refusal_short_circuits_effects():
    """Refusal schema ({"refused": true, "reason": "..."}) narrates
    the reason and drops any accompanying effects. Iris's authored
    prompt teaches this path for off-tone requests; the refusal
    handling itself is the standard data-skill contract."""
    refused = {
        "refused": True,
        "reason": "Iris simply smiles and lets the question pass like a moth through the window.",
        "effects": [
            {"kind": "narrate", "text": "this text should never reach the client"}
        ],
    }
    with TestClient(app) as client:
        admin.main(["skill", "add", str(IRIS_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=refused)):
            with client.websocket_connect("/ws") as ws:
                _walk_to_attic(ws)
                ws.send_json({"kind": "input", "text": "iris build me a flying machine"})
                msg = ws.receive_json()
    assert msg["event"]["kind"] == "narrate"
    text = msg["event"]["payload"]["text"]
    assert "moth" in text or "smiles" in text
    assert "should never reach" not in text
