"""ComfyUI client: workflow loading, prompt substitution, mocked end-to-end
flow, error wrapping. No real ComfyUI required; httpx calls are patched."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from daydream.images import cache, client


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


# ---- workflow loading ---------------------------------------------------


def test_workflow_file_exists_and_parses():
    raw = json.loads(client.DEFAULT_WORKFLOW.read_text())
    assert isinstance(raw, dict)
    # Strip _meta to mirror what load_workflow() sends to ComfyUI
    wf = {k: v for k, v in raw.items() if not k.startswith("_")}
    assert client.POSITIVE_PROMPT_NODE in wf


def test_load_workflow_strips_meta():
    wf = client.load_workflow()
    assert "_meta" not in wf
    # All remaining keys are node ids with class_type
    for k, v in wf.items():
        assert "class_type" in v


def test_workflow_has_required_nodes():
    wf = client.load_workflow()
    class_types = {n["class_type"] for n in wf.values()}
    expected = {
        "CheckpointLoaderSimple",
        "LoraLoader",
        "CLIPTextEncode",
        "EmptyLatentImage",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    }
    assert expected.issubset(class_types), f"missing: {expected - class_types}"


# ---- prompt substitution -----------------------------------------------


def test_build_prompt_workflow_sets_positive_text():
    wf = client.load_workflow()
    out = client.build_prompt_workflow(wf, "a quiet meadow at dusk", seed=42)
    assert out[client.POSITIVE_PROMPT_NODE]["inputs"]["text"] == "a quiet meadow at dusk"


def test_build_prompt_workflow_pins_ksampler_seed():
    wf = client.load_workflow()
    out = client.build_prompt_workflow(wf, "anything", seed=12345)
    ksamplers = [n for n in out.values() if n.get("class_type") == "KSampler"]
    assert ksamplers
    assert all(n["inputs"]["seed"] == 12345 for n in ksamplers)


def test_build_prompt_workflow_does_not_mutate_input():
    wf = client.load_workflow()
    original_text = wf[client.POSITIVE_PROMPT_NODE]["inputs"]["text"]
    client.build_prompt_workflow(wf, "different text", seed=0)
    assert wf[client.POSITIVE_PROMPT_NODE]["inputs"]["text"] == original_text


def test_build_prompt_workflow_rejects_missing_node():
    bad = {"99": {"class_type": "Foo", "inputs": {}}}
    with pytest.raises(client.ComfyUIError, match="missing positive-prompt"):
        client.build_prompt_workflow(bad, "x")


# ---- submit_and_wait (mocked HTTP) -------------------------------------


def _mock_http_response(json_data, status_code=200):
    r = MagicMock()
    r.json.return_value = json_data
    r.status_code = status_code
    r.raise_for_status = MagicMock()
    return r


@pytest.mark.asyncio
async def test_submit_and_wait_returns_history_entry():
    submit_resp = _mock_http_response({"prompt_id": "abc"})
    history_resp = _mock_http_response({"abc": {"outputs": {"8": {"images": [{"filename": "x.png"}]}}}})

    async def fake_post(*a, **kw):
        return submit_resp

    async def fake_get(*a, **kw):
        return history_resp

    with patch("httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.post = AsyncMock(side_effect=fake_post)
        instance.get = AsyncMock(side_effect=fake_get)
        result = await client.submit_and_wait({"1": {}}, timeout=2.0, poll_interval=0.01)
    assert "outputs" in result


@pytest.mark.asyncio
async def test_submit_and_wait_times_out():
    submit_resp = _mock_http_response({"prompt_id": "abc"})
    # /history returns empty dict forever
    history_resp = _mock_http_response({})

    with patch("httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=submit_resp)
        instance.get = AsyncMock(return_value=history_resp)
        with pytest.raises(client.ComfyUIError, match="did not finish"):
            await client.submit_and_wait({"1": {}}, timeout=0.2, poll_interval=0.05)


@pytest.mark.asyncio
async def test_submit_and_wait_wraps_http_error():
    with patch("httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(client.ComfyUIError, match="HTTP error"):
            await client.submit_and_wait({"1": {}})


# ---- fetch_output_image (mocked HTTP) ----------------------------------


@pytest.mark.asyncio
async def test_fetch_output_image_returns_bytes():
    history = {"outputs": {"8": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}}}
    img_resp = MagicMock()
    img_resp.content = b"\x89PNG\r\n\x1a\nfake-bytes"
    img_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=img_resp)
        out = await client.fetch_output_image(history)
    assert out == b"\x89PNG\r\n\x1a\nfake-bytes"


@pytest.mark.asyncio
async def test_fetch_output_image_raises_on_no_images():
    with pytest.raises(client.ComfyUIError, match="no images"):
        await client.fetch_output_image({"outputs": {}})


# ---- generate_room_background end-to-end (mocked) ----------------------


@pytest.mark.asyncio
async def test_generate_room_background_writes_to_cache_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))

    fake_history = {"outputs": {"8": {"images": [{"filename": "x.png"}]}}}
    fake_bytes = b"\x89PNG\r\n\x1a\nfake-image-bytes-here"

    with (
        patch.object(client, "submit_and_wait", new=AsyncMock(return_value=fake_history)),
        patch.object(client, "fetch_output_image", new=AsyncMock(return_value=fake_bytes)),
    ):
        out = await client.generate_room_background("w-1", "r-1", "a meadow at dusk")

    assert out.exists()
    assert out.read_bytes() == fake_bytes
    assert out == cache.cache_path("w-1", "r-1", "a meadow at dusk")


@pytest.mark.asyncio
async def test_generate_room_background_short_circuits_on_cache_hit(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    p = cache.cache_path("w-1", "r-1", "seed")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"already cached")

    submit = AsyncMock()
    fetch = AsyncMock()
    with patch.object(client, "submit_and_wait", new=submit), patch.object(client, "fetch_output_image", new=fetch):
        out = await client.generate_room_background("w-1", "r-1", "seed")

    assert out.read_bytes() == b"already cached"
    submit.assert_not_awaited()
    fetch.assert_not_awaited()
