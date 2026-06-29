"""Permanent toon delete (SPEC 2026-06-29, session-presence-polish).

A new path removes a human toon entirely and frees its slot, alongside the
existing recoverable kick/rest, handling the toon's dependent rows."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events, toons
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


def test_delete_removes_toon_and_frees_slot():
    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/slots/3/create", json={"name": "Bram", "appearance_seed": "a reed"}
        )
        assert r.status_code == 200, r.text
        toon_id = r.json()["id"]

        r = client.post("/api/slots/3/delete")
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] == toon_id

        # Slot reads empty (distinct from kick, which leaves a resting row).
        slot3 = next(s for s in client.get("/api/slots").json()["slots"] if s["slot"] == 3)
        assert slot3["toon"] is None
        assert toons.get_toon(toon_id) is None  # row gone


def test_delete_refuses_empty_and_out_of_range_slots():
    with TestClient(app) as client:
        _login(client)
        assert client.post("/api/slots/4/delete").status_code == 404  # empty
        assert client.post("/api/slots/9/delete").status_code == 404  # out of range


def test_delete_handles_carried_items_without_fk_error():
    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/slots/5/create", json={"name": "Mossy", "appearance_seed": "a fern"}
        )
        toon_id = r.json()["id"]
        # Give the toon a carried item (items.toon_id FKs toons(id)).
        db.get_conn().execute(
            "INSERT INTO items (id, world_id, name, seed, room_id, toon_id) "
            "VALUES ('it-test', 'w-bunny', 'a pebble', 'smooth', NULL, ?)",
            (toon_id,),
        )
        # Delete must not FK-fail; the carried item goes with the toon.
        assert client.post("/api/slots/5/delete").status_code == 200
        assert db.get_conn().execute(
            "SELECT 1 FROM items WHERE id = 'it-test'"
        ).fetchone() is None
        assert toons.get_toon(toon_id) is None
