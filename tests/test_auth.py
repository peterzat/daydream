"""Auth: password gate, session cookie, redirect behavior. SPEC criterion 2."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.server import app


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
