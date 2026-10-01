"""Things the prose shows that the hands can't reach (playtest 2026-09-29b:
"get the jar" read "You don't see the jar here" right after the shelf's look
said a jar glinted up there). daydream/glimpse.py: an authored reason first;
a name the scene's own prose says gets its sentence for a look and one
validated local line for anything else; "You don't see" only for a name the
scene never said. Over the canonical world; the model is a mock."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import (
    db,
    events,
    glimpse,
    heard,
    objects,
    parser,
    toons,
    verbs,
    walkthrough,
    worldclock,
)
from daydream.llm import client, format2

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())
WALLS_LINE = "The brick walls stand firm behind the shelves, holding their jars too steady for your hands."
WALLS = ("Shelves run along the brick walls, and on them sit rows of small glass jars, each holding "
         "a folded slip of paper: an hour somebody saved and never spent.")


@pytest.fixture()
def llm(monkeypatch):
    mock = AsyncMock(return_value={"line": WALLS_LINE})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", mock)
    return mock


@pytest.fixture()
def village(tmp_path, llm):
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "glimpse-test",
                                     owner_account="a-glimpse")
    yield toon.id
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


@pytest.fixture()
def cellar(village):
    objects.move(village, "r-cellar")
    return village


async def _said(actor: str, line: str) -> list[events.Event]:
    before = events.max_seq()
    lp = await parser.parse_line(actor, line)
    for p in lp.commands:
        await verbs.execute_command(actor, p.verb, p.dobj_id, p.iobj_id, p.args,
                                    dobj_name=p.dobj_name)
    return [e for e in events.fetch_since(before)
            if e.kind == "narrate" and e.recipient_id == actor]


async def test_the_jar_on_the_shelf_says_why_in_authored_words(cellar, llm):
    said = await _said(cellar, "get the jar")
    assert [e.payload["text"] for e in said] == [
        "The jars along the shelves are Umber's to keep, and the one that glints on the highest "
        "shelf, set apart from the rest, is far above the lantern's reach: no ladder in the cellar "
        "is tall enough to bring it down."]
    looked = await _said(cellar, "examine the jar")
    assert "much too far away to read" in looked[0].payload["text"]
    assert llm.await_count == 0


async def test_a_long_name_reaches_its_glimpse_by_its_head(cellar, llm):
    for line in ("take the lantern by the stair", "look at the lantern by the stair"):
        said = await _said(cellar, line)
        assert "It's the cellar's only light" in said[0].payload["text"]
    assert llm.await_count == 0


async def test_a_look_at_a_name_the_room_says_reads_the_room(cellar, llm):
    said = await _said(cellar, "examine the brick walls")
    assert [e.payload["text"] for e in said] == [WALLS]
    assert llm.await_count == 0


async def test_a_name_the_room_says_gets_one_local_line_then_the_same_one(cellar, llm):
    first = await _said(cellar, "take the brick walls")
    assert [e.payload["text"] for e in first] == [WALLS_LINE]
    assert first[0].payload.get("src") == "local"  # the dream digest lists it
    again = await _said(cellar, "grab the brick walls")
    assert [e.payload["text"] for e in again] == [WALLS_LINE]
    assert llm.await_count == 1  # cached per sentence: one reason, told the same way
    assert llm.await_args.kwargs["user"] == glimpse.user_prompt(WALLS, "take", "brick walls")


async def test_writing_the_scene_only_mentions_reads_as_a_dreams_words(cellar, llm):
    """A grown room's label "holds a handwritten note in careful script", and
    "read the note" repeated the description (playthrough 2026-10-01c)."""
    objects.spawn("w-lost-hours", "thing", "paper time label", "r-cellar",
                  prototype_id=objects.PROTO_THING,
                  properties={"seed": "a paper time label that holds a handwritten note in careful script"})
    said = await _said(cellar, "read the handwritten note")
    assert [e.payload["text"] for e in said] == [
        "You try to read the handwritten note, but the words drift like a half-remembered "
        "dream and will not hold still."]
    looked = await _said(cellar, "examine the handwritten note")
    assert "careful script" in looked[0].payload["text"]  # a look still reads the scene
    said = await _said(cellar, "read the paper time label")
    assert "will not hold still" in said[0].payload["text"]
    assert llm.await_count == 0


async def test_a_line_that_fails_or_a_quiet_model_reads_plainly(cellar, llm):
    llm.return_value = {"line": "Bell took them to the square."}  # a name the scene never said
    said = await _said(cellar, "take the brick walls")
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("brick walls")]
    assert "src" not in said[0].payload
    llm.side_effect = client.LLMUnavailable("down")
    said = await _said(cellar, "lift the shelves")  # the jars' alias: a real thing answers
    assert said and "You don't see" not in said[0].payload["text"]
    asked = llm.await_count
    said = await _said(cellar, "take the folded slip")  # prose only, never asked: the outage
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("folded slip")]
    assert llm.await_count == asked + 1


async def test_the_switch_off_reads_plainly_with_no_model_call(cellar, llm, monkeypatch):
    monkeypatch.setenv("DAYDREAM_GLIMPSE_LLM", "0")
    said = await _said(cellar, "take the brick walls")
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("brick walls")]
    assert llm.await_count == 0


async def test_the_great_clock_answers_by_where_the_prologue_stands(village, llm):
    from daydream import worldstate

    said = await _said(village, "wind the great clock")
    assert "The repair ledger open on the lectern might say why." in said[0].payload["text"]
    await _said(village, "read repair ledger")
    said = await _said(village, "wind the clock")
    assert "its escapement gear" in said[0].payload["text"]
    worldstate.set_flag("w-lost-hours", "CLOCK-STARTED", True)
    said = await _said(village, "look at the clock face")
    assert "its hands are moving again" in said[0].payload["text"]
    said = await _said(village, "wind the great clock")
    assert "wants no winding from below" in said[0].payload["text"]
    assert llm.await_count == 0


async def test_the_clock_case_answers_to_its_door_and_lock(village, llm):
    said = await _said(village, "open the little door")
    assert "You don't see" not in said[0].payload["text"]
    assert objects.get("o-clock-case").properties.get("state") == "locked"
    said = await _said(village, "take the pendulum")
    assert "isn't a thing to carry off" in said[0].payload["text"]


async def test_the_cellar_lantern_and_motts_button_say_why_in_authored_words(village, llm):
    objects.move(village, "r-cellar")
    said = await _said(village, "take the lantern")
    assert "It's the cellar's only light" in said[0].payload["text"]
    objects.move(village, "r-workshop")
    said = await _said(village, "pick up the button")
    assert "The brown button is Mott's" in said[0].payload["text"]
    said = await _said(village, "take the something folded")
    assert "keeps his thumb over the folded thing" in said[0].payload["text"]
    assert llm.await_count == 0


@pytest.mark.parametrize("typed,name,ok", [
    ("jar", "jar", True), ("jars", "jar", True), ("jar on the top shelf", "jar", True),
    ("dusty glinting jar", "glinting jar", True), ("little brass clock", "clock", False),
    ("button letter", "letter", False), ("jar up there", "jar", False),
])
def test_names_match_whole_not_by_a_word_inside(typed, name, ok):
    assert glimpse._name_matches(glimpse._norm(typed), name) is ok


async def test_a_dark_room_shows_nothing_its_prose_names(cellar, llm):
    # Codereview 2026-09-29g: in Zork's unlit cellar "examine the ramp" read
    # the room's ramp sentence while `look` said it was pitch black.
    objects.set_property("r-cellar", "dark", True)
    said = []
    for line in ("examine the brick walls", "take the brick walls", "take the lantern"):
        said += await _said(cellar, line)
    assert [e.payload["text"] for e in said] == [
        "You don't see the brick walls here.", "You don't see the brick walls here.",
        "You don't see the lantern here."]
    assert llm.await_count == 0


@pytest.mark.parametrize("typed,prose,ok", [
    ("jar", "rows of small glass jars", True), ("jar", "a jar glints", True),
    ("jars", "a jar glints", False), ("pockets", "a pocket watch ticks", False),
    ("hands", "an older, looping hand", False), ("hands", "its hands stand still", True),
])
def test_a_typed_plural_finds_only_a_plural(typed, prose, ok):
    assert bool(glimpse._phrase_pattern(typed).search(prose)) is ok


async def test_the_hands_are_the_great_clocks_not_the_ledgers_hand(village, llm):
    # Codereview 2026-09-29g: after the clock's look ("Its hands stand
    # still."), "look at the hands" read the ledger's "older, looping hand".
    said = await _said(village, "look at the hands")
    assert said[0].payload["text"].endswith("Its hands stand still.")
    assert llm.await_count == 0


async def test_a_way_the_prose_names_is_the_way_not_out_of_reach(village, llm):
    # Codereview 2026-09-29g: in the well-court "open the gate" (the south
    # exit) read "You can see the gate ... but it isn't within reach".
    objects.move(village, "r-well")
    said = await _said(village, "open the gate")
    assert [e.payload["text"] for e in said] == ["The gate is the way south to the Pendulum Garden."]
    assert llm.await_count == 0


def test_a_plain_line_says_they_for_a_plural():
    assert "but they aren't within reach" in glimpse.plain_line("stairs")
    assert "but it isn't within reach" in glimpse.plain_line("gate")


async def test_a_name_the_scene_never_said_is_not_here(cellar, llm):
    said = await _said(cellar, "take the moon")
    assert [e.payload["text"] for e in said] == ["You don't see the moon here."]
    assert llm.await_count == 0


SOURCE = "The lantern by the stair burns low and steady."


@pytest.mark.parametrize("line,ok", [
    ("It burns on by the stair, and you leave the lantern to its work.", True),
    ("Tace hung it there, so you leave it be.", False),            # a name never said
    ("You hear it say \"leave me\" and step back.", False),          # dialogue
    ("The lantern burns on by the stair, too warm and fixed to carry.", True),
    ("Too warm.", False),                                            # too short
    ("You must hurry past the lantern.", False),                     # urgency
    ("You count 3 flames and leave it.", False),                     # a number never said
    ("I cannot help with that, but you may look.", False),           # a refusal
    ("You " + "leave it " * 40, False),                              # too long
    (None, False),
    ("It burns on by the stair, and it seems to say 'not you, not yet'.", False),  # speech
    ("The lantern burns on by the stair, where OONA set it.", False),              # all caps
])
def test_a_local_line_says_nothing_the_scene_did_not(line, ok):
    assert glimpse.valid_line(line, SOURCE) is ok


def test_an_all_caps_word_the_scene_said_may_stay():
    assert glimpse.valid_line("You leave the jar be, as its label says: DO NOT WAKE.",
                              "A label on the jar reads DO NOT WAKE.")


def test_a_local_line_keeps_the_worlds_canon_words():
    # As growth applies never_words: a lowercase entry in any case, a
    # capitalized one (a name) only as written (codereview 2026-09-29g).
    baker = "The baker left it by the stair, far from your hands."
    assert glimpse.valid_line(baker, SOURCE)
    assert not glimpse.valid_line(baker, SOURCE, ["baker"])
    assert glimpse.valid_line("You wend past the lantern by the stair, and leave it be.",
                              SOURCE, ["Wend"])


async def test_a_local_line_that_breaks_the_village_canon_reads_plainly(cellar, llm):
    line = "The walls keep the jars for the mayor of the village, far too steady for your hands."
    assert glimpse.valid_line(line, WALLS)  # only the village's never_words refuse it
    llm.return_value = {"line": line}
    said = await _said(cellar, "take the brick walls")
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("brick walls")]


@pytest.mark.parametrize("mutate,needle", [
    (lambda g: g[0].update(names=[]), "names must be"),
    (lambda g: g[0].update(names=["jar on the top shelf"]), "four words or more"),
    (lambda g: g[0].update(text=""), "text must be"),
    (lambda g: g[0].update(verbs={"examine": 3}), "verbs must map"),
    (lambda g: g[0].update(when="soon"), "unknown key"),
    (lambda g: g[0].update({"if": [{"ending": "tace-hour/nowhere"}]}), "unknown ending"),
])
def test_authored_glimpses_fail_loud(mutate, needle):
    env = copy.deepcopy(ENV)
    shelf = next(t for t in env["things"] if t["id"] == "o-high-shelf")
    mutate(shelf["properties"]["glimpsed"])
    with pytest.raises(format2.Format2ValidationError, match=needle):
        format2.validate_envelope2(env)


def test_an_unknown_per_verb_key_fails_the_loader():
    env = copy.deepcopy(ENV)
    shelf = next(t for t in env["things"] if t["id"] == "o-high-shelf")
    shelf["properties"]["glimpsed"][0]["verbs"] = {"exmaine": "a typo never answers"}
    with pytest.raises(format2.Format2ValidationError, match="unknown verb"):
        format2.validate_envelope2(env)


async def test_a_function_word_is_not_a_noun(cellar, llm):
    said = await _said(cellar, "examine and")
    assert [e.payload["text"] for e in said] == ["You don't see the and here."]
    assert llm.await_count == 0


async def test_carrying_wends_ladder_has_its_own_jar_line(cellar, llm):
    objects.move("o-tace-hour-ladder", cellar)
    said = await _said(cellar, "take the jar")
    assert "You have Wend's ladder with you" in said[0].payload["text"]


async def test_using_a_thing_the_scene_shows_answers_with_its_glimpse(cellar, llm):
    """ "use the lantern on the jar": the lantern is only the cellar's prose,
    so its glimpse answers, not a refusal about the jars (playtest
    2026-09-29b class 10)."""
    said = await _said(cellar, "use the lantern on the jar")
    assert "It's the cellar's only light" in said[0].payload["text"]
    assert llm.await_count == 0


async def test_the_lectern_is_authored_not_improvised(village, llm):
    """The model's line called the lectern leather (the ledger is leather):
    an authored glimpse answers it now (playtest 2026-09-29b class 10)."""
    said = await _said(village, "take the lectern")
    assert "plain old oak" in said[0].payload["text"]
    assert llm.await_count == 0


def test_a_rooms_glimpses_are_read_beside_its_exit_names():
    """A room with exit names has its glimpses validated too (codereview
    2026-09-30: an elif skipped them in the cellar, the Clocktower, the
    lamphouse and the Dusk Road)."""
    env = copy.deepcopy(ENV)
    cellar = next(r for r in env["rooms"] if r["id"] == "r-cellar")
    assert cellar["properties"]["exit_names"]
    cellar["properties"]["glimpsed"][0]["verbs"] = {"exmaine": "a typo never answers"}
    with pytest.raises(format2.Format2ValidationError, match="unknown verb"):
        format2.validate_envelope2(env)


# ---- parts: a detail a thing's look names (playtest 2026-09-30) -------------

FMN_LOOK = ("One of the resting clocks is no bigger than a teacup, with forget-me-nots painted "
            "all the way round its face")


@pytest.fixture()
def loft(village):
    objects.move(village, "r-loft")
    return village


async def test_a_part_answers_a_look_with_its_own_words(loft, llm):
    """"look at forget-me-nots" read the whole shelf's look, the sentence the
    player had just read; the part has words of its own."""
    for line in ("look at forget-me-nots", "examine the painted clock", "x forget-me-not clock",
                 "look at the flowers"):
        said = await _said(loft, line)
        assert [e.payload["text"][:len(FMN_LOOK)] for e in said] == [FMN_LOOK], line
        assert "Shelves of small resting clocks" not in said[0].payload["text"]
    assert llm.await_count == 0


async def test_a_part_answers_the_verbs_it_names(loft, llm):
    said = await _said(loft, "take the forget-me-nots")
    assert [e.payload["text"] for e in said] == [
        "You lift the forget-me-not clock an inch, and its tick skips, the way a sleeper "
        "stirs. You set it back among the others to rest."]
    assert llm.await_count == 0


async def test_every_other_verb_is_done_to_its_thing(loft, llm):
    """Winding the painted clock is winding a resting clock: the shelf's own
    rules answer, the old custom included."""
    said = await _said(loft, "wind the forget-me-not clock")
    assert said and said[0].payload["text"].startswith(("You wind", "You turn the key")), said
    from daydream import worldstate

    worldstate.set_flag("w-lost-hours", "CLOCK-STARTED", True)
    said = await _said(loft, "wind the painted clock")
    assert "By old custom a new keeper winds a clock of their own" in said[0].payload["text"]
    assert llm.await_count == 0


async def test_a_verb_its_thing_does_not_take_is_refused_by_the_parts_name(loft, llm):
    said = await _said(loft, "open the painted clock")
    assert [e.payload["text"] for e in said] == ["You can't open the painted clock."]


async def test_a_refusal_says_back_the_name_the_player_used(loft, llm):
    """"take forget-me-nots" was refused as "You can't take the resting
    clocks": the answer named a thing the player hadn't asked for."""
    said = await _said(loft, "take the clocks")
    assert [e.payload["text"] for e in said] == ["You can't take the clocks."]
    said = await _said(loft, "take tace")
    assert [e.payload["text"] for e in said] == ["You can't take Tace."]


@pytest.mark.parametrize("mutate,needle", [
    (lambda th: th["properties"]["glimpsed"][0].update(part="yes"), "part must be true or false"),
    (lambda th: th["properties"]["glimpsed"][0]["names"].append("small clocks"),
     "also its thing's name or alias"),
])
def test_parts_fail_loud(mutate, needle):
    env = copy.deepcopy(ENV)
    mutate(next(t for t in env["things"] if t["id"] == "o-resting-clocks"))
    with pytest.raises(format2.Format2ValidationError, match=needle):
        format2.validate_envelope2(env)


def test_only_a_thing_has_parts():
    env = copy.deepcopy(ENV)
    room = next(r for r in env["rooms"] if r["id"] == "r-cellar")
    room.setdefault("properties", {}).setdefault("glimpsed", []).append(
        {"names": ["mortar"], "text": "Old and soft.", "part": True})
    with pytest.raises(format2.Format2ValidationError, match="only a thing has parts"):
        format2.validate_envelope2(env)


async def test_a_part_links_on_the_page_and_a_click_opens_its_card(loft, llm):
    """The page links a part where prose names it; a click sends its name,
    and its look comes back as a card of its own, keyed to the part."""
    from daydream.api import ws

    side = ws._entity_sidecar(loft)
    parts = [e for e in side if e.get("part")]
    assert {e["alias"] for e in parts} >= {"forget-me-nots", "painted clock"}
    assert {e["object_id"] for e in parts} == {"o-resting-clocks"}
    assert len({e["part"] for e in parts}) == 1
    before = events.max_seq()
    await ws._handle_command({"kind": "command", "verb": "examine",
                              "dobj_name": "forget-me-nots"}, loft)
    said = [e for e in events.fetch_since(before) if e.kind == "narrate"]
    card = said[0].payload["card"]
    assert card["part"] == parts[0]["part"] and card["object_id"] == "o-resting-clocks"
    assert card["body"].startswith(FMN_LOOK) and card["name"] == "the forget-me-nots"
    # Beside an id, a clicked name is ignored: the id is the target.
    before = events.max_seq()
    await ws._handle_command({"kind": "command", "verb": "examine", "dobj_id": "o-workbench",
                              "dobj_name": "forget-me-nots"}, loft)
    said = [e for e in events.fetch_since(before) if e.kind == "narrate"]
    assert said[0].payload["card"]["object_id"] == "o-workbench"
    assert llm.await_count == 0


# ---- the review's fixes (codereview 2026-09-30c) -----------------------------


async def test_a_refusal_never_says_back_a_pronoun_or_loses_a_names_capital(loft, llm):
    """"take it" read "You can't take the it.", and "wind mott's tin" lost
    the capital of Mott's tin: a refusal says back only a name the thing
    carries, as authored."""
    await _said(loft, "examine the clocks")
    for line in ("take it", "take them"):
        lp = await parser.parse_line(loft, line)
        assert [p.dobj_name for p in lp.commands] == [None], line
        said = await _said(loft, line)
        assert [e.payload["text"] for e in said] == ["You can't take the resting clocks."], line
    objects.move(loft, "r-workshop")
    said = await _said(loft, "wind mott's tin")
    assert [e.payload["text"] for e in said] == ["You can't wind Mott's tin."]
    assert llm.await_count == 0


async def test_a_parts_look_lets_a_chain_run_on(loft, llm):
    """A part's look is the look asked for, not a refusal: the chain went on
    no further than it."""
    from daydream.api import ws

    before = events.max_seq()
    await ws._handle_input("examine the forget-me-nots. examine the workbench", loft, {})
    said = [e.payload["text"] for e in events.fetch_since(before)
            if e.kind == "narrate" and e.recipient_id == loft]
    assert said[0].startswith(FMN_LOOK), said
    assert said[-1].startswith("You examine the workbench"), said
    assert llm.await_count == 0


async def test_it_is_the_part_whose_verb_its_thing_did(loft, llm):
    """"wind the painted clock" left IT on the workbench examined before it."""
    await _said(loft, "examine the workbench")
    await _said(loft, "wind the painted clock")
    said = await _said(loft, "examine it")
    assert [e.payload["text"][:len(FMN_LOOK)] for e in said] == [FMN_LOOK]
    assert llm.await_count == 0


async def test_a_part_stands_for_its_thing_where_a_line_needs_an_object(loft, llm):
    """A gesture at a part, or a part as a line's second thing, reached the
    model once the part stopped being an alias of its thing."""
    await _said(loft, "take the pendulum")
    for line, want in (("wave at the forget-me-nots", ("gesture", "o-resting-clocks", None)),
                       ("put the pendulum on the painted clock",
                        ("put", "o-brass-pendulum", "o-resting-clocks")),
                       ("give the pendulum to the painted clock",
                        ("give", "o-brass-pendulum", "o-resting-clocks"))):
        lp = await parser.parse_line(loft, line)
        assert [(p.verb, p.dobj_id, p.iobj_id) for p in lp.commands] == [want], line
    assert llm.await_count == 0
