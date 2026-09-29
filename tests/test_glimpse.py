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
LANTERN_LINE = "The lantern by the stair burns on where it hangs, and you leave it to its work."


@pytest.fixture()
def llm(monkeypatch):
    mock = AsyncMock(return_value={"line": LANTERN_LINE})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", mock)
    return mock


@pytest.fixture()
def cellar(tmp_path, llm):
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "glimpse-test",
                                     owner_account="a-glimpse")
    objects.move(toon.id, "r-cellar")
    yield toon.id
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


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
        "The jar glints far above the lantern's reach, set apart from all the rest, "
        "and no ladder in the cellar is tall enough to bring it down."]
    looked = await _said(cellar, "examine the jar")
    assert "much too far away to read" in looked[0].payload["text"]
    assert llm.await_count == 0


async def test_a_look_at_a_name_the_room_says_reads_the_room(cellar, llm):
    said = await _said(cellar, "examine the lantern")
    assert [e.payload["text"] for e in said] == ["The lantern by the stair burns low and steady."]
    assert llm.await_count == 0


async def test_a_name_the_room_says_gets_one_local_line_then_the_same_one(cellar, llm):
    first = await _said(cellar, "take the lantern")
    assert [e.payload["text"] for e in first] == [LANTERN_LINE]
    assert first[0].payload.get("src") == "local"  # the dream digest lists it
    again = await _said(cellar, "take the lantern")
    assert [e.payload["text"] for e in again] == [LANTERN_LINE]
    assert llm.await_count == 1  # cached per sentence: one reason, told the same way
    assert llm.await_args.kwargs["user"] == glimpse.user_prompt(
        "The lantern by the stair burns low and steady.", "take", "lantern")


async def test_a_line_that_fails_or_a_quiet_model_reads_plainly(cellar, llm):
    llm.return_value = {"line": "Bell took it to the square."}  # a name the scene never said
    said = await _said(cellar, "take the lantern")
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("lantern")]
    assert "src" not in said[0].payload
    llm.side_effect = client.LLMUnavailable("down")
    said = await _said(cellar, "take the brick walls")
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("brick walls")]


async def test_the_switch_off_reads_plainly_with_no_model_call(cellar, llm, monkeypatch):
    monkeypatch.setenv("DAYDREAM_GLIMPSE_LLM", "0")
    said = await _said(cellar, "take the lantern")
    assert [e.payload["text"] for e in said] == [glimpse.plain_line("lantern")]
    assert llm.await_count == 0


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
