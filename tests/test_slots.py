"""Slot-picker API: list / create / claim / kick + concurrent-create
atomicity. Mirrors the SPEC 2026-05-07 toon-slot-management contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events, toons
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _login(client: TestClient, username: str = "tester", role: str = "player") -> None:
    authhelp.login(client, username, role=role)


MIRA = {"name": "Mira", "appearance_seed": "a fox in a wool hat"}
IVO = {"name": "Ivo", "appearance_seed": "a tall heron"}


# ---- the admin's slot view -------------------------------------------------------


def test_list_slots_is_the_admins_view_of_populated_slots():
    """Since accounts (SPEC 2026-09-27 criterion 5) the slot list is an admin
    view of who exists; a player sees only their own toons at /api/dreamer.
    The seeded world has Wren at slot 1 (unowned, resting)."""
    with TestClient(app) as client:
        _login(client)
        assert client.get("/api/slots").status_code == 403
    with TestClient(app) as admin:
        _login(admin, "keeper", role="admin")
        slots = admin.get("/api/slots").json()["slots"]
    assert [s["slot"] for s in slots] == [1]
    wren = slots[0]["toon"]
    assert wren["name"] == "Wren" and wren["owner_account"] is None
    assert wren["claimed_by_me"] is False  # seeded as is_human_controlled=0


# ---- create ---------------------------------------------------------------------------


def test_create_in_empty_slot_creates_an_owned_toon_and_claims_it():
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/slots/3/create", json=MIRA)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Mira" and body["slot"] == 3
        assert body["is_human_controlled"] is True and body["claimed_by_me"] is True
        assert body["kicked_at"] is None
        from daydream import accounts
        assert body["owner_account"] == accounts.get_account("tester")["id"]
        mine = client.get("/api/dreamer").json()
        assert [t["name"] for t in mine["toons"]] == ["Mira"]
        assert mine["can_create"] is False and mine["toons"][0]["claimed_by_me"] is True


def test_dreamer_create_picks_the_next_free_slot():
    with TestClient(app) as client:
        _login(client)
        assert client.get("/api/dreamer").json() == {
            "toons": [], "can_create": True, "display_name": "tester", "is_admin": False}
        r = client.post("/api/dreamer/create", json=MIRA)
        assert r.status_code == 200 and r.json()["slot"] == 2  # Wren holds 1


def test_a_player_holds_one_dreamer_per_world_an_admin_several():
    with TestClient(app) as client:
        _login(client)
        assert client.post("/api/dreamer/create", json=MIRA).status_code == 200
        r = client.post("/api/dreamer/create", json=IVO)
        assert r.status_code == 409 and "already" in r.json()["detail"]
        assert client.post("/api/slots/5/create", json=IVO).status_code == 409
    with TestClient(app) as admin:
        _login(admin, "keeper", role="admin")
        assert admin.post("/api/dreamer/create", json=MIRA).status_code == 200
        assert admin.post("/api/dreamer/create", json=IVO).status_code == 200


def test_twelve_friends_each_hold_a_toon():
    with TestClient(app) as client:
        for i in range(12):
            client.cookies.clear()
            _login(client, f"friend{i:02d}")
            r = client.post("/api/dreamer/create",
                            json={"name": f"Dreamer{i}", "appearance_seed": "a kind face"})
            assert r.status_code == 200, r.text
        owners = {t.owner_account for t in toons._query("owner_account IS NOT NULL", ())}
    assert len(owners) == 12


def test_create_on_populated_slot_returns_409():
    """Creating in slot 1 fails because Wren is already there."""
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/slots/1/create", json={"name": "Stowaway",
                                                    "appearance_seed": "a quiet stranger"})
        assert r.status_code == 409


def test_create_with_invalid_input_returns_400():
    """Empty / missing / non-string name or appearance_seed -> 400."""
    with TestClient(app) as client:
        _login(client)
        assert client.post("/api/slots/2/create", json={"appearance_seed": "a friend"}).status_code == 400
        assert client.post("/api/slots/2/create", json={"name": "   ", "appearance_seed": "x"}).status_code == 400
        assert client.post("/api/slots/2/create", json={"name": "Mira", "appearance_seed": ""}).status_code == 400
        assert client.post("/api/dreamer/create", json={"name": "Mira"}).status_code == 400


def test_create_with_out_of_range_slot_returns_404():
    """Slot 0 and 100+ are outside the human range (1-99): 404."""
    with TestClient(app) as client:
        _login(client)
        for bad in (0, 100, 150):
            r = client.post(f"/api/slots/{bad}/create", json={"name": "X", "appearance_seed": "y"})
            assert r.status_code == 404, f"slot {bad} should 404"


# ---- kick / claim of your own ----------------------------------------------------------


def test_kick_clears_claim_and_sets_kicked_at():
    with TestClient(app) as client:
        _login(client)
        client.post("/api/slots/4/create", json=MIRA)
        r = client.post("/api/slots/4/kick")
        assert r.status_code == 200
        body = r.json()
        assert body["is_human_controlled"] is False
        assert body["kicked_at"] is not None
        assert body["claimed_by_me"] is False
        assert body["current_room_id"] == "r-meadow"


def test_kick_on_empty_slot_returns_404():
    with TestClient(app) as client:
        _login(client)
        assert client.post("/api/slots/2/kick").status_code == 404


def test_claim_on_your_rested_toon_re_adopts():
    with TestClient(app) as client:
        _login(client)
        client.post("/api/slots/2/create", json=MIRA)
        client.post("/api/slots/2/kick")
        r = client.post("/api/slots/2/claim")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kicked_at"] is None and body["is_human_controlled"] is True
        assert body["claimed_by_me"] is True


def test_claim_on_empty_slot_returns_404():
    with TestClient(app) as client:
        _login(client)
        assert client.post("/api/slots/3/claim").status_code == 404


def test_your_second_tab_takes_over_your_own_live_toon(monkeypatch):
    """The same account opening a second tab or device takes control of its
    own toon even while the first is live (criterion 5)."""
    from daydream.api import ws as ws_mod

    with TestClient(app) as tab1:
        _login(tab1)
        tab1.post("/api/slots/2/create", json=MIRA)
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: True)
        with TestClient(app) as tab2:
            _login(tab2)
            r = tab2.post("/api/slots/2/claim")
            assert r.status_code == 200 and r.json()["claimed_by_me"] is True


def test_kick_own_toon_allowed_even_when_live(monkeypatch):
    from daydream.api import ws as ws_mod

    with TestClient(app) as client:
        _login(client)
        client.post("/api/slots/4/create", json=MIRA)
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: True)
        assert client.post("/api/slots/4/kick").status_code == 200


# ---- another account's toon ------------------------------------------------------------


@pytest.mark.parametrize("live", [True, False])
def test_another_accounts_toon_is_off_limits(monkeypatch, live):
    """Ownership, not liveness: another player's toon cannot be claimed,
    kicked or deleted, live or not. It is left untouched."""
    from daydream.api import ws as ws_mod

    with TestClient(app) as c1, TestClient(app) as c2:
        _login(c1, "ivo-player")
        _login(c2, "someone-else")
        c1.post("/api/slots/3/create", json=IVO)
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: live)
        assert c2.post("/api/slots/3/claim").status_code == 403
        assert c2.post("/api/slots/3/kick").status_code == 403
        assert c2.post("/api/slots/3/delete").status_code == 403
        t = toons.get_toon_in_slot(3)
        assert t is not None and t.is_human_controlled and t.kicked_at is None


def test_an_admin_browser_session_cannot_touch_a_friends_toon(monkeypatch):
    """SECURITY WARN 2026-09-27: in the browser an admin gets exactly three
    extras (repaint, status, several toons); moderating a friend's toon is the
    shell's job."""
    from daydream import admin as admin_cli
    from daydream.api import ws as ws_mod

    with TestClient(app) as c1, TestClient(app) as keeper:
        _login(c1, "ivo-player")
        _login(keeper, "keeper", role="admin")
        c1.post("/api/slots/3/create", json=IVO)
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: False)
        assert keeper.post("/api/slots/3/claim").status_code == 403
        assert keeper.post("/api/slots/3/kick").status_code == 403
        assert keeper.post("/api/slots/3/delete").status_code == 403
        assert admin_cli.cmd_toon_moderate("Ivo", "rest") == 0
        assert toons.get_toon_in_slot(3).kicked_at is not None
        assert admin_cli.cmd_toon_moderate("ivo", "delete") == 0
        assert toons.get_toon_in_slot(3) is None


def test_moderating_an_ambiguous_name_refuses_and_an_id_picks_one():
    """SECURITY NOTE 2026-09-28: two players can share a name; by name the
    shell used to act on whichever came first."""
    from daydream import admin as admin_cli

    with TestClient(app) as a, TestClient(app) as b:
        _login(a, "ivo-one")
        _login(b, "ivo-two")
        a.post("/api/slots/3/create", json=IVO)
        b.post("/api/slots/4/create", json=IVO)
        first, second = toons.get_toon_in_slot(3), toons.get_toon_in_slot(4)
        assert first.name == second.name
        assert admin_cli.cmd_toon_moderate("Ivo", "delete") == 2
        assert toons.get_toon_in_slot(3) is not None and toons.get_toon_in_slot(4) is not None
        assert admin_cli.cmd_toon_moderate(second.id, "delete") == 0
        assert toons.get_toon_in_slot(4) is None
        assert toons.get_toon_in_slot(3).id == first.id


def test_a_toon_named_after_another_toons_id_is_ambiguous():
    """security NOTE 2026-09-28: an exact id match used to win, so a toon
    named after a friend's toon id diverted `delete-toon` to the friend."""
    from daydream import admin as admin_cli

    with TestClient(app) as a, TestClient(app) as b:
        _login(a, "ivo-one")
        _login(b, "copycat")
        a.post("/api/slots/3/create", json=IVO)
        friend = toons.get_toon_in_slot(3)
        b.post("/api/slots/4/create", json={**IVO, "name": friend.id})
        assert toons.get_toon_in_slot(4).name == friend.id
        assert admin_cli.cmd_toon_moderate(friend.id, "delete") == 2
        assert toons.get_toon_in_slot(3) is not None and toons.get_toon_in_slot(4) is not None


# ---- unowned toons (seeded or from before accounts) -------------------------------------


def test_claiming_an_unowned_toon_adopts_it():
    from daydream import accounts

    with TestClient(app) as client:
        _login(client)
        assert client.post("/api/slots/1/kick").status_code == 200  # Wren, unowned
        r = client.post("/api/slots/1/claim")
        assert r.status_code == 200
        assert r.json()["owner_account"] == accounts.get_account("tester")["id"]
        # ...and now it is theirs: a second player may not take it.
    with TestClient(app) as other:
        _login(other, "someone-else")
        assert other.post("/api/slots/1/claim").status_code == 403


def test_an_unowned_toon_held_by_a_live_session_is_protected(monkeypatch):
    from daydream.api import ws as ws_mod

    with TestClient(app) as c1:
        _login(c1)
        # An unowned human toon controlled by some other live session.
        toons.create_toon_in_slot(2, "Legacy", "an old friend", "s-someone")
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: sid == "s-someone")
        assert c1.post("/api/slots/2/claim").status_code == 409
        assert c1.post("/api/slots/2/kick").status_code == 403
        monkeypatch.setattr(ws_mod, "is_session_live", lambda sid: False)
        assert c1.post("/api/slots/2/kick").status_code == 200


def test_a_player_with_a_dreamer_cannot_adopt_another():
    with TestClient(app) as client:
        _login(client)
        client.post("/api/dreamer/create", json=MIRA)
        client.post("/api/slots/1/kick")
        assert client.post("/api/slots/1/claim").status_code == 409


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
        before = toons.toon_card(toons.get_toon_in_slot(3))
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
        by_slot = {s["slot"]: s["toon"] for s in toons.get_human_slots(session_id=None)}
        assert by_slot[3]["id"] == before_id
        assert by_slot[3]["kicked_at"] is not None


def test_npc_slots_100_plus_excluded_from_picker():
    """Hand-authored NPCs in slots 100 (Rook) and 101 (Iris) are not
    in the slot listing, can't be created in (would 404), can't be
    claimed/kicked through the API."""
    with TestClient(app) as client:
        _login(client, "keeper", role="admin")
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
            _login(client_b, "keeper", role="admin")
            slots = client_b.get("/api/slots").json()["slots"]
            entry = next(s for s in slots if s["slot"] == 2)
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
    assert [s["toon"]["name"] for s in slots] == ["Visitor"]
    ddb.close_db()
