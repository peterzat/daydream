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
        # Give the toon a carried thing (located on the toon via location_id,
        # the self-referential FK delete must satisfy before removing the toon).
        from daydream import objects
        objects.spawn(
            "w-bunny", "thing", "a pebble", toon_id,
            prototype_id=objects.PROTO_THING,
            properties={"seed": "smooth"}, object_id="o-test",
        )
        room_id = toons.get_toon(toon_id).current_room_id
        # Delete must not FK-fail; the carried thing is reparented to the room
        # (dropped), not destroyed, so no child references the deleted toon.
        assert client.post("/api/slots/5/delete").status_code == 200
        assert toons.get_toon(toon_id) is None
        assert objects.get("o-test").location_id == room_id


def test_delete_drops_carried_items_into_room():
    """A deleted toon's belongings are dropped into its current room so they
    persist in the world to be found, not destroyed with the toon
    (BACKLOG toon-delete-drops-items)."""
    from daydream import objects

    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/slots/2/create", json={"name": "Fenn", "appearance_seed": "a thistle"}
        )
        toon_id = r.json()["id"]
        room_id = toons.get_toon(toon_id).current_room_id
        assert room_id is not None
        objects.spawn(
            "w-bunny", "thing", "a copper key", toon_id,
            prototype_id=objects.PROTO_THING,
            properties={"seed": "tarnished"}, object_id="o-key",
        )

        assert client.post("/api/slots/2/delete").status_code == 200
        # The toon is gone, but its key now rests on the ground in the room.
        assert toons.get_toon(toon_id) is None
        key = objects.get("o-key")
        assert key is not None
        assert key.location_id == room_id
        assert "o-key" in objects.content_ids(room_id, "thing")
