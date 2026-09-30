"""Every verb has a default, in the world's voice (spec 2026-09-29 criterion
6): smell, touch, knock, push, pull, climb, light, look behind and under,
dance and jump answer with the thing's name, varied, from lines the world
authors, with zero model calls; an object or a room may override them. And
the cellar's tea (criterion 12): drink there finds Umber's cup."""

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
                        AsyncMock(side_effect=AssertionError("no model call for a default")))
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "s-defaults",
                                     owner_account="a-defaults")
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


async def test_smell_names_the_thing_and_never_repeats_straight_away(dreamer):
    objects.move(dreamer, "r-cellar")
    first = await _said(dreamer, "smell the jars")
    second = await _said(dreamer, "sniff the jars")
    assert len(first) == 1 and "jars of saved hours" in first[0]
    assert second != first


@pytest.mark.parametrize("room,line,word", [
    ("r-clocktower", "look behind the clock case", "the clock case"),
    ("r-loft", "look under the workbench", "the workbench"),
    ("r-clocktower", "knock on the clock case", "the clock case"),
    ("r-clocktower", "push the clock case", "the clock case"),
    ("r-loft", "touch the round window", "the round window"),
    ("r-square", "light the paper lantern", "the paper lantern"),
])
async def test_each_default_names_its_thing(dreamer, room, line, word):
    objects.move(dreamer, room)
    said = await _said(dreamer, line)
    assert len(said) == 1 and word in said[0].lower(), said


async def test_alone_verbs_and_moving_as_people_say_it(dreamer):
    assert (await _said(dreamer, "dance"))[0].startswith("You ")
    assert (await _said(dreamer, "jump"))[0].startswith("You ")
    await _said(dreamer, "run east")
    assert objects.get(dreamer).location_id == "r-square"
    await _said(dreamer, "head back west")
    await _said(dreamer, "climb down the stairs")
    assert objects.get(dreamer).location_id == "r-cellar"


async def test_an_object_overrides_the_default(dreamer):
    objects.move(dreamer, "r-cellar")
    said = await _said(dreamer, "climb the highest shelf")
    assert said == ["The highest shelf is far above the lantern's reach, and nothing in the "
                    "cellar is tall enough to climb it by."]


async def test_the_cellar_pours_umbers_tea(dreamer):
    objects.move(dreamer, "r-cellar")
    said = await _said(dreamer, "drink tea")
    assert "Umber fills a chipped cup" in said[0]
    assert any(o.name == "chipped cup" for o in objects.contents(dreamer, kind="thing"))
    said = await _said(dreamer, "drink tea")
    assert said == ["You sip Umber's tea. It is strong and warm and tastes faintly of old "
                    "paper and patience, exactly as the label promised."]


@pytest.mark.parametrize("first", ["drink tea", "ask umber about tea"])
async def test_umbers_cup_is_poured_once_per_dreamer(dreamer, first):
    """The first pour gives the cup; later pours, asked or drunk, are drunk in
    the cellar and leave no cup behind (security 2026-09-30: drop, pour,
    repeat made a cup a line without limit)."""
    objects.move(dreamer, "r-cellar")
    await _said(dreamer, first)
    await _said(dreamer, "drop all")
    said = await _said(dreamer, "drink tea")
    assert "not to take away" in said[0]
    said = await _said(dreamer, "ask umber about tea")
    assert said and said[0].startswith("Umber")
    await _said(dreamer, "drop all")
    await _said(dreamer, "drink")
    cups = [o for o in objects.all_of_kind("w-lost-hours", "thing") if o.name == "chipped cup"]
    assert len(cups) == 1


def test_a_world_verb_takes_only_known_fields():
    env = copy.deepcopy(ENV)
    env["verbs"]["smell"]["fail_variants"] = "not a list"
    with pytest.raises(format2.Format2ValidationError, match="fail_variants"):
        format2.validate_envelope2(env)
