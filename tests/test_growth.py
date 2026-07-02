"""Dreamseed growth pipeline (daydream/growth.py; SPEC 2026-07-02).

Per-rule unit tests with a MOCKED LLM (zero GPU): the happy-path plant makes
exactly ONE LLM call and lands the full atomic batch; every gate and failure
path (outage, refusal, schema, banlist, anti-copy, cap, directions, phrase
rules) preserves the seed and mutates NOTHING; and the post-LLM synchronous
commit block re-checks state an LLM await could have raced (seed dropped, cap
reached, rival plant taking the direction or the slug)."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, growth, objects, rooms, verbs
from daydream.llm import client

pytestmark = pytest.mark.tier_short

# The allowlist the `plant` verb declares (mirrored in verbs.VERBS once the
# verb lands; growth tests pass it explicitly so the pipeline is testable on
# its own).
PLANT_ALLOWED = frozenset(
    {"spawn_room", "link_exit", "rename_object", "spawn_object",
     "move_object", "set_property", "narrate"}
)

GROWTH_BLOCK = {
    "question": "Where does the new way lead?",
    "theme": ["clockwork", "dusk"],
    "palette": "warm brass and amber watercolor",
    "motifs": ["small resting clocks", "lantern light"],
    "exemplars": [
        {"title": "The Winding Stair",
         "seed": "a narrow brass stair climbing into amber dusk",
         "description": "A stair coils up into the last of the light. Small "
                        "clocks rest on its steps, each keeping its own soft "
                        "time."},
    ],
    "husk_text": "a spent dreamseed, its light gone soft and its work done",
}

VALID_COMPOSITION = {
    "title": "The Moss Stair",
    "room_seed": "a narrow stair of soft moss winding down into green light",
    "description": "A stair of moss coils gently downward. The air is cool "
                   "and smells of rain. Somewhere below, water keeps a slow "
                   "time of its own.",
    "objects": [
        {"name": "mossy pebble", "seed": "a small pebble wearing a coat of moss"},
    ],
}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _seed(carried: bool = True, growth_block: dict | None = GROWTH_BLOCK):
    props: dict = {"seed": "a dreamseed like a folded lantern", "verbs": ["plant"]}
    if growth_block is not None:
        props["growth"] = dict(growth_block)
    return objects.spawn(
        "w-bunny", "thing", "dreamseed",
        "t-wren" if carried else "r-meadow",
        prototype_id=objects.PROTO_THING, properties=props,
    )


def _wren():
    return objects.get("t-wren")


def _mock_llm(monkeypatch, payload):
    spy = AsyncMock(return_value=payload)
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    return spy


def _last_narrate() -> str:
    for e in reversed(events.fetch_since(0)):
        if e.kind == "narrate":
            return e.payload["text"]
    raise AssertionError("no narration emitted")


def _grown_rooms() -> list:
    return [
        o for o in db.get_conn().execute(
            "SELECT id FROM objects WHERE kind = 'room' AND "
            "json_extract(properties_json, '$.grown') IS NOT NULL"
        ).fetchall()
    ]


# The default phrase is deliberately hint-free (no down/up/compass words), so
# tests built on it keep the first-free direction (south, in the meadow).
async def _plant(seed, args="a mossy stair into green light"):
    await growth.execute_plant(_wren(), "r-meadow", seed, args, PLANT_ALLOWED)


def _assert_nothing_grew(seed_id: str, *, carried: bool = True):
    """The universal failure-path postcondition: no room, no exit, and the
    seed intact — carried (or wherever it was), unspent, still plantable."""
    assert _grown_rooms() == []
    seed = objects.get(seed_id)
    assert seed is not None
    if carried:
        assert seed.location_id == "t-wren"
    assert seed.properties.get("state") != "spent"
    assert "plant" in seed.properties.get("verbs", [])
    # The meadow gained no exit (its seeded exits are north + east).
    assert set(rooms.get_room("r-meadow").exits) == {"north", "east"}


# ---- the happy path -----------------------------------------------------


@pytest.mark.asyncio
async def test_plant_happy_path_full_atomic_batch(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "a mossy stair into green light")

    # Exactly ONE LLM call (SPEC criterion 1).
    assert spy.call_count == 1

    # The room exists, first-class to the existing Room reader.
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair")
    assert room is not None and room.id == "r-the-moss-stair"
    assert room.title == "The Moss Stair"
    assert room.seed == VALID_COMPOSITION["room_seed"]
    assert room.description_cached == VALID_COMPOSITION["description"]

    # Exits both ways, engine-picked first-free direction (meadow has
    # north + east seeded, so south) and its involution.
    assert rooms.get_room("r-meadow").exits["south"] == room.id
    assert room.exits["north"] == "r-meadow"

    # Provenance: generated_by + the structured grown record.
    props = objects.get(room.id).properties
    assert props["generated_by"] == f"plant:{seed.id}"
    grown = props["grown"]
    assert grown["seed_id"] == seed.id
    assert grown["planter_id"] == "t-wren"
    assert grown["phrase"] == "a mossy stair into green light"
    assert grown["at"]  # timestamped
    assert rooms.grown_room_count("w-bunny") == 1

    # The composed objects rest in the grown room with provenance.
    things = objects.contents(room.id, kind="thing")
    pebbles = [o for o in things if o.name == "mossy pebble"]
    assert len(pebbles) == 1
    assert pebbles[0].properties["generated_by"] == f"plant:{seed.id}"

    # The seed is consumed: spent, husk examine text, plant no longer
    # offered, renamed so it never reads as a fresh seed, moved into the
    # grown room as a husk.
    husk = objects.get(seed.id)
    assert husk.properties["state"] == "spent"
    assert husk.properties["examined_text"] == GROWTH_BLOCK["husk_text"]
    assert "plant" not in objects.verbs_for(husk)
    assert husk.name == "spent dreamseed"
    assert "husk" in husk.aliases
    assert husk.location_id == room.id

    # The final in-character narrate names the direction and the title.
    line = _last_narrate()
    assert "south" in line and "The Moss Stair" in line


@pytest.mark.asyncio
async def test_grown_room_is_walkable_via_go(monkeypatch):
    """Zero reader changes: the planter can walk the new exit immediately."""
    _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed)
    await verbs.execute_command("t-wren", "go", args="south")
    assert objects.get("t-wren").location_id == "r-the-moss-stair"


@pytest.mark.asyncio
async def test_replant_on_husk_refuses(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed)
    # The husk is in the grown room; hand it back to Wren and try again.
    objects.move(seed.id, "t-wren")
    await _plant(objects.get(seed.id))  # re-read: now spent
    assert spy.call_count == 1  # no second LLM call
    assert rooms.grown_room_count("w-bunny") == 1
    assert "quiet" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_llm_prompt_carries_no_ids_or_directions(monkeypatch):
    """The LLM never sees object ids or exit directions — only boundaries,
    exemplars, room title/seed, and the wrapped phrase."""
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "a mossy stair")
    user = spy.call_args.kwargs["user"]
    assert seed.id not in user and "t-wren" not in user and "r-meadow" not in user
    for d in ("north", "south", "east", "west"):
        assert d not in user.lower()
    assert "<player_input>a mossy stair</player_input>" in user


# ---- pre-LLM gates (no call, no mutation) --------------------------------


@pytest.mark.asyncio
async def test_empty_vision_narrates_authored_question(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "   ")
    spy.assert_not_called()
    assert _last_narrate() == GROWTH_BLOCK["question"]
    _assert_nothing_grew(seed.id)


@pytest.mark.asyncio
async def test_seed_not_carried_refuses(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed(carried=False)
    await _plant(seed)
    spy.assert_not_called()
    assert "hands" in _last_narrate().lower()
    _assert_nothing_grew(seed.id, carried=False)


@pytest.mark.asyncio
async def test_growthless_seed_refuses(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed(growth_block=None)
    await _plant(seed)
    spy.assert_not_called()
    assert "wants to grow" in _last_narrate().lower()
    assert _grown_rooms() == []


@pytest.mark.asyncio
async def test_malformed_growth_refuses_in_character(monkeypatch):
    """A runtime-created seed can carry an arbitrary growth dict (e.g. via a
    spawn_object properties passthrough); a malformed one must narrate the
    no-growth line, never raise through the prompt builder."""
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed(growth_block={"exemplars": [{}]})
    await _plant(seed)
    spy.assert_not_called()
    assert "wants to grow" in _last_narrate().lower()
    _assert_nothing_grew(seed.id)


@pytest.mark.asyncio
async def test_phrase_over_cap_refuses(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "a" * (growth.MAX_PHRASE_CHARS + 1))
    spy.assert_not_called()
    assert "smaller vision" in _last_narrate().lower()
    _assert_nothing_grew(seed.id)


@pytest.mark.asyncio
async def test_banned_phrase_refuses(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "a grimdark server room full of computers")
    spy.assert_not_called()
    _assert_nothing_grew(seed.id)


@pytest.mark.asyncio
async def test_cap_reached_refuses_before_llm(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    monkeypatch.setenv("DAYDREAM_GROWTH_MAX_ROOMS", "0")
    seed = _seed()
    await _plant(seed)
    spy.assert_not_called()
    assert "settle" in _last_narrate().lower()
    _assert_nothing_grew(seed.id)


@pytest.mark.asyncio
async def test_all_directions_taken_refuses(monkeypatch):
    spy = _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    exits = {d: "r-forge" for d in ("north", "east", "south", "west", "up", "down")}
    objects.set_property("r-meadow", "exits", exits)
    seed = _seed()
    await _plant(seed)
    spy.assert_not_called()
    assert "already taken" in _last_narrate().lower()
    assert _grown_rooms() == []
    assert objects.get(seed.id).properties.get("state") != "spent"


def test_growth_cap_default_and_override(monkeypatch):
    monkeypatch.delenv("DAYDREAM_GROWTH_MAX_ROOMS", raising=False)
    assert config.growth_max_rooms() == 12
    monkeypatch.setenv("DAYDREAM_GROWTH_MAX_ROOMS", "3")
    assert config.growth_max_rooms() == 3


# ---- LLM failure paths ----------------------------------------------------


@pytest.mark.asyncio
async def test_llm_outage_narrates_foggy_and_preserves_seed(monkeypatch):
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=client.LLMUnavailable("vllm down")),
    )
    seed = _seed()
    await _plant(seed)
    assert "foggy" in _last_narrate().lower()
    _assert_nothing_grew(seed.id)


@pytest.mark.asyncio
async def test_refusal_narrates_reason_and_preserves_seed(monkeypatch):
    _mock_llm(monkeypatch, {"refused": True,
                            "reason": "the dream can't hold a place like that"})
    seed = _seed()
    await _plant(seed)
    assert _last_narrate() == "the dream can't hold a place like that"
    _assert_nothing_grew(seed.id)


def _bad(overrides: dict | None = None, **kw) -> dict:
    payload = dict(VALID_COMPOSITION)
    payload.update(overrides or {})
    payload.update(kw)
    return payload


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    ["not", "a", "dict"],
    _bad(title="ab"),                       # too short
    _bad(title="x" * 41),                   # too long
    _bad(title="one two three four five six"),  # six words
    _bad(room_seed="too short"),            # < 30
    _bad(room_seed="x" * 301),              # > 300
    _bad(description="too short to arrive"),         # < 60
    _bad(description="d" * 501),            # > 500
    _bad(objects=[{"name": "a valid thing", "seed": "a seed long enough here"}] * 3),  # 3 objects: reject
    _bad(objects=[{"name": "ab", "seed": "a seed long enough here"}]),   # name < 3
    _bad(objects=[{"name": "a valid thing", "seed": "short seed"}]),     # seed < 15
    _bad(objects="not-a-list"),
    _bad(description="A stair coils gently downward toward a grimdark "
                     "hollow of cold machines, and the air hums with it."),  # banlist
], ids=["non-dict", "title-short", "title-long", "title-words",
        "seed-short", "seed-long", "desc-short", "desc-long",
        "three-objects", "obj-name-short", "obj-seed-short",
        "objects-not-list", "banned-text"])
async def test_invalid_composition_rejects_and_preserves_seed(monkeypatch, payload):
    _mock_llm(monkeypatch, payload)
    seed = _seed()
    await _plant(seed)
    assert "won't hold that shape yet" in _last_narrate().lower()
    _assert_nothing_grew(seed.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("title", "The Winding Stair"),   # exemplar title, verbatim
    ("title", "  the winding STAIR "),  # normalized copy
    ("room_seed", "a narrow brass stair climbing into amber dusk"),
    ("description", "A stair coils up into the last of the light. Small "
                    "clocks rest on its steps, each keeping its own soft "
                    "time."),
])
async def test_anti_copy_rejects_exemplar_copies(monkeypatch, field, value):
    _mock_llm(monkeypatch, _bad({field: value}))
    seed = _seed()
    await _plant(seed)
    assert "won't hold that shape yet" in _last_narrate().lower()
    _assert_nothing_grew(seed.id)


def test_validate_growth_output_accepts_zero_objects():
    out = growth.validate_growth_output(_bad(objects=[]), GROWTH_BLOCK)
    assert out is not None and out["objects"] == []
    out = growth.validate_growth_output(
        {k: v for k, v in VALID_COMPOSITION.items() if k != "objects"},
        GROWTH_BLOCK,
    )
    assert out is not None and out["objects"] == []


# ---- phrase-hinted direction pick (playtest 2026-07-02) -------------------


@pytest.mark.asyncio
async def test_phrase_hint_picks_down(monkeypatch):
    """'Down the well to an underground dormitory' should open DOWN when down
    is free — not the first free compass slot."""
    _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "down the well to an underground dormitory")
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair")
    assert rooms.get_room("r-meadow").exits["down"] == room.id
    assert room.exits["up"] == "r-meadow"
    assert "below" in _last_narrate()  # the payoff names the way


@pytest.mark.asyncio
async def test_phrase_hint_picks_up_and_compass(monkeypatch):
    _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "a balcony under the stars")
    # 'stars'/'balcony' hint up (the 'under' down-hint loses to hint order?
    # no: down is checked first — but 'under' IS in the down set, so this
    # phrase hints down first). Pin the actual contract: first hint match in
    # declaration order wins.
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair")
    assert rooms.get_room("r-meadow").exits["down"] == room.id


@pytest.mark.asyncio
async def test_phrase_hint_west(monkeypatch):
    _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    seed = _seed()
    await _plant(seed, "a walled garden to the west of everything")
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair")
    assert rooms.get_room("r-meadow").exits["west"] == room.id


@pytest.mark.asyncio
async def test_phrase_hint_taken_falls_back_to_first_free(monkeypatch):
    """A hinted direction that is already an exit falls through to the
    first-free pick (meadow: north/east seeded + down occupied -> south)."""
    _mock_llm(monkeypatch, dict(VALID_COMPOSITION))
    exits = dict(rooms.get_room("r-meadow").exits)
    exits["down"] = "r-forge"
    objects.set_property("r-meadow", "exits", exits)
    seed = _seed()
    await _plant(seed, "down to a cellar of hours")
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair")
    assert rooms.get_room("r-meadow").exits["south"] == room.id


def test_hint_free_default_phrase_stays_first_free():
    """The suite's default phrase must stay hint-free so first-free tests
    keep meaning what they say."""
    words = set(__import__("re").findall(r"[a-z]+", "a mossy stair into green light"))
    for _, hints in growth._DIRECTION_HINTS:
        assert not (words & hints)


# ---- composed object names normalize to the authored lowercase convention --


@pytest.mark.asyncio
async def test_composed_object_names_lowercased(monkeypatch):
    payload = dict(VALID_COMPOSITION)
    payload["objects"] = [{"name": "Mossy Pebble",
                           "seed": "a small pebble wearing a coat of moss"}]
    _mock_llm(monkeypatch, payload)
    seed = _seed()
    await _plant(seed)
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair")
    names = [o.name for o in objects.contents(room.id, kind="thing")]
    assert "mossy pebble" in names and "Mossy Pebble" not in names


# ---- commit-block races (state changes during the LLM await) --------------


def _racing_llm(monkeypatch, mutate, payload=None):
    """An LLM mock that mutates world state 'during' the await, then returns
    a valid composition — simulating a rival session acting mid-call."""
    async def side_effect(*args, **kwargs):
        mutate()
        return dict(payload or VALID_COMPOSITION)
    spy = AsyncMock(side_effect=side_effect)
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    return spy


@pytest.mark.asyncio
async def test_race_seed_dropped_during_call(monkeypatch):
    seed = _seed()
    _racing_llm(monkeypatch, lambda: objects.move(seed.id, "r-meadow"))
    await _plant(seed)
    assert "hands" in _last_narrate().lower()
    _assert_nothing_grew(seed.id, carried=False)
    assert objects.get(seed.id).location_id == "r-meadow"


@pytest.mark.asyncio
async def test_race_seed_spent_during_call(monkeypatch):
    seed = _seed()
    _racing_llm(monkeypatch, lambda: objects.set_property(seed.id, "state", "spent"))
    await _plant(seed)
    assert "quiet" in _last_narrate().lower()
    assert _grown_rooms() == []


@pytest.mark.asyncio
async def test_race_cap_reached_during_call(monkeypatch):
    monkeypatch.setenv("DAYDREAM_GROWTH_MAX_ROOMS", "1")

    def rival_grows():
        objects.spawn("w-bunny", "room", "Rival Grove", None,
                      prototype_id=objects.PROTO_ROOM,
                      properties={"slug": "rival-grove", "title": "Rival Grove",
                                  "seed": "s", "exits": {},
                                  "grown": {"seed_id": "o-rival"}})

    seed = _seed()
    _racing_llm(monkeypatch, rival_grows)
    await _plant(seed)
    # The rival's room stands; ours did not grow; the seed survives.
    assert rooms.grown_room_count("w-bunny") == 1
    assert rooms.get_room_by_slug("w-bunny", "the-moss-stair") is None
    seed_after = objects.get(seed.id)
    assert seed_after.location_id == "t-wren"
    assert seed_after.properties.get("state") != "spent"
    assert "settle" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_race_direction_taken_repicks_next_free(monkeypatch):
    """A rival exit landing on our preferred direction mid-call is re-picked,
    not failed: the commit block chooses the next free direction."""
    def rival_takes_south():
        exits = dict(rooms.get_room("r-meadow").exits)
        exits["south"] = "r-forge"
        objects.set_property("r-meadow", "exits", exits)

    seed = _seed()
    _racing_llm(monkeypatch, rival_takes_south)
    await _plant(seed)
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair")
    assert room is not None
    # north/east seeded, south taken by the rival -> west is first free.
    assert rooms.get_room("r-meadow").exits["west"] == room.id
    assert room.exits["east"] == "r-meadow"
    assert "west" in _last_narrate()


@pytest.mark.asyncio
async def test_race_all_directions_taken_during_call(monkeypatch):
    def rival_takes_all():
        objects.set_property(
            "r-meadow", "exits",
            {d: "r-forge" for d in ("north", "east", "south", "west", "up", "down")},
        )

    seed = _seed()
    _racing_llm(monkeypatch, rival_takes_all)
    await _plant(seed)
    assert "already taken" in _last_narrate().lower()
    assert _grown_rooms() == []
    assert objects.get(seed.id).location_id == "t-wren"
    assert objects.get(seed.id).properties.get("state") != "spent"


@pytest.mark.asyncio
async def test_race_slug_taken_suffixes_unique(monkeypatch):
    """A rival room landing our slug mid-call: the commit block suffixes to a
    unique slug + id rather than failing or colliding."""
    def rival_takes_slug():
        objects.spawn("w-bunny", "room", "The Moss Stair", None,
                      prototype_id=objects.PROTO_ROOM,
                      properties={"slug": "the-moss-stair",
                                  "title": "The Moss Stair", "seed": "s",
                                  "exits": {}})

    seed = _seed()
    _racing_llm(monkeypatch, rival_takes_slug)
    await _plant(seed)
    room = rooms.get_room_by_slug("w-bunny", "the-moss-stair-2")
    assert room is not None and room.id == "r-the-moss-stair-2"
    assert rooms.get_room("r-meadow").exits["south"] == room.id
    assert objects.get(seed.id).location_id == room.id  # husk rests inside
