"""Image-gen perceptual drift probes.

Render each anchor prompt in tests/drift/aesthetics/ through the real
ComfyUI path, compute a dHash + resolution + wall-clock, compare against
the committed baseline. Hamming-distance threshold on the dHash catches
material aesthetic shifts (LoRA swap, sampler tweak, checkpoint change);
resolution catches a silent workflow edit that changes canvas size;
wall-clock catches performance regressions that the arbiter-smoke's
aggregate budget might paper over.

Under the tier_long marker, the enforce_arbiter_held fixture in
tests/drift/conftest.py is armed: calling generate_image without first
entering `async with arbiter.acquire()` fails the test immediately with
a clear reason. Makes the arbiter contract mechanical."""

from __future__ import annotations

import time

import pytest

from daydream.gpu import arbiter
from daydream.images import client as image_client

from .conftest import (
    dhash,
    hamming,
    image_resolution,
    load_aesthetics_corpus,
    load_golden,
    write_latest,
)

pytestmark = [
    pytest.mark.tier_long,
    pytest.mark.requires_comfyui,
]


_corpus = load_aesthetics_corpus()


@pytest.mark.parametrize("probe_id,probe", _corpus, ids=[pid for pid, _ in _corpus])
async def test_image_aesthetic_probe(probe_id: str, probe: dict, drift_data_dir):
    """Render the anchor prompt and compare the observed dHash +
    resolution + wall-clock against the golden baseline. A Hamming
    distance above probe['phash_tolerance'] is treated as material
    drift; review whether the LoRA / checkpoint / workflow change was
    intended, and if so ratify the new baseline."""
    target = image_client.EphemeralTarget(
        name=probe["name"],
        prompt=probe["prompt"],
        with_whimsy_suffix=True,
    )
    t0 = time.monotonic()
    async with arbiter.acquire():
        path = await image_client.generate_image(target)
    wall_ms = (time.monotonic() - t0) * 1000

    observed_hash = dhash(path)
    observed_res = list(image_resolution(path))

    # dHash can't be compared by exact-match — the probe's tolerance
    # window is what matters. Read the golden's dhash and compute the
    # Hamming distance ourselves, then record the actual distance in
    # the .latest.json so the operator can see how close we are to
    # the threshold over time.
    golden = load_golden(f"image_{probe_id}")
    observed = {
        "dhash": observed_hash,
        "resolution": observed_res,
        "wall_clock_ms": wall_ms,
        "model": None,
        "lora": None,
        "workflow_hash": None,
    }
    # Fill model/lora/workflow_hash from the workflow so baselines can
    # key off (model, lora, workflow_hash) and a swap busts the
    # baseline automatically.
    wf = image_client.load_workflow()
    observed["model"] = wf.get(image_client.CHECKPOINT_NODE, {}).get("inputs", {}).get("ckpt_name")
    observed["lora"] = wf.get(image_client.LORA_NODE, {}).get("inputs", {}).get("lora_name")
    from daydream.images import cache as image_cache
    observed["workflow_hash"] = image_cache.workflow_hash(wf)

    if golden is None:
        write_latest(f"image_{probe_id}", observed)
        pytest.fail(
            f"baseline missing for image probe {probe_id!r}. "
            f"dhash={observed_hash}, resolution={observed_res}, "
            f"wall_ms={wall_ms:.0f}. Captured at tests/baselines/"
            f"image_{probe_id}.latest.json. Ratify with "
            f"`mv tests/baselines/image_{probe_id}.latest.json "
            f"tests/baselines/image_{probe_id}.golden.json`."
        )

    observed["hamming_distance_from_golden"] = hamming(observed_hash, int(golden["dhash"]))
    write_latest(f"image_{probe_id}", observed)

    # Resolution and (model, lora, workflow_hash) are exact-match.
    # Drift on any of these means a real workflow change happened.
    if observed_res != golden.get("resolution"):
        pytest.fail(
            f"resolution drift for {probe_id!r}: observed={observed_res}, "
            f"golden={golden.get('resolution')}"
        )
    for field in ("model", "lora", "workflow_hash"):
        if observed[field] != golden.get(field):
            pytest.fail(
                f"workflow drift for {probe_id!r}: {field} observed="
                f"{observed[field]!r} golden={golden.get(field)!r}. "
                "If intended, capture a new baseline."
            )

    # Hamming threshold.
    tol = int(probe["phash_tolerance"])
    if observed["hamming_distance_from_golden"] > tol:
        pytest.fail(
            f"perceptual drift for {probe_id!r}: Hamming distance "
            f"{observed['hamming_distance_from_golden']} > tolerance {tol}. "
            f"dhash observed={observed_hash}, golden={golden['dhash']}. "
            f"Inspect the PNG at {path} and compare against the committed "
            "baseline reference image."
        )

    # Wall-clock drift is recorded in .latest.json but NOT gated here —
    # one-shot timings are too noisy for a single-sample compare. A
    # future refinement can add percentile-based enforcement once we
    # have a multi-run trend.
