"""Unified image generation: one entry point (`generate_image`) for both
persistent (cached + DB-recorded) and ephemeral (one-off, no record) work.

The two callers — the WS layer (room backgrounds) and the `bin/game image-
test` CLI (aesthetic A/B) — used to live in two different functions with
overlapping internals. This module now exposes a single `generate_image`
that takes a target dataclass:

  PersistentTarget — bound to an in-world entity (room, toon, item).
                     Cached at images/cache/{world}/{kind}/{id}/{hash}.png,
                     recorded in generated_assets, deduped via the cache
                     hash (which includes the workflow JSON).
  EphemeralTarget  — one-off output. Lives at images/ephemeral/{name}-
                     {prompt_hash}.png; deterministic per-prompt path so
                     re-runs overwrite (good for A/B). Never recorded.

Both share the same workflow build, the same ComfyUI HTTP plumbing, and
the same arbiter contract: callers MUST hold the GPU arbiter lock for the
duration of any generate_image() call. The arbiter is in
daydream.gpu.arbiter; see CLAUDE.md "GPU posture".

Operational notes:
- ComfyUI runs as a separate process at config.comfyui_base_url() (default
  http://localhost:8188).
- The workflow file at daydream/images/workflows/painterly_room.json is
  shared by both target kinds; per-call model/lora/seed overrides are
  applied before hashing so they bust the persistent cache."""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from daydream import assets, config
from daydream.images import cache

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = Path(__file__).resolve().parent / "workflows"
DEFAULT_WORKFLOW = WORKFLOWS_DIR / "painterly_room.json"

# Node ids in the workflow JSON. If the workflow shape changes, the _meta
# block in the JSON is the source of truth; these constants must stay in
# sync.
POSITIVE_PROMPT_NODE = "3"
CHECKPOINT_NODE = "1"
LORA_NODE = "2"

# Verbatim from WHIMSY.md "## Prompt suffix". WHIMSY.md is the durable
# tone source; this constant mirrors it for the image-gen call sites.
# tests/test_whimsy_prompt_suffix.py is the drift catcher.
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


# ---- target types -------------------------------------------------------


@dataclass(frozen=True)
class PersistentTarget:
    """Generated asset bound to an in-world entity.

    The cache key folds (world_id, target_kind, target_id, seed, workflow)
    so:
    - two rooms with the same seed text get distinct files (target_id
      differs),
    - editing the seed text busts the cache,
    - editing the workflow JSON busts the cache too.

    On generation success, a row lands in generated_assets via
    daydream.assets.record_image_generation."""

    world_id: str
    target_kind: str            # 'room' for v1; 'toon' / 'item' later
    target_id: str
    seed: str                   # the prompt source text
    prompt_suffix: str = ""     # appended to seed; usually WHIMSY_PROMPT_SUFFIX


@dataclass(frozen=True)
class EphemeralTarget:
    """One-off output for aesthetic A/B, debugging, scratch work.

    No cache key, no DB row. Deterministic per-prompt path under
    images/ephemeral/ so re-running with the same prompt overwrites in
    place (which is what A/B work wants — easy to compare 'old vs new').

    Pass `out_path` to override the derived path (the CLI's --out flag
    routes through here)."""

    name: str                       # human-readable; sanitized into the filename
    prompt: str                     # literal user prompt
    with_whimsy_suffix: bool = True
    out_path: Path | None = None    # if set, overrides ephemeral_path()


# ---- workflow + helpers -------------------------------------------------


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


def _apply_overrides(workflow: dict, model: str | None, lora: str | None) -> dict:
    """Apply model/lora overrides to a fresh workflow copy. Returns the
    modified workflow; the input is not mutated."""
    wf = deepcopy(workflow)
    if model:
        wf[CHECKPOINT_NODE]["inputs"]["ckpt_name"] = model
    if lora:
        wf[LORA_NODE]["inputs"]["lora_name"] = lora
    return wf


def is_persistent_cached(target: PersistentTarget) -> bool:
    """True if the cache file for this target exists. Uses the default
    workflow with no overrides; for callers that have applied overrides,
    use cache.cache_path directly."""
    workflow = load_workflow()
    return cache.is_cached(
        target.world_id, target.target_kind, target.target_id, target.seed, workflow
    )


def target_dedup_key(target: PersistentTarget) -> tuple[str, str, str, str]:
    """A stable key for in-flight dedup across concurrent connections.
    Combines world / kind / id / combined_hash so two requests for the
    same logical asset collapse to one generation."""
    workflow = load_workflow()
    return (
        target.world_id,
        target.target_kind,
        target.target_id,
        cache.combined_hash(target.seed, workflow),
    )


def ephemeral_path(name: str, prompt: str, root: Path | None = None) -> Path:
    """Deterministic per-prompt path under images/ephemeral/. Same prompt
    always lands at the same path so re-runs overwrite cleanly (which is
    what A/B work wants). Caller may override `root` for tests."""
    if root is None:
        root = config.data_dir() / "images" / "ephemeral"
    h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    safe = "".join(c if c.isalnum() else "-" for c in name[:40]).strip("-") or "untitled"
    return root / f"{safe}-{h}.png"


# ---- ComfyUI HTTP -------------------------------------------------------


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


async def _execute_workflow(workflow: dict, base_url: str | None = None) -> bytes:
    """Submit workflow to ComfyUI and return the rendered image bytes.
    Single low-level path shared by both target kinds; tests mock here."""
    history = await submit_and_wait(workflow, base_url=base_url)
    return await fetch_output_image(history, base_url=base_url)


# ---- unified entry point -----------------------------------------------


async def generate_image(
    target: PersistentTarget | EphemeralTarget,
    *,
    model: str | None = None,
    lora: str | None = None,
    seed: int | None = None,
    base_url: str | None = None,
) -> Path:
    """End-to-end image generation. Caller MUST hold the arbiter lock.

    Returns the output path on success.

    Persistent: short-circuits on cache hit (no regen, no record). On miss,
    runs the workflow, writes the file, and records to generated_assets.
    Recording is REQUIRED on this path — if the DB isn't initialized, the
    asset module raises (this is a programming bug, not a runtime error).

    Ephemeral: always runs the workflow, writes to the deterministic
    ephemeral path (or target.out_path if set). Never recorded."""
    base_workflow = _apply_overrides(load_workflow(), model, lora)

    if isinstance(target, PersistentTarget):
        return await _generate_persistent(target, base_workflow, seed, base_url)
    if isinstance(target, EphemeralTarget):
        return await _generate_ephemeral(target, base_workflow, seed, base_url)
    raise TypeError(f"unknown target type: {type(target).__name__}")


async def _generate_persistent(
    target: PersistentTarget,
    base_workflow: dict,
    seed_override: int | None,
    base_url: str | None,
) -> Path:
    out = cache.cache_path(
        target.world_id, target.target_kind, target.target_id, target.seed, base_workflow
    )
    if out.exists():
        return out
    full_prompt = " ".join(
        p for p in [target.seed.strip(), target.prompt_suffix.strip()] if p
    )
    ksampler_seed = (
        seed_override
        if seed_override is not None
        else int(cache.seed_hash(target.seed)[:8], 16)
    )
    wf_to_run = build_prompt_workflow(base_workflow, full_prompt, seed=ksampler_seed)
    image_bytes = await _execute_workflow(wf_to_run, base_url=base_url)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    _record_persistent(target, full_prompt, base_workflow, out)
    return out


async def _generate_ephemeral(
    target: EphemeralTarget,
    base_workflow: dict,
    seed_override: int | None,
    base_url: str | None,
) -> Path:
    full_prompt = target.prompt.strip()
    if target.with_whimsy_suffix:
        full_prompt = (full_prompt + " " + WHIMSY_PROMPT_SUFFIX).strip()
    ksampler_seed = seed_override if seed_override is not None else 0
    wf_to_run = build_prompt_workflow(base_workflow, full_prompt, seed=ksampler_seed)
    image_bytes = await _execute_workflow(wf_to_run, base_url=base_url)
    out = target.out_path or ephemeral_path(target.name, full_prompt)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    return out


def _record_persistent(
    target: PersistentTarget,
    full_prompt: str,
    workflow: dict,
    out_path: Path,
) -> None:
    """Write the generated_assets row for a freshly-rendered persistent
    asset. Pulls model/lora from the workflow that was actually sent (not
    the workflow defaults), so the recorded values reflect the override-
    applied state."""
    model = workflow.get(CHECKPOINT_NODE, {}).get("inputs", {}).get("ckpt_name")
    lora = workflow.get(LORA_NODE, {}).get("inputs", {}).get("lora_name")
    relpath = str(out_path.relative_to(config.data_dir()))
    file_bytes = out_path.stat().st_size
    assets.record_image_generation(
        world_id=target.world_id,
        target_kind=target.target_kind,
        target_id=target.target_id,
        target_seed=target.seed,
        seed_hash=cache.seed_hash(target.seed),
        file_relpath=relpath,
        model=model,
        lora=lora,
        prompt_text=full_prompt,
        file_bytes=file_bytes,
        workflow_hash=cache.workflow_hash(workflow),
    )
