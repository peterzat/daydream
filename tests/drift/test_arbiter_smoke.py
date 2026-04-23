"""Pytest-ified arbiter smoke: 5 alternating LLM + image-gen calls,
aggregate wall-clock under budget, per-call latencies within windows.

Source of truth for the arbiter-smoke scenario. The standalone
`tools/arbiter-smoke.py` is preserved for ad-hoc human use but reads
the same prompts from tests/drift/prompts/ so the two can't drift.

Why pytest-ify: the smoke wasn't discoverable via `bin/game test` and
its asserts (single aggregate budget) were coarser than what drift
detection wants. The pytest version adds per-call budgets and plugs
into the baseline write-then-compare loop.

Requires BOTH vLLM and ComfyUI reachable. Marked tier_long so it never
fires during short/medium runs."""

from __future__ import annotations

import time

import pytest

from daydream.gpu import arbiter
from daydream.images import client as image_client
from daydream.llm import client as llm_client

from .conftest import write_latest

pytestmark = [
    pytest.mark.tier_long,
    pytest.mark.requires_vllm,
    pytest.mark.requires_comfyui,
]


AGGREGATE_BUDGET_S = 90.0
LLM_PER_CALL_BUDGET_S = 5.0
IMAGE_PER_CALL_BUDGET_S = 40.0


async def _llm_one(n: int) -> float:
    t = time.monotonic()
    result = await llm_client.acompletion_json(
        system="Reply with valid JSON only. No prose.",
        user=f'Echo this number as JSON: {{"n": {n}}}',
        max_tokens=64,
    )
    if "n" not in result:
        raise AssertionError(
            f"LLM #{n}: unexpected response shape {result!r} — likely the "
            "strict-JSON tripwire from docs/gpu-and-models.md"
        )
    return time.monotonic() - t


async def _image_one(n: int) -> float:
    t = time.monotonic()
    async with arbiter.acquire():
        path = await image_client.generate_image(
            image_client.EphemeralTarget(
                name=f"smoke-{n}",
                prompt=f"a quiet meadow at dusk, take {n}, fireflies and warm sunset",
                with_whimsy_suffix=True,
            ),
        )
    if not path.exists():
        raise AssertionError(f"image #{n}: missing output {path}")
    return time.monotonic() - t


async def test_arbiter_smoke_alternating_calls(drift_data_dir):
    """Five alternating LLM + image calls through the real arbiter path.
    Asserts the arbiter serializes correctly (no OOM) AND each call
    stays within its per-call budget AND the aggregate is under 90s."""
    sequence = [
        ("llm", _llm_one, 1),
        ("image", _image_one, 2),
        ("llm", _llm_one, 3),
        ("image", _image_one, 4),
        ("llm", _llm_one, 5),
    ]
    per_call_ms: dict[str, float] = {}
    failures: list[str] = []
    t_total = time.monotonic()
    for kind, fn, n in sequence:
        try:
            dt = await fn(n)
        except Exception as e:  # noqa: BLE001 — we want to record it
            failures.append(f"{kind} #{n}: {type(e).__name__}: {e}")
            continue
        per_call_ms[f"{kind}_{n}"] = dt * 1000
        budget = LLM_PER_CALL_BUDGET_S if kind == "llm" else IMAGE_PER_CALL_BUDGET_S
        if dt > budget:
            failures.append(f"{kind} #{n}: {dt:.1f}s > {budget:.0f}s budget")
    total_s = time.monotonic() - t_total

    # Capture the whole run regardless of pass/fail so trends are visible.
    write_latest(
        "arbiter_smoke",
        {
            "per_call_ms": per_call_ms,
            "total_s": total_s,
            "aggregate_budget_s": AGGREGATE_BUDGET_S,
            "failures": failures,
        },
    )

    if failures:
        pytest.fail("arbiter smoke failures:\n  " + "\n  ".join(failures))
    if total_s > AGGREGATE_BUDGET_S:
        pytest.fail(
            f"arbiter smoke aggregate {total_s:.1f}s exceeded budget "
            f"{AGGREGATE_BUDGET_S:.0f}s — individual calls passed their "
            "per-call budgets, so this is a serialization-overhead or "
            "warmup regression. Check the per-call breakdown in "
            "tests/baselines/arbiter_smoke.latest.json."
        )
