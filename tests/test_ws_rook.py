"""End-to-end WS integration for the `rook` NPC dialogue data skill.

Covers SPEC 2026-04-24 "NPC dialogue (Rook speaks)" — criteria 1-5.
skills/rook.json gives Rook a voice via the existing data-skill
pipeline (Option B: NPC-as-data-skill). These tests mock the LLM for
determinism; the drift tier is where real-LLM voice behavior lives.
The prompt_template in rook.json is voice-critical; tests here pin
the protocol (install, routing, safety, refusal) rather than prose.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from daydream import admin, db, events, memories
from daydream.server import app
from daydream.skills import registry

pytestmark = pytest.mark.tier_medium


ROOK_JSON = Path(__file__).resolve().parent.parent / "skills" / "rook.json"


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


# ---- criterion 1: install via the CLI -----------------------------------


def test_rook_json_installs_and_registry_sees_it():
    """The checked-in skills/rook.json must satisfy the CLI's validation
    gate, and the registry must see the installed row as a kind='data'
    skill. Regression guard: if the author file drifts out of the
    author-schema contract, this test fails."""
    with TestClient(app) as client:
        rc = admin.main(["skill", "add", str(ROOK_JSON)])
        assert rc == 0
        spec = registry.find("rook")
        assert spec is not None
        assert spec.kind == "data"
        # ui_hint and description carry the authored intent into the
        # interpreter candidate list.
        assert spec.ui_hint == "Rook"
        assert "forge-keeper" in spec.description.lower()


# ---- criterion 2: happy path end-to-end at r-forge ----------------------


def test_rook_happy_path_at_r_forge():
    """At r-forge, `rook hello` dispatches through the data-skill
    pipeline; the (mocked) LLM returns one narrate effect, which
    reaches the client as a narrate event with the canned text.
    Also asserts that player_input was wrapped in role-separator
    tags (criterion 4's prompt-injection containment flowing through
    the authored template)."""
    canned = {
        "effects": [
            {"kind": "narrate",
             "text": "Rook looks up from the anvil, wipes their hands on the apron, and says, 'the embers are particular tonight.'"}
        ]
    }
    captured: dict = {}

    async def fake_llm(*, system: str, user: str, **kwargs):
        captured["user"] = user
        return canned

    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json", new=fake_llm):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # meadow snapshot
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move event
                ws.receive_json()  # forge snapshot
                ws.receive_json()  # Rook's presence narrate (prior spec)
                ws.send_json({"kind": "input", "text": "rook hello"})
                msg = ws.receive_json()
    assert msg["event"]["kind"] == "narrate"
    assert "embers are particular" in msg["event"]["payload"]["text"]
    # The player's text was wrapped before reaching the LLM.
    assert "<player_input>hello</player_input>" in captured["user"]


def test_rook_empty_input_still_dispatches():
    """`rook` with no args still routes: the template invites Rook to
    acknowledge the player's presence. The canned LLM response stands
    in for Rook's acknowledgment."""
    canned = {
        "effects": [
            {"kind": "narrate", "text": "Rook looks up, nods once, and goes back to the bellows."}
        ]
    }
    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=canned)):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move
                ws.receive_json()  # forge snapshot
                ws.receive_json()  # presence narrate
                ws.send_json({"kind": "input", "text": "rook"})
                msg = ws.receive_json()
    assert msg["event"]["kind"] == "narrate"
    assert "bellows" in msg["event"]["payload"]["text"]


# ---- criterion 3: hidden outside r-forge --------------------------------


def test_rook_hidden_in_meadow():
    """At r-meadow, `rook hello` must NOT dispatch the rook skill
    (predicate scopes it to r-forge). The input falls through to the
    LLM interpreter, which with a canned `skill:none` response produces
    the chat-fallback narrate. Exactly one LLM call fires — the
    interpreter — NOT a second call for the rook skill itself."""
    interpreter_response = {"skill": "none", "args": "hello"}
    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=interpreter_response)) as mock_llm:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # meadow snapshot
                ws.send_json({"kind": "input", "text": "rook hello"})
                msg = ws.receive_json()
        assert msg["event"]["kind"] == "narrate"
        # The narrate is the chat fallback, not a rook-voice response.
        # The literal text reads "You think to yourself: ..." per
        # daydream/api/ws._handle_input's chatter path.
        assert "rook" not in msg["event"]["payload"]["text"].lower() or \
               "you think to yourself" in msg["event"]["payload"]["text"].lower()
        # One LLM call = the interpreter. A second would mean the rook
        # skill dispatched in a room where its predicate hides it.
        assert mock_llm.call_count == 1


def test_rook_not_in_meadow_snapshot_skills():
    """Companion to the hidden-in-meadow dispatch test: the snapshot
    `skills` list also excludes rook in the meadow (the SPA would
    otherwise show a 'Rook' button in a room without Rook)."""
    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert snap["room"]["slug"] == "meadow"
    skill_names = [s["name"] for s in snap["skills"]]
    assert "rook" not in skill_names


# ---- criterion 4: safety baseline regression guards ---------------------


def test_rook_banned_input_short_circuits_before_llm():
    """A banlist hit in the player's args (e.g. 'pixel-art' —
    WHIMSY category 1) short-circuits to the fallback narrate; the
    LLM is never called. This is the standard data-skill input-banlist
    contract; criterion 4 pins it for the rook path as a regression
    guard."""
    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        mock_llm = AsyncMock()
        with patch("daydream.llm.client.acompletion_json", new=mock_llm):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move
                ws.receive_json()  # forge snapshot
                ws.receive_json()  # presence narrate
                ws.send_json({"kind": "input", "text": "rook a pixel-art knife please"})
                msg = ws.receive_json()
        assert msg["event"]["kind"] == "narrate"
        # The safety fallback text is "The dream won't hold that thought."
        # The rook persona-voice narration would not contain the word "dream".
        assert "dream" in msg["event"]["payload"]["text"].lower()
        # And the LLM was never called for the rook skill.
        mock_llm.assert_not_awaited()


def test_rook_refusal_short_circuits_effects():
    """Refusal schema ({"refused": true, "reason": "..."}) narrates
    the reason and drops any accompanying effects. Rook's authored
    prompt explicitly teaches this path for off-tone requests; the
    refusal handling itself is the standard data-skill contract."""
    refused = {
        "refused": True,
        "reason": "Rook just smiles, shakes their head, and goes back to the work.",
        "effects": [
            {"kind": "narrate", "text": "this text should never reach the client"}
        ],
    }
    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json",
                   new=AsyncMock(return_value=refused)):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move
                ws.receive_json()  # forge snapshot
                ws.receive_json()  # presence narrate
                ws.send_json({"kind": "input", "text": "rook a shield for a battle"})
                msg = ws.receive_json()
    assert msg["event"]["kind"] == "narrate"
    text = msg["event"]["payload"]["text"]
    assert "smiles" in text and "work" in text
    assert "should never reach" not in text


# ---- memory: capture on turn 1 surfaces in the prompt on turn 2 --------


def test_rook_dialogue_captures_and_recalls_memory(monkeypatch):
    """End-to-end memory loop: turn 1 dispatches Rook with mocked LLM
    output; turn 2's prompt to the LLM contains the memories block
    populated from turn 1's capture. This exercises the C4 wiring
    (data.py retrieve before render, capture after dispatch) and the
    C5 templates (memories block renders when present).

    The embedder is mocked so the test never loads BGE-small. The
    deterministic vector means the turn-2 query embeds to the same
    point as turn-1 captures, so cosine similarity is ~1.0 and both
    captured memories rank in the top-K."""
    monkeypatch.setenv("DAYDREAM_MEMORY_ENABLED", "1")

    same_vec = [1.0, 0.0]
    monkeypatch.setattr(memories, "_embed", lambda _t: list(same_vec))

    canned_turn1 = {
        "effects": [
            {"kind": "narrate",
             "text": "Rook lifts a forearm and brushes soot from the anvil's edge, and says, 'iron's a stubborn one today.'"}
        ]
    }
    canned_turn2 = {
        "effects": [
            {"kind": "narrate",
             "text": "Rook nods at a remembered something and says, 'and still warmer than yesterday.'"}
        ]
    }

    captured: list[str] = []

    async def fake_llm(*, system: str, user: str, **kwargs):
        captured.append(user)
        # Return turn1 first, turn2 next, in call order.
        return canned_turn1 if len(captured) == 1 else canned_turn2

    texts: list[str] = []
    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json", new=fake_llm):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # meadow snapshot
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()  # move
                ws.receive_json()  # forge snapshot
                ws.receive_json()  # presence narrate

                # Turn 1: input + Rook's response. Memory captures fire
                # after the WS handler returns; we drain the narrate
                # then assert the row count to confirm capture landed.
                ws.send_json({"kind": "input", "text": "rook hello"})
                ws.receive_json()  # turn-1 narrate

                # Turn 2: a different input. Retrieval should pull the
                # turn-1 memories and inject them into the prompt.
                ws.send_json({"kind": "input", "text": "rook how have you been"})
                ws.receive_json()  # turn-2 narrate
        # Inspect the memories table before the lifespan tears the DB
        # down. TestClient's __exit__ runs db.close_db(). Four rows:
        # two per turn (player input + Rook's narration), two turns.
        rows = db.get_conn().execute(
            "SELECT text FROM memories WHERE npc_id = 't-rook' AND world_id = 'w-bunny' "
            "ORDER BY id"
        ).fetchall()
        texts = [r["text"] for r in rows]
    assert len(texts) == 4
    assert "the visitor said: hello" in texts
    assert any("Rook said:" in t and "stubborn one today" in t for t in texts)
    assert "the visitor said: how have you been" in texts

    # Turn 2's prompt should contain the memories block populated from
    # turn 1. Assert at least one captured snippet reached the LLM.
    assert len(captured) == 2
    turn2_prompt = captured[1]
    assert "small recent moments" in turn2_prompt  # the prompt-template lead-in
    assert "the visitor said: hello" in turn2_prompt


def test_rook_memory_disabled_path_skips_capture(monkeypatch):
    """The default test path (DAYDREAM_MEMORY_ENABLED=0) MUST NOT
    capture: the memories table stays empty, the prompt has no
    memories block, and the turn-1 narrate reaches the client
    unchanged. Regression guard against the test conftest's opt-out
    silently leaking into a memory-on state."""
    canned = {
        "effects": [
            {"kind": "narrate",
             "text": "Rook hums and turns a half-finished hinge in the firelight, then says, 'good company tonight.'"}
        ]
    }
    seen: list[str] = []

    async def fake_llm(*, system: str, user: str, **kwargs):
        seen.append(user)
        return canned

    n = -1
    with TestClient(app) as client:
        admin.main(["skill", "add", str(ROOK_JSON)])
        _login(client)
        with patch("daydream.llm.client.acompletion_json", new=fake_llm):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "go north"})
                ws.receive_json()
                ws.receive_json()
                ws.receive_json()
                ws.send_json({"kind": "input", "text": "rook hello"})
                ws.receive_json()
        n = db.get_conn().execute("SELECT count(*) AS n FROM memories").fetchone()["n"]
    assert n == 0
    # The memories block lead-in is absent from the prompt.
    assert "small recent moments" not in seen[0]
