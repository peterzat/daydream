"""The wide deterministic parser surface (Zork turn, SPEC 2026-07-02
criterion 9): direction abbreviations, multi-word verb aliases,
verb-preposition-object forms, ALL/AND/EXCEPT, IT, AGAIN/G, THEN chaining,
clarify round-trips, and GWIM slot defaults — all with an LLM spy proving
zero calls on every deterministic path."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, parser, pronouns, worldstate

pytestmark = pytest.mark.tier_short

WORLD = "w-bunny"
ACTOR = "t-wren"
ROOM = "r-meadow"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    pronouns.reset()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()
    pronouns.reset()


@pytest.fixture(autouse=True)
def llm_spy(monkeypatch):
    """Every test here is a deterministic path: the spy trips on any call."""
    spy = AsyncMock(side_effect=AssertionError("LLM must not be called"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    return spy


async def line(text: str, pending=None) -> parser.LineParse:
    return await parser.parse_line(ACTOR, text, pending=pending)


def cmds(lp: parser.LineParse) -> list[tuple]:
    return [(p.verb, p.dobj_id, p.iobj_id, p.args) for p in lp.commands]


# ---- directions -----------------------------------------------------------


async def test_direction_abbreviations_map_to_go():
    for word, canonical in [("n", "north"), ("ne", "northeast"), ("u", "up"),
                            ("d", "down"), ("sw", "southwest")]:
        lp = await line(word)
        assert cmds(lp) == [("go", None, None, canonical)], word


async def test_full_directions_and_in_out_are_go_even_without_exit():
    for word in ("north", "in", "out", "land", "launch", "climb"):
        lp = await line(word)
        assert cmds(lp) == [("go", None, None, word)]


# ---- multi-word verbs + world verbs -----------------------------------------


def install_light_verbs():
    worldstate.set(WORLD, "def:verbs", {
        "light": {"ui_hint": "Light", "description": "Set something burning.",
                  "needs_dobj": True, "valid_dobj_kinds": ["thing"],
                  "aliases": ["turn on"], "preps": ["with"],
                  "iobj_default": {"key": "ignites", "eq": True}},
        "extinguish": {"ui_hint": "Extinguish", "description": "Put out a flame.",
                       "needs_dobj": True, "valid_dobj_kinds": ["thing"],
                       "aliases": ["douse", "blow out", "turn off"]},
    })


def spawn_lamp():
    return objects.spawn(WORLD, "thing", "brass lantern", ACTOR,
                         prototype_id=objects.PROTO_THING,
                         aliases=["lamp", "lantern"],
                         properties={"verbs": ["light", "extinguish"]},
                         object_id="o-lamp")


async def test_multiword_alias_longest_prefix_wins():
    install_light_verbs()
    spawn_lamp()
    lp = await line("turn on the lamp")
    assert cmds(lp) == [("light", "o-lamp", None, "")]
    lp = await line("blow out lamp")
    assert cmds(lp) == [("extinguish", "o-lamp", None, "")]
    lp = await line("douse the lamp")
    assert cmds(lp) == [("extinguish", "o-lamp", None, "")]


async def test_world_verb_prep_form_grounds_both():
    worldstate.set(WORLD, "def:verbs", {
        "attack": {"ui_hint": "Attack", "description": "Strike a foe.",
                   "needs_dobj": True, "needs_iobj": True,
                   "valid_dobj_kinds": ["toon"], "valid_iobj_kinds": ["thing"],
                   "preps": ["with"]},
    })
    objects.set_property("t-rook", "verbs", ["attack"])
    objects.move("t-rook", ROOM)
    sword = objects.spawn(WORLD, "thing", "elvish sword", ACTOR,
                          aliases=["sword"], object_id="o-sword")
    lp = await line("attack rook with the sword")
    assert cmds(lp) == [("attack", "t-rook", "o-sword", "")]
    assert sword.id == "o-sword"


# ---- GWIM defaults --------------------------------------------------------------


async def test_gwim_fills_unique_iobj():
    install_light_verbs()
    spawn_lamp()
    objects.spawn(WORLD, "thing", "matchbook", ACTOR,
                  properties={"ignites": True}, object_id="o-match")
    lp = await line("light lamp")
    assert cmds(lp) == [("light", "o-lamp", "o-match", "")]


async def test_gwim_does_not_guess_between_two():
    install_light_verbs()
    spawn_lamp()
    objects.spawn(WORLD, "thing", "matchbook", ACTOR,
                  properties={"ignites": True}, object_id="o-match")
    objects.spawn(WORLD, "thing", "flint", ACTOR,
                  properties={"ignites": True}, object_id="o-flint")
    lp = await line("light lamp")
    assert cmds(lp) == [("light", "o-lamp", None, "")]  # executor asks


# ---- ALL / AND / EXCEPT -----------------------------------------------------------


def spawn_ground_items():
    objects.spawn(WORLD, "thing", "sword", ROOM,
                  prototype_id=objects.PROTO_THING, object_id="o-sword")
    objects.spawn(WORLD, "thing", "garlic", ROOM,
                  prototype_id=objects.PROTO_THING, object_id="o-garlic")


async def test_take_all_expands_per_item():
    spawn_ground_items()
    lp = await line("take all")
    got = {c[1] for c in cmds(lp)}
    assert got == {"i-lantern", "o-sword", "o-garlic"}
    assert all(c[0] == "take" for c in cmds(lp))


async def test_take_all_except():
    spawn_ground_items()
    lp = await line("take all except the garlic and sword")
    assert {c[1] for c in cmds(lp)} == {"i-lantern"}


async def test_take_and_list_with_missing_name():
    spawn_ground_items()
    lp = await line("take sword and moon")
    assert ("take", "o-sword", None, "") in cmds(lp)
    missing = [p for p in lp.commands if p.dobj_name == "moon"]
    assert len(missing) == 1


async def test_drop_all_when_empty_handed_messages():
    lp = await line("drop all")
    assert lp.commands == () and lp.message == "You're carrying nothing."


async def test_put_all_in_container_excludes_the_container():
    objects.spawn(WORLD, "thing", "sack", ACTOR,
                  prototype_id=objects.PROTO_THING,
                  properties={"container": True}, object_id="o-sack")
    objects.spawn(WORLD, "thing", "coin", ACTOR,
                  prototype_id=objects.PROTO_THING, object_id="o-coin")
    lp = await line("put all in sack")
    assert cmds(lp) == [("put", "o-coin", "o-sack", "")]


# ---- IT / AGAIN / THEN ---------------------------------------------------------------


async def test_it_refers_to_last_direct_object():
    lp = await line("take lantern")
    assert cmds(lp) == [("take", "i-lantern", None, "")]
    lp = await line("drop it")
    assert cmds(lp) == [("drop", "i-lantern", None, "")]


async def test_again_repeats_last_input():
    await line("take lantern")
    lp = await line("again")
    assert cmds(lp) == [("take", "i-lantern", None, "")]
    lp = await line("g")
    assert cmds(lp) == [("take", "i-lantern", None, "")]


async def test_again_with_no_history():
    lp = await line("again")
    assert lp.message and "repeat" in lp.message


async def test_then_and_period_chain_commands():
    lp = await line("take lantern then north")
    assert cmds(lp) == [("take", "i-lantern", None, ""),
                        ("go", None, None, "north")]
    lp = await line("drop lantern. s")
    assert cmds(lp) == [("drop", "i-lantern", None, ""),
                        ("go", None, None, "south")]


# ---- clarify --------------------------------------------------------------------------


def spawn_two_lanterns():
    objects.spawn(WORLD, "thing", "broken lantern", ROOM,
                  prototype_id=objects.PROTO_THING,
                  aliases=["lantern"], object_id="o-lantern2")
    # The seeded i-lantern's display name is 'lantern'; give both the shared
    # alias so "take lantern" is genuinely ambiguous.


async def test_ambiguous_name_returns_clarify():
    spawn_two_lanterns()
    lp = await line("take lantern")
    assert lp.commands == () and lp.clarify is not None
    c = lp.clarify
    assert c.verb == "take" and c.slot == "dobj"
    assert {oid for oid, _ in c.options} == {"i-lantern", "o-lantern2"}
    assert "Which lantern do you mean" in c.prompt


async def test_clarify_resolved_by_typed_reply():
    spawn_two_lanterns()
    lp = await line("take lantern")
    answered = await line("the broken one", pending=lp.clarify)
    # "broken" uniquely narrows to the broken lantern.
    assert cmds(answered) == [("take", "o-lantern2", None, "")]


async def test_clarify_nonanswer_parses_as_new_input():
    spawn_two_lanterns()
    lp = await line("take lantern")
    other = await line("north", pending=lp.clarify)
    assert cmds(other) == [("go", None, None, "north")]


# ---- misc ------------------------------------------------------------------------------


async def test_engine_aliases_resolve():
    lp = await line("get lantern")
    assert cmds(lp) == [("take", "i-lantern", None, "")]
    lp = await line("i")
    assert cmds(lp) == [("inventory", None, None, "")]
    lp = await line("l")
    assert cmds(lp) == [("look", None, None, "")]


async def test_put_prep_variants():
    objects.spawn(WORLD, "thing", "sack", ROOM,
                  prototype_id=objects.PROTO_THING,
                  properties={"container": True}, object_id="o-sack")
    objects.move("i-lantern", ACTOR)
    for prep in ("in", "into", "inside"):
        lp = await line(f"put the lantern {prep} the sack")
        assert cmds(lp) == [("put", "i-lantern", "o-sack", "")], prep
