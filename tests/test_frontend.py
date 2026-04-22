"""Frontend assets: SPA shell, watercolor PNG, JS/CSS served. SPEC criterion 9
plus the SPA-load half of criterion 4."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.server import app

WEB = Path(__file__).resolve().parent.parent / "web"


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "REDACTED"})
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


def test_style_css_served_with_cozy_palette():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert r.status_code == 200
    # Sage/cream palette tokens locked in by the WHIMSY anchor.
    assert "--sage" in r.text
    assert "--paper" in r.text
