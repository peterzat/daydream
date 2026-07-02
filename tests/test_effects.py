"""Unit tests for daydream/skills/effects.py.

Covers SPEC criterion 4: effect allowlist executes only enumerated
kinds; unknown kinds drop with a log warning AND emit a narrate
fallback so the player always sees something. Uses a real tmp SQLite
DB so state mutations (add_item, set_mood) are verified end-to-end."""

from pathlib import Path

import pytest

from daydream import config, db, events, items, toons
from daydream.skills import effects

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


# ---- allowlist contract ----------------------------------------------------


def test_allowlist_contains_minimum_kinds():
    # SPEC criterion 4: v1 allowlist covers at minimum these three.
    # Extra kinds may be added; these three are the floor.
    assert "narrate" in effects.ALLOWED_KINDS
    assert "add_item" in effects.ALLOWED_KINDS
    assert "set_mood" in effects.ALLOWED_KINDS


def test_allowlist_contains_world_mutation_kinds():
    # SPEC 2026-06-30: the world-mutation vocabulary.
    assert {"narrate", "set_property", "spawn_object", "move_object"} <= effects.ALLOWED_KINDS


# ---- narrate --------------------------------------------------------------


def test_narrate_effect_emits_event():
    applied = effects.dispatch_effects(
        [{"kind": "narrate", "text": "the embers stir gently"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert len(applied) == 1
    assert applied[0].kind == "narrate"
    assert applied[0].event is not None
    assert applied[0].event.kind == "narrate"
    assert applied[0].event.payload["text"] == "the embers stir gently"


def test_narrate_without_text_is_dropped_silently():
    applied = effects.dispatch_effects(
        [{"kind": "narrate"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert len(applied) == 1
    # Allowed kinds with bad shape return event=None (no fallback narrate);
    # only UNKNOWN kinds get the fallback, because a malformed-but-allowed
    # effect is a skill-authoring bug the author should fix, not a player
    # surface.
    assert applied[0].event is None


# ---- add_item -------------------------------------------------------------


def test_add_item_inserts_row_and_emits_event():
    before = {i.name for i in items.get_items_in_room("r-meadow")}
    applied = effects.dispatch_effects(
        [{"kind": "add_item", "name": "clay cup",
          "seed": "a small hand-thrown clay cup, warm brown glaze"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None
    assert applied[0].event.kind == "item_added"
    after = {i.name for i in items.get_items_in_room("r-meadow")}
    assert after - before == {"clay cup"}


def test_add_item_without_name_is_dropped():
    applied = effects.dispatch_effects(
        [{"kind": "add_item", "seed": "no name"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is None


def test_add_item_with_empty_seed_still_allowed():
    # seed="" is a legitimate choice for a skill author; only missing
    # name is a hard fail. An empty seed just makes the item less
    # interesting when later examined.
    applied = effects.dispatch_effects(
        [{"kind": "add_item", "name": "pebble"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None
    names = {i.name for i in items.get_items_in_room("r-meadow")}
    assert "pebble" in names


# ---- set_mood -------------------------------------------------------------


def test_set_mood_updates_toon_and_emits_event():
    before = toons.get_toon("t-wren").mood
    applied = effects.dispatch_effects(
        [{"kind": "set_mood", "toon_id": "t-wren", "mood": "amused"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None
    assert applied[0].event.kind == "mood_set"
    after = toons.get_toon("t-wren").mood
    assert after == "amused" and after != before


def test_set_mood_defaults_target_to_actor():
    applied = effects.dispatch_effects(
        [{"kind": "set_mood", "mood": "wistful"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None
    assert toons.get_toon("t-wren").mood == "wistful"


def test_set_mood_unknown_toon_drops():
    applied = effects.dispatch_effects(
        [{"kind": "set_mood", "toon_id": "t-nonexistent", "mood": "x"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is None


# ---- unknown kind / malformed entries -------------------------------------


def test_unknown_kind_drops_and_emits_narrate_fallback():
    applied = effects.dispatch_effects(
        [{"kind": "teleport_planet", "target": "jupiter"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].kind == "teleport_planet"
    assert applied[0].event is not None
    # Fallback is a narrate so the player still sees *something*.
    assert applied[0].event.kind == "narrate"


def test_malformed_entries_all_get_fallback():
    applied = effects.dispatch_effects(
        [None, "a string", 42, {"no": "kind"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert len(applied) == 4
    for a in applied:
        assert a.event is not None
        assert a.event.kind == "narrate"


# ---- ordering + batch behavior --------------------------------------------


def test_dispatch_preserves_input_order():
    applied = effects.dispatch_effects(
        [
            {"kind": "narrate", "text": "first"},
            {"kind": "narrate", "text": "second"},
            {"kind": "narrate", "text": "third"},
        ],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert [a.event.payload["text"] for a in applied] == ["first", "second", "third"]


# ---- world-mutation kinds: set_property / spawn_object / move_object -------


def test_set_property_updates_object():
    from daydream import objects
    applied = effects.dispatch_effects(
        [{"kind": "set_property", "target_id": "i-lantern", "key": "lit", "value": False}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None
    assert applied[0].event.kind == "property_set"
    assert objects.get_property("i-lantern", "lit") is False


def test_set_property_without_value_is_dropped():
    applied = effects.dispatch_effects(
        [{"kind": "set_property", "target_id": "i-lantern", "key": "lit"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is None


def test_spawn_object_creates_clickable_thing():
    from daydream import items
    before = {i.name for i in items.get_items_in_room("r-meadow")}
    applied = effects.dispatch_effects(
        [{"kind": "spawn_object", "name": "a sheaf of papers",
          "seed": "loose pages in a careful hand", "readable": True,
          "aliases": ["papers"], "generated_by": "talk:rook"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None
    assert applied[0].event.kind == "object_spawned"
    after = {i.name for i in items.get_items_in_room("r-meadow")}
    assert after - before == {"a sheaf of papers"}


def test_spawn_object_verbs_passthrough_grants_per_object_verbs():
    """An optional `verbs` list on spawn_object lands in properties.verbs, so a
    spawned object gains affordances beyond its prototype (a given key becomes
    use-able)."""
    from daydream import objects
    applied = effects.dispatch_effects(
        [{"kind": "spawn_object", "name": "case key", "seed": "a small warm key",
          "aliases": ["key"], "verbs": ["use"], "generated_by": "give:t-rook"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None and applied[0].event.kind == "object_spawned"
    key = next(o for o in objects.contents("r-meadow", "thing") if o.name == "case key")
    # Prototype defaults (examine/take/drop) unioned with the per-object `use`.
    assert "use" in objects.verbs_for(key)


def test_spawn_object_ignores_malformed_verbs():
    """A non-list / all-empty `verbs` is ignored (no properties.verbs written),
    so a malformed effect never corrupts the spawned object."""
    from daydream import objects
    effects.dispatch_effects(
        [{"kind": "spawn_object", "name": "plain stone", "seed": "a stone",
          "verbs": "notalist"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    stone = next(o for o in objects.contents("r-meadow", "thing") if o.name == "plain stone")
    assert "verbs" not in stone.properties


def test_move_object_reparents_into_inventory():
    from daydream import objects
    applied = effects.dispatch_effects(
        [{"kind": "move_object", "object_id": "i-lantern", "dest_id": "t-wren"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is not None
    assert applied[0].event.kind == "object_moved"
    assert objects.get("i-lantern").location_id == "t-wren"


def test_move_object_unknown_target_drops():
    applied = effects.dispatch_effects(
        [{"kind": "move_object", "object_id": "i-nope", "dest_id": "t-wren"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert applied[0].event is None


# ---- per-verb allowlist gate ----------------------------------------------


def test_per_verb_allowlist_rejects_disallowed_kind():
    """A verb declaring only {narrate} cannot emit move_object: the effect is
    rejected (fallback narrate) and NO state is mutated."""
    from daydream import objects
    before = objects.get("i-lantern").location_id
    applied = effects.dispatch_effects(
        [{"kind": "move_object", "object_id": "i-lantern", "dest_id": "t-wren"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=frozenset({"narrate"}),
    )
    # Rejected like an unknown kind: fallback narrate, no mutation.
    assert applied[0].kind == "move_object"
    assert applied[0].event is not None and applied[0].event.kind == "narrate"
    assert objects.get("i-lantern").location_id == before


def test_per_verb_allowlist_permits_declared_kind():
    from daydream import objects
    applied = effects.dispatch_effects(
        [{"kind": "move_object", "object_id": "i-lantern", "dest_id": "t-wren"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=frozenset({"move_object", "narrate"}),
    )
    assert applied[0].event is not None and applied[0].event.kind == "object_moved"
    assert objects.get("i-lantern").location_id == "t-wren"


# ---- world-shaping kinds: spawn_room / link_exit (SPEC 2026-07-02) ---------


_GROW = frozenset({"spawn_room", "link_exit", "narrate"})


def _spawn_room(room_id="r-test-grove", slug="test-grove", *, properties=None,
                allowed=_GROW, **overrides):
    eff = {
        "kind": "spawn_room", "room_id": room_id, "slug": slug,
        "title": "The Test Grove", "seed": "a soft grove of test pines",
        "description": "A quiet grove where assertions grow on low branches.",
    }
    if properties is not None:
        eff["properties"] = properties
    eff.update(overrides)
    return effects.dispatch_effects(
        [eff], actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=allowed,
    )


def test_default_kinds_exclude_world_shaping():
    """allowed=None (the data-skill default) must never grant world-shaping:
    spawn_room / link_exit are in ALLOWED_KINDS but NOT in DEFAULT_KINDS."""
    assert effects.WORLD_SHAPING_KINDS <= effects.ALLOWED_KINDS
    assert not (effects.WORLD_SHAPING_KINDS & effects.DEFAULT_KINDS)
    assert "narrate" in effects.DEFAULT_KINDS  # the standard vocabulary remains


def test_spawn_room_creates_first_class_room():
    from daydream import objects, rooms
    applied = _spawn_room()
    assert applied[0].event is not None
    assert applied[0].event.kind == "room_grown"
    assert applied[0].event.payload["room_id"] == "r-test-grove"
    # The existing Room reader consumes it with zero changes.
    room = rooms.get_room("r-test-grove")
    assert room is not None
    assert room.slug == "test-grove"
    assert room.title == "The Test Grove"
    assert room.seed == "a soft grove of test pines"
    assert room.description_cached.startswith("A quiet grove")
    assert room.exits == {}
    obj = objects.get("r-test-grove")
    assert obj.kind == "room" and obj.prototype_id == objects.PROTO_ROOM
    assert obj.location_id is None  # rooms are top-level


def test_spawn_room_duplicate_id_rejected():
    from daydream import objects
    _spawn_room()
    applied = _spawn_room(slug="other-slug")  # same id, different slug
    assert applied[0].event is None
    assert objects.get("r-test-grove").properties["slug"] == "test-grove"


def test_spawn_room_duplicate_slug_rejected():
    from daydream import objects
    _spawn_room()
    applied = _spawn_room(room_id="r-other")  # different id, same slug
    assert applied[0].event is None
    assert objects.get("r-other") is None


def test_spawn_room_missing_fields_rejected():
    from daydream import objects
    for missing in ("room_id", "slug", "title", "seed"):
        applied = _spawn_room(**{missing: ""})
        assert applied[0].event is None, f"empty {missing} must reject"
    assert objects.get("r-test-grove") is None


def test_spawn_room_properties_passthrough_computed_keys_win():
    from daydream import objects
    applied = _spawn_room(properties={
        "generated_by": "plant:o-seed", "grown": {"seed_id": "o-seed"},
        "slug": "evil-slug", "exits": {"north": "r-meadow"},
    })
    assert applied[0].event is not None
    props = objects.get("r-test-grove").properties
    # Provenance passes through; the computed room shape wins on collision.
    assert props["generated_by"] == "plant:o-seed"
    assert props["grown"] == {"seed_id": "o-seed"}
    assert props["slug"] == "test-grove"
    assert props["exits"] == {}


def test_link_exit_writes_both_sides():
    from daydream import rooms
    _spawn_room()
    applied = effects.dispatch_effects(
        [{"kind": "link_exit", "from_room_id": "r-meadow",
          "to_room_id": "r-test-grove", "direction": "up",
          "reverse_direction": "down"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=_GROW,
    )
    assert applied[0].event is not None
    assert applied[0].event.kind == "exit_linked"
    assert rooms.get_room("r-meadow").exits["up"] == "r-test-grove"
    assert rooms.get_room("r-test-grove").exits["down"] == "r-meadow"


def test_link_exit_occupied_direction_all_or_nothing():
    """A link whose TO side is taken writes NEITHER side — never a one-way
    exit."""
    from daydream import rooms
    _spawn_room()  # r-test-grove
    _spawn_room(room_id="r-test-attic", slug="test-attic")
    ok = effects.dispatch_effects(
        [{"kind": "link_exit", "from_room_id": "r-test-grove",
          "to_room_id": "r-test-attic", "direction": "north",
          "reverse_direction": "south"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny", allowed=_GROW,
    )
    assert ok[0].event is not None
    _spawn_room(room_id="r-test-cellar", slug="test-cellar")
    # cellar -> attic: 'east' is free on the cellar, but 'south' is taken on
    # the attic. The whole link must reject with neither side written.
    applied = effects.dispatch_effects(
        [{"kind": "link_exit", "from_room_id": "r-test-cellar",
          "to_room_id": "r-test-attic", "direction": "east",
          "reverse_direction": "south"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny", allowed=_GROW,
    )
    assert applied[0].event is None
    assert rooms.get_room("r-test-cellar").exits == {}
    assert rooms.get_room("r-test-attic").exits == {"south": "r-test-grove"}


def test_link_exit_rejects_unknown_or_non_room_or_self():
    from daydream import rooms
    _spawn_room()
    for bad in (
        {"from_room_id": "r-test-grove", "to_room_id": "r-nowhere"},
        {"from_room_id": "r-nowhere", "to_room_id": "r-test-grove"},
        {"from_room_id": "r-test-grove", "to_room_id": "i-lantern"},
        {"from_room_id": "r-test-grove", "to_room_id": "r-test-grove"},
    ):
        applied = effects.dispatch_effects(
            [{"kind": "link_exit", "direction": "north",
              "reverse_direction": "south", **bad}],
            actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
            allowed=_GROW,
        )
        assert applied[0].event is None, f"link must reject: {bad}"
    assert rooms.get_room("r-test-grove").exits == {}


def test_spawn_object_properties_passthrough():
    """An authored `properties` dict rides into the spawned object; the
    computed keys (seed et al.) win on collision."""
    from daydream import objects
    effects.dispatch_effects(
        [{"kind": "spawn_object", "name": "dreamseed", "seed": "winner",
          "verbs": ["plant"],
          "properties": {"growth": {"question": "where to?"}, "seed": "loser"}}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    seed_obj = next(o for o in objects.contents("r-meadow", "thing")
                    if o.name == "dreamseed")
    assert seed_obj.properties["growth"] == {"question": "where to?"}
    assert seed_obj.seed == "winner"
    assert seed_obj.properties["verbs"] == ["plant"]


def test_world_shaping_rejected_for_data_skill_default():
    """allowed=None (an NPC dialogue / standalone data skill) attempting
    spawn_room or link_exit is rejected exactly like an unknown kind: fallback
    narrate, NO mutation (SPEC 2026-07-02 criterion 4)."""
    from daydream import objects
    applied = effects.dispatch_effects(
        [{"kind": "spawn_room", "room_id": "r-sneaky", "slug": "sneaky",
          "title": "Sneaky", "seed": "s"},
         {"kind": "link_exit", "from_room_id": "r-meadow",
          "to_room_id": "r-forge", "direction": "up", "reverse_direction": "down"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=None,
    )
    assert [a.event.kind for a in applied] == ["narrate", "narrate"]  # fallbacks
    assert objects.get("r-sneaky") is None


def test_world_shaping_rejected_for_undeclaring_verb():
    """A verb whose allowlist omits the world-shaping kinds cannot emit them."""
    from daydream import objects
    applied = effects.dispatch_effects(
        [{"kind": "spawn_room", "room_id": "r-sneaky", "slug": "sneaky",
          "title": "Sneaky", "seed": "s"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=frozenset({"narrate", "spawn_object"}),
    )
    assert applied[0].event is not None and applied[0].event.kind == "narrate"
    assert objects.get("r-sneaky") is None


def test_grown_room_count_counts_only_grown():
    from daydream import rooms
    assert rooms.grown_room_count("w-bunny") == 0
    _spawn_room()  # no `grown` provenance: an authored-style room
    assert rooms.grown_room_count("w-bunny") == 0
    _spawn_room(room_id="r-test-fern", slug="test-fern",
                properties={"grown": {"seed_id": "o-seed", "planter_id": "t-wren",
                                      "phrase": "a mossy hollow", "at": "now"}})
    assert rooms.grown_room_count("w-bunny") == 1


def test_one_bad_effect_does_not_poison_others():
    applied = effects.dispatch_effects(
        [
            {"kind": "narrate", "text": "keeps going"},
            {"kind": "lava_flood"},  # unknown; drops
            {"kind": "set_mood", "mood": "steady"},
        ],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
    )
    assert len(applied) == 3
    assert applied[0].event.kind == "narrate"
    assert applied[1].event.kind == "narrate"  # fallback
    assert applied[2].event.kind == "mood_set"
    assert toons.get_toon("t-wren").mood == "steady"
