"""World-integrity invariants for the shipped canonical world (SPEC 2026-07-01).

Loads worlds/clockmakers-loft.json keyless into a temp live DB and asserts the
structural contract the quest depends on: 5 rooms with bidirectional exits, 4
toons (1 human-claimable + 3 NPCs with bound dialogue), the stateful clock-case
(fixture, use rule, payload), the readable ledger, the takeable/giveable gear,
2 ambient skills, and that the by-name cross-references actually resolve
(Tace.wants -> the gear; clock-case use.with -> Tace's reward). A malformed edit
to the world file fails this test rather than surfacing as a broken playthrough."""

from pathlib import Path

import pytest

from daydream import admin, config, db, events, objects

pytestmark = pytest.mark.tier_short

REPO = Path(__file__).resolve().parent.parent
WORLD = REPO / "worlds" / "clockmakers-loft.json"


@pytest.fixture()
def loft_db(tmp_path: Path):
    out = tmp_path / "live.db"
    assert admin.main(["load", str(WORLD), "--output", str(out)]) == 0
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=out, migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _room(slug: str) -> objects.Object:
    r = objects.by_slug("w-bunny", slug, kind="room")
    assert r is not None, f"missing room {slug!r}"
    return r


def _thing(name: str) -> objects.Object:
    for o in db.get_conn().execute(
        "SELECT * FROM objects WHERE kind = 'thing' AND name = ?", (name,)
    ):
        return objects.Object.from_row(o)
    raise AssertionError(f"missing thing {name!r}")


def _toon(name: str) -> objects.Object:
    for o in db.get_conn().execute(
        "SELECT * FROM objects WHERE kind = 'toon' AND name = ?", (name,)
    ):
        return objects.Object.from_row(o)
    raise AssertionError(f"missing toon {name!r}")


# ---- rooms + bidirectional exits ---------------------------------------


def test_five_rooms_with_bidirectional_exits(loft_db):
    slugs = ["clocktower", "loft", "square", "workshop", "well"]
    rooms = {s: _room(s) for s in slugs}
    # Every exit target is a real room, and every edge has a return path.
    ids = {r.id for r in rooms.values()}
    edges = set()
    for r in rooms.values():
        for direction, dest in r.properties.get("exits", {}).items():
            assert dest in ids, f"{r.name} exit {direction} -> unknown {dest}"
            edges.add((r.id, dest))
    for src, dst in edges:
        assert (dst, src) in edges, f"no return path for {src} -> {dst}"


def test_start_room_is_the_clocktower(loft_db):
    row = db.get_conn().execute("SELECT starting_room_id FROM worlds").fetchone()
    assert row["starting_room_id"] == _room("clocktower").id


# ---- toons: 1 human-claimable + 3 dialogue NPCs ------------------------


def test_four_toons_one_claimable_three_with_dialogue(loft_db):
    wick = _toon("Wick")
    assert wick.slot == 1  # the human-claimable visitor at the start
    for name in ("Tace", "Bell", "Mott"):
        npc = _toon(name)
        assert "talk" in objects.verbs_for(npc)
        # Bound dialogue installed + referenced (reached only via `talk`).
        skill = npc.properties.get("dialogue")
        assert isinstance(skill, str) and skill.startswith("dlg-")


# ---- the stateful clock-case (fixture) ---------------------------------


def test_clock_case_is_a_stateful_fixture(loft_db):
    case = _thing("clock case")
    verbs = objects.verbs_for(case)
    assert "open" in verbs and "examine" in verbs
    assert "take" not in verbs and "drop" not in verbs  # immovable fixture
    assert case.properties.get("state") == "locked"
    use = case.properties.get("use")
    assert use["with"] == "case key" and use["from_state"] == "locked"
    assert case.properties.get("contains", {}).get("name") == "warm brass cog"


def test_repair_ledger_is_readable_with_a_clue(loft_db):
    ledger = _thing("repair ledger")
    assert "read" in objects.verbs_for(ledger)
    assert "escapement gear" in ledger.properties.get("text", "").lower()


def test_escapement_gear_is_takeable_and_giveable(loft_db):
    gear = _thing("escapement gear")
    verbs = objects.verbs_for(gear)
    assert {"take", "drop", "give"} <= set(verbs)


# ---- by-name cross-references actually resolve -------------------------


def test_quest_cross_references_resolve_by_name(loft_db):
    tace = _toon("Tace")
    gear = _thing("escapement gear")
    case = _thing("clock case")
    # Tace wants the gear (name/alias match).
    wants = tace.properties["wants"].lower()
    assert wants == gear.name.lower() or wants in [a.lower() for a in gear.aliases]
    # Tace's reward is the key the clock-case's use rule expects.
    reward = tace.properties["gives"]["name"]
    assert case.properties["use"]["with"] == reward
    # The reward carries `use`, so the given key is use-able.
    assert "use" in tace.properties["gives"].get("verbs", [])


# ---- ambient skills ----------------------------------------------------


def test_two_ambient_room_skills_present(loft_db):
    names = {r["name"] for r in db.get_conn().execute(
        "SELECT name FROM skills WHERE author = 'opus-bootstrap'"
    )}
    assert names == {"wind", "listen"}
