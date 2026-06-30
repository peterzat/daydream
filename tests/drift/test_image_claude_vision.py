"""Claude-vision aesthetic gate probe (tier_long, opt-in).

For each aesthetic anchor, render it through the real ComfyUI path and rate the
output against the WHIMSY rubric via the vision gate (daydream/testing/
vision_gate.py). This is the automated counterpart to the human qpeek review:
it converts "an operator eyeballs the render" into a mechanical pass/fail.

SKIPPED unless DAYDREAM_CLAUDE_VISION_GATE is set — the gate is opt-in because
it costs Anthropic API tokens (and needs ANTHROPIC_API_KEY). Routine and
autonomous `tier_long` runs therefore pay nothing for it. The gate is design-
time tooling, not a runtime call (CLAUDE.md local-only policy)."""

from __future__ import annotations

import pytest

from daydream.gpu import arbiter
from daydream.images import client as image_client
from daydream.testing import vision_gate

from .conftest import load_aesthetics_corpus

pytestmark = [pytest.mark.tier_long, pytest.mark.requires_comfyui]

_corpus = load_aesthetics_corpus()


@pytest.mark.skipif(
    not vision_gate.enabled(),
    reason=f"vision gate off (set {vision_gate.ENV_FLAG}=1 + ANTHROPIC_API_KEY)",
)
@pytest.mark.parametrize("probe_id,probe", _corpus, ids=[pid for pid, _ in _corpus])
async def test_anchor_passes_vision_rubric(probe_id: str, probe: dict, drift_data_dir):
    """Render the anchor and assert it clears the WHIMSY rubric threshold.
    Complements the perceptual-hash probe: that one catches *change*, this one
    catches *off-aesthetic* (a render that drifted into a banned mood / look)."""
    target = image_client.EphemeralTarget(
        name=probe["name"], prompt=probe["prompt"], with_whimsy_suffix=True,
    )
    async with arbiter.acquire():
        path = await image_client.generate_image(target)
    verdict = await vision_gate.rate_image(path, subject=probe["name"])
    assert verdict.passed, (
        f"{probe_id} failed the WHIMSY vision rubric: {verdict.label} "
        f"banned={list(verdict.banned)} — {verdict.reason}"
    )
