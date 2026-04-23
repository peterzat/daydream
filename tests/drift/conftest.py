"""Drift-probe helpers: baselines, perceptual hash, arbiter-held tripwire.

Every test under tests/drift/ is a drift probe — it runs the real code
path (LLM call through vLLM, image gen through ComfyUI, constants check
against docs) and compares a measured fingerprint to a git-committed
golden baseline at tests/baselines/<probe_id>.golden.json.

State transitions:
  no baseline present  → test FAILS with a clear "baseline missing"
                         message; a .latest.json is written so the
                         operator can `mv *.latest.json *.golden.json`
                         and commit when the first measurement is
                         known-good.
  baseline matches     → test PASSES; .latest.json is refreshed.
  baseline diverges    → test FAILS with a diff-friendly message;
                         .latest.json captures the divergent values
                         so the operator can decide: is this a
                         regression to fix, or a new accepted baseline?

Per TESTING.md (commit 5), a baseline update is a PR event — reviewing
the diff is the point. In-tree JSON keeps that review loop honest.

The pHash used here is a pure-Pillow difference hash (dHash). No numpy
or imagehash dependency. dHash is slightly less robust than the DCT-based
pHash for small edits, but perfectly adequate for drift detection: a
material aesthetic change (LoRA swap, sampler tweak) produces many-bit
differences, not 1-2 bit differences."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

BASELINES_DIR = Path(__file__).resolve().parent.parent / "baselines"


# ---- dHash (pure Pillow, no numpy) --------------------------------------


def dhash(image_path: Path, hash_size: int = 8) -> int:
    """Perceptual difference hash. Resize to (hash_size+1)*hash_size,
    convert to grayscale, compare adjacent pixels in each row to form
    `hash_size*hash_size` bits. Returns an int holding those bits (64
    bits for hash_size=8, which is the default).

    Why dHash not pHash: dHash is a ~10-line algorithm that runs on
    Pillow alone. pHash needs a DCT, which needs scipy/numpy. For drift
    *detection* (not content ID), dHash is sensitive enough — a material
    aesthetic shift moves many bits, not 1-2."""
    img = Image.open(image_path).convert("L").resize(
        (hash_size + 1, hash_size), Image.LANCZOS
    )
    pixels = list(img.getdata())
    bits = 0
    stride = hash_size + 1
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * stride + col]
            right = pixels[row * stride + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    """Count differing bits between two hashes."""
    return bin(a ^ b).count("1")


def image_resolution(image_path: Path) -> tuple[int, int]:
    with Image.open(image_path) as img:
        return img.size


# ---- baseline load/write ------------------------------------------------


def baseline_path(probe_id: str, kind: str = "golden") -> Path:
    """kind in {'golden', 'latest'}. 'golden' is git-committed; 'latest'
    is gitignored and written on every run so the operator can review
    the diff before ratifying."""
    return BASELINES_DIR / f"{probe_id}.{kind}.json"


def load_golden(probe_id: str) -> dict[str, Any] | None:
    p = baseline_path(probe_id, "golden")
    if not p.exists():
        return None
    return json.loads(p.read_text())


def write_latest(probe_id: str, data: dict[str, Any]) -> Path:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    p = baseline_path(probe_id, "latest")
    payload = dict(data)
    payload.setdefault("captured_at", datetime.now(tz=timezone.utc).isoformat(timespec="seconds"))
    p.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return p


def assert_against_baseline(probe_id: str, observed: dict[str, Any], *, compare_keys: list[str]) -> None:
    """Write .latest, compare against .golden, fail with a diff-friendly
    message on miss or absence. compare_keys lists the observed fields
    the baseline must match (others are metadata, always written, never
    compared — e.g., captured_at, model, lora)."""
    latest_path = write_latest(probe_id, observed)
    golden = load_golden(probe_id)
    if golden is None:
        pytest.fail(
            f"baseline missing for probe {probe_id!r}.\n"
            f"captured first observation at {latest_path}\n"
            f"review and ratify with:\n"
            f"  cp {latest_path.relative_to(Path.cwd())} "
            f"{baseline_path(probe_id, 'golden').relative_to(Path.cwd())}\n"
            f"  git add {baseline_path(probe_id, 'golden').relative_to(Path.cwd())}"
        )
    diffs: list[str] = []
    for k in compare_keys:
        obs = observed.get(k)
        exp = golden.get(k)
        if obs != exp:
            diffs.append(f"  {k}: observed={obs!r} golden={exp!r}")
    if diffs:
        pytest.fail(
            f"drift detected for probe {probe_id!r}:\n"
            + "\n".join(diffs)
            + f"\n\nlatest written to {latest_path}\n"
            "if this is an accepted change, ratify with:\n"
            f"  mv {latest_path.relative_to(Path.cwd())} "
            f"{baseline_path(probe_id, 'golden').relative_to(Path.cwd())}"
        )


def assert_within(
    probe_id: str, observed: dict[str, Any], *, within: dict[str, tuple[float, float]]
) -> None:
    """Like assert_against_baseline but for numeric fields where the
    baseline defines a tolerance window. `within` maps field name to
    (lower_multiplier, upper_multiplier) relative to the golden value.
    Example: {"latency_ms": (0.5, 2.0)} accepts a 2x regression or a 2x
    improvement before alarming.

    Non-numeric fields fall back to exact match via compare_keys semantics."""
    latest_path = write_latest(probe_id, observed)
    golden = load_golden(probe_id)
    if golden is None:
        pytest.fail(
            f"baseline missing for probe {probe_id!r}.\n"
            f"captured first observation at {latest_path}\n"
            f"review and ratify with:\n"
            f"  cp {latest_path.relative_to(Path.cwd())} "
            f"{baseline_path(probe_id, 'golden').relative_to(Path.cwd())}"
        )
    diffs: list[str] = []
    for k, (lo_mult, hi_mult) in within.items():
        obs = observed.get(k)
        exp = golden.get(k)
        if obs is None or exp is None:
            diffs.append(f"  {k}: observed={obs!r} golden={exp!r} (one side missing)")
            continue
        lo, hi = exp * lo_mult, exp * hi_mult
        if not (lo <= obs <= hi):
            diffs.append(
                f"  {k}: observed={obs} outside window [{lo:.1f}, {hi:.1f}] "
                f"(golden={exp}, tolerance={lo_mult}x-{hi_mult}x)"
            )
    if diffs:
        pytest.fail(
            f"drift detected for probe {probe_id!r}:\n"
            + "\n".join(diffs)
            + f"\n\nlatest written to {latest_path}"
        )


# ---- arbiter-held tripwire ----------------------------------------------


@pytest.fixture(autouse=True)
def enforce_arbiter_held(request, monkeypatch):
    """tier_long tests running real image-gen must hold the GPU arbiter
    for the duration of the call. This fixture monkey-patches
    daydream.images.client._execute_workflow to assert arbiter.is_locked()
    at call time. Turns the 'caller MUST hold the arbiter' policy into a
    mechanical tripwire. No-op for tests not marked tier_long.

    The LLM client acquires internally, so no such patch is needed on
    that path — the lock is always held when the HTTP call fires."""
    if not request.node.get_closest_marker("tier_long"):
        return

    from daydream.gpu import arbiter
    from daydream.images import client as image_client

    real_execute = image_client._execute_workflow

    async def checked_execute(*args, **kwargs):
        assert arbiter.is_locked(), (
            "real-GPU image-gen call fired without arbiter held. Wrap "
            "the generate_image call in `async with arbiter.acquire():`."
        )
        return await real_execute(*args, **kwargs)

    monkeypatch.setattr(image_client, "_execute_workflow", checked_execute)


# ---- test-scoped ephemeral data dir -------------------------------------


@pytest.fixture
def drift_data_dir(tmp_path, monkeypatch):
    """Isolate drift probes from the operator's ~/data/daydream/ so their
    PNGs and cache entries don't pile up. Each test gets a tmp data dir
    pointed at by DAYDREAM_DATA_DIR for its duration."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield tmp_path


# ---- probe corpus loaders -----------------------------------------------


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
AESTHETICS_DIR = Path(__file__).resolve().parent / "aesthetics"


def load_prompt_corpus() -> list[tuple[str, dict[str, Any]]]:
    """Read tests/drift/prompts/*.json. Each file is a JSON probe
    (system, user, expected_schema_keys, max_tokens). Returns
    [(probe_id, probe_dict)] sorted by probe_id for stable param order.

    Used by test_llm_json_adherence.py via pytest parametrize, and by
    tools/arbiter-smoke.py (post-commit-3) so the two run the same
    prompts."""
    items: list[tuple[str, dict[str, Any]]] = []
    for p in sorted(PROMPTS_DIR.glob("*.json")):
        items.append((p.stem, json.loads(p.read_text())))
    return items


def load_aesthetics_corpus() -> list[tuple[str, dict[str, Any]]]:
    """Read tests/drift/aesthetics/*.json. Each: (name, prompt,
    expected_resolution, phash_tolerance)."""
    items: list[tuple[str, dict[str, Any]]] = []
    for p in sorted(AESTHETICS_DIR.glob("*.json")):
        items.append((p.stem, json.loads(p.read_text())))
    return items
