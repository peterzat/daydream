"""Project-wide pytest configuration. Loaded before any test module is
collected, so env vars set here are visible to module-level imports such as
`daydream.server.app` (which calls `config.session_secret()` at import time
to seed SessionMiddleware).

Without this, a clean `pytest` run would materialize
`~/.config/daydream/session_secret` in the developer's real home directory,
because `session_secret()` falls back to writing there when no env var is set.
"""

import os
import tempfile
from unittest.mock import AsyncMock

import httpx
import pytest

# Stable test value for the session-cookie signing secret. Set before any
# `from daydream.server import app` runs, so SessionMiddleware never triggers
# the on-disk fallback during tests.
os.environ.setdefault("DAYDREAM_SESSION_SECRET", "test-session-secret-not-for-production")

# Stable test value for the shared site password. Decoupled from whatever
# .env holds in production so tests never depend on or leak the real value.
# Force-override for the same reason DAYDREAM_ACCESS does: a developer
# .env sourced by `bin/game test` would otherwise set DAYDREAM_PASSWORD
# to the real value and tests' hardcoded "test-password" would fail auth.
os.environ["DAYDREAM_PASSWORD"] = "test-password"

# TestClient connects from "testclient" (not a real IP). Bypass the
# AccessMiddleware in tests so we don't have to forge a tailnet IP for
# every TestClient call. tests/test_access_middleware.py exercises the
# middleware contract directly with mocked scope.client.
#
# Force-override (not setdefault): when `bin/game test` sources the
# project .env before running pytest, a developer's DAYDREAM_ACCESS=
# tailscale would otherwise leak into TestClient boots and cause 403s.
# Test-wide invariant wins over caller env here; per-test tailscale
# exercises go through monkeypatch.setenv as they already do.
os.environ["DAYDREAM_ACCESS"] = "public"

# Drift loop emits soft narrate events every 5-30 minutes by default.
# In a test run nothing would fire (sleep intervals are far above test
# wall-clock budgets), but the asyncio.Task gets created on every
# TestClient lifespan startup and adds noise to traceback output if
# the test happens to fail during cleanup. Disable by default; tests
# that exercise drift opt in via monkeypatch.setenv.
os.environ["DAYDREAM_DRIFT_ENABLED"] = "0"

# LLM-driven drift narrates default ON in production but OFF in tests:
# the existing 5 drift tests exercise the canned-pool path, and tests
# that exercise the LLM path opt in via monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
# AND mock daydream.llm.client.acompletion_json. Without this default,
# any drift tick fired by a TestClient lifespan would try to import
# litellm and contact a vLLM endpoint.
os.environ["DAYDREAM_DRIFT_LLM_ENABLED"] = "0"

# Mood-affecting drift defaults ON in production (drift narrates
# probabilistically nudge `toons.mood`) but OFF in tests so existing
# drift tests don't see surprise mood transitions perturbing their
# DB-state assertions. Tests that exercise the mood-drift path opt in
# via monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "1")
# and seed an RNG that makes the probability roll deterministic.
os.environ["DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED"] = "0"

# NPC memory subsystem (capture + retrieve via BGE-small on CPU). Off
# by default in tests so the existing 16 Rook/Iris dialogue tests don't
# pay the embedder cost or load sentence-transformers; tests that
# exercise memory opt in via monkeypatch.setenv("DAYDREAM_MEMORY_ENABLED", "1")
# AND mock daydream.memories._embed to avoid loading the real model.
os.environ["DAYDREAM_MEMORY_ENABLED"] = "0"

# Redirect HOME to a session-scoped temp dir as a belt-and-suspenders measure:
# any other code that resolves `~/...` during tests writes under this dir,
# which the OS reaps. Use mkdtemp (not TemporaryDirectory) so the dir lives
# for the whole pytest process; pytest's own tmp_path fixture is unaffected.
os.environ.setdefault("HOME", tempfile.mkdtemp(prefix="daydream-test-home-"))


@pytest.fixture(autouse=True)
def _no_real_image_gen(request, monkeypatch):
    """Suppress the WS auto-enqueue path so tests never fire ComfyUI.

    Tests that exercise the image-gen flow opt out via the
    @pytest.mark.real_image_gen marker; they are then responsible for
    mocking daydream.images.client.generate_image themselves."""
    if request.node.get_closest_marker("real_image_gen"):
        return
    monkeypatch.setattr("daydream.api.ws._generate_and_emit", AsyncMock(return_value=None))


@pytest.fixture(autouse=True)
def _reset_arbiter():
    """The GPU arbiter is a process-wide singleton; reset between tests so
    a leaked acquire in one test cannot block the next."""
    from daydream.gpu import arbiter

    arbiter.reset()
    yield
    arbiter.reset()


@pytest.fixture(autouse=True)
def _reset_in_flight():
    """The WS layer dedups in-flight image gen via a module-level set;
    reset between tests so prior state never bleeds through."""
    from daydream.api import ws

    ws.reset_in_flight()
    yield
    ws.reset_in_flight()


# ---- operational target + engine liveness ------------------------------
#
# Two scaffolds landing together:
# 1. _resolve_target: skip tier_medium/tier_long tests cleanly when the
#    DAYDREAM_TARGET is not 'local'. Probes for staging / prod_verify
#    are scaffolded for a later commit; until then, the skip reason
#    makes the gap explicit instead of running a local-only test
#    against a remote env and erroring mysteriously.
# 2. _vllm_live / _comfyui_live: one HTTP probe per session, cached.
#    Tests carrying requires_vllm / requires_comfyui consult the cached
#    result via _check_required_engines and skip with a clear reason
#    when the engine is not reachable.


@pytest.fixture(autouse=True)
def _resolve_target(request):
    """Skip tier_medium / tier_long tests when the operational target
    is not 'local'. tier_short is target-agnostic; never skipped here."""
    from daydream import config

    t = config.target()
    if t == "local":
        return
    for tier in ("tier_medium", "tier_long"):
        if request.node.get_closest_marker(tier):
            pytest.skip(f"{t} target not yet wired for {tier} tests")


@pytest.fixture(scope="session")
def _vllm_live() -> bool:
    """One-shot liveness probe for vLLM. Cached per session, reused by
    every requires_vllm test; no test pays the HTTP cost more than once.
    Short 2s timeout so 'not running' doesn't stall test start-up."""
    from daydream import config

    url = config.llm_base_url().rstrip("/") + "/models"
    try:
        r = httpx.get(url, timeout=2.0)
        return r.status_code < 500
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session")
def _comfyui_live() -> bool:
    """One-shot liveness probe for ComfyUI. Cached per session."""
    from daydream import config

    url = config.comfyui_base_url().rstrip("/") + "/system_stats"
    try:
        r = httpx.get(url, timeout=2.0)
        return r.status_code < 500
    except httpx.HTTPError:
        return False


@pytest.fixture(autouse=True)
def _check_required_engines(request):
    """Gate tests carrying requires_vllm / requires_comfyui markers on
    the session-scoped liveness probes. Lazy fixture resolution: the
    HTTP probe only runs when a test actually needs it. Without the
    marker, this is a no-op."""
    from daydream import config

    if request.node.get_closest_marker("requires_vllm"):
        if not request.getfixturevalue("_vllm_live"):
            pytest.skip(f"vLLM unreachable at {config.llm_base_url()}")
    if request.node.get_closest_marker("requires_comfyui"):
        if not request.getfixturevalue("_comfyui_live"):
            pytest.skip(f"ComfyUI unreachable at {config.comfyui_base_url()}")
