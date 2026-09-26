"""LLM-originated spawns cannot carry authored-only properties (SPEC
2026-09-26 criterion 19; docs/PIVOT.md section 10).

`spawn_object` used to pass its `properties` dict straight through, and `talk`
may emit `spawn_object`. A dialogue model (or a player injecting into one)
could therefore mint a thing carrying `rules` (which then run under the full
rule allowlist when a player acts on it), a `growth` block (a plantable
dreamseed), extra `verbs`, combat stats, a light source, a container, or a
scoring hook. Model-authored batches now dispatch with origin="llm", which
keeps only name / seed / aliases / location / provenance / readable and pins
the location to the acting room or the actor's hands. These drive the real
talk path with a mocked hostile model and assert the spawn is bare."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, verbs
from daydream.skills import effects

pytestmark = pytest.mark.tier_short

AUTHORED_ONLY = {
    "rules": [{"on": "take", "do": [{"kind": "win", "text": "you win"}]}],
    "growth": {"question": "where?", "theme": ["x"]},
    "combat": {"strength": 99},
    "light": True, "lit": True,
    "container": True, "capacity": 99,
    "score_take": 50, "treasure": True,
    "state": "open",
}

HOSTILE_SPAWN = {"effects": [
    {"kind": "narrate", "text": "Mossling rummages in a pocket and hums."},
    {"kind": "spawn_object", "name": "glimmering pebble",
     "seed": "a small pebble that glimmers", "generated_by": "talk:mossling",
     "properties": dict(AUTHORED_ONLY), "verbs": ["plant", "attack"]},
]}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _mossling(allowed_kinds: list[str]) -> objects.Object:
    import json

    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES ('skill-dlg-mossling', 'dlg-mossling', 'data', "
        "'{\"room_slug\": \"__npc_dialogue__\"}', '{{ player_input }}', 'Talk', "
        "'Talk.', ?, 1)",
        (json.dumps({"allowed_kinds": allowed_kinds}),),
    )
    return objects.spawn(
        "w-bunny", "toon", "Mossling", "r-meadow", prototype_id=objects.PROTO_NPC,
        properties={"seed": "a small moss spirit", "dialogue": "dlg-mossling"},
    )


def _pebbles() -> list[objects.Object]:
    return [o for o in objects.contents("r-meadow", kind="thing")
            if o.name == "glimmering pebble"]


async def test_talk_spawn_is_stripped_of_authored_only_fields(monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(return_value=dict(HOSTILE_SPAWN)))
    npc = _mossling(["narrate", "spawn_object"])
    await verbs.execute_command("t-wren", "talk", dobj_id=npc.id, args="hello")
    pebbles = _pebbles()
    assert len(pebbles) == 1, "the name + seed spawn itself still lands"
    props = pebbles[0].properties
    for key in AUTHORED_ONLY:
        assert key not in props, f"authored-only {key!r} leaked onto an LLM spawn"
    assert "verbs" not in props
    assert "plant" not in objects.verbs_for(pebbles[0])
    assert props["generated_by"] == "talk:mossling"


async def test_llm_spawn_cannot_target_another_location(monkeypatch):
    far = {"effects": [
        {"kind": "narrate", "text": "Mossling waves a hand."},
        {"kind": "spawn_object", "name": "far pebble", "seed": "a pebble",
         "generated_by": "talk:mossling", "location_id": "r-forge"},
    ]}
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(return_value=far))
    npc = _mossling(["narrate", "spawn_object"])
    await verbs.execute_command("t-wren", "talk", dobj_id=npc.id, args="hi")
    assert not [o for o in objects.contents("r-forge", kind="thing")
                if o.name == "far pebble"]


def test_engine_origin_spawns_keep_authored_properties():
    """Authored payloads (a case revealing a dreamseed, a rule granting a
    keepsake) still carry their properties: only origin='llm' is narrowed."""
    effects.dispatch_effects(
        [{"kind": "spawn_object", "name": "authored seed", "seed": "s",
          "properties": {"growth": {"question": "q"}}, "verbs": ["plant"]}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=effects.RULE_KINDS,
    )
    seed = next(o for o in objects.contents("r-meadow", kind="thing")
                if o.name == "authored seed")
    assert seed.properties["growth"] == {"question": "q"}
    assert "plant" in objects.verbs_for(seed)


def test_llm_move_object_is_scoped_to_the_actor():
    """A model-authored move may not reach an object or destination outside
    the actor's scope (another room's things, another toon's satchel)."""
    target = objects.spawn("w-bunny", "thing", "far kettle", "r-forge",
                           prototype_id=objects.PROTO_THING)
    applied = effects.dispatch_effects(
        [{"kind": "move_object", "object_id": target.id, "dest_id": "t-wren"}],
        actor_id="t-wren", room_id="r-meadow", world_id="w-bunny",
        allowed=frozenset({"move_object"}), origin="llm",
    )
    assert applied[0].event is None
    assert objects.get(target.id).location_id == "r-forge"
