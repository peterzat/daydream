"""The regen-UI kill switch (DAYDREAM_REGEN_UI, BACKLOG regen-ui-gate).

With the flag off, the two repaint endpoints answer 404 — the surface
looks unmounted, not forbidden — and the snapshot's features flag tells
the SPA to keep the plate tools unbound. tests/test_rooms_image.py covers
the flag-on behavior (the default)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.api import ws as ws_module
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    ws_module.reset_in_flight()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()
    ws_module.reset_in_flight()


def _login(client: TestClient) -> None:
    # Repainting is admin-only since the going-live turn; these tests are
    # about the kill switch, so they sign in as an admin.
    authhelp.login(client, "keeper", role="admin")


def test_endpoints_404_when_flag_off(monkeypatch):
    monkeypatch.setenv("DAYDREAM_REGEN_UI", "0")
    with TestClient(app) as client:
        _login(client)
        r = client.get("/api/rooms/r-meadow/image-prompt")
        assert r.status_code == 404
        r = client.post("/api/rooms/r-meadow/image", json={})
        assert r.status_code == 404


def test_signed_out_caller_learns_nothing_about_the_surface(monkeypatch):
    """A signed-out caller gets the sign-in gate's one answer for every
    guarded path, the switched-off surface and a nonexistent path alike, so
    nothing distinguishes them (SPEC 2026-09-27: the account gate runs before
    every handler; this replaced the old 404-before-auth ordering)."""
    monkeypatch.setenv("DAYDREAM_REGEN_UI", "0")
    with TestClient(app) as client:
        a = client.get("/api/rooms/r-meadow/image-prompt")
        b = client.get("/api/rooms/r-meadow/no-such-surface")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_snapshot_features_flag_follows_env(monkeypatch):
    monkeypatch.setenv("DAYDREAM_REGEN_UI", "0")
    with TestClient(app) as client:
        _login(client)
        client.post("/api/slots/1/kick")
        assert client.post("/api/slots/1/claim").status_code == 200
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert snap["features"] == {"regen_ui": False}


def test_snapshot_features_flag_defaults_on():
    with TestClient(app) as client:
        _login(client)
        client.post("/api/slots/1/kick")
        assert client.post("/api/slots/1/claim").status_code == 200
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert snap["features"] == {"regen_ui": True}


def test_spa_gates_plate_tools_on_the_feature_flag():
    """The SPA half of the gate (grep contract, mirroring test_frontend's
    style): the snapshot flag lands in featureRegenUi and showPlateTool
    refuses to reveal the tools without it."""
    src = (Path(__file__).resolve().parents[2] / "web/assets/main.js").read_text()
    assert "featureRegenUi = !!(snap.features && snap.features.regen_ui)" in src
    assert "if (!featureRegenUi) return;" in src


def test_a_player_never_gets_the_repaint_surface():
    """Admin-only (SPEC 2026-09-27 criterion 4): with the flag ON, a player's
    snapshot keeps the tools off and both endpoints refuse with 403."""
    with TestClient(app) as client:
        authhelp.login(client, "wren")
        client.post("/api/slots/1/kick")
        assert client.post("/api/slots/1/claim").status_code == 200
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
        assert snap["features"] == {"regen_ui": False}
        assert client.get("/api/rooms/r-meadow/image-prompt").status_code == 403
        assert client.post("/api/rooms/r-meadow/image", json={}).status_code == 403
