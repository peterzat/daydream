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
