"""A world's verbs are its own (spec 2026-09-29 criterion 7): the village
opts out of the engine verbs another world needed (combat, a health report,
boats), so they never parse there, never reach its verb bar, and never
answer in its voice. Zork's own files are untouched."""

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
WORLD = "w-lost-hours"


@pytest.fixture()
def village(tmp_path, monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(return_value={"verb": "none"}))
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "verbs-off",
                                     owner_account="a-verbs-off")
    yield toon.id
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def test_the_village_declares_what_it_leaves_out():
    assert set(ENV["config"]["engine_verbs_off"]) >= {"attack", "diagnose", "board", "disembark"}


def test_an_opted_out_verb_resolves_to_nothing_there(village):
    for word in ("diagnose", "board", "embark", "attack", "kill", "disembark"):
        assert verbs.resolve(WORLD, word) is None, word
    assert verbs.resolve(None, "diagnose") is not None  # other worlds keep it


async def test_it_never_parses_or_reaches_the_bar(village):
    lp = await parser.parse_line(village, "board the highest shelf")
    assert all(p.verb != "board" for p in lp.commands)
    names = {v.name for v in verbs.bar_verbs(WORLD, village)} | {
        v.name for v in verbs.bar_verbs(WORLD)}
    assert not names & {"attack", "diagnose", "board", "disembark"}
    objects.move(village, "r-waiting")  # the board of room keys is a noun here
    lp = await parser.parse_line(village, "read the board")
    assert [p.verb for p in lp.commands] == ["read"]


def test_an_unknown_verb_in_the_list_fails_the_loader():
    env = copy.deepcopy(ENV)
    env["config"]["engine_verbs_off"] = ["attack", "juggle"]
    with pytest.raises(format2.Format2ValidationError, match="'juggle' is not an engine verb"):
        format2.validate_envelope2(env)
