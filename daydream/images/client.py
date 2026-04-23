"""ComfyUI HTTP client.

Loads the shared workflow JSON, substitutes the prompt and a deterministic
seed, posts to ComfyUI's /prompt endpoint, polls /history for completion,
fetches the result, writes it to the cache.

Operational notes:
- ComfyUI runs as a separate process at config.comfyui_base_url()
  (default http://localhost:8188).
- The workflow file at daydream/images/workflows/painterly_room.json is
  shared by this client and by bin/game image-test (Inc 7).
- Callers MUST hold the GPU arbiter lock for the duration of any
  generate_room_background() call. The arbiter is in daydream.gpu.arbiter."""

import asyncio
import json
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from daydream import config
from daydream.images import cache

WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"
DEFAULT_WORKFLOW = WORKFLOWS_DIR / "painterly_room.json"

# Node id in the workflow that holds the positive-prompt CLIPTextEncode.
# If the workflow JSON layout changes, the _meta.node_ids block in that
# file is the source of truth; this constant must stay in sync.
POSITIVE_PROMPT_NODE = "3"
CHECKPOINT_NODE = "1"
LORA_NODE = "2"

# Per WHIMSY.md ## Prompt suffix. Kept here as the single source of truth
# for image-gen call sites; daydream/llm/prompts.py will gain its own copy
# for narration prompts in v1's safety-baseline-v1 increment.
WHIMSY_PROMPT_SUFFIX = (
    "soft watercolor, painterly, warm late-day light, cozy storybook "
    "illustration, gentle composition, no text, no logos, no people in "
    "modern dress, no machinery, no harsh edges, Spiritfarer-adjacent, "
    "A Short Hike-adjacent, low-saturation cream and sage palette"
)


class ComfyUIError(Exception):
    """Raised when ComfyUI is unreachable, rejects the workflow, or fails
    to produce an image. The caller is expected to handle this gracefully
    (e.g., narrate a 'painting failed, will try again' event)."""


def load_workflow(path: Path = DEFAULT_WORKFLOW) -> dict:
    raw = json.loads(path.read_text())
    # Strip _meta before sending to ComfyUI; it is documentation only.
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def build_prompt_workflow(workflow: dict, prompt_text: str, seed: int = 0) -> dict:
    """Return a deep copy of the workflow with the positive prompt substituted
    and the KSampler seed pinned for reproducibility."""
    wf = deepcopy(workflow)
    if POSITIVE_PROMPT_NODE not in wf:
        raise ComfyUIError(f"workflow missing positive-prompt node {POSITIVE_PROMPT_NODE!r}")
    node = wf[POSITIVE_PROMPT_NODE]
    if node.get("inputs", {}).get("text") is None:
        raise ComfyUIError(f"node {POSITIVE_PROMPT_NODE} is not a CLIPTextEncode")
    node["inputs"]["text"] = prompt_text
    for n in wf.values():
        if n.get("class_type") == "KSampler" and "seed" in n.get("inputs", {}):
            n["inputs"]["seed"] = int(seed)
    return wf


async def submit_and_wait(
    workflow: dict,
    base_url: str | None = None,
    timeout: float = 120.0,
    poll_interval: float = 0.5,
) -> dict:
    """Submit the workflow to ComfyUI and wait for completion. Returns the
    /history entry for the prompt (a dict with 'outputs' keyed by node id).

    Raises ComfyUIError on backend failure or timeout."""
    if base_url is None:
        base_url = config.comfyui_base_url()
    client_id = str(uuid.uuid4())
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
            r = await http.post("/prompt", json={"prompt": workflow, "client_id": client_id})
            r.raise_for_status()
            prompt_id = r.json()["prompt_id"]
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                r = await http.get(f"/history/{prompt_id}")
                r.raise_for_status()
                data = r.json()
                if prompt_id in data:
                    return data[prompt_id]
                await asyncio.sleep(poll_interval)
            raise ComfyUIError(f"ComfyUI did not finish prompt {prompt_id} in {timeout}s")
    except httpx.HTTPError as e:
        raise ComfyUIError(f"ComfyUI HTTP error: {e}") from e


async def fetch_output_image(history_entry: dict, base_url: str | None = None) -> bytes:
    """Pull the first output image from a finished history entry."""
    if base_url is None:
        base_url = config.comfyui_base_url()
    outputs = history_entry.get("outputs", {})
    for node_outputs in outputs.values():
        images = node_outputs.get("images", [])
        if images:
            img = images[0]
            params: dict[str, Any] = {
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
            }
            try:
                async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as http:
                    r = await http.get("/view", params=params)
                    r.raise_for_status()
                    return r.content
            except httpx.HTTPError as e:
                raise ComfyUIError(f"ComfyUI image fetch failed: {e}") from e
    raise ComfyUIError("ComfyUI history entry contained no images")


async def generate_room_background(
    world_id: str,
    room_id: str,
    room_seed: str,
    prompt_suffix: str = "",
    base_url: str | None = None,
) -> Path:
    """End-to-end: build prompt, generate, save to cache, return the cache path.
    Caller MUST hold the arbiter lock. Returns immediately if the file already
    exists in the cache (no regen)."""
    out = cache.cache_path(world_id, room_id, room_seed)
    if out.exists():
        return out
    full_prompt = " ".join(p for p in [room_seed.strip(), prompt_suffix.strip()] if p)
    deterministic_seed = int(cache.seed_hash(room_seed)[:8], 16)
    workflow = build_prompt_workflow(load_workflow(), full_prompt, seed=deterministic_seed)
    history = await submit_and_wait(workflow, base_url=base_url)
    image_bytes = await fetch_output_image(history, base_url=base_url)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    return out


async def generate_to_path(
    prompt: str,
    out_path: Path,
    model: str | None = None,
    lora: str | None = None,
    seed: int = 0,
    base_url: str | None = None,
) -> Path:
    """Generic image gen with optional model and LoRA overrides. Used by the
    bin/game image-test harness so aesthetic A/B swaps stay one-liners; the
    room-background path always uses the workflow's defaults. Caller is
    responsible for any GPU coordination (the harness typically runs while
    vLLM is not active, so no arbiter dance is required)."""
    workflow = load_workflow()
    if model:
        workflow[CHECKPOINT_NODE]["inputs"]["ckpt_name"] = model
    if lora:
        workflow[LORA_NODE]["inputs"]["lora_name"] = lora
    workflow = build_prompt_workflow(workflow, prompt, seed=seed)
    history = await submit_and_wait(workflow, base_url=base_url)
    image_bytes = await fetch_output_image(history, base_url=base_url)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)
    return out_path
