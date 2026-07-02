"""Real containers (Zork turn, SPEC 2026-07-02 criterion 4): visibility
governs scope, `put`/take honor open/closed/transparent/surface plus
capacity and size limits, contents ride along on container moves, and look/
examine compose visible contents."""

from pathlib import Path

import pytest

from daydream import config, db, events, objects, verbs

pytestmark = pytest.mark.tier_short

WORLD = "w-bunny"
ACTOR = "t-wren"
ROOM = "r-meadow"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def narrates() -> list[str]:
    return [e.payload.get("text", "") for e in events.fetch_since(0)
            if e.kind == "narrate"]


def spawn_sack(state="closed", **props):
    return objects.spawn(
        WORLD, "thing", "sack", ROOM,
        prototype_id=objects.PROTO_THING,
        properties={"container": True, "state": state,
                    "verbs": ["open", "close"], **props},
        object_id="o-sack",
    )


def spawn_garlic(location):
    return objects.spawn(WORLD, "thing", "garlic", location,
                         prototype_id=objects.PROTO_THING, object_id="o-garlic")


def in_scope_ids():
    return {o.id for o in objects.in_scope(ACTOR)}


# ---- scope + visibility -----------------------------------------------------


def test_closed_opaque_container_hides_contents():
    sack = spawn_sack("closed")
    spawn_garlic(sack.id)
    assert "o-garlic" not in in_scope_ids()


def test_open_container_reveals_contents():
    sack = spawn_sack("open")
    spawn_garlic(sack.id)
    assert "o-garlic" in in_scope_ids()


def test_transparent_closed_container_shows_contents():
    bottle = objects.spawn(
        WORLD, "thing", "bottle", ROOM,
        properties={"container": True, "transparent": True, "state": "closed"},
        object_id="o-bottle",
    )
    objects.spawn(WORLD, "thing", "quantity of water", bottle.id, object_id="o-water")
    assert "o-water" in in_scope_ids()


def test_surface_contents_always_visible():
    table = objects.spawn(WORLD, "thing", "table", ROOM,
                          properties={"surface": True}, object_id="o-table")
    objects.spawn(WORLD, "thing", "knife", table.id, object_id="o-knife")
    assert "o-knife" in in_scope_ids()


def test_stateless_container_is_always_open_basket():
    basket = objects.spawn(WORLD, "thing", "basket", ROOM,
                           properties={"container": True}, object_id="o-basket")
    spawn_garlic(basket.id)
    assert objects.container_open(basket)
    assert "o-garlic" in in_scope_ids()


def test_nested_visibility_stops_at_closed_inner():
    outer = objects.spawn(WORLD, "thing", "crate", ROOM,
                          properties={"container": True, "state": "open"},
                          object_id="o-crate")
    inner = objects.spawn(WORLD, "thing", "tin", outer.id,
                          properties={"container": True, "state": "closed"},
                          object_id="o-tin")
    objects.spawn(WORLD, "thing", "coin", inner.id, object_id="o-coin")
    ids = in_scope_ids()
    assert "o-tin" in ids and "o-coin" not in ids


def test_nested_visibility_recurses_when_open():
    outer = objects.spawn(WORLD, "thing", "crate", ROOM,
                          properties={"container": True, "state": "open"},
                          object_id="o-crate")
    inner = objects.spawn(WORLD, "thing", "tin", outer.id,
                          properties={"container": True, "state": "open"},
                          object_id="o-tin")
    objects.spawn(WORLD, "thing", "coin", inner.id, object_id="o-coin")
    assert "o-coin" in in_scope_ids()


def test_contents_ride_along_when_container_moves():
    sack = spawn_sack("open")
    spawn_garlic(sack.id)
    objects.move(sack.id, "r-forge")
    assert objects.get("o-garlic").location_id == sack.id
    assert "o-garlic" not in in_scope_ids()  # actor stayed in the meadow


def test_find_all_in_scope_by_name_returns_every_match():
    objects.spawn(WORLD, "thing", "lantern", ACTOR, object_id="o-lantern2")
    matches = objects.find_all_in_scope_by_name(ACTOR, "lantern")
    assert {m.id for m in matches} == {"i-lantern", "o-lantern2"}


# ---- take gates ---------------------------------------------------------------


async def test_take_from_open_container_works():
    sack = spawn_sack("open")
    spawn_garlic(sack.id)
    await verbs.execute_command(ACTOR, "take", "o-garlic")
    assert objects.get("o-garlic").location_id == ACTOR


async def test_take_from_transparent_closed_container_refused():
    bottle = objects.spawn(
        WORLD, "thing", "bottle", ROOM,
        properties={"container": True, "transparent": True, "state": "closed"},
        object_id="o-bottle",
    )
    objects.spawn(WORLD, "thing", "quantity of water", bottle.id,
                  prototype_id=objects.PROTO_THING, object_id="o-water")
    await verbs.execute_command(ACTOR, "take", "o-water")
    assert objects.get("o-water").location_id == "o-bottle"
    assert "The bottle is closed." in narrates()


async def test_take_respects_carry_capacity():
    from daydream import worldstate

    worldstate.set(WORLD, "config", {"carry_capacity": 8})
    objects.spawn(WORLD, "thing", "anvil", ROOM,
                  prototype_id=objects.PROTO_THING,
                  properties={"size": 6}, object_id="o-anvil")
    objects.spawn(WORLD, "thing", "feather", ROOM,
                  prototype_id=objects.PROTO_THING,
                  properties={"size": 1}, object_id="o-feather")
    await verbs.execute_command(ACTOR, "take", "o-anvil")
    assert objects.get("o-anvil").location_id == ACTOR
    await verbs.execute_command(ACTOR, "take", "i-lantern")  # size default 5: over
    assert objects.get("i-lantern").location_id == ROOM
    assert "You're carrying too much already." in narrates()
    await verbs.execute_command(ACTOR, "take", "o-feather")  # 6+1 fits
    assert objects.get("o-feather").location_id == ACTOR


# ---- put --------------------------------------------------------------------


async def take_lantern():
    await verbs.execute_command(ACTOR, "take", "i-lantern")
    assert objects.get("i-lantern").location_id == ACTOR


async def test_put_into_open_container():
    spawn_sack("open")
    await take_lantern()
    await verbs.execute_command(ACTOR, "put", "i-lantern", "o-sack")
    assert objects.get("i-lantern").location_id == "o-sack"
    assert "You put the lantern in the sack." in narrates()


async def test_put_onto_surface_says_on():
    objects.spawn(WORLD, "thing", "table", ROOM,
                  properties={"surface": True}, object_id="o-table")
    await take_lantern()
    await verbs.execute_command(ACTOR, "put", "i-lantern", "o-table")
    assert objects.get("i-lantern").location_id == "o-table"
    assert "You put the lantern on the table." in narrates()


async def test_put_requires_carrying():
    spawn_sack("open")
    await verbs.execute_command(ACTOR, "put", "i-lantern", "o-sack")
    assert objects.get("i-lantern").location_id == ROOM
    assert "You aren't carrying the lantern." in narrates()


async def test_put_into_closed_container_refused():
    spawn_sack("closed")
    await take_lantern()
    await verbs.execute_command(ACTOR, "put", "i-lantern", "o-sack")
    assert objects.get("i-lantern").location_id == ACTOR
    assert "The sack is closed." in narrates()


async def test_put_into_non_container_refused():
    objects.spawn(WORLD, "thing", "rock", ROOM, object_id="o-rock")
    await take_lantern()
    await verbs.execute_command(ACTOR, "put", "i-lantern", "o-rock")
    assert objects.get("i-lantern").location_id == ACTOR
    assert "You can't put things in the rock." in narrates()


async def test_put_thing_inside_itself_refused():
    sack = spawn_sack("open")
    objects.move(sack.id, ACTOR)  # carry the sack
    await verbs.execute_command(ACTOR, "put", "o-sack", "o-sack")
    assert objects.get("o-sack").location_id == ACTOR
    assert "You can't put the sack inside itself." in narrates()


async def test_put_containment_cycle_refused():
    sack = spawn_sack("open")
    objects.move(sack.id, ACTOR)
    box = objects.spawn(WORLD, "thing", "box", sack.id,
                        properties={"container": True, "state": "open"},
                        object_id="o-box")
    # box is inside the carried sack; putting the sack into the box would
    # orbit them both out of the world.
    await verbs.execute_command(ACTOR, "put", "o-sack", "o-box")
    assert objects.get("o-sack").location_id == ACTOR
    assert "You can't put the sack inside itself." in narrates()
    assert box.id == "o-box"


async def test_put_capacity_overflow_refused():
    basket = objects.spawn(WORLD, "thing", "basket", ROOM,
                           properties={"container": True, "capacity": 9},
                           object_id="o-basket")
    await take_lantern()  # size 5 (default)
    coal = objects.spawn(WORLD, "thing", "coal", ACTOR,
                         prototype_id=objects.PROTO_THING,
                         properties={"size": 5}, object_id="o-coal")
    await verbs.execute_command(ACTOR, "put", "i-lantern", "o-basket")
    assert objects.get("i-lantern").location_id == basket.id
    await verbs.execute_command(ACTOR, "put", "o-coal", "o-basket")  # 5+5 > 9
    assert objects.get(coal.id).location_id == ACTOR
    assert "The coal won't fit in the basket." in narrates()


async def test_put_oversized_item_refused_outright():
    tiny = objects.spawn(WORLD, "thing", "thimble", ROOM,
                         properties={"container": True, "capacity": 2},
                         object_id="o-thimble")
    await take_lantern()
    await verbs.execute_command(ACTOR, "put", "i-lantern", "o-thimble")
    assert objects.get("i-lantern").location_id == ACTOR
    assert tiny.id == "o-thimble"


# ---- close + look/examine composition ----------------------------------------


async def test_close_open_container_hides_contents():
    sack = spawn_sack("open")
    spawn_garlic(sack.id)
    await verbs.execute_command(ACTOR, "close", "o-sack")
    assert objects.get(sack.id).properties["state"] == "closed"
    assert "You close the sack." in narrates()
    assert "o-garlic" not in in_scope_ids()


async def test_close_already_closed():
    spawn_sack("closed")
    await verbs.execute_command(ACTOR, "close", "o-sack")
    assert "The sack is already closed." in narrates()


async def test_open_then_contents_in_scope_again():
    sack = spawn_sack("closed")
    spawn_garlic(sack.id)
    await verbs.execute_command(ACTOR, "open", "o-sack")
    assert objects.get(sack.id).properties["state"] == "open"
    assert "o-garlic" in in_scope_ids()


async def test_look_reads_out_visible_container_contents():
    sack = spawn_sack("open")
    spawn_garlic(sack.id)
    await verbs.execute_command(ACTOR, "look")
    assert any("The sack holds: garlic." in t for t in narrates())


async def test_look_stays_quiet_about_closed_containers():
    sack = spawn_sack("closed")
    spawn_garlic(sack.id)
    await verbs.execute_command(ACTOR, "look")
    assert not any("holds" in t for t in narrates())


async def test_examine_container_shows_holds_empty_closed():
    sack = spawn_sack("open", seed="a rough burlap sack")
    spawn_garlic(sack.id)
    await verbs.execute_command(ACTOR, "examine", "o-sack")
    assert any("The sack holds: garlic." in t for t in narrates())
    objects.move("o-garlic", ROOM)
    await verbs.execute_command(ACTOR, "examine", "o-sack")
    assert any("The sack is empty." in t for t in narrates())
    objects.set_property("o-sack", "state", "closed")
    await verbs.execute_command(ACTOR, "examine", "o-sack")
    assert any("The sack is closed." in t for t in narrates())


def test_put_verb_rides_thing_prototypes():
    # Migration 015 appends `put` to the seeded thing/readable prototypes;
    # the loader's _PROTOTYPES table carries it for world-loaded DBs.
    lantern = objects.get("i-lantern")
    assert "put" in objects.verbs_for(lantern)
