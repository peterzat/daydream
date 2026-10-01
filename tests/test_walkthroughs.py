"""Every arc ending is a contract (SPEC 2026-09-26 criterion 2): each
walkthrough dataset replays through the real parser and executor over a
fresh world, with a fake clock and ZERO LLM calls, ending at asserted state.
Discovers the fixture world's datasets and the canonical world's."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import db, events, pronouns, walkthrough, worldclock

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ENV = json.loads((ROOT / "tests/data/story_fixture.json").read_text())
FIXTURE_SETS = sorted((ROOT / "tests/data/fixture_walkthroughs").glob("*.json"))


@pytest.fixture()
def zero_llm(monkeypatch):
    spy = AsyncMock(side_effect=AssertionError(
        "criterion 2: walkthroughs make ZERO LLM calls"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    pronouns.reset()
    yield spy
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


@pytest.mark.parametrize("path", FIXTURE_SETS, ids=[p.stem for p in FIXTURE_SETS])
async def test_fixture_walkthrough(zero_llm, tmp_path, path):
    dataset = walkthrough.load_dataset(path)
    walkthrough.fresh_world(json.loads(json.dumps(FIXTURE_ENV)), tmp_path / "w.db")
    run = await walkthrough.replay(dataset)
    assert run.steps > 0
    assert zero_llm.await_count == 0


# ---- The Village of Lost Hours ------------------------------------------------

LOST_HOURS = ROOT / "worlds/lost-hours.json"
LOST_HOURS_SETS = sorted((ROOT / "worlds/lost-hours/walkthroughs").glob("*.json"))


@pytest.mark.parametrize("path", LOST_HOURS_SETS, ids=[p.stem for p in LOST_HOURS_SETS])
async def test_lost_hours_walkthrough(zero_llm, tmp_path, path):
    dataset = walkthrough.load_dataset(path)
    walkthrough.fresh_world(json.loads(LOST_HOURS.read_text()), tmp_path / "w.db")
    run = await walkthrough.replay(dataset)
    assert run.steps > 0
    assert zero_llm.await_count == 0


async def test_the_gear_tace_hands_back_goes_home_to_the_loft(zero_llm, tmp_path):
    """Tace hands the gear back with the key; a player who rests before
    opening the case finds both at Tace's bench, not the gear back in the
    well-court's moss (codereview 2026-10-01c)."""
    from daydream import objects, toons

    dataset = walkthrough.load_dataset(LOST_HOURS_SETS[0].parent / "prologue.json")
    cmds = dataset["segments"][0]["commands"]
    upto = next(i for i, c in enumerate(cmds) if c.get("cmd") == "give gear to tace")
    dataset["segments"] = [{**dataset["segments"][0], "commands": cmds[:upto + 1]}]
    walkthrough.fresh_world(json.loads(LOST_HOURS.read_text()), tmp_path / "w.db")
    run = await walkthrough.replay(dataset)
    toons.send_home_things(run.actors["A"])
    assert objects.get("o-escapement-gear").location_id == "r-loft"
    key = next(o for o in objects.contents("r-loft", "thing") if o.name == "case key")
    assert toons.home_of(key).id == "r-loft"
