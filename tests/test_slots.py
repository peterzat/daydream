"""Slot-picker API: list / create / claim / kick + concurrent-create
atomicity. Mirrors the SPEC 2026-05-07 toon-slot-management contract."""

from __future__ import annotations

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
    """Push the session through /api/login so the cookie is set and the
    session has the per-session UUID stamped by `_ensure_session_id`."""
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)


def test_list_slots_returns_5_entries():
    """The seeded world has Wren at slot 1; the listing returns 5 slot
    entries with Wren in slot 1 and the rest empty."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/api/slots")
        assert r.status_code == 200
        body = r.json()
        slots = body["slots"]
        assert len(slots) == 5
        assert [s["slot"] for s in slots] == [1, 2, 3, 4, 5]
        wren = slots[0]["toon"]
        assert wren is not None
        assert wren["name"] == "Wren"
        assert wren["claimed_by_me"] is False  # seeded as is_human_controlled=0
        for s in slots[1:]:
            assert s["toon"] is None


def test_create_in_empty_slot_creates_toon_and_claims_session():
    """POST /api/slots/3/create with valid body creates the toon and
    sets the requester's session as the controller."""
    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/slots/3/create",
            json={"name": "Mira", "appearance_seed": "a fox in a wool hat"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Mira"
        assert body["slot"] == 3
        assert body["is_human_controlled"] is True
        assert body["claimed_by_me"] is True
        assert body["kicked_at"] is None

        # And it shows up in the listing.
        r = client.get("/api/slots")
        slots = r.json()["slots"]
        assert slots[2]["toon"]["name"] == "Mira"
        assert slots[2]["toon"]["claimed_by_me"] is True


def test_create_on_populated_slot_returns_409():
    """Creating in slot 1 fails because Wren is already there."""
    with TestClient(app) as client:
        _login(client)
        r = client.post(
            "/api/slots/1/create",
            json={"name": "Stowaway", "appearance_seed": "a quiet stranger"},
        )
        assert r.status_code == 409


def test_create_with_invalid_input_returns_400():
    """Empty / missing / non-string name or appearance_seed → 400."""
    with TestClient(app) as client:
        _login(client)
        # Missing name.
        r = client.post(
            "/api/slots/2/create",
            json={"appearance_seed": "a friend"},
        )
        assert r.status_code == 400
        # Whitespace-only name.
        r = client.post(
            "/api/slots/2/create",
            json={"name": "   ", "appearance_seed": "x"},
        )
        assert r.status_code == 400
        # Empty appearance.
        r = client.post(
            "/api/slots/2/create",
            json={"name": "Mira", "appearance_seed": ""},
        )
        assert r.status_code == 400


def test_create_with_out_of_range_slot_returns_404():
    """Slot 0 / 6 / 100 are out of the human range; 404."""
    with TestClient(app) as client:
        _login(client)
        for bad in (0, 6, 100):
            r = client.post(
                f"/api/slots/{bad}/create",
                json={"name": "X", "appearance_seed": "y"},
            )
            assert r.status_code == 404, f"slot {bad} should 404"


def test_kick_clears_claim_and_sets_kicked_at():
    """Kick a slot's toon → controller_session NULL, is_human_controlled
    0, kicked_at set. Subsequent listing reflects the new state."""
    with TestClient(app) as client:
        _login(client)
        # Create at slot 4, then kick.
        client.post(
            "/api/slots/4/create",
            json={"name": "Mira", "appearance_seed": "a small fox"},
        )
        r = client.post("/api/slots/4/kick")
        assert r.status_code == 200
        body = r.json()
        assert body["is_human_controlled"] is False
        assert body["kicked_at"] is not None
        assert body["claimed_by_me"] is False
        # Inventory + room preserved.
        assert body["current_room_id"] == "r-meadow"


def test_kick_on_empty_slot_returns_404():
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/slots/2/kick")
        assert r.status_code == 404


def test_claim_on_kicked_npc_re_adopts():
    """Kick a created toon, then claim it again — the toon's
    kicked_at is cleared and is_human_controlled flips back to 1."""
    with TestClient(app) as client:
        _login(client)
        client.post(
            "/api/slots/2/create",
            json={"name": "Mira", "appearance_seed": "a small fox"},
        )
        client.post("/api/slots/2/kick")
        r = client.post("/api/slots/2/claim")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kicked_at"] is None
        assert body["is_human_controlled"] is True
        assert body["claimed_by_me"] is True


def test_claim_on_empty_slot_returns_404():
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/slots/3/claim")
        assert r.status_code == 404


def test_claim_controlled_by_live_session_returns_409(monkeypatch):
    """A toon held by a session with a LIVE WS connection is protected: a claim
    from another session is refused with 409 (kick first)."""
    from daydream.api import ws as ws_mod

    with TestClient(app) as client:
        _login(client)
        client.post(
            "/api/slots/2/create",
            json={"name": "Mira", "appearance_seed": "a small fox"},
        )
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: True)
        r = client.post("/api/slots/2/claim")
        assert r.status_code == 409


def test_claim_takes_over_when_controller_not_live(monkeypatch):
    """A toon whose controlling session has NO live WS connection (an abandoned
    claim, e.g. the tab was closed) is reclaimable: the claim succeeds
    (takeover) rather than 409."""
    from daydream.api import ws as ws_mod

    with TestClient(app) as client:
        _login(client)
        client.post(
            "/api/slots/2/create",
            json={"name": "Mira", "appearance_seed": "a small fox"},
        )
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: False)
        r = client.post("/api/slots/2/claim")
        assert r.status_code == 200, r.text
        assert r.json()["claimed_by_me"] is True


def test_kicked_toon_keeps_inventory_and_memories():
    """Per the spec: kick preserves current_room_id, inventory_json,
    mood, and any accrued memories. The kicked toon row stays intact
    except for controller_session, is_human_controlled, kicked_at."""
    with TestClient(app) as client:
        _login(client)
        client.post(
            "/api/slots/3/create",
            json={"name": "Mira", "appearance_seed": "a small fox"},
        )
        # Inspect via the toons module directly (bypass the API).
        slots = toons.get_human_slots(session_id=None)
        before = slots[2]["toon"]
        before_id = before["id"]
        before_room = before["current_room_id"]
        before_mood = before["mood"]

        client.post("/api/slots/3/kick")

        after = toons.get_toon(before_id)
        assert after is not None
        assert after.current_room_id == before_room
        assert after.mood == before_mood
        assert after.inventory == []  # what we created with
        # And the row is still findable in the slot listing.
        slots_after = toons.get_human_slots(session_id=None)
        assert slots_after[2]["toon"]["id"] == before_id
        assert slots_after[2]["toon"]["kicked_at"] is not None


def test_npc_slots_100_plus_excluded_from_picker():
    """Hand-authored NPCs in slots 100 (Rook) and 101 (Iris) are not
    in the slot listing, can't be created in (would 404), can't be
    claimed/kicked through the API."""
    with TestClient(app) as client:
        _login(client)
        body = client.get("/api/slots").json()
        # No slot 100 in the listing.
        slot_nums = [s["slot"] for s in body["slots"]]
        assert 100 not in slot_nums
        assert 101 not in slot_nums
        # Out-of-range create / claim / kick on 100 → 404.
        assert client.post(
            "/api/slots/100/create",
            json={"name": "X", "appearance_seed": "y"},
        ).status_code == 404
        assert client.post("/api/slots/100/claim").status_code == 404
        assert client.post("/api/slots/100/kick").status_code == 404


def test_session_isolation_for_claimed_by_me():
    """Two TestClient instances see each other's claims as
    `claimed_by_me: false`."""
    with TestClient(app) as client_a:
        _login(client_a)
        client_a.post(
            "/api/slots/2/create",
            json={"name": "Mira", "appearance_seed": "a small fox"},
        )

        with TestClient(app) as client_b:
            _login(client_b)
            slots = client_b.get("/api/slots").json()["slots"]
            entry = slots[1]
            assert entry["toon"]["name"] == "Mira"
            assert entry["toon"]["claimed_by_me"] is False


def test_toon_creation_follows_the_live_world(tmp_path):
    """The swap-rehearsal regression (criterion 15): in a DB whose single
    world is NOT the legacy default, slot listing, creation, and claiming
    must all resolve THAT world — a hardcoded world id turns every picker
    action into a foreign-key 500 the moment `world swap` installs a new
    world."""
    from daydream import db as ddb
    from daydream import objects, toons

    ddb.close_db()
    ddb.init_live(path=tmp_path / "other-world.db")
    conn = ddb.get_conn()
    # A `world load`ed DB holds exactly ONE world: the loader removes the
    # migration-seeded default (keeping the prototype rows). Mirror that.
    conn.execute(
        "INSERT INTO worlds (id, name, slug, aesthetic_seed, starting_room_id) "
        "VALUES ('w-elsewhere', 'Elsewhere', 'elsewhere', 'seed', 'r-first')"
    )
    conn.execute(
        "UPDATE objects SET world_id = 'w-elsewhere' WHERE kind = 'prototype'"
    )
    for child in ("events", "memories", "generated_assets", "world_state"):
        conn.execute(f"DELETE FROM {child}")
    conn.execute("DELETE FROM objects WHERE kind != 'prototype'")
    conn.execute("DELETE FROM worlds WHERE id != 'w-elsewhere'")
    objects.spawn("w-elsewhere", "room", "First Room", None,
                  properties={"slug": "first", "seed": "s", "exits": {}},
                  object_id="r-first")
    assert toons.live_world_id() == "w-elsewhere"

    created = toons.create_toon_in_slot(2, "Visitor", "a traveler", "sess-x")
    assert created is not None
    assert created.world_id == "w-elsewhere"
    assert created.current_room_id == "r-first"
    slots = toons.get_human_slots("sess-x")
    assert slots[1]["toon"]["name"] == "Visitor"
    ddb.close_db()
