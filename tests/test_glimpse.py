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

from daydream import db, events, glimpse, heard, objects, parser, toons, verbs, walkthrough, worldclock
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


async def test_a_line_that_fails_or_a_quiet_model_reads_plainly(cellar, llm):
    llm.return_value = {"line": "Bell took them to the square."}  # a name the scene never said
    said = await _said(cellar, "take the brick walls")
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("brick walls")]
    assert "src" not in said[0].payload
    llm.side_effect = client.LLMUnavailable("down")
    said = await _said(cellar, "lift the shelves")  # the jars' alias: a real thing answers
    assert said and "You don't see" not in said[0].payload["text"]


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
])
def test_a_local_line_says_nothing_the_scene_did_not(line, ok):
    assert glimpse.valid_line(line, SOURCE) is ok


@pytest.mark.parametrize("mutate,needle", [
    (lambda g: g[0].update(names=[]), "names must be"),
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
