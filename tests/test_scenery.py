"""Scenery once, and exits by their names (spec 2026-09-29 criterion 9). The
sky, the walls, the lanterns and the cobbles answer in every room that shows
them, from one authored definition; a way out named in the prose ("stairs",
"low door", "gate", "arch") takes you through when you move by it and says
where it leads otherwise. Zero model calls."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import db, events, heard, objects, parser, toons, verbs, walkthrough, worldclock
from daydream.llm import format2

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())


@pytest.fixture()
def dreamer(tmp_path, monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(side_effect=AssertionError("no model call here")))
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "s-scenery",
                                     owner_account="a-scenery")
    yield toon.id
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


async def _said(actor: str, line: str) -> list[str]:
    before = events.max_seq()
    lp = await parser.parse_line(actor, line)
    for p in lp.commands:
        await verbs.execute_command(actor, p.verb, p.dobj_id, p.iobj_id, p.args,
                                    dobj_name=p.dobj_name)
    return [e.payload.get("text", "") for e in events.fetch_since(before)
            if e.recipient_id == actor and e.kind == "narrate"]


@pytest.mark.parametrize("start,line,end", [
    ("r-clocktower", "climb the stairs", "r-loft"),
    ("r-cellar", "take the stairs", "r-clocktower"),
    ("r-well", "go through the gate", "r-garden"),
    ("r-garden", "go through the arch", "r-orchard"),
    ("r-bridge", "go down the steps", "r-river"),
])
async def test_moving_by_a_ways_name_goes_that_way(dreamer, start, line, end):
    objects.move(dreamer, start)
    await _said(dreamer, line)
    assert objects.get(dreamer).location_id == end


async def test_any_other_verb_on_a_way_says_where_it_leads(dreamer):
    said = await _said(dreamer, "open the low door")
    assert said == ["The low door is the way down to the Hour Cellar."]


@pytest.mark.parametrize("room,line,phrase", [
    ("r-square", "look at the sky", "hasn't quite made up its mind"),
    ("r-hill", "take the sky", "far out of reach"),
    ("r-square", "take the cobbles", "worn smooth"),
    ("r-lane", "open a blue door", "The blue doors stay shut."),
    ("r-loft", "touch the wall", "part of the room"),
    ("r-square", "catch a moth", "won't be caught"),
])
async def test_shared_scenery_answers_where_it_is_shown(dreamer, room, line, phrase):
    objects.move(dreamer, room)
    said = await _said(dreamer, line)
    assert said and phrase in said[0], said


async def test_scenery_stays_in_its_rooms(dreamer):
    objects.move(dreamer, "r-cellar")
    said = await _said(dreamer, "look at the sky")
    assert said == ["You don't see the sky here."]


@pytest.mark.parametrize("mutate,needle", [
    (lambda e: e["config"]["scenery"][0]["rooms"].append("r-nowhere"), "unknown room"),
    (lambda e: e["rooms"][0]["properties"]["exit_names"].update(west=["door"]),
     "not an exit of this room"),
])
def test_scenery_and_exit_names_fail_loud(mutate, needle):
    env = copy.deepcopy(ENV)
    mutate(env)
    with pytest.raises(format2.Format2ValidationError, match=needle):
        format2.validate_envelope2(env)
