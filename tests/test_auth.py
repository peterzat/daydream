"""Auth: password gate, session cookie, redirect behavior. SPEC criterion 2."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.server import app

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def test_root_unauthed_redirects_to_login():
    with TestClient(app, follow_redirects=False) as client:
        r = client.get("/")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_login_form_renders():
    with TestClient(app) as client:
        r = client.get("/login")
    assert r.status_code == 200
    assert '<title>daydream</title>' in r.text
    assert 'name="password"' in r.text
    assert '>enter</button>' in r.text


def test_login_with_correct_password_redirects_and_authes():
    with TestClient(app, follow_redirects=False) as client:
        r = client.post("/api/login", data={"password": "test-password"})
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        # Same client (cookies persisted) can now reach root:
        r2 = client.get("/")
        assert r2.status_code == 200
        assert "daydream" in r2.text.lower()


def test_login_with_wrong_password_does_not_grant_access():
    with TestClient(app, follow_redirects=False) as client:
        r = client.post("/api/login", data={"password": "wrong-password"})
        assert r.status_code == 401
        # Subsequent root request still redirects to login: cookie did not auth.
        r2 = client.get("/")
        assert r2.status_code == 302
        assert r2.headers["location"] == "/login"


def test_no_password_configured_returns_503(monkeypatch):
    """When DAYDREAM_PASSWORD is unset/empty, the auth endpoint refuses every
    login (including an empty form value) so the published source default
    cannot grant access."""
    monkeypatch.setenv("DAYDREAM_PASSWORD", "")
    with TestClient(app, follow_redirects=False) as client:
        r1 = client.post("/api/login", data={"password": ""})
        r2 = client.post("/api/login", data={"password": "anything"})
    assert r1.status_code == 503
    assert r2.status_code == 503


def test_logout_clears_session():
    with TestClient(app, follow_redirects=False) as client:
        client.post("/api/login", data={"password": "test-password"})
        r = client.post("/api/logout")
        assert r.status_code == 303
        r2 = client.get("/")
        assert r2.status_code == 302
        assert r2.headers["location"] == "/login"


# ---- tailscale mode: password bypassed ----------------------------------
#
# In DAYDREAM_ACCESS=tailscale (the default), tailnet membership IS the
# auth: the AccessMiddleware rejects any non-tailnet source IP at the
# outer edge, so by the time a request reaches the auth layer the
# password would be belt-and-suspenders that costs UX every login.
#
# These tests exercise the full TestClient integration path in
# tailscale mode by monkey-patching daydream.api.access.is_tailscale_or_local
# to always return True. That's what simulates "TestClient came in from
# the tailnet" without having to forge ASGI client tuples; the middleware
# contract itself is covered by tests/test_access_middleware.py.


def _make_tailnet(monkeypatch):
    from daydream.api import access
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    # AccessMiddleware caches nothing; each request re-reads access_mode.
    # Flip the CGNAT check so TestClient's synthetic source IP passes.
    monkeypatch.setattr(access, "is_tailscale_or_local", lambda host: True)


def test_is_authed_returns_true_in_tailscale_regardless_of_session(monkeypatch):
    """The unit-level contract: tailscale mode skips the session check."""
    from daydream.api.auth import is_authed
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    assert is_authed({}) is True
    assert is_authed({"authed": False}) is True
    assert is_authed({"authed": True}) is True


def test_is_authed_requires_session_in_public_mode(monkeypatch):
    from daydream.api.auth import is_authed
    monkeypatch.setenv("DAYDREAM_ACCESS", "public")
    assert is_authed({}) is False
    assert is_authed({"authed": False}) is False
    assert is_authed({"authed": True}) is True


def test_tailscale_root_serves_spa_without_login(monkeypatch):
    """GET / in tailscale mode serves the SPA directly — no redirect to
    /login. The user's main request: don't show the 'mellon' prompt."""
    _make_tailnet(monkeypatch)
    with TestClient(app, follow_redirects=False) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert "daydream" in r.text.lower()


def test_tailscale_login_form_redirects_home(monkeypatch):
    """GET /login in tailscale mode redirects to / rather than rendering
    a password form a tailnet user can't usefully submit. Covers stale
    bookmarks and any cached link."""
    _make_tailnet(monkeypatch)
    with TestClient(app, follow_redirects=False) as client:
        r = client.get("/login")
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_tailscale_login_post_succeeds_regardless_of_password(monkeypatch):
    """A cached login form that somehow still gets submitted must not
    bounce the user with 401 — the auth model has changed under them.
    Tailscale mode accepts any POST to /api/login and hands back a
    session + redirect home."""
    _make_tailnet(monkeypatch)
    with TestClient(app, follow_redirects=False) as client:
        r = client.post("/api/login", data={"password": "anything-or-nothing"})
        assert r.status_code == 303
        assert r.headers["location"] == "/"


def test_tailscale_ws_accepts_without_prior_login(monkeypatch):
    """WebSocket endpoint uses the same is_authed helper; tailscale mode
    means no session cookie is required. The connection is ACCEPTED (not
    closed 1008); with no claimed toon it routes to the character picker
    (a `needs_toon` frame) under picker-first entry (SPEC 2026-06-30),
    rather than auto-controlling a default toon."""
    from starlette.websockets import WebSocketDisconnect
    _make_tailnet(monkeypatch)
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws") as ws:
                frame = ws.receive_json()
            assert frame == {"kind": "needs_toon"}
        except WebSocketDisconnect as e:
            raise AssertionError(
                f"tailscale WS should accept without login, got disconnect {e}"
            ) from e


def test_tailscale_logout_redirects_home_not_to_login(monkeypatch):
    """POST /api/logout in tailscale mode is a de-facto no-op (the very
    next request re-authes), so the redirect should go home rather
    than to a login form that will itself bounce home."""
    _make_tailnet(monkeypatch)
    with TestClient(app, follow_redirects=False) as client:
        r = client.post("/api/logout")
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_public_mode_still_requires_login(monkeypatch):
    """Belt-and-suspenders for the public-mode contract: nothing the
    tailscale branch does should leak into the public-mode password
    gate. Explicit public mode + wrong password still 401s."""
    monkeypatch.setenv("DAYDREAM_ACCESS", "public")
    with TestClient(app, follow_redirects=False) as client:
        r = client.post("/api/login", data={"password": "wrong"})
    assert r.status_code == 401
