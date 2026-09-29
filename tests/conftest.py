"""Project-wide pytest configuration. Loaded before any test module is
collected, so env vars set here are visible to module-level imports such as
`daydream.server.app`."""

import os
import tempfile
from unittest.mock import AsyncMock

import httpx
import pytest

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

# The retell layer (criterion 13) is additive polish: off by default in
# tests so the deterministic spine stays provably LLM-free (the zork
# walkthrough's zero-call spy is the teeth). Retell tests opt in via
# monkeypatch.setenv("DAYDREAM_RETELL_ENABLED", "1") and mock the client.
os.environ["DAYDREAM_RETELL_ENABLED"] = "0"

# The dream journal (leave-triggered recap, SPEC 2026-07-07) defaults ON in
# production but OFF in tests: the leave endpoint fires a background LLM
# task, and every session-lifecycle test would otherwise race one. Journal
# tests opt in via monkeypatch.setenv("DAYDREAM_JOURNAL_ENABLED", "1") AND
# mock daydream.llm.client.acompletion_json.
os.environ["DAYDREAM_JOURNAL_ENABLED"] = "0"

# The village loop (real-time phase processing) and the director's LLM
# ranking default ON in production, OFF in tests: with no loop running, every
# command runs the deterministic catch-up itself (fake clock), so story tests
# and walkthroughs stay LLM-free and time-pinned (SPEC 2026-09-26).
os.environ["DAYDREAM_VILLAGE_ENABLED"] = "0"
os.environ["DAYDREAM_DIRECTOR_LLM"] = "0"

# Accounts (SPEC 2026-09-27): argon2id's production profile costs 64 MiB and
# tens of milliseconds per hash; the suite uses a cheap profile. Hashes encode
# their own parameters, so nothing else changes.
os.environ["DAYDREAM_PASSWORD_HASH_PROFILE"] = "test"

# Redirect HOME to a session-scoped temp dir as a belt-and-suspenders measure:
# any other code that resolves `~/...` during tests writes under this dir,
# which the OS reaps. Use mkdtemp (not TemporaryDirectory) so the dir lives
# for the whole pytest process; pytest's own tmp_path fixture is unaffected.
os.environ.setdefault("HOME", tempfile.mkdtemp(prefix="daydream-test-home-"))

# Never the real data dir. HOME above is only a default (it is already set in
# a normal shell), so a test that boots the app without its own
# DAYDREAM_DATA_DIR used to open the operator's real ~/data/daydream live world
# and accounts DB (found 2026-09-27: a test admin account appeared in the dev
# accounts DB). Force a throwaway dir for the whole run; tests that set their
# own via monkeypatch still win.
os.environ["DAYDREAM_DATA_DIR"] = tempfile.mkdtemp(prefix="daydream-test-data-")

# No cross-process GPU lock in the suite (it would be the prod install's real
# file); tests of that layer name their own lock path.
os.environ["DAYDREAM_GPU_LOCK"] = ""


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
def _no_real_llm(request, monkeypatch):
    """Point the LLM at an unreachable port for every test that hasn't opted
    into the real engine (@pytest.mark.requires_vllm), so the GPU-free tiers
    behave identically with engines up or down.

    The first-ever CI run (2026-07-07, no engines) caught five say-tests that
    had been silently grounding through the dev box's LIVE vLLM — the
    documented contract ("mock the LLM client") had no enforcement. Tests
    that mock daydream.llm.client.acompletion_json never notice this; an
    unmocked, unmarked call now degrades to LLMUnavailable/foggy in every
    environment instead of only in CI."""
    if request.node.get_closest_marker("requires_vllm"):
        return
    monkeypatch.setenv("DAYDREAM_LLM_BASE_URL", "http://127.0.0.1:9/v1")


@pytest.fixture(autouse=True)
def _reset_arbiter():
    """The GPU arbiter is a process-wide singleton; reset between tests so
    a leaked acquire in one test cannot block the next."""
    from daydream.gpu import arbiter

    arbiter.reset()
    yield
    arbiter.reset()


@pytest.fixture(autouse=True)
def _reset_accounts():
    """The accounts DB connection is a process-wide singleton bound to the
    data dir current when it opened; close it around every test so each test's
    DAYDREAM_DATA_DIR gets its own accounts database."""
    from daydream import accounts

    accounts.close()
    yield
    accounts.close()


@pytest.fixture(autouse=True)
def _no_github(monkeypatch):
    """`bin/game ci` (and prod plan / prod check through it) asks GitHub via
    `gh`; the suite never does. Tests that read CI fake `ci._gh` themselves."""
    monkeypatch.setattr("daydream.ci._gh", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _reset_presence_throttle():
    """Leave/claim/kick share a per-account budget in module state; clear it
    so one test's comings and goings never throttle the next."""
    from daydream.api import slots

    slots.reset_presence_throttle()
    yield
    slots.reset_presence_throttle()


@pytest.fixture(autouse=True)
def _reset_heard_cache():
    """The askable-subject vocabulary is cached in module state; clear it so
    a test that rebuilds a world with other topics never reads the last one's."""
    from daydream import heard

    heard.clear_cache()
    yield
    heard.clear_cache()


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

    if (request.node.get_closest_marker("requires_vllm")
            or request.node.get_closest_marker("requires_comfyui")):
        # A real-GPU test must coordinate with any running daydream (prod,
        # dev) through the shared cross-process lock (criterion 21).
        request.getfixturevalue("monkeypatch").delenv("DAYDREAM_GPU_LOCK", raising=False)
    if request.node.get_closest_marker("requires_vllm"):
        if not request.getfixturevalue("_vllm_live"):
            pytest.skip(f"vLLM unreachable at {config.llm_base_url()}")
    if request.node.get_closest_marker("requires_comfyui"):
        if not request.getfixturevalue("_comfyui_live"):
            pytest.skip(f"ComfyUI unreachable at {config.comfyui_base_url()}")
