"""Conditional movement, vehicles, and teleports (Zork turn, SPEC 2026-07-02
criterion 7): exit condition lists, blocked text (with the clock still
ticking), on-traverse effects with inline ifs, secret exits hidden until
passable, message-only non-exits, room entry gates, board/disembark, the
vehicle riding along on go, and enter rules firing on arrival."""

from pathlib import Path

import pytest

from daydream import config, db, events, objects, verbs, worldstate

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


def narrates():
    return [e.payload.get("text", "") for e in events.fetch_since(0)
            if e.kind == "narrate"]


def set_exits(exits: dict, room_id=ROOM):
    objects.set_property(room_id, "exits", exits)


def wren_room() -> str:
    return objects.get(ACTOR).location_id


# ---- conditional exits --------------------------------------------------------


async def test_plain_string_exit_still_works():
    set_exits({"north": "r-forge"})
    await verbs.execute_command(ACTOR, "go", args="north")
    assert wren_room() == "r-forge"


async def test_conditional_exit_blocked_refuses_with_text_and_ticks():
    set_exits({"down": {"to": "r-forge", "if": [{"flag": "TRAP-OPEN"}],
                        "blocked_text": "The trap door is shut fast."}})
    turn_before = worldstate.turn(WORLD)
    await verbs.execute_command(ACTOR, "go", args="down")
    assert wren_room() == ROOM
    assert "The trap door is shut fast." in narrates()
    assert worldstate.turn(WORLD) == turn_before + 1  # blocked still ticks


async def test_conditional_exit_opens_when_condition_holds():
    set_exits({"down": {"to": "r-forge", "if": [{"flag": "TRAP-OPEN"}],
                        "blocked_text": "The trap door is shut fast."}})
    worldstate.set_flag(WORLD, "TRAP-OPEN", True)
    await verbs.execute_command(ACTOR, "go", args="down")
    assert wren_room() == "r-forge"


async def test_message_only_non_exit():
    set_exits({"west": {"text": "The door is boarded shut."}})
    await verbs.execute_command(ACTOR, "go", args="west")
    assert wren_room() == ROOM
    assert "The door is boarded shut." in narrates()


async def test_on_traverse_effects_with_inline_if():
    set_exits({"down": {"to": "r-forge", "on_traverse": [
        {"kind": "narrate", "text": "You slide down the chute!"},
        {"kind": "narrate", "text": "Your lamp rattles.",
         "if": [{"carried": "i-lantern"}]},
        {"kind": "adjust_counter", "name": "slides", "delta": 1},
    ]}})
    await verbs.execute_command(ACTOR, "go", args="down")
    assert wren_room() == "r-forge"
    texts = narrates()
    assert "You slide down the chute!" in texts
    assert "Your lamp rattles." not in texts  # inline if filtered it
    assert worldstate.counter(WORLD, "slides") == 1
    # The traverse narration lands in the DESTINATION room's log.
    slide = next(e for e in events.fetch_since(0)
                 if e.kind == "narrate" and "chute" in e.payload["text"])
    assert slide.room_id == "r-forge"


async def test_one_way_exit_is_fine():
    set_exits({"down": "r-forge"})  # no return exit authored
    await verbs.execute_command(ACTOR, "go", args="down")
    assert wren_room() == "r-forge"
    # No matching return direction back to the meadow (the forge's own
    # seeded exits go south/up): a one-way slide is a legal world shape.
    await verbs.execute_command(ACTOR, "go", args="down")
    assert wren_room() == "r-forge"


# ---- secret exits + snapshot visibility ------------------------------------------


def test_visible_exits_hides_secret_until_passable():
    room = objects.get(ROOM)
    set_exits({
        "north": "r-forge",
        "down": {"to": "r-forge", "secret": True, "if": [{"flag": "RUG-MOVED"}]},
        "west": {"text": "Boarded."},
    })
    from daydream import rooms

    r = rooms.get_room(ROOM)
    actor = objects.get(ACTOR)
    vis = verbs.visible_exits(r, actor)
    assert vis == {"north": "r-forge", "west": None}
    worldstate.set_flag(WORLD, "RUG-MOVED", True)
    vis = verbs.visible_exits(rooms.get_room(ROOM), actor)
    assert vis == {"north": "r-forge", "down": "r-forge", "west": None}
    assert room.id == ROOM


async def test_secret_exit_walkable_once_passable():
    set_exits({"down": {"to": "r-forge", "secret": True,
                        "if": [{"flag": "RUG-MOVED"}],
                        "blocked_text": "You see no way down."}})
    await verbs.execute_command(ACTOR, "go", args="down")
    assert wren_room() == ROOM
    assert "You see no way down." in narrates()
    worldstate.set_flag(WORLD, "RUG-MOVED", True)
    await verbs.execute_command(ACTOR, "go", args="down")
    assert wren_room() == "r-forge"


# ---- room entry gates + vehicles ---------------------------------------------------


def spawn_boat(room_id=ROOM):
    return objects.spawn(
        WORLD, "thing", "magic boat", room_id,
        properties={"vehicle": True, "verbs": ["board"],
                    "board_text": "You settle into the magic boat."},
        object_id="o-boat",
    )


def make_river():
    objects.spawn(
        WORLD, "room", "Frigid River", None,
        prototype_id=objects.PROTO_ROOM,
        properties={"slug": "river-1", "title": "Frigid River",
                    "seed": "cold water", "exits": {"west": ROOM},
                    "enter_if": [{"in_vehicle": True}],
                    "enter_blocked_text": "The water is far too cold for swimming."},
        object_id="r-river1",
    )
    set_exits({"east": "r-river1"})


async def test_room_entry_gate_refuses_on_foot():
    make_river()
    await verbs.execute_command(ACTOR, "go", args="east")
    assert wren_room() == ROOM
    assert "The water is far too cold for swimming." in narrates()


async def test_board_go_carries_vehicle_disembark():
    make_river()
    boat = spawn_boat()
    await verbs.execute_command(ACTOR, "board", "o-boat")
    assert "You settle into the magic boat." in narrates()
    assert objects.get(ACTOR).properties["aboard"] == "o-boat"
    await verbs.execute_command(ACTOR, "go", args="east")
    assert wren_room() == "r-river1"            # gate passed aboard
    assert objects.get(boat.id).location_id == "r-river1"  # vehicle rode along
    await verbs.execute_command(ACTOR, "disembark")
    assert objects.get(ACTOR).properties["aboard"] is None
    assert "You climb out of the magic boat." in narrates()


async def test_board_refuses_non_vehicle_and_carried_vehicle():
    rock = objects.spawn(WORLD, "thing", "rock", ROOM,
                         properties={"verbs": ["board"]}, object_id="o-rock")
    await verbs.execute_command(ACTOR, "board", "o-rock")
    assert "You can't board the rock." in narrates()
    boat = spawn_boat()
    objects.move(boat.id, ACTOR)  # carried
    await verbs.execute_command(ACTOR, "board", "o-boat")
    assert "Put the magic boat down first." in narrates()
    assert rock.id == "o-rock"


async def test_disembark_when_not_aboard():
    await verbs.execute_command(ACTOR, "disembark")
    assert "You aren't aboard anything." in narrates()


async def test_double_board_refused():
    spawn_boat()
    objects.spawn(WORLD, "thing", "basket", ROOM,
                  properties={"vehicle": True, "verbs": ["board"]},
                  object_id="o-basket")
    await verbs.execute_command(ACTOR, "board", "o-boat")
    await verbs.execute_command(ACTOR, "board", "o-basket")
    assert objects.get(ACTOR).properties["aboard"] == "o-boat"
    assert "You're already aboard the magic boat." in narrates()


# ---- teleport + enter rules ------------------------------------------------------


async def test_teleport_effect_relocates_with_move_event():
    from daydream.skills import effects as fx

    fx.dispatch_effects([{"kind": "teleport_actor", "room_id": "r-forge"}],
                        actor_id=ACTOR, room_id=ROOM, world_id=WORLD,
                        allowed=fx.RULE_KINDS)
    assert wren_room() == "r-forge"
    moves = [e for e in events.fetch_since(0) if e.kind == "move"]
    assert moves and moves[-1].payload["teleport"] is True


async def test_enter_rules_fire_on_arrival_with_once_scoring():
    objects.set_property("r-forge", "rules", [
        {"on": "enter",
         "do": [{"kind": "adjust_score", "delta": 10, "once": "visit:forge"},
                {"kind": "narrate", "text": "The forge glows in welcome."}]},
    ])
    set_exits({"north": "r-forge"})
    objects.set_property("r-forge", "exits", {"south": ROOM})
    await verbs.execute_command(ACTOR, "go", args="north")
    assert worldstate.score(WORLD) == 10
    assert "The forge glows in welcome." in narrates()
    await verbs.execute_command(ACTOR, "go", args="south")
    await verbs.execute_command(ACTOR, "go", args="north")
    assert worldstate.score(WORLD) == 10  # once-key held
