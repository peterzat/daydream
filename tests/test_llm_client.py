"""LLM client: JSON completion wrapper, error wrapping. All tests mock
litellm.acompletion so the test suite never touches GPU or network."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daydream.llm import client


@pytest.mark.asyncio
async def test_acompletion_json_happy_path():
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"skill": "look", "args": ""}'))
    ]
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        result = await client.acompletion_json("sys", "usr")
    assert result == {"skill": "look", "args": ""}


@pytest.mark.asyncio
async def test_acompletion_json_wraps_litellm_exception():
    with patch(
        "litellm.acompletion",
        new=AsyncMock(side_effect=ConnectionError("boom")),
    ):
        with pytest.raises(client.LLMUnavailable, match="LLM call failed"):
            await client.acompletion_json("sys", "usr")


@pytest.mark.asyncio
async def test_acompletion_json_wraps_non_json():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="not valid json at all"))]
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        with pytest.raises(client.LLMUnavailable, match="non-JSON"):
            await client.acompletion_json("sys", "usr")


@pytest.mark.asyncio
async def test_acompletion_json_wraps_no_message():
    mock_response = MagicMock()
    mock_response.choices = []
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        with pytest.raises(client.LLMUnavailable, match="no message"):
            await client.acompletion_json("sys", "usr")


@pytest.mark.asyncio
async def test_acompletion_json_wraps_empty_message_content():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=None))]
    with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        with pytest.raises(client.LLMUnavailable, match="non-JSON"):
            await client.acompletion_json("sys", "usr")
