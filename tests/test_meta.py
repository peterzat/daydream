"""Questions about the game answer from state (spec 2026-09-29 criterion 4):
"what time is it", "where am I", "who am I", "help me", "what should I do",
"where can I go". The common phrasings make no model call."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import db, events, heard, meta, toons, walkthrough, worldclock
from daydream.api import ws as ws_module

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())
WORLD = "w-lost-hours"


@pytest.fixture()
def village(tmp_path, monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(side_effect=AssertionError("no model call for these")))
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "round spectacles and a patched blue coat",
                                     "meta-test", owner_account="a-meta")
    yield toon.id
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


async def _said(toon: str, line: str) -> list[str]:
    before = events.max_seq()
    await ws_module._handle_input(line, toon, {})
    return [e.payload.get("text", "") for e in events.fetch_since(before)
            if e.recipient_id in (toon, None) and e.kind == "narrate"]


@pytest.mark.parametrize("line,kind", [
    ("what time is it?", "time"), ("What's the time", "time"), ("is it night yet", "time"),
    ("where am I", "where"), ("what is this place?", "where"),
    ("who am i", "who"), ("what do I look like", "who"),
    ("where can I go", "ways"), ("go somewhere else", "ways"), ("which way?", "ways"),
    ("run", "ways"), ("wander off", "ways"),
    ("take the lantern", None), ("where is Bell", None),
    ("who is this", None),  # asked beside a stranger, never the dreamer's card (2026-09-30)
])
def test_the_questions_are_recognized(line, kind):
    assert meta.kind(line) == kind


async def test_time_stands_still_until_the_clock_runs(village):
    assert await _said(village, "what time is it") == ["Time stands still here."]
    from daydream import village as village_mod

    village_mod.start_time(WORLD)
    said = await _said(village, "what time is it")
    assert said[0].startswith("Day ") and "and it's" in said[0]


async def test_where_who_and_ways_read_the_state(village):
    where = await _said(village, "where am I")
    assert any("great clock" in s for s in where)
    who = await _said(village, "who am I")
    assert any("Wren" in s and "spectacles" in s for s in who)
    ways = await _said(village, "where can I go")
    assert ways == ["From here you can go up to the Clockmaker's Loft, east to the "
                    "Lantern Square or down to the Hour Cellar."]


async def test_help_me_and_im_stuck_have_their_answers(village):
    help_line = await _said(village, "help me")
    assert help_line == [ws_module.HELP_TEXT]
    stuck = await _said(village, "I'm stuck")
    assert stuck and stuck[0] == ws_module.WHAT_NOW_LEAD


@pytest.mark.parametrize("kind,expect", [
    ("ways", "From here you can go"), ("next", None), ("help", None)])
async def test_a_paraphrase_the_parser_triages_gets_the_same_answer(village, monkeypatch, kind,
                                                                     expect):
    """A question the fixed phrasings miss reaches the model once, and its
    triage routes it to the same state answer (spec 2026-09-29 criterion 3)."""
    spy = AsyncMock(return_value={"verb": "none", "dobj_id": None, "iobj_id": None,
                                  "args": "", "kind": kind})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    said = await _said(village, "so, er, what now for someone like me")
    assert spy.await_count == 1
    want = {"ways": expect, "next": ws_module.WHAT_NOW_LEAD, "help": ws_module.HELP_TEXT}[kind]
    assert said and (said[0].startswith(want) or said[0] in (ws_module.WHAT_NOW_NONE, want))
