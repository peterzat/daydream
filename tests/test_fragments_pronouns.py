"""Fragments and pronouns (spec 2026-09-29 criterion 11). After "Take what?",
a line that is not a command of its own completes the verb; IT means the
last thing looked at, taken, clicked or glimpsed, HIM / HER / THEM the last
person addressed, and "ask <someone> about it" asks about that thing by
name. Zero model calls."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import (
    db,
    events,
    heard,
    objects,
    parser,
    pronouns,
    toons,
    verbs,
    walkthrough,
    worldclock,
)

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())


@pytest.fixture()
def dreamer(tmp_path, monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(side_effect=AssertionError("no model call here")))
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    pronouns.reset()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "s-frag",
                                     owner_account="a-frag")
    yield toon.id
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


async def _run(actor: str, line: str, pending=None):
    before = events.max_seq()
    lp = await parser.parse_line(actor, line, pending=pending)
    for p in lp.commands:
        await verbs.execute_command(actor, p.verb, p.dobj_id, p.iobj_id, p.args,
                                    dobj_name=p.dobj_name)
    said = [e.payload.get("text", "") for e in events.fetch_since(before)
            if e.recipient_id == actor and e.kind == "narrate"]
    return lp, said


async def test_take_what_then_a_fragment_completes_it(dreamer):
    objects.move(dreamer, "r-square")
    lp, _ = await _run(dreamer, "take")
    assert lp.clarify is not None and lp.clarify.prompt == "Take what?"
    await _run(dreamer, "the paper lantern", pending=lp.clarify)
    assert any(o.name == "paper lantern" for o in objects.contents(dreamer, kind="thing"))


async def test_a_command_of_its_own_is_not_a_fragment(dreamer):
    objects.move(dreamer, "r-square")
    lp, _ = await _run(dreamer, "take")
    await _run(dreamer, "west", pending=lp.clarify)
    assert objects.get(dreamer).location_id == "r-clocktower"


async def test_it_follows_a_look_and_a_glimpse(dreamer):
    _, said = await _run(dreamer, "examine the clock case")
    _, again = await _run(dreamer, "look at it")
    assert again == said
    objects.move(dreamer, "r-cellar")
    await _run(dreamer, "get the jar")
    _, looked = await _run(dreamer, "look at it")
    assert "much too far away to read" in looked[0]


async def test_ask_about_it_asks_about_the_thing_by_name(dreamer):
    objects.move(dreamer, "r-loft")
    await _run(dreamer, "examine the little brass clock")
    lp, said = await _run(dreamer, "ask Tace about it")
    assert [c.args for c in lp.commands] == ["little brass clock"]
    assert not any("About it" in s for s in said)


async def test_him_her_them_mean_the_last_person_addressed(dreamer):
    objects.move(dreamer, "r-loft")
    await _run(dreamer, "wave to Tace")
    lp, _ = await _run(dreamer, "hug them")
    assert [(c.verb, c.dobj_id) for c in lp.commands] == [("gesture", "t-tace")]
    parser.remember_referents(dreamer, "o-workbench")  # a click on a thing
    lp, _ = await _run(dreamer, "examine it")
    assert [c.dobj_id for c in lp.commands] == ["o-workbench"]


async def test_x_chains_like_any_command(dreamer):
    objects.move(dreamer, "r-workshop")
    lp, said = await _run(dreamer, "x tin. south")
    assert [c.verb for c in lp.commands] == ["examine", "go"]
    assert objects.get(dreamer).location_id == "r-square"
