"""Per-world starting room: where a toon wakes after any rest (2026-06-30).

claim/create place the toon in the world's starting room; the helper falls
back to the world's first room when the column is unset/stale."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events, rooms, toons
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


def test_claim_wakes_toon_in_starting_room():
    with TestClient(app) as client:
        _login(client)
        toon_id = client.post(
            "/api/slots/2/create", json={"name": "Fen", "appearance_seed": "a wisp"}
        ).json()["id"]
        start = rooms.starting_room_id("w-bunny")
        assert start == "r-meadow"  # seeded by migration 010

        # Move away, rest (leave), then wake by re-claiming.
        toons.set_current_room(toon_id, "r-forge")
        client.post("/api/session/leave")
        assert client.post("/api/slots/2/claim").status_code == 200

        woke = toons.get_toon(toon_id)
        assert woke.current_room_id == start  # woke in the starting room
        assert woke.current_room_id != "r-forge"


def test_create_spawns_in_starting_room():
    with TestClient(app) as client:
        _login(client)
        toon_id = client.post(
            "/api/slots/3/create", json={"name": "Bram", "appearance_seed": "a reed"}
        ).json()["id"]
        assert toons.get_toon(toon_id).current_room_id == rooms.starting_room_id("w-bunny")


def test_starting_room_falls_back_to_first_room_when_unset():
    with TestClient(app):
        db.get_conn().execute(
            "UPDATE worlds SET starting_room_id = NULL WHERE id = 'w-bunny'"
        )
        first = db.get_conn().execute(
            "SELECT id FROM objects WHERE kind = 'room' AND world_id = 'w-bunny' "
            "ORDER BY id LIMIT 1"
        ).fetchone()[0]
        assert rooms.starting_room_id("w-bunny") == first
