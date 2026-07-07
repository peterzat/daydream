"""The appearance_seed input gates on POST /api/slots/{slot}/create
(codereview WARN 2026-07-07).

appearance_seed is an SDXL prompt rendered into portraits visible to
co-located players and every picker viewer, so create_slot mirrors the
growth-phrase gates: a length cap (MAX_APPEARANCE_SEED_CHARS) and the
WHIMSY input banlist (safety.first_banned), each rejected with a 400
before any toon is created. Loader-authored NPC seeds are design-time
and unaffected."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events, toons
from daydream.api import slots as slots_module
from daydream.api import ws as ws_module
from daydream.server import app

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
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)


def test_over_cap_seed_rejected_400():
    with TestClient(app) as client:
        _login(client)
        long_seed = "a" * (slots_module.MAX_APPEARANCE_SEED_CHARS + 1)
        r = client.post(
            "/api/slots/2/create",
            json={"name": "Fern", "appearance_seed": long_seed},
        )
        assert r.status_code == 400
        assert toons.get_toon_in_slot(2) is None


def test_banned_word_seed_rejected_400():
    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/slots/2/create",
            json={"name": "Fern", "appearance_seed": "a grimdark wraith of smoke"},
        )
        assert r.status_code == 400
        assert toons.get_toon_in_slot(2) is None


def test_at_cap_benign_seed_accepted():
    """Boundary: exactly MAX_APPEARANCE_SEED_CHARS benign chars creates."""
    with TestClient(app) as client:
        _login(client)
        seed = ("a wisp of dusk " * 30)[: slots_module.MAX_APPEARANCE_SEED_CHARS]
        assert len(seed) == slots_module.MAX_APPEARANCE_SEED_CHARS
        r = client.post(
            "/api/slots/2/create",
            json={"name": "Fern", "appearance_seed": seed},
        )
        assert r.status_code == 200
        assert toons.get_toon_in_slot(2) is not None
