"""CSRF Origin-check middleware (daydream/api/csrf.py).

State-changing POSTs from a cross-origin browser context are rejected — the
confused-deputy / CSRF vector against the friend-scope slot+session endpoints,
which in the default tailscale mode have no cookie check. Requests with no
Origin/Referer (non-browser clients: the world-swap CLI, the test suite) pass
through untouched, and safe methods (the WS upgrade GET, reads) are never gated.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.api.csrf import origin_allows
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


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303), f"login failed: {r.status_code} {r.text}"


def test_cross_origin_post_is_rejected():
    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/session/leave", headers={"origin": "http://evil.example"}
        )
        assert r.status_code == 403
        assert "cross-origin" in r.text.lower()


def test_same_origin_post_is_allowed():
    # TestClient's Host is "testserver"; a matching Origin passes the gate and
    # the endpoint runs normally.
    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/session/leave", headers={"origin": "http://testserver"}
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True


def test_post_without_origin_is_allowed():
    # Non-browser clients (the world-swap CLI over urllib, curl, the test
    # suite) send no Origin and must not be gated.
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/session/leave")  # no Origin header
        assert r.status_code == 200


def test_safe_method_with_foreign_origin_is_allowed():
    # GET is never gated (the WS upgrade is a GET; reads are safe).
    with TestClient(app) as client:
        _login(client)
        r = client.get("/api/slots", headers={"origin": "http://evil.example"})
        assert r.status_code == 200


def test_cross_origin_delete_rejected_before_the_route_runs():
    # The middleware short-circuits before auth/route logic, so even the
    # irreversible delete is closed to the confused deputy. No login: a 403
    # from the middleware, not a 401/404 from the handler.
    with TestClient(app) as client:
        r = client.post(
            "/api/slots/1/delete", headers={"origin": "http://evil.example"}
        )
        assert r.status_code == 403


def test_origin_allows_unit():
    # Direct unit coverage of the matcher's three cases.
    host = [(b"host", b"box:54321")]
    assert origin_allows(host) is True  # no Origin/Referer -> allow
    assert origin_allows(host + [(b"origin", b"http://box:54321")]) is True
    assert origin_allows(host + [(b"origin", b"http://evil:54321")]) is False
    # Referer fallback when Origin is absent.
    assert origin_allows(host + [(b"referer", b"http://box:54321/x")]) is True
    assert origin_allows(host + [(b"referer", b"http://evil/x")]) is False
