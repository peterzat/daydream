"""Grounded natural-language command parser (daydream/parser.py).

Covers the SPEC 2026-06-30 "structured command bus & local-LLM parser"
criteria with a MOCKED LLM: grounded NL parsing (say/talk/greet rook ->
talk(t-rook, "hi")), the deterministic fast-path (exit directions + bare verbs
-> zero LLM calls), malformed/unresolvable parses failing safe, and graceful
LLM-outage handling."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, parser
from daydream.llm import client

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    # Co-locate Wren with Rook in the forge so Rook is in scope for parsing.
    objects.move("t-wren", "r-forge")
    yield
    db.close_db()
    events.reset_subscribers()


def _mock_llm(monkeypatch, payload):
    spy = AsyncMock(return_value=payload)
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    return spy


# ---- grounded natural-language parsing ---------------------------------


@pytest.mark.asyncio
async def test_talk_to_someone_here_is_deterministic(monkeypatch):
    """`talk to <someone here>[: words]` grounds with no parser call, and a
    multi-sentence line reaches them whole (playtest 2026-09-26); a bare
    "talk to rook" says hello. "say hi to rook" is talking to Rook too."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "talk to rook")
    assert (p.verb, p.dobj_id, p.args) == ("talk", "t-rook", "hello")
    lp = await parser.parse_line("t-wren", "talk to Rook: I keep bees back home. Do you like honey?")
    assert [(c.verb, c.dobj_id, c.args) for c in lp.commands] == [
        ("talk", "t-rook", "I keep bees back home. Do you like honey?")]
    p = await parser.parse("t-wren", "say hi to rook")
    assert (p.verb, p.dobj_id, p.args) == ("talk", "t-rook", "hi")
    lp = await parser.parse_line("t-wren", "say Hello all! I'm Wren. I'm off to the loft.")
    assert [(c.verb, c.args) for c in lp.commands] == [("say", "Hello all! I'm Wren. I'm off to the loft.")]
    assert spy.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["greet rook"])
async def test_natural_phrasings_ground_to_talk_rook(monkeypatch, text):
    # The model returns the grounded command; the parser validates it against
    # the real in-scope id set.
    _mock_llm(monkeypatch, {"verb": "talk", "dobj_id": "t-rook", "iobj_id": None, "args": "hi"})
    p = await parser.parse("t-wren", text)
    assert p.verb == "talk"
    assert p.dobj_id == "t-rook"
    assert p.args == "hi"


@pytest.mark.asyncio
async def test_bare_say_resolves_without_target(monkeypatch):
    # "say hi" has free-text args, so it goes to the LLM (which has no target to
    # ground -> a plain say), not the fast-path; bare-with-target would become talk.
    _mock_llm(monkeypatch, {"verb": "say", "dobj_id": None, "iobj_id": None, "args": "hi"})
    p = await parser.parse("t-wren", "say hi")
    assert p.verb == "say"
    assert p.dobj_id is None
    assert p.args == "hi"


# ---- deterministic fast-path (zero LLM calls) --------------------------


@pytest.mark.asyncio
async def test_exit_direction_is_fast_path(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")  # meadow has exits north/east
    p = await parser.parse("t-wren", "north")
    assert p.verb == "go" and p.args == "north"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_bare_verb_is_fast_path(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "look")
    assert p.verb == "look"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_verb_plus_name_is_fast_path(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")  # the lantern is here
    p = await parser.parse("t-wren", "examine the lantern")
    assert p.verb == "examine" and p.dobj_id == "i-lantern"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_look_at_name_grounds_to_examine(monkeypatch):
    # "look at <name>" routes to examine the named in-scope object (a bare
    # `look` describes the room). Deterministic fast-path, zero LLM calls.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")  # the lantern is here
    p = await parser.parse("t-wren", "look at the lantern")
    assert p.verb == "examine" and p.dobj_id == "i-lantern"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_look_at_npc_grounds_to_examine(monkeypatch):
    # The fixture co-locates Wren with Rook in r-forge.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "look at rook")
    assert p.verb == "examine" and p.dobj_id == "t-rook"
    spy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("line,verb", [
    ("pick up the moon", "take"), ("grab the moon", "take"), ("lift the moon", "take"),
    ("reach for the moon", "take"),
    ("x moon", "examine"), ("inspect the moon", "examine"), ("study the moon", "examine"),
    ("describe the moon", "examine"), ("check out the moon", "examine"),
])
async def test_the_ways_players_say_take_and_examine_stay_deterministic(monkeypatch, line, verb):
    # Playtest 2026-09-29b: "pick up the jar" went to the model, which grounds
    # only in-scope ids, so a thing the prose named came back "not understood".
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", line)
    assert p.verb == verb and p.dobj_name == "moon"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_carry_to_someone_is_not_a_take(monkeypatch):
    # Codereview 2026-09-29g: the letters thread says "carry it to whoever it
    # nearly means"; as a take alias, "carry the letter to Bell" answered
    # "You're already carrying" instead of reaching the model, which has give.
    spy = _mock_llm(monkeypatch, {"verb": "give", "dobj_id": "i-lantern",
                                  "iobj_id": "t-rook", "args": ""})
    objects.move("i-lantern", "t-wren")
    p = await parser.parse("t-wren", "carry the lantern to rook")
    assert (p.verb, p.dobj_id, p.iobj_id) == ("give", "i-lantern", "t-rook")
    assert spy.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("line", [
    "check on rook", "check it out", "check inventory", "check my pockets",
    "check the satchel", "check myself", "grab at the moon", "lift up the moon",
])
async def test_an_alias_idiom_is_not_a_name(monkeypatch, line):
    # Codereview 2026-09-29g: "check on Mott" read "You don't see the on Mott
    # here" and "check my pockets" a pocket watch's sentence. After an alias of
    # take or examine, a preposition, a split particle, or the dreamer's self
    # or satchel goes to the model, as before the aliases.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", line)
    assert p.dobj_name is None
    assert spy.await_count == 1


@pytest.mark.asyncio
async def test_an_alias_still_grounds_what_you_carry(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("i-lantern", "t-wren")
    p = await parser.parse("t-wren", "check my lantern")
    assert (p.verb, p.dobj_id) == ("examine", "i-lantern")
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_a_one_letter_word_without_a_target_verb_stays_a_sentence(monkeypatch):
    _mock_llm(monkeypatch, {"verb": "say", "args": "I keep bees back home"})
    p = await parser.parse("t-wren", "I keep bees back home")
    assert p.verb != "inventory"


@pytest.mark.asyncio
async def test_look_at_an_absent_name_passes_it_through_like_examine(monkeypatch):
    # Playtest 2026-09-29b: "look at the lantern" for a lantern the room's prose
    # names (no object) fell to the LLM and read "nothing takes that up".
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "look at the moon")
    assert p.verb == "examine" and p.dobj_id is None and p.dobj_name == "moon"
    spy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("line,verb,dobj_id", [
    ("look at me", "examine", "t-wren"), ("look at myself", "examine", "t-wren"),
    ("look at the room", "look", None), ("look at the view", "look", None),
    ("look in my satchel", "inventory", None), ("look at my pockets", "inventory", None),
    ("look at rook's hands", "examine", "t-rook"),
])
async def test_look_at_self_room_or_satchel_is_not_a_missing_name(monkeypatch, line, verb, dobj_id):
    # Codereview 2026-09-29g: "look at me" read "You don't see the me here",
    # "look at the room" the same; each is the dreamer, the place or the
    # satchel, and "<someone>'s X" looks at them.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", line)
    assert (p.verb, p.dobj_id, p.dobj_name) == (verb, dobj_id, None)
    spy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("line,verb", [
    ("take the moon by the stair", "take"), ("look at the moon over the far hill", "examine"),
])
async def test_a_long_name_passes_its_head(monkeypatch, line, verb):
    # Codereview 2026-09-29g: "take the lantern by the stair" went to the model,
    # which never sets a name, so the glimpse never heard of the lantern.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", line)
    assert (p.verb, p.dobj_id, p.dobj_name) == (verb, None, "moon")
    spy.assert_not_called()
    p = await parser.parse("t-wren", "take the stub of blue chalk")  # no trailing phrase
    assert p.dobj_name is None and spy.await_count == 1


@pytest.mark.asyncio
async def test_verb_plus_absent_name_passes_name_through(monkeypatch):
    # "take the moon": a known verb + a name not in scope. The fast-path passes
    # the (article-stripped) name through as dobj_name so the executor can say
    # "you don't see the moon here" -- no LLM call, no grounded id.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")
    p = await parser.parse("t-wren", "take the moon")
    assert p.verb == "take" and p.dobj_id is None and p.dobj_name == "moon"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_skill_name_is_fast_path(monkeypatch):
    # Install a room-affordance skill and confirm "<name> ..." fast-paths.
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES ('skill-forge', 'forge', 'data', '{}', '{{ player_input }}', "
        "'Forge', 'Forge a thing.', '{}', 1)"
    )
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "forge a ring")
    assert p.verb == "forge" and p.args == "a ring"
    spy.assert_not_called()


# ---- two-object verbs: deterministic two-target fast-path --------------


@pytest.mark.asyncio
async def test_give_x_to_y_is_fast_path(monkeypatch):
    # The fixture co-locates Wren + Rook in the forge. Make the lantern
    # giveable and carried, then "give lantern to rook" grounds both ids.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.set_property("i-lantern", "verbs", ["give"])
    objects.move("i-lantern", "t-wren")
    p = await parser.parse("t-wren", "give lantern to rook")
    assert p.verb == "give" and p.dobj_id == "i-lantern" and p.iobj_id == "t-rook"
    spy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("prep", ["on", "with"])
async def test_use_x_on_or_with_y_is_fast_path(monkeypatch, prep):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.set_property("i-lantern", "verbs", ["use"])
    objects.move("i-lantern", "t-wren")
    box = objects.spawn("w-bunny", "thing", "clock case", "r-forge",
                        prototype_id=objects.PROTO_THING, aliases=["case"])
    p = await parser.parse("t-wren", f"use the lantern {prep} the case")
    assert p.verb == "use" and p.dobj_id == "i-lantern" and p.iobj_id == box.id
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_bare_give_prompts_deterministically(monkeypatch):
    # "give" alone asks "Give what?" deterministically, as an orphan the next
    # line can complete (spec 2026-09-29 criterion 11); no LLM.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    lp = await parser.parse_line("t-wren", "give")
    assert not lp.commands and lp.clarify is not None
    assert lp.clarify.verb == "give" and lp.clarify.prompt == "Give what?"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_two_target_miss_defers_to_llm(monkeypatch):
    # "give lantern to somebody": no in-scope 'somebody' -> the fast-path misses
    # and the LLM grounds it (a fuzzier match the fast-path won't attempt).
    spy = _mock_llm(monkeypatch, {"verb": "give", "dobj_id": "i-lantern",
                                  "iobj_id": "t-rook", "args": ""})
    objects.set_property("i-lantern", "verbs", ["give"])
    objects.move("i-lantern", "t-wren")
    p = await parser.parse("t-wren", "give lantern to somebody")
    spy.assert_called_once()
    assert p.verb == "give" and p.dobj_id == "i-lantern" and p.iobj_id == "t-rook"


# ---- plant: bare fast-path + free-text vision via the LLM ---------------


@pytest.mark.asyncio
async def test_bare_plant_is_fast_path(monkeypatch):
    # Bare "plant" asks "Plant what?" deterministically, as an orphan the next
    # line can complete. Zero LLM calls (SPEC 2026-07-02 criterion 5;
    # spec 2026-09-29 criterion 11).
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    lp = await parser.parse_line("t-wren", "plant")
    assert not lp.commands and lp.clarify is not None
    assert lp.clarify.verb == "plant" and lp.clarify.prompt == "Plant what?"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_plant_with_a_vision_is_deterministic(monkeypatch):
    """`plant <seed>: <vision>` (the form the seed's own hint teaches) and
    `plant the <seed> to <vision>` ground the seed here and carry every
    word after its name as the vision, with no parser call (beta rehearsal
    2026-09-28: a typed plant paid a model call before the growth call)."""
    seed = objects.spawn("w-bunny", "thing", "dreamseed", "t-wren",
                         prototype_id=objects.PROTO_THING,
                         properties={"verbs": ["plant"]})
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "plant dreamseed: a moonlit orchard, where the owls keep time")
    assert p.verb == "plant" and p.dobj_id == seed.id
    assert p.args == "a moonlit orchard, where the owls keep time"
    p = await parser.parse("t-wren", "plant the dreamseed to a moonlit orchard")
    assert p.verb == "plant" and p.dobj_id == seed.id and p.args == "a moonlit orchard"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_plant_of_nothing_here_defers_to_the_model(monkeypatch):
    """A vision with no seed named in it is still the model's to read."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "plant a moonlit orchard by the river")
    spy.assert_called_once()
    assert p.verb == "none"


# ---- fail safe: malformed / unresolvable -------------------------------


@pytest.mark.asyncio
async def test_unknown_verb_grounds_to_none(monkeypatch):
    _mock_llm(monkeypatch, {"verb": "obliterate", "dobj_id": "t-rook", "args": ""})
    p = await parser.parse("t-wren", "obliterate rook")
    assert p.verb == "none"


@pytest.mark.asyncio
async def test_out_of_scope_object_grounds_to_none(monkeypatch):
    # The model hallucinated an id that isn't in scope -> fail safe.
    _mock_llm(monkeypatch, {"verb": "talk", "dobj_id": "t-ghost", "args": "hi"})
    p = await parser.parse("t-wren", "talk to the ghost")
    assert p.verb == "none"


@pytest.mark.asyncio
async def test_non_dict_llm_output_grounds_to_none(monkeypatch):
    _mock_llm(monkeypatch, ["not", "a", "dict"])
    p = await parser.parse("t-wren", "do something weird")
    assert p.verb == "none"


# ---- LLM outage --------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_outage_sets_error(monkeypatch):
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=client.LLMUnavailable("vllm down")),
    )
    p = await parser.parse("t-wren", "tell rook a long rambling story")
    assert p.verb == "none"
    assert p.error is not None


@pytest.mark.asyncio
async def test_outage_does_not_break_fast_path(monkeypatch):
    # Even with the LLM down, deterministic input still resolves (no call made).
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=client.LLMUnavailable("vllm down")),
    )
    objects.move("t-wren", "r-meadow")
    p = await parser.parse("t-wren", "north")
    assert p.verb == "go" and p.error is None


# ---- codereview 2026-09-27 ------------------------------------------------


@pytest.mark.asyncio
async def test_take_all_leaves_another_players_private_find(monkeypatch):
    """"take all" never reaches a thing private to someone else (it would
    otherwise refuse by name and leak the hidden find)."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    mine = objects.spawn("w-bunny", "thing", "brass minute", "r-forge",
                         prototype_id=objects.PROTO_THING, properties={"private_to": "t-wren"})
    theirs = objects.spawn("w-bunny", "thing", "silver minute", "r-forge",
                           prototype_id=objects.PROTO_THING, properties={"private_to": "t-rook"})
    lp = await parser.parse_line("t-wren", "take all")
    ids = [c.dobj_id for c in lp.commands]
    assert mine.id in ids and theirs.id not in ids
    assert spy.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("text,verb,args", [
    ("talk to moss: the bees are back", "talk", "the bees are back"),
    ("say to moss: good morning", "talk", "good morning"),
    ("ask moss about the lanterns", "ask", "the lanterns"),
])
async def test_a_clarify_keeps_the_players_words(monkeypatch, text, verb, args):
    """Two toons answer to one name: the question carries what was said, so
    the answer (typed or clicked) completes the whole command."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.spawn("w-bunny", "toon", "elder moss", "r-forge",
                  prototype_id=objects.PROTO_NPC, aliases=["moss"])
    young = objects.spawn("w-bunny", "toon", "young moss", "r-forge",
                          prototype_id=objects.PROTO_NPC, aliases=["moss"])
    lp = await parser.parse_line("t-wren", text)
    assert lp.clarify is not None
    assert (lp.clarify.verb, lp.clarify.args) == (verb, args)
    answered = await parser.parse_line("t-wren", "the young one", pending=lp.clarify)
    assert [(c.verb, c.dobj_id, c.args) for c in answered.commands] == [(verb, young.id, args)]
    assert spy.await_count == 0


@pytest.mark.asyncio
async def test_take_from_a_container_naming_nothing_asks_what(monkeypatch):
    """"take from the anvil" names nothing to take (it once read back "you
    don't see the from the anvi here")."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    lp = await parser.parse_line("t-wren", "take from the anvil")
    assert not lp.commands and lp.clarify is not None and lp.clarify.prompt == "Take what?"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_a_thing_whose_name_holds_from_grounds_whole(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    letter = objects.spawn("w-bunny", "thing", "letter from home", "r-forge",
                           prototype_id=objects.PROTO_THING)
    p = await parser.parse("t-wren", "take the letter from home")
    assert (p.verb, p.dobj_id) == ("take", letter.id)
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_a_trailing_phrase_does_not_hide_the_name(monkeypatch):
    """Playtest 2026-09-28b: "wind the turned-back clock for linden" named
    nothing whole, went to the model, and wound the other clock. The name
    before a trailing "for/on/with ..." phrase grounds when it alone matches."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    turned = objects.spawn("w-bunny", "thing", "turned-back clock", location_id="t-wren",
                         prototype_id=objects.PROTO_THING, properties={"seed": "a clock"})
    objects.spawn("w-bunny", "thing", "small clock", location_id="t-wren",
                  prototype_id=objects.PROTO_THING, properties={"seed": "a clock"})
    p = await parser.parse("t-wren", "examine the turned-back clock for linden")
    assert (p.verb, p.dobj_id) == ("examine", turned.id)
    assert spy.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["take both letters", "take all the letters",
                                  "take all of the letters", "take every letter"])
async def test_a_group_named_by_its_noun_takes_each_one(monkeypatch, text):
    """"take both letters" read "You don't see the both letters here"."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    a = objects.spawn("w-bunny", "thing", "crayon letter", location_id="r-forge",
                      prototype_id=objects.PROTO_THING, properties={"seed": "a letter"})
    b = objects.spawn("w-bunny", "thing", "marble letter", location_id="r-forge",
                      prototype_id=objects.PROTO_THING, properties={"seed": "a letter"})
    lp = await parser.parse_line("t-wren", text)
    assert sorted(c.dobj_id for c in lp.commands) == sorted([a.id, b.id])
    assert all(c.verb == "take" for c in lp.commands)
    lp = await parser.parse_line("t-wren", "take both spoons")
    assert lp.message == "You don't see any spoons here."
    assert spy.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["take both the letter and the key",
                                  "take all of the letter and the key",
                                  "take each of the letter, the key"])
async def test_a_quantified_and_list_takes_each_named_thing(monkeypatch, text):
    """The group reading swallowed "and" lists: "take both the letter and the
    key" read "You don't see any letter and the key here" (codereview
    2026-09-28h)."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    letter = objects.spawn("w-bunny", "thing", "letter", location_id="r-forge",
                           prototype_id=objects.PROTO_THING, properties={"seed": "a letter"})
    key = objects.spawn("w-bunny", "thing", "key", location_id="r-forge",
                        prototype_id=objects.PROTO_THING, properties={"seed": "a key"})
    lp = await parser.parse_line("t-wren", text)
    assert lp.message is None
    assert [(c.verb, c.dobj_id) for c in lp.commands] == [("take", letter.id), ("take", key.id)]
    assert spy.await_count == 0


@pytest.mark.asyncio
async def test_a_no_target_verb_carries_the_thing_it_names(monkeypatch):
    """"look at the lantern" style: a verb that needs no target still carries
    the one thing here it names, so the thing's own rules can answer (beta
    rehearsal 2026-09-28: typed "ring bell" found no bell; the click rang it)."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("t-wren", "r-meadow")  # where the lantern lies
    p = await parser.parse("t-wren", "inventory lantern")
    assert p.verb == "inventory" and p.dobj_id == "i-lantern"
    p = await parser.parse("t-wren", "inventory")
    assert p.verb == "inventory" and p.dobj_id is None
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_give_to_someone_for_someone_keeps_the_someone(monkeypatch):
    """"give the lantern to Rook for Ivo": the someone it is for rides along
    as args, so the post keeper can file it (beta rehearsal 2026-09-28)."""
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    objects.move("i-lantern", "t-wren")
    objects.set_property("i-lantern", "verbs", ["give"])  # the canonical loader's things can be given
    p = await parser.parse("t-wren", "give the lantern to rook for Ivo")
    assert p.verb == "give" and p.dobj_id == "i-lantern" and p.iobj_id == "t-rook"
    assert p.args == "for Ivo"
    p = await parser.parse("t-wren", "give the lantern to rook")
    assert p.verb == "give" and p.iobj_id == "t-rook" and p.args == ""
    spy.assert_not_called()


# ---- triage in the parser's one call (spec 2026-09-29 criterion 3) ----------


@pytest.mark.asyncio
async def test_a_question_about_the_game_becomes_a_state_answer(monkeypatch):
    spy = _mock_llm(monkeypatch, {"verb": "none", "kind": "time"})
    lp = await parser.parse_line("t-wren", "how late does the day run here")
    assert [(c.verb, c.args) for c in lp.commands] == [("meta", "time")]
    assert spy.await_count == 1


@pytest.mark.asyncio
async def test_a_target_not_in_scope_passes_through_by_name(monkeypatch):
    _mock_llm(monkeypatch, {"verb": "take", "dobj_id": None, "kind": "act",
                            "target": "the glinting jar"})
    lp = await parser.parse_line("t-wren", "please could I have that glinting jar")
    assert [(c.verb, c.dobj_id, c.dobj_name) for c in lp.commands] == [
        ("take", None, "glinting jar")]


@pytest.mark.asyncio
async def test_further_commands_come_back_in_order(monkeypatch):
    objects.move("t-wren", "r-meadow")
    _mock_llm(monkeypatch, {"verb": "take", "dobj_id": "i-lantern", "kind": "act",
                            "then": [{"verb": "look"}, {"verb": "juggle"}]})
    lp = await parser.parse_line("t-wren", "grab the lamp and then have a look round")
    assert [(c.verb, c.dobj_id) for c in lp.commands] == [("take", "i-lantern"), ("look", None)]


@pytest.mark.asyncio
async def test_triage_switched_off_is_the_old_single_command(monkeypatch):
    monkeypatch.setenv("DAYDREAM_PARSER_TRIAGE", "0")
    _mock_llm(monkeypatch, {"verb": "none", "kind": "time"})
    lp = await parser.parse_line("t-wren", "how late does the day run here")
    assert [c.verb for c in lp.commands] == ["none"]
    assert '"kind"' not in parser.system_prompt()


@pytest.mark.parametrize("line,name", [
    ("reach for the lamp on the far shelf", "lamp"),
    ("climb up onto the rafters", "rafters"),
    ("pick up the glinting jar", "glinting jar"),
    ("take the tweezers off the workbench", "tweezers"),
    ("take it", ""),
    ("examine the very long winding name", ""),
])
def test_the_typed_name_is_the_words_after_the_verb(line, name):
    assert parser._typed_target(line) == name


@pytest.mark.asyncio
async def test_a_verb_without_its_object_carries_the_typed_name(monkeypatch):
    """The model chose a verb and named nothing: the line's own words name
    the thing, so glimpses and "not here" answer it, never "Take what?"."""
    _mock_llm(monkeypatch, {"verb": "take", "dobj_id": None, "kind": "act"})
    lp = await parser.parse_line("t-wren", "fetch the moonstone from the high shelf")
    assert [(c.verb, c.dobj_id, c.dobj_name) for c in lp.commands] == [
        ("take", None, "moonstone")]


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [
    {"verb": "take", "dobj_id": None, "kind": "act"},
    {"verb": "take", "dobj_id": None, "kind": "act", "target": "lantern"},
])
async def test_a_typed_name_that_is_here_grounds(monkeypatch, reply):
    objects.move("t-wren", "r-meadow")
    _mock_llm(monkeypatch, reply)
    lp = await parser.parse_line("t-wren", "fetch the lantern")
    assert [(c.verb, c.dobj_id, c.dobj_name) for c in lp.commands] == [
        ("take", "i-lantern", None)]


@pytest.mark.asyncio
async def test_a_gesture_the_model_reads_goes_to_gestures(monkeypatch):
    _mock_llm(monkeypatch, {"verb": "talk", "dobj_id": "t-rook", "kind": "gesture"})
    lp = await parser.parse_line("t-wren", "give rook a big warm hug")
    assert [(c.verb, c.dobj_id, c.args) for c in lp.commands] == [("gesture", "t-rook", "hug")]


@pytest.mark.asyncio
async def test_triage_off_keeps_the_verb_without_a_name(monkeypatch):
    monkeypatch.setenv("DAYDREAM_PARSER_TRIAGE", "0")
    _mock_llm(monkeypatch, {"verb": "take", "dobj_id": None, "kind": "act"})
    lp = await parser.parse_line("t-wren", "fetch the moonstone from the high shelf")
    assert lp.commands == () and lp.clarify is not None  # "What do you want to take?"
