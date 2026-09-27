"""The seam for remote reflexes (SPEC 2026-09-27 criterion 23): choosing the
LLM or image backend is configuration; the local default changes no cache
key; the GPU arbiter gates only local backends. The shipped runtime stays
local-only (tests/test_no_cloud_keys.py); nothing here calls a cloud."""

import json
from unittest.mock import AsyncMock

import pytest

from daydream import config
from daydream.gpu import arbiter
from daydream.images import cache, client
from daydream.llm import client as llm_client

pytestmark = pytest.mark.tier_short

ROOM = client.PersistentTarget(world_id="w-x", target_kind="room", target_id="r-x",
                               seed="a small lamplit room", prompt_suffix=client.WHIMSY_PROMPT_SUFFIX)


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DAYDREAM_IMAGE_BACKEND", raising=False)
    arbiter.reset()
    yield
    arbiter.reset()


def test_the_default_is_local_everywhere():
    assert config.image_backend() == "comfyui" and client.image_backend_is_local()
    assert config.llm_is_local()


def test_the_default_changes_no_cache_key():
    raw = client.load_workflow(client.workflow_path(ROOM.workflow_name))
    assert client.load_workflow_for(ROOM) == raw
    assert "backend" not in client.load_workflow_for(ROOM)
    assert (cache.cache_path("w-x", "room", "r-x", ROOM.seed, client.load_workflow_for(ROOM))
            == cache.cache_path("w-x", "room", "r-x", ROOM.seed, raw))


def test_another_backend_gets_its_own_cache_keys(monkeypatch):
    default_path = cache.cache_path("w-x", "room", "r-x", ROOM.seed, client.load_workflow_for(ROOM))
    monkeypatch.setenv("DAYDREAM_IMAGE_BACKEND", "workers-ai")
    monkeypatch.setenv("DAYDREAM_IMAGE_BACKEND_MODEL", "@cf/black-forest-labs/flux-1-schnell")
    wf = client.load_workflow_for(ROOM)
    assert wf["backend"] == {"id": "workers-ai", "model": "@cf/black-forest-labs/flux-1-schnell"}
    assert cache.cache_path("w-x", "room", "r-x", ROOM.seed, wf) != default_path


def test_render_params_read_the_workflow():
    wf = client.build_prompt_workflow(client.load_workflow_for(ROOM), "a lamplit room", seed=7)
    p = client.render_params(wf)
    assert (p.prompt, p.width, p.height, p.seed, p.steps) == ("a lamplit room", 1024, 384, 7, 22)
    assert "pixel art" in p.negative


async def test_a_registered_backend_renders_without_comfyui_or_the_gpu_slot(monkeypatch, tmp_path):
    seen = []

    async def fake_backend(params):
        seen.append((params, arbiter.is_locked()))
        return b"\x89PNG\r\n\x1a\nfake"

    comfy = AsyncMock(side_effect=AssertionError("ComfyUI must not be called"))
    monkeypatch.setattr(client, "_execute_workflow", comfy)
    monkeypatch.setitem(client.IMAGE_BACKENDS, "fake", fake_backend)
    monkeypatch.setenv("DAYDREAM_IMAGE_BACKEND", "fake")
    target = client.EphemeralTarget(name="seam", prompt="a sleepy village",
                                    out_path=tmp_path / "x.png")
    async with client.render_slot():
        out = await client.generate_image(target)
    assert out.read_bytes().endswith(b"fake")
    (params, locked), = seen
    assert params.prompt.startswith("a sleepy village") and locked is False


async def test_an_unknown_backend_fails_cleanly(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYDREAM_IMAGE_BACKEND", "nowhere")
    with pytest.raises(client.ComfyUIError, match="not available"):
        await client.generate_image(client.EphemeralTarget(name="x", prompt="y",
                                                           out_path=tmp_path / "x.png"))


def _fake_completion(record):
    class R:
        class _C:
            class message:
                content = json.dumps({"ok": True})
        choices = [_C()]
        usage = None

    async def acompletion(**kw):
        record.append(arbiter.is_locked())
        return R()

    return acompletion


async def test_a_local_llm_holds_the_gpu_slot_and_a_remote_one_does_not(monkeypatch):
    seen = []
    monkeypatch.setattr(llm_client.litellm, "acompletion", _fake_completion(seen))
    monkeypatch.setenv("DAYDREAM_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    await llm_client.acompletion_json("s", "u", purpose="test")
    monkeypatch.setenv("DAYDREAM_LLM_BASE_URL",
                       "https://api.cloudflare.com/client/v4/accounts/x/ai/v1")
    assert not config.llm_is_local()
    await llm_client.acompletion_json("s", "u", purpose="test")
    assert seen == [True, False]
