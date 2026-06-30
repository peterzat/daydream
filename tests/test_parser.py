"""Grounded natural-language command parser (daydream/parser.py).

Covers the SPEC 2026-06-30 "structured command bus & local-LLM parser"
criteria with a MOCKED LLM: grounded NL parsing (say/talk/greet rook ->
talk(t-rook, "hi")), the deterministic fast-path (exit directions + bare verbs
-> zero LLM calls), malformed/unresolvable parses failing safe, and graceful
LLM-outage handling."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, parser
from daydream.llm import client

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    # Co-locate Wren with Rook in the forge so Rook is in scope for parsing.
    objects.move("t-wren", "r-forge")
    yield
    db.close_db()
    events.reset_subscribers()


def _mock_llm(monkeypatch, payload):
    spy = AsyncMock(return_value=payload)
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    return spy


# ---- grounded natural-language parsing ---------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["say hi to rook", "talk to rook", "greet rook"])
async def test_natural_phrasings_ground_to_talk_rook(monkeypatch, text):
    # The model returns the grounded command; the parser validates it against
    # the real in-scope id set.
    _mock_llm(monkeypatch, {"verb": "talk", "dobj_id": "t-rook", "iobj_id": None, "args": "hi"})
    p = await parser.parse("t-wren", text)
    assert p.verb == "talk"
    assert p.dobj_id == "t-rook"
    assert p.args == "hi"


@pytest.mark.asyncio
async def test_bare_say_resolves_without_target(monkeypatch):
    # "say hi" has free-text args, so it goes to the LLM (which has no target to
    # ground -> a plain say), not the fast-path; bare-with-target would become talk.
    _mock_llm(monkeypatch, {"verb": "say", "dobj_id": None, "iobj_id": None, "args": "hi"})
    p = await parser.parse("t-wren", "say hi")
    assert p.verb == "say"
    assert p.dobj_id is None
    assert p.args == "hi"


# ---- deterministic fast-path (zero LLM calls) --------------------------


@pytest.mark.asyncio
async def test_exit_direction_is_fast_path(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")  # meadow has exits north/east
    p = await parser.parse("t-wren", "north")
    assert p.verb == "go" and p.args == "north"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_bare_verb_is_fast_path(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "look")
    assert p.verb == "look"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_verb_plus_name_is_fast_path(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")  # the lantern is here
    p = await parser.parse("t-wren", "examine the lantern")
    assert p.verb == "examine" and p.dobj_id == "i-lantern"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_look_at_name_grounds_to_examine(monkeypatch):
    # "look at <name>" routes to examine the named in-scope object (a bare
    # `look` describes the room). Deterministic fast-path, zero LLM calls.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")  # the lantern is here
    p = await parser.parse("t-wren", "look at the lantern")
    assert p.verb == "examine" and p.dobj_id == "i-lantern"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_look_at_npc_grounds_to_examine(monkeypatch):
    # The fixture co-locates Wren with Rook in r-forge.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "look at rook")
    assert p.verb == "examine" and p.dobj_id == "t-rook"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_verb_plus_absent_name_passes_name_through(monkeypatch):
    # "take the moon": a known verb + a name not in scope. The fast-path passes
    # the (article-stripped) name through as dobj_name so the executor can say
    # "you don't see the moon here" -- no LLM call, no grounded id.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")
    p = await parser.parse("t-wren", "take the moon")
    assert p.verb == "take" and p.dobj_id is None and p.dobj_name == "moon"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_skill_name_is_fast_path(monkeypatch):
    # Install a room-affordance skill and confirm "<name> ..." fast-paths.
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES ('skill-forge', 'forge', 'data', '{}', '{{ player_input }}', "
        "'Forge', 'Forge a thing.', '{}', 1)"
    )
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "forge a ring")
    assert p.verb == "forge" and p.args == "a ring"
    spy.assert_not_called()


# ---- fail safe: malformed / unresolvable -------------------------------


@pytest.mark.asyncio
async def test_unknown_verb_grounds_to_none(monkeypatch):
    _mock_llm(monkeypatch, {"verb": "obliterate", "dobj_id": "t-rook", "args": ""})
    p = await parser.parse("t-wren", "obliterate rook")
    assert p.verb == "none"


@pytest.mark.asyncio
async def test_out_of_scope_object_grounds_to_none(monkeypatch):
    # The model hallucinated an id that isn't in scope -> fail safe.
    _mock_llm(monkeypatch, {"verb": "talk", "dobj_id": "t-ghost", "args": "hi"})
    p = await parser.parse("t-wren", "talk to the ghost")
    assert p.verb == "none"


@pytest.mark.asyncio
async def test_non_dict_llm_output_grounds_to_none(monkeypatch):
    _mock_llm(monkeypatch, ["not", "a", "dict"])
    p = await parser.parse("t-wren", "do something weird")
    assert p.verb == "none"


# ---- LLM outage --------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_outage_sets_error(monkeypatch):
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=client.LLMUnavailable("vllm down")),
    )
    p = await parser.parse("t-wren", "tell rook a long rambling story")
    assert p.verb == "none"
    assert p.error is not None


@pytest.mark.asyncio
async def test_outage_does_not_break_fast_path(monkeypatch):
    # Even with the LLM down, deterministic input still resolves (no call made).
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=client.LLMUnavailable("vllm down")),
    )
    objects.move("t-wren", "r-meadow")
    p = await parser.parse("t-wren", "north")
    assert p.verb == "go" and p.error is None
