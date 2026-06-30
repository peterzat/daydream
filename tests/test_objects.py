"""Unit tests for the unified object access layer (daydream/objects.py) and
the migration-011 schema it sits on.

Covers the SPEC 2026-06-30 "object model & schema" criteria: one unified
object store (old tables gone), containment via `location_id`, and prototypes
providing default verbs without per-object re-declaration. Uses a real tmp
SQLite DB seeded by the full migration chain so the transform + constraints
are exercised end to end."""

from pathlib import Path

import pytest

from daydream import config, db, events, objects

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


# ---- schema: one unified store, old tables gone ------------------------


def test_old_tables_are_gone_objects_remains():
    tables = {
        r[0] for r in db.get_conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "objects" in tables
    assert not ({"rooms", "toons", "items"} & tables)


def test_seed_transformed_into_objects():
    # The seeded ids survive the cutover with their kind + containment intact.
    meadow = objects.get("r-meadow")
    assert meadow is not None and meadow.kind == "room" and meadow.location_id is None
    rook = objects.get("t-rook")
    assert rook is not None and rook.kind == "toon" and rook.location_id == "r-forge"
    lantern = objects.get("i-lantern")
    assert lantern is not None and lantern.kind == "thing" and lantern.location_id == "r-meadow"
    # Kind-specific fields landed in properties.
    assert meadow.properties["slug"] == "meadow"
    assert meadow.properties["exits"]["north"] == "r-forge"
    assert lantern.seed and "hairline crack" in lantern.seed


# ---- containment via location_id ---------------------------------------


def test_contents_lists_room_occupants_and_things():
    contents = objects.contents("r-forge")
    ids = {o.id for o in contents}
    assert "t-rook" in ids  # the forge-keeper stands in the forge
    # Filter by kind.
    toon_ids = {o.id for o in objects.contents("r-forge", kind="toon")}
    assert toon_ids == {"t-rook"}


def test_move_reparents_and_is_reflected():
    # Move the lantern from the meadow into Rook's inventory.
    assert objects.get("i-lantern").location_id == "r-meadow"
    objects.move("i-lantern", "t-rook")
    assert objects.get("i-lantern").location_id == "t-rook"
    # It now shows up in the toon's inventory and not on the meadow floor.
    assert "i-lantern" in objects.content_ids("t-rook", kind="thing")
    assert "i-lantern" not in objects.content_ids("r-meadow", kind="thing")


def test_in_scope_is_actor_room_and_co_located_and_inventory():
    # Put a thing in Wren's hands; Wren is in the meadow with the lantern.
    objects.spawn(
        "w-bunny", "thing", "a pebble", "t-wren",
        prototype_id=objects.PROTO_THING, properties={"seed": "smooth"},
        object_id="o-pebble",
    )
    scope_ids = {o.id for o in objects.in_scope("t-wren")}
    assert "t-wren" in scope_ids       # the actor itself
    assert "r-meadow" in scope_ids     # its room
    assert "i-lantern" in scope_ids    # a thing on the ground
    assert "o-pebble" in scope_ids     # carried inventory
    # Prototypes are never in scope.
    assert not any(o.kind == "prototype" for o in objects.in_scope("t-wren"))


def test_find_in_scope_by_name_matches_name_and_alias():
    objects.spawn(
        "w-bunny", "thing", "sheaf of papers", "r-meadow",
        prototype_id=objects.PROTO_READABLE,
        properties={"seed": "loose pages"}, aliases=["papers", "sheaf"],
        object_id="o-papers",
    )
    by_name = objects.find_in_scope_by_name("t-wren", "sheaf of papers")
    by_alias = objects.find_in_scope_by_name("t-wren", "papers")
    assert by_name is not None and by_name.id == "o-papers"
    assert by_alias is not None and by_alias.id == "o-papers"
    assert objects.find_in_scope_by_name("t-wren", "nonexistent thing") is None


# ---- properties --------------------------------------------------------


def test_set_and_get_property_round_trip():
    assert objects.set_property("t-rook", "mood", "weary") is True
    assert objects.get_property("t-rook", "mood") == "weary"
    # Setting one key preserves the others.
    assert objects.get_property("t-rook", "presence_text")  # still there
    # Unknown object: no-op, returns False / default.
    assert objects.set_property("o-nonexistent", "x", 1) is False
    assert objects.get_property("o-nonexistent", "x", "fallback") == "fallback"


# ---- prototypes provide default verbs ----------------------------------


def test_prototypes_seeded_with_verb_sets():
    proto = objects.get(objects.PROTO_THING)
    assert proto is not None and proto.kind == "prototype"
    assert proto.properties["verbs"] == ["examine", "take", "drop"]


def test_concrete_object_inherits_prototype_verbs():
    # A readable thing exposes the readable/thing verbs WITHOUT re-declaring
    # them per object (they come from its prototype).
    papers = objects.spawn(
        "w-bunny", "thing", "sheaf of papers", "r-forge",
        prototype_id=objects.PROTO_READABLE, properties={"seed": "loose pages"},
        object_id="o-papers2",
    )
    assert objects.verbs_for(papers) == ["examine", "take", "drop"]
    # An NPC inherits examine + talk from proto-npc.
    assert objects.verbs_for(objects.get("t-rook")) == ["examine", "talk"]


def test_per_object_verbs_union_with_prototype():
    # A per-object `properties.verbs` extends (not replaces) prototype defaults.
    obj = objects.spawn(
        "w-bunny", "thing", "a music box", "r-meadow",
        prototype_id=objects.PROTO_THING,
        properties={"seed": "tinkling", "verbs": ["wind"]},
        object_id="o-box",
    )
    assert objects.verbs_for(obj) == ["examine", "take", "drop", "wind"]


# ---- spawn -------------------------------------------------------------


def test_spawn_creates_clickable_thing_with_default_id():
    obj = objects.spawn(
        "w-bunny", "thing", "a feather", "r-meadow",
        prototype_id=objects.PROTO_THING, properties={"seed": "soft grey down"},
    )
    assert obj.id.startswith("o-")
    fetched = objects.get(obj.id)
    assert fetched is not None
    assert fetched.name == "a feather" and fetched.location_id == "r-meadow"
