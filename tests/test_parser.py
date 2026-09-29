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
async def test_look_at_an_absent_name_passes_it_through_like_examine(monkeypatch):
    # Playtest 2026-09-29b: "look at the lantern" for a lantern the room's prose
    # names (no object) fell to the LLM and read "nothing takes that up".
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "look at the moon")
    assert p.verb == "examine" and p.dobj_id is None and p.dobj_name == "moon"
    spy.assert_not_called()


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
    # "give" alone -> a bare Parse so execute_command narrates "Give what?"; no LLM.
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "give")
    assert p.verb == "give" and p.dobj_id is None and p.iobj_id is None
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
    # Bare "plant" -> Parse("plant") deterministically; execute_command then
    # narrates "Plant what?". Zero LLM calls (SPEC 2026-07-02 criterion 5).
    spy = _mock_llm(monkeypatch, {"verb": "none"})
    p = await parser.parse("t-wren", "plant")
    assert p.verb == "plant" and p.dobj_id is None and p.args == ""
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
    p = await parser.parse("t-wren", "take from the anvil")
    assert (p.verb, p.dobj_id, p.dobj_name) == ("take", None, None)
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
