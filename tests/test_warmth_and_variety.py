"""Authored voice leads and nothing repeats verbatim (SPEC 2026-09-26
criterion 11): prose surfaces run warm while the parser stays at 0, and a
world-declared affordance's authored variants never repeat within the
recent tellings in a room."""

from unittest.mock import AsyncMock

import pytest

from daydream import (
    db,
    dialogue,
    events,
    growth,
    journal,
    objects,
    parser,
    retell,
    verbs,
    worldclock,
)
from tests.story_helpers import at, load, player, say

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def world(tmp_path):
    at("2026-10-01T10:00:00+00:00")
    load(tmp_path)
    yield
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def test_prose_surfaces_run_warm():
    assert journal.JOURNAL_TEMPERATURE > 0
    assert growth.GROWTH_TEMPERATURE > 0
    assert verbs.EXAMINE_TEMPERATURE > 0
    assert retell.RETELL_TEMPERATURE > 0
    assert dialogue.temperature() > 0


async def test_the_parser_stays_deterministic(monkeypatch):
    ada = player(1, "Ada", "r-green")
    seen = {}

    async def fake(**kw):
        seen.update(kw)
        return {"verb": "none", "dobj_id": None, "iobj_id": None, "args": ""}

    monkeypatch.setattr("daydream.llm.client.acompletion_json", fake)
    await parser.parse_line(ada, "hum a little song to the evening")
    assert seen["purpose"] == "parser"
    assert seen.get("temperature", 0.0) == 0.0


async def test_affordance_variants_never_repeat_within_recent_tellings(monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(side_effect=AssertionError("no LLM")))
    ada = player(1, "Ada", "r-mill")
    told = [" ".join(await say(ada, "listen")) for _ in range(10)]
    assert all(t for t in told)
    for i in range(1, len(told)):
        assert told[i] not in told[max(0, i - 3):i], told
    assert objects.get(ada).location_id == "r-mill"
