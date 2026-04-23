"""Live GPU-arbiter smoke test.

Runs 5 alternating LLM + image-gen requests through the same code paths
the WS layer uses (LLM via daydream.llm.client.acompletion_json which
acquires the arbiter internally; image-gen via daydream.images.client
.generate_room_background under an external arbiter.acquire(), mirroring
daydream/api/ws.py's _generate_and_emit).

Verifies SPEC criteria 3 (5 alternating requests, no OOM, under 90 s
wall-clock) and 6 (LLM still routes correctly after image-gen cycles).

Requires both vLLM (bin/game vllm-up) and ComfyUI (bin/game comfyui-up)
running. Run from the project root with the daydream venv:

    .venv/bin/python tools/arbiter-smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

# Use a temp data dir so the real ~/data/daydream/ cache stays clean.
TMP = tempfile.mkdtemp(prefix="daydream-arbiter-smoke-")
os.environ["DAYDREAM_DATA_DIR"] = TMP

from daydream.gpu import arbiter  # noqa: E402
from daydream.images import client as image_client  # noqa: E402
from daydream.llm import client as llm_client  # noqa: E402


BUDGET_S = 90.0


async def llm_call(n: int) -> float:
    """One LLM round-trip. acompletion_json acquires the arbiter internally."""
    t = time.monotonic()
    result = await llm_client.acompletion_json(
        system="Reply with valid JSON only. No prose.",
        user=f'Echo this number as JSON: {{"n": {n}}}',
        max_tokens=64,
    )
    if "n" not in result:
        raise RuntimeError(f"LLM #{n}: unexpected response shape {result!r}")
    return time.monotonic() - t


async def image_call(n: int) -> float:
    """One image-gen round-trip. Mirrors WS _generate_and_emit: caller wraps."""
    t = time.monotonic()
    async with arbiter.acquire():
        path = await image_client.generate_room_background(
            world_id="smoke",
            room_id=f"r-{n}",
            room_seed=f"a quiet meadow at dusk, take {n}, fireflies and warm sunset",
            prompt_suffix=image_client.WHIMSY_PROMPT_SUFFIX,
        )
    if not path.exists():
        raise RuntimeError(f"image #{n}: missing output {path}")
    return time.monotonic() - t


async def main() -> int:
    sequence = [
        ("llm  ", llm_call, 1),
        ("image", image_call, 2),
        ("llm  ", llm_call, 3),
        ("image", image_call, 4),
        ("llm  ", llm_call, 5),
    ]
    print(f"data dir: {TMP}")
    print(f"vLLM: {llm_client.config.llm_base_url()}")
    print(f"ComfyUI: {image_client.config.comfyui_base_url()}")
    print()
    t0 = time.monotonic()
    for kind, fn, n in sequence:
        try:
            dt = await fn(n)
        except Exception as e:
            print(f"  {kind} #{n}: FAILED ({type(e).__name__}: {e})")
            return 1
        print(f"  {kind} #{n}: {dt:5.2f}s")
    total = time.monotonic() - t0
    print()
    print(f"5 alternating requests in {total:.1f}s (budget {BUDGET_S:.0f}s)")
    if total > BUDGET_S:
        print("  WARN: over budget — criterion 3 not met as written")
        return 1
    print("  OK — criterion 3 met. The final LLM call following an image-gen")
    print("       cycle satisfying criterion 6 implicitly (no permanently-fogged state).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
