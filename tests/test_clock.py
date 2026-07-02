"""The world clock, lighting, and death (Zork turn, SPEC 2026-07-02
criteria 5 + 6): turn advance on every executed command, fuel burn with
authored warnings and permanent burnout, fuse timing (arm-tick skip), script
daemons under seeded RNG, darkness scope/look/snapshot suppression, the
seeded movement hazard, and a scripted die-and-recover sequence through the
authored death policy."""

from pathlib import Path

import pytest

from daydream import clock, config, db, events, lighting, objects, verbs, worldstate

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


def narrates(recipient=None):
    return [
        e.payload.get("text", "")
        for e in events.fetch_since(0)
        if e.kind == "narrate" and (recipient is None or e.recipient_id == recipient)
    ]


def spawn_lamp(fuel=3, lit=True, **props):
    return objects.spawn(
        WORLD, "thing", "lamp", ACTOR,
        prototype_id=objects.PROTO_THING,
        properties={
            "light": True, "lit": lit, "fuel": fuel,
            "fuel_warnings": {"2": "The lamp is getting dim."},
            "burnout_text": "The lamp has gone out.",
            **props,
        },
        object_id="o-lamp",
    )


def make_dark_room(room_id="r-cave", title="Cave"):
    return objects.spawn(
        WORLD, "room", title, None,
        prototype_id=objects.PROTO_ROOM,
        properties={"slug": room_id[2:], "title": title, "seed": "dark stone",
                    "dark": True, "exits": {}},
        object_id=room_id,
    )


# ---- turn advance -----------------------------------------------------------


async def test_every_executed_command_ticks_the_clock():
    assert worldstate.turn(WORLD) == 0
    await verbs.execute_command(ACTOR, "look")
    assert worldstate.turn(WORLD) == 1
    # An in-world refusal still ticks (blocked exits, missing targets...).
    await verbs.execute_command(ACTOR, "take", None)
    assert worldstate.turn(WORLD) == 2
    # An unknown verb is a parse miss: no turn passes.
    await verbs.execute_command(ACTOR, "frobnicate")
    assert worldstate.turn(WORLD) == 2


# ---- fuel ---------------------------------------------------------------------


def test_fuel_burns_only_while_lit():
    lamp = spawn_lamp(fuel=5, lit=False)
    clock.tick(ACTOR)
    assert objects.get(lamp.id).properties["fuel"] == 5
    objects.set_property(lamp.id, "lit", True)
    clock.tick(ACTOR)
    assert objects.get(lamp.id).properties["fuel"] == 4


def test_fuel_warning_reaches_the_holder_privately():
    spawn_lamp(fuel=3, lit=True)
    clock.tick(ACTOR)  # 3 -> 2: warning threshold
    assert "The lamp is getting dim." in narrates(recipient=ACTOR)


def test_burnout_is_permanent_and_narrated():
    lamp = spawn_lamp(fuel=1, lit=True)
    clock.tick(ACTOR)
    p = objects.get(lamp.id).properties
    assert p["fuel"] == 0 and p["lit"] is False and p["burned_out"] is True
    assert "The lamp has gone out." in narrates()
    clock.tick(ACTOR)  # no further burn, no repeat narration
    assert objects.get(lamp.id).properties["fuel"] == 0
    assert narrates().count("The lamp has gone out.") == 1


def test_burnout_clears_a_dynamic_flame_property():
    """A world tracking open flames (hazard rules key on `flame`) must not
    see a burned-out source still reading as burning; a source with no such
    property is untouched."""
    match = spawn_lamp(fuel=1, lit=True, flame=True)
    clock.tick(ACTOR)
    assert objects.get(match.id).properties["flame"] is False
    plain = objects.spawn(WORLD, "thing", "stub-lamp", ACTOR,
                          properties={"light": True, "lit": True, "fuel": 1},
                          object_id="o-plain")
    clock.tick(ACTOR)
    assert "flame" not in objects.get(plain.id).properties


def test_permanent_source_never_burns():
    torch = objects.spawn(WORLD, "thing", "torch", ACTOR,
                          properties={"light": True, "lit": True},
                          object_id="o-torch")
    clock.tick(ACTOR)
    assert "fuel" not in objects.get(torch.id).properties


# ---- fuses ---------------------------------------------------------------------


def arm_fuse(name="bell", turns=2, do=None):
    worldstate.set(WORLD, "def:fuses", {
        name: {"turns": turns,
               "do": do or [{"kind": "narrate", "text": f"fuse {name} fired",
                             "to": "@actor"}]},
    })
    from daydream.skills import effects as fx

    fx.dispatch_effects(
        [{"kind": "start_fuse", "name": name}],
        actor_id=ACTOR, room_id=ROOM, world_id=WORLD, allowed=fx.RULE_KINDS,
    )


def test_fuse_fires_after_exactly_n_further_ticks():
    arm_fuse(turns=2)
    clock.tick(ACTOR)  # the arming command's own tick: skipped
    assert worldstate.get(WORLD, "fuse:bell") is not None
    clock.tick(ACTOR)  # 2 -> 1
    assert "fuse bell fired" not in narrates()
    clock.tick(ACTOR)  # 1 -> 0: fires
    assert "fuse bell fired" in narrates()
    assert worldstate.get(WORLD, "fuse:bell") is None


def test_fuse_context_is_captured_at_arm_time():
    # The fuse narrates to @actor even though a different toon ticks later.
    arm_fuse(name="candle", turns=1,
             do=[{"kind": "narrate", "text": "the wax gutters", "to": "@actor"}])
    clock.tick(ACTOR)  # arming tick, skipped
    clock.tick("t-rook")  # someone else advances the world
    fired = [e for e in events.fetch_since(0)
             if e.kind == "narrate" and e.payload["text"] == "the wax gutters"]
    assert fired and fired[0].recipient_id == ACTOR


def test_stopped_fuse_never_fires():
    from daydream.skills import effects as fx

    arm_fuse(turns=1)
    fx.dispatch_effects([{"kind": "stop_fuse", "name": "bell"}],
                        actor_id=ACTOR, room_id=ROOM, world_id=WORLD,
                        allowed=fx.RULE_KINDS)
    clock.tick(ACTOR)
    clock.tick(ACTOR)
    assert "fuse bell fired" not in narrates()


# ---- script daemons --------------------------------------------------------------


def start_daemon(name, d):
    worldstate.set(WORLD, "def:daemons", {name: d})
    from daydream.skills import effects as fx

    fx.dispatch_effects([{"kind": "start_daemon", "name": name}],
                        actor_id=ACTOR, room_id=ROOM, world_id=WORLD,
                        allowed=fx.RULE_KINDS)


def test_script_daemon_runs_when_conditions_hold():
    worldstate.set_flag(WORLD, "GATES-OPEN", True)
    start_daemon("drain", {
        "kind": "script",
        "if": [{"flag": "GATES-OPEN"}],
        "do": [{"kind": "adjust_counter", "name": "water", "delta": -1}],
    })
    clock.tick(ACTOR)
    clock.tick(ACTOR)
    assert worldstate.counter(WORLD, "water") == -2
    worldstate.set_flag(WORLD, "GATES-OPEN", False)
    clock.tick(ACTOR)
    assert worldstate.counter(WORLD, "water") == -2  # conditions gate it


def test_once_daemon_deactivates_after_firing():
    worldstate.adjust_score(WORLD, 350)
    start_daemon("map-reveal", {
        "kind": "script", "once": True,
        "if": [{"score": {"gte": 350}}],
        "do": [{"kind": "set_flag", "name": "WON-FLAG", "value": True}],
    })
    worldstate.set(WORLD, "def:flags", ["WON-FLAG"])
    clock.tick(ACTOR)
    assert worldstate.get_flag(WORLD, "WON-FLAG") is True
    assert worldstate.get(WORLD, "daemon:map-reveal")["active"] is False


def test_inactive_daemon_does_not_run():
    start_daemon("drain", {
        "kind": "script", "if": [],
        "do": [{"kind": "adjust_counter", "name": "water", "delta": -1}],
    })
    from daydream.skills import effects as fx

    fx.dispatch_effects([{"kind": "stop_daemon", "name": "drain"}],
                        actor_id=ACTOR, room_id=ROOM, world_id=WORLD,
                        allowed=fx.RULE_KINDS)
    clock.tick(ACTOR)
    assert worldstate.counter(WORLD, "water") == 0


# ---- lighting + dark scope ---------------------------------------------------------


def test_room_lit_logic():
    cave = make_dark_room()
    assert lighting.room_lit(ROOM) is True  # not authored dark
    assert lighting.room_lit(cave.id) is False
    lamp = spawn_lamp(fuel=10, lit=True)
    objects.move(ACTOR, cave.id)  # carrying the lit lamp
    assert lighting.room_lit(cave.id) is True
    objects.set_property(lamp.id, "lit", False)
    assert lighting.room_lit(cave.id) is False


def test_dark_scope_reduces_to_self_room_inventory():
    cave = make_dark_room()
    objects.spawn(WORLD, "thing", "chest", cave.id, object_id="o-chest")
    lamp = spawn_lamp(fuel=10, lit=False)
    objects.move(ACTOR, cave.id)
    ids = {o.id for o in objects.in_scope(ACTOR)}
    assert "o-chest" not in ids          # can't see the room's contents
    assert lamp.id in ids                # can feel what you carry
    assert ACTOR in ids and cave.id in ids
    objects.set_property(lamp.id, "lit", True)
    ids = {o.id for o in objects.in_scope(ACTOR)}
    assert "o-chest" in ids              # light restores the room


async def test_look_in_darkness_narrates_authored_text():
    worldstate.set(WORLD, "config", {"darkness": {"text": "It is pitch black."}})
    cave = make_dark_room()
    objects.move(ACTOR, cave.id)
    await verbs.execute_command(ACTOR, "look")
    assert "It is pitch black." in narrates(recipient=ACTOR)


# ---- darkness hazard + death policy -----------------------------------------------


def install_death_world():
    """Two dark rooms and a lit respawn, plus the authored death policy."""
    cave = make_dark_room("r-cave", "Cave")
    deep = make_dark_room("r-deep", "Deep Passage")
    objects.set_property("r-cave", "exits", {"down": "r-deep"})
    objects.set_property("r-deep", "exits", {"up": "r-cave"})
    worldstate.set(WORLD, "config", {
        "darkness": {
            "text": "It is pitch black. Something hungry is near.",
            "hazard_chance": 1.0,
            "hazard_text": "Slavering fangs find you in the dark.",
        },
        "death": {
            "penalty": 10,
            "respawn_room": ROOM,
            "messages": ["You have died.", "You have died AGAIN."],
            "scatter": {
                "special": {"o-lamp": "r-forge"},
                "filters": [{"key": "treasure", "eq": True, "rooms": ["r-deep"]}],
                "default_rooms": [ROOM],
            },
            "set_flags": {"TRAP-OPEN": False},
            "stop_fuses": ["bell"],
        },
    })
    return cave, deep


async def test_entering_darkness_warns_but_does_not_kill():
    install_death_world()
    objects.move(ACTOR, "r-cave")  # place at the dark mouth without a tick
    # Entering dark from a LIT room: warned, safe (even at hazard 1.0).
    objects.move(ACTOR, ROOM)
    objects.set_property(ROOM, "exits", {"down": "r-cave"})
    await verbs.execute_command(ACTOR, "go", args="down")
    assert objects.get(ACTOR).location_id == "r-cave"
    assert "Something hungry is near." in " ".join(narrates(recipient=ACTOR))


async def test_moving_dark_to_dark_applies_hazard_and_death_policy():
    install_death_world()
    spawn_lamp(fuel=10, lit=False)
    treasure = objects.spawn(WORLD, "thing", "jeweled egg", ACTOR,
                             properties={"treasure": True}, object_id="o-egg")
    worldstate.set_flag(WORLD, "TRAP-OPEN", True)
    worldstate.adjust_score(WORLD, 50)
    objects.move(ACTOR, "r-cave")
    await verbs.execute_command(ACTOR, "go", args="down")  # dark -> dark, chance 1.0
    # Death policy applied:
    assert objects.get(ACTOR).location_id == ROOM          # respawned
    assert worldstate.score(WORLD) == 40                    # -10
    assert worldstate.counter(WORLD, "deaths") == 1
    assert objects.get("o-lamp").location_id == "r-forge"   # special-case
    assert objects.get("o-egg").location_id == "r-deep"     # treasure filter
    assert worldstate.get_flag(WORLD, "TRAP-OPEN") is False
    texts = narrates(recipient=ACTOR)
    assert "Slavering fangs find you in the dark." in texts
    assert "You have died." in texts
    move_events = [e for e in events.fetch_since(0)
                   if e.kind == "move" and e.payload.get("died")]
    assert move_events and move_events[0].payload["deaths"] == 1


async def test_die_and_recover_play_continues_cleanly():
    install_death_world()
    objects.move(ACTOR, "r-cave")
    await verbs.execute_command(ACTOR, "go", args="down")   # dies, respawns
    assert objects.get(ACTOR).location_id == ROOM
    # Post-death commands work: look, take, walk back into the dark.
    await verbs.execute_command(ACTOR, "take", "i-lantern")
    assert objects.get("i-lantern").location_id == ACTOR
    objects.set_property(ROOM, "exits", {"down": "r-cave"})
    await verbs.execute_command(ACTOR, "go", args="down")   # lit->dark: safe
    assert objects.get(ACTOR).location_id == "r-cave"
    await verbs.execute_command(ACTOR, "go", args="down")   # dark->dark: dies again
    assert worldstate.counter(WORLD, "deaths") == 2
    assert "You have died AGAIN." in narrates(recipient=ACTOR)


async def test_standing_still_in_darkness_is_safe():
    install_death_world()
    objects.move(ACTOR, "r-cave")
    await verbs.execute_command(ACTOR, "look")
    await verbs.execute_command(ACTOR, "inventory")
    assert worldstate.counter(WORLD, "deaths") == 0
    assert objects.get(ACTOR).location_id == "r-cave"


def test_hazard_chance_is_seeded():
    install_death_world()
    worldstate.set(WORLD, "config", {
        "darkness": {"text": "dark", "hazard_chance": 0.5},
        "death": {"respawn_room": ROOM},
    })
    worldstate.set(WORLD, "rng_seed", "pin")
    # The clock advances the turn to 1 BEFORE rolling, so precompute the
    # roll from the documented convention f"{seed}:{turn}:{purpose}".
    import random

    roll = random.Random("pin:1:darkness-hazard").random()
    objects.move(ACTOR, "r-cave")
    clock.tick(ACTOR, from_room_id="r-deep")  # dark -> dark move simulation
    died = worldstate.counter(WORLD, "deaths") == 1
    assert died == (roll < 0.5)
    # And the same seed replays identically: reset, re-run, same outcome.
    worldstate.set(WORLD, "turn", 0)
    worldstate.set_counter(WORLD, "deaths", 0)
    objects.move(ACTOR, "r-cave")
    clock.tick(ACTOR, from_room_id="r-deep")
    assert (worldstate.counter(WORLD, "deaths") == 1) == (roll < 0.5)


def test_kill_actor_without_policy_is_noop():
    from daydream.skills import effects as fx

    applied = fx.dispatch_effects([{"kind": "kill_actor"}],
                                  actor_id=ACTOR, room_id=ROOM, world_id=WORLD,
                                  allowed=fx.RULE_KINDS)
    assert applied[0].event is None
    assert objects.get(ACTOR).location_id == ROOM
