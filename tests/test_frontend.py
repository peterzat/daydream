"""Frontend assets: SPA shell, watercolor PNG, JS/CSS served. SPEC criterion 9
plus the SPA-load half of criterion 4."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.server import app

WEB = Path(__file__).resolve().parent.parent / "web"

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
    assert r.status_code in (200, 303)


def test_authed_root_serves_spa_shell():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert r.status_code == 200
    assert "<title>daydream</title>" in r.text
    assert "/assets/main.js" in r.text
    assert "/assets/style.css" in r.text
    assert "/assets/placeholder-meadow.png" in r.text


def test_placeholder_png_is_committed_and_substantial():
    asset = WEB / "assets" / "placeholder-meadow.png"
    assert asset.exists(), "v0 watercolor placeholder must be committed at web/assets/"
    # Real PNG, not a 1x1 stub: header bytes plus a meaningful payload.
    data = asset.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "must be a real PNG"
    assert len(data) > 5_000, f"placeholder PNG looks too small: {len(data)} bytes"


def test_placeholder_png_served_at_assets():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/placeholder-meadow.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 5_000


def test_main_js_served_with_websocket_logic():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert r.status_code == 200
    assert "WebSocket" in r.text
    assert "state_snapshot" in r.text
    assert "kind" in r.text


def test_main_js_handles_room_image_ready_and_painting_state():
    """SPA hooks for SPEC criterion 5: painting overlay + bg swap."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "room_image_ready" in r.text
    assert "setRoomBackground" in r.text or "image_url" in r.text
    assert "painting-overlay" in r.text


def test_style_css_served_with_cozy_palette():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert r.status_code == 200
    # Sage/cream palette tokens locked in by the WHIMSY anchor.
    assert "--sage" in r.text
    assert "--paper" in r.text


def test_style_css_has_painting_overlay():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert "#painting-overlay" in r.text


def test_index_html_has_painting_overlay_element():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="painting-overlay"' in r.text


def test_logout_link_posts_not_gets():
    """Regression: the logout control must POST (endpoint is POST-only).
    A plain <a href="/api/logout"> GET would produce 405 when clicked,
    so the control has to be a form with method='post'."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'action="/api/logout"' in r.text
    assert 'method="post"' in r.text
    assert ">leave the dream<" in r.text


# ---- no-cache on /assets/ ----------------------------------------------


def test_assets_served_with_no_store_cache_control():
    """Regression for the hard-refresh-after-web-edit workflow. Browsers
    (Safari especially) aggressively cache /assets/main.js; stamping
    Cache-Control: no-store on every /assets/* response lets Cmd+R pick
    up edits without a hard-reload. See daydream/api/nocache.py for why
    the scope is narrow (only /assets/, not /cache/ or the SPA shell)."""
    with TestClient(app) as client:
        _login(client)
        for path in ("/assets/main.js", "/assets/style.css", "/assets/placeholder-meadow.png"):
            r = client.get(path)
            assert r.status_code == 200, f"{path} returned {r.status_code}"
            assert r.headers.get("cache-control") == "no-store", (
                f"{path} has cache-control={r.headers.get('cache-control')!r}"
            )


def test_non_assets_paths_unaffected_by_nocache_middleware():
    """The middleware must NOT touch /, /login, /api/*, or /cache/. Those
    follow FastAPI's default header behavior (no Cache-Control set by
    us). A bug in the path filter that stamped no-store broadly would
    degrade the SPA shell and, in future, cacheability of content-
    addressed generated images."""
    with TestClient(app) as client:
        r = client.get("/login")
        # The login form is a small HTML blob; no Cache-Control from us.
        assert r.headers.get("cache-control") is None
        _login(client)
        r = client.get("/")
        # The SPA shell should also be un-stamped: it's already cheap to
        # fetch (re-pulls /assets/main.js as a child request), and
        # stamping here would fight the OS-level file cache on the box
        # for no benefit.
        assert r.headers.get("cache-control") is None
