"""Hostiles (Zork turn, SPEC 2026-07-02 criterion 8): seeded combat with
per-villain strength and weak-weapon data, the unkillable villain, on-death
drops and hoard reveal, the wanderer daemon's roam/steal/deposit loop, the
conveyor carrying vehicle + rider, and the glow item. All pinned-seed."""

from pathlib import Path

import pytest

from daydream import clock, config, db, events, objects, verbs, worldstate

pytestmark = pytest.mark.tier_short

WORLD = "w-bunny"
ACTOR = "t-wren"
ROOM = "r-meadow"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    worldstate.set(WORLD, "rng_seed", "pin")
    yield
    db.close_db()
    events.reset_subscribers()


def narrates():
    return [e.payload.get("text", "") for e in events.fetch_since(0)
            if e.kind == "narrate"]


def spawn_troll(strength=2, **combat_overrides):
    combat = {
        "strength": strength,
        "weak_to": "o-sword",
        "hit_texts": ["The troll reels."],
        "miss_texts": ["You miss."],
        "death_text": "The troll dissolves into black smoke.",
        "counter_kill_chance": 0.0,
        "counter_texts": ["The axe sweeps past you."],
        "on_death": [{"kind": "set_flag", "name": "TROLL-DEAD", "value": True}],
        **combat_overrides,
    }
    return objects.spawn(
        WORLD, "toon", "troll", ROOM,
        properties={"combat": combat, "verbs": ["attack", "examine"]},
        object_id="t-troll",
    )


def spawn_sword(location=ACTOR):
    return objects.spawn(WORLD, "thing", "elvish sword", location,
                         aliases=["sword"], object_id="o-sword")


# ---- combat ------------------------------------------------------------------


async def test_correct_weapon_kills_in_strength_hits():
    spawn_troll(strength=2)
    spawn_sword()
    await verbs.execute_command(ACTOR, "attack", "t-troll", "o-sword")
    assert objects.get("t-troll") is not None  # one hit down, still up
    assert "The troll reels." in narrates()
    await verbs.execute_command(ACTOR, "attack", "t-troll", "o-sword")
    assert objects.get("t-troll") is None      # correct weapon: deterministic
    assert "The troll dissolves into black smoke." in narrates()
    assert worldstate.get_flag(WORLD, "TROLL-DEAD") is True


async def test_death_drops_carried_hoard_to_room():
    troll = spawn_troll(strength=1)
    spawn_sword()
    loot = objects.spawn(WORLD, "thing", "stolen chalice", troll.id,
                         object_id="o-chalice")
    await verbs.execute_command(ACTOR, "attack", "t-troll", "o-sword")
    assert objects.get(loot.id).location_id == ROOM


async def test_wrong_weapon_is_seeded_probabilistic():
    spawn_troll(strength=100)  # never dies in this test
    objects.spawn(WORLD, "thing", "rubber chicken", ACTOR, object_id="o-chicken")
    import random as _r

    # Replay the handler's stream: turn advances before... attack rolls
    # happen DURING the command (before its tick), so turn is the pre-tick
    # value each time. Track expected hits over 6 swings.
    hits = 0
    for i in range(6):
        turn = worldstate.turn(WORLD)
        roll = _r.Random(f"pin:{turn}:combat:t-troll").random()
        await verbs.execute_command(ACTOR, "attack", "t-troll", "o-chicken")
        if roll < 0.4:
            hits += 1
    strength = objects.get("t-troll").properties.get("combat_strength")
    assert strength == 100 - hits


async def test_unkillable_villain_refuses_combat():
    spawn_troll(unkillable=True, refuse_text="The cyclops shrugs you off.")
    spawn_sword()
    await verbs.execute_command(ACTOR, "attack", "t-troll", "o-sword")
    assert objects.get("t-troll") is not None
    assert objects.get("t-troll").properties.get("combat_strength") is None
    assert "The cyclops shrugs you off." in narrates()


async def test_counterattack_can_kill_under_death_policy():
    worldstate.set(WORLD, "config", {"death": {
        "penalty": 10, "respawn_room": "r-forge",
        "messages": ["You have died."],
    }})
    spawn_troll(strength=100, counter_kill_chance=1.0)
    spawn_sword()
    # Swing with the correct weapon: it lands, troll survives (100), then
    # counter kills at chance 1.0.
    await verbs.execute_command(ACTOR, "attack", "t-troll", "o-sword")
    assert objects.get(ACTOR).location_id == "r-forge"
    assert worldstate.counter(WORLD, "deaths") == 1


async def test_attack_non_combatant_declines():
    objects.set_property("t-rook", "verbs", ["attack"])
    objects.move("t-rook", ROOM)
    spawn_sword()
    await verbs.execute_command(ACTOR, "attack", "t-rook", "o-sword")
    assert "Rook doesn't want to fight." in narrates()
    assert objects.get("t-rook") is not None


async def test_diagnose_reports_deaths():
    await verbs.execute_command(ACTOR, "diagnose")
    assert "You are in perfect health." in narrates()
    worldstate.adjust_counter(WORLD, "deaths", 2)
    await verbs.execute_command(ACTOR, "diagnose")
    assert any("died 2 times" in t for t in narrates())


# ---- wanderer -----------------------------------------------------------------


def install_thief(move_chance=1.0, **overrides):
    objects.spawn(WORLD, "toon", "thief", "r-forge",
                  properties={"verbs": ["attack", "examine"]},
                  object_id="t-thief")
    d = {
        "kind": "wanderer", "toon": "t-thief",
        "rooms": [ROOM, "r-forge", "r-bridge"],
        "move_chance": move_chance,
        "steal_from_room_chance": 1.0,
        "steal_from_player_chance": 1.0,
        "steal_filter": {"key": "treasure", "eq": True},
        "deposit_room": "r-attic",
        "arrive_text": "A shadowy figure slips in.",
        "leave_text": "The shadowy figure melts away.",
        "steal_text": "You feel a light touch at your satchel.",
        **overrides,
    }
    worldstate.set(WORLD, "def:daemons", {"thief": d})
    worldstate.set(WORLD, "daemon:thief", {"active": True})
    return d


def test_wanderer_roams_its_room_set():
    install_thief(move_chance=1.0)
    clock.tick(ACTOR)
    loc = objects.get("t-thief").location_id
    assert loc in (ROOM, "r-forge", "r-bridge")


def test_wanderer_steals_from_room_and_deposits_in_lair():
    install_thief(move_chance=0.0)
    objects.spawn(WORLD, "thing", "emerald", "r-forge",
                  properties={"treasure": True}, object_id="o-emerald")
    clock.tick(ACTOR)
    assert objects.get("o-emerald").location_id == "t-thief"
    # Teleport the thief home: pockets empty into the lair on its tick.
    objects.move("t-thief", "r-attic")
    clock.tick(ACTOR)
    assert objects.get("o-emerald").location_id == "r-attic"


def test_wanderer_picks_player_pocket_with_private_narrate():
    # The seed ships Wren unclaimed; the wanderer robs PLAYERS (claimed or
    # human-controlled toons), so mark her as the live player she'd be.
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1 WHERE id = 't-wren'"
    )
    install_thief(move_chance=0.0)
    objects.move("t-thief", ROOM)
    objects.spawn(WORLD, "thing", "jeweled egg", ACTOR,
                  properties={"treasure": True}, object_id="o-egg")
    clock.tick(ACTOR)
    assert objects.get("o-egg").location_id == "t-thief"
    private = [e for e in events.fetch_since(0)
               if e.kind == "narrate" and e.recipient_id == ACTOR]
    assert any("light touch" in e.payload["text"] for e in private)


def test_wanderer_ignores_non_matching_items():
    install_thief(move_chance=0.0)
    objects.move("t-thief", ROOM)
    clock.tick(ACTOR)
    assert objects.get("i-lantern").location_id == ROOM  # not a treasure


def test_dead_wanderer_daemon_idles():
    install_thief()
    objects.delete("t-thief")
    clock.tick(ACTOR)  # no crash, nothing to do


# ---- conveyor -----------------------------------------------------------------


def river_world():
    for rid in ("r-river1", "r-river2", "r-river3"):
        objects.spawn(WORLD, "room", rid[2:], None,
                      prototype_id=objects.PROTO_ROOM,
                      properties={"slug": rid[2:], "title": rid[2:],
                                  "seed": "water", "exits": {}},
                      object_id=rid)
    boat = objects.spawn(WORLD, "thing", "boat", "r-river1",
                         properties={"vehicle": True}, object_id="o-boat")
    worldstate.set(WORLD, "def:daemons", {"river": {
        "kind": "conveyor", "vehicle": "o-boat",
        "path": ["r-river1", "r-river2", "r-river3"],
        "delays": [2, 1],
        "carry_text": "The current carries you along.",
    }})
    worldstate.set(WORLD, "daemon:river", {"active": True})
    return boat


def test_conveyor_carries_vehicle_and_rider_with_delays():
    river_world()
    objects.move(ACTOR, "r-river1")
    objects.set_property(ACTOR, "aboard", "o-boat")
    clock.tick(ACTOR)  # progress 1/2: stays
    assert objects.get("o-boat").location_id == "r-river1"
    clock.tick(ACTOR)  # progress 2/2: moves to river2
    assert objects.get("o-boat").location_id == "r-river2"
    assert objects.get(ACTOR).location_id == "r-river2"  # rider came along
    clock.tick(ACTOR)  # delay 1 at river2: straight on to river3
    assert objects.get("o-boat").location_id == "r-river3"
    clock.tick(ACTOR)  # end of path: stays
    assert objects.get("o-boat").location_id == "r-river3"


def test_conveyor_ignores_beached_vehicle():
    boat = river_world()
    objects.move(boat.id, ROOM)  # ashore, off the path
    clock.tick(ACTOR)
    assert objects.get(boat.id).location_id == ROOM


def test_conveyor_leaves_non_riders_behind():
    river_world()
    objects.move(ACTOR, "r-river1")  # present but NOT aboard
    clock.tick(ACTOR)
    clock.tick(ACTOR)
    assert objects.get("o-boat").location_id == "r-river2"
    assert objects.get(ACTOR).location_id == "r-river1"


# ---- glow ---------------------------------------------------------------------


def glow_world():
    objects.spawn(WORLD, "toon", "troll", "r-forge",
                  properties={}, object_id="t-troll")
    sword = objects.spawn(WORLD, "thing", "elvish sword", ACTOR,
                          object_id="o-sword")
    worldstate.set(WORLD, "def:daemons", {"swordglow": {
        "kind": "glow", "item": "o-sword", "hostiles": ["t-troll"],
        "bright_text": "Your sword has begun to glow very brightly.",
        "faint_text": "Your sword is glowing with a faint blue glow.",
        "dim_text": "Your sword is no longer glowing.",
    }})
    worldstate.set(WORLD, "daemon:swordglow", {"active": True})
    return sword


def test_glow_levels_track_adjacency_and_presence():
    sword = glow_world()
    # Meadow is adjacent to forge (north exit): faint.
    clock.tick(ACTOR)
    assert objects.get(sword.id).properties["glow_level"] == 1
    faint = [e for e in events.fetch_since(0)
             if e.kind == "narrate" and "faint" in e.payload.get("text", "")]
    assert faint and faint[0].recipient_id == ACTOR
    # Same room: bright. (Narrates on change only.)
    objects.move("t-troll", ROOM)
    clock.tick(ACTOR)
    assert objects.get(sword.id).properties["glow_level"] == 2
    clock.tick(ACTOR)
    brights = [e for e in events.fetch_since(0)
               if e.kind == "narrate" and "brightly" in e.payload.get("text", "")]
    assert len(brights) == 1  # no repeat while unchanged
    # Hostile gone: dim.
    objects.delete("t-troll")
    clock.tick(ACTOR)
    assert objects.get(sword.id).properties["glow_level"] == 0
