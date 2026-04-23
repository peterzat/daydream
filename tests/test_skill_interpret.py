"""LLM-driven skill interpreter: routing, none fallback, graceful failure.

Covers SPEC criteria 6 (route 'look around' to look skill, route 'sing a song'
to none) and 7 (LLM-down produces a graceful fallback rather than crashing).
All tests mock the LLM client so no GPU or network is required."""

from unittest.mock import AsyncMock, patch

import pytest

from daydream.llm import client
from daydream.skills import interpreter, registry

pytestmark = pytest.mark.tier_short


def _available():
    return registry.list_available_for_room("r-meadow")


@pytest.mark.asyncio
async def test_interpret_routes_known_skill():
    canned = {"skill": "look", "args": "around"}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        result = await interpreter.interpret("look around", _available())
    assert result.skill == "look"
    assert result.args == "around"
    assert result.error is None


@pytest.mark.asyncio
async def test_interpret_returns_none_for_chatter():
    canned = {"skill": "none", "args": ""}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        result = await interpreter.interpret("sing a song", _available())
    assert result.skill == "none"
    assert result.error is None


@pytest.mark.asyncio
async def test_interpret_normalizes_hallucinated_skill_to_none():
    """The LLM might hallucinate a skill name not in the registry. The
    interpreter must reject it rather than dispatching to a phantom."""
    canned = {"skill": "fly", "args": "to the moon"}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        result = await interpreter.interpret("fly to the moon", _available())
    assert result.skill == "none"


@pytest.mark.asyncio
async def test_interpret_handles_llm_unavailable():
    """SPEC criterion 7: LLM down -> graceful 'none' with error set, so the
    caller narrates a 'foggy' fallback rather than crashing the websocket."""
    with patch(
        "daydream.llm.client.acompletion_json",
        new=AsyncMock(side_effect=client.LLMUnavailable("vLLM unreachable")),
    ):
        result = await interpreter.interpret("look around", _available())
    assert result.skill == "none"
    assert result.error is not None
    assert "unreachable" in result.error


@pytest.mark.asyncio
async def test_interpret_empty_input_short_circuits():
    """Empty input never hits the LLM."""
    not_called = AsyncMock()
    with patch("daydream.llm.client.acompletion_json", new=not_called):
        result = await interpreter.interpret("   ", _available())
    assert result.skill == "none"
    not_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_interpret_case_insensitive_skill_name():
    """LLM might return 'LOOK' instead of 'look'; interpreter normalizes."""
    canned = {"skill": "LOOK", "args": ""}
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        result = await interpreter.interpret("look", _available())
    assert result.skill == "look"


@pytest.mark.asyncio
async def test_interpret_missing_fields_in_response():
    """LLM might omit a field; treat as none rather than crash."""
    canned = {"args": "some text"}  # no 'skill' key
    with patch("daydream.llm.client.acompletion_json", new=AsyncMock(return_value=canned)):
        result = await interpreter.interpret("hello", _available())
    assert result.skill == "none"
