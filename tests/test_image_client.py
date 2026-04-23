"""ComfyUI client: workflow loading, prompt substitution, mocked end-to-end
flow, error wrapping. No real ComfyUI required; httpx calls are patched.

The end-to-end recording tests for generate_image live in test_assets.py
(they exercise the persistent path's interaction with the DB). This file
covers the workflow plumbing and ComfyUI HTTP layer."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from daydream.images import client


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


# ---- workflow loading ---------------------------------------------------


def test_workflow_file_exists_and_parses():
    raw = json.loads(client.DEFAULT_WORKFLOW.read_text())
    assert isinstance(raw, dict)
    wf = {k: v for k, v in raw.items() if not k.startswith("_")}
    assert client.POSITIVE_PROMPT_NODE in wf


def test_load_workflow_strips_meta():
    wf = client.load_workflow()
    assert "_meta" not in wf
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


# ---- override application ----------------------------------------------


def test_apply_overrides_swaps_model_and_lora():
    wf = client.load_workflow()
    out = client._apply_overrides(wf, model="custom.safetensors", lora="custom_lora.safetensors")
    assert out[client.CHECKPOINT_NODE]["inputs"]["ckpt_name"] == "custom.safetensors"
    assert out[client.LORA_NODE]["inputs"]["lora_name"] == "custom_lora.safetensors"


def test_apply_overrides_preserves_input_when_none():
    wf = client.load_workflow()
    original_ckpt = wf[client.CHECKPOINT_NODE]["inputs"]["ckpt_name"]
    out = client._apply_overrides(wf, model=None, lora=None)
    assert out[client.CHECKPOINT_NODE]["inputs"]["ckpt_name"] == original_ckpt


# ---- ephemeral_path -----------------------------------------------------


def test_ephemeral_path_is_deterministic():
    p1 = client.ephemeral_path("a quiet meadow", "a quiet meadow soft watercolor")
    p2 = client.ephemeral_path("a quiet meadow", "a quiet meadow soft watercolor")
    assert p1 == p2


def test_ephemeral_path_changes_with_prompt():
    p1 = client.ephemeral_path("name", "prompt one")
    p2 = client.ephemeral_path("name", "prompt two")
    assert p1 != p2


def test_ephemeral_path_includes_name_slug():
    p = client.ephemeral_path("a quiet meadow", "anything")
    assert "quiet" in p.name or "meadow" in p.name
    assert p.suffix == ".png"


def test_ephemeral_path_handles_long_or_messy_names():
    p = client.ephemeral_path("x" * 200 + " ! @ # $ %", "any")
    assert p.suffix == ".png"
    assert len(p.name) < 100


def test_ephemeral_path_lives_under_images_ephemeral():
    p = client.ephemeral_path("x", "y")
    assert "ephemeral" in p.parts


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
