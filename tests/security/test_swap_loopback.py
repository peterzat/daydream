"""The world-swap loopback gate.

`POST /api/world/swap` replaces the entire live world; its only real
client is `bin/game world swap` running on the box. Tailnet membership
(the friend-scope gate) is not enough — a non-loopback peer gets 403
before any target validation runs. tests/test_ws_swap.py covers the
loopback happy paths (its clients present loopback peers)."""

from __future__ import annotations

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


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)


def test_non_loopback_peer_gets_403():
    """An authed tailnet peer (any non-loopback address) may not swap."""
    with TestClient(app, client=("100.64.0.7", 40000)) as client:
        _login(client)
        r = client.post("/api/world/swap", json={"target": "whatever.db"})
    assert r.status_code == 403
    assert "loopback" in r.json()["error"]


def test_loopback_peer_passes_the_gate():
    """A loopback caller reaches target validation (400 on a bad target,
    not 403 — the gate itself admitted the request)."""
    with TestClient(app, client=("127.0.0.1", 40000)) as client:
        _login(client)
        r = client.post("/api/world/swap", json={"target": "no-such.db"})
    assert r.status_code != 403


def test_unauthenticated_still_401_first():
    with TestClient(app, client=("127.0.0.1", 40000)) as client:
        r = client.post("/api/world/swap", json={"target": "x.db"})
    assert r.status_code == 401
