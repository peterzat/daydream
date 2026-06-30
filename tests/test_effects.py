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
