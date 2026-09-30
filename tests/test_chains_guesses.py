"""One line, several actions (spec 2026-09-29 criterion 5), and guesses said
aloud (criterion 12). "take the lantern and go west" runs both in order; a
refusal stops the rest and says so; a noun list stays a list. When the
parser fills a target itself (the one other person here), the reply names
its guess in parentheses."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import db, events, heard, objects, pronouns, toons, walkthrough, worldclock
from daydream.api import ws as ws_module

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
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "s-chain",
                                     owner_account="a-chain")
    yield toon.id
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


async def _said(toon: str, line: str) -> list[str]:
    before = events.max_seq()
    await ws_module._handle_input(line, toon, {})
    return [e.payload.get("text", "") for e in events.fetch_since(before)
            if e.recipient_id == toon and e.kind == "narrate"]


async def test_two_actions_run_in_order(dreamer):
    objects.move(dreamer, "r-square")
    await _said(dreamer, "take the paper lantern and go west")
    assert objects.get(dreamer).location_id == "r-clocktower"
    assert any(o.name == "paper lantern" for o in objects.contents(dreamer, kind="thing"))


async def test_a_refusal_stops_the_rest_and_says_so(dreamer):
    objects.move(dreamer, "r-square")
    said = await _said(dreamer, "take the moon and go west")
    assert said[-1] == "(So you leave the next part for now.)"
    assert objects.get(dreamer).location_id == "r-square"


async def test_a_guessed_person_is_named(dreamer):
    objects.move(dreamer, "r-loft")
    said = await _said(dreamer, "ask about the loft")
    assert said[0] == "(Tace)"


async def test_a_noun_list_runs_every_item_past_a_missing_one(dreamer):
    """A refusal stops a chain only before its next part: the items of one
    list all run (codereview BLOCK 2026-09-30)."""
    objects.move(dreamer, "r-square")
    said = await _said(dreamer, "take the moon and the paper lantern")
    assert said[0] == "You don't see the moon here."
    assert not any(s.startswith("(So you leave") for s in said)
    assert any(o.name == "paper lantern" for o in objects.contents(dreamer, kind="thing"))


@pytest.mark.parametrize("line", ["take the paper lantern and then go west",
                                  "take the paper lantern, and then go west"])
async def test_and_then_joins_two_actions(dreamer, line):
    """The "and" goes with the THEN (codereview 2026-09-30: "You don't see
    the paper lantern and here")."""
    objects.move(dreamer, "r-square")
    await _said(dreamer, line)
    assert objects.get(dreamer).location_id == "r-clocktower"
    assert any(o.name == "paper lantern" for o in objects.contents(dreamer, kind="thing"))
