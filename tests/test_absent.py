"""The absent answer as absent (spec 2026-09-29 criterion 1). With Tace in the
loft and Bell in the square, "ask Bell about the lanterns" was answered by
Tace: the name fell to the model parser, which grounds only to who is here.
A name that belongs to someone of this world who isn't here now says where
they are, with zero model calls, and no one here answers for them."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import (
    config,
    db,
    events,
    heard,
    objects,
    parser,
    toons,
    verbs,
    walkthrough,
    worldclock,
)

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())


@pytest.fixture()
def llm(monkeypatch):
    mock = AsyncMock(side_effect=AssertionError("no model call for someone absent"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", mock)
    return mock


@pytest.fixture()
def loft(tmp_path, llm):
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    toon = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "absent-test",
                                     owner_account="a-absent")
    objects.move(toon.id, "r-loft")
    objects.move("t-bell", "r-square")
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
            if e.recipient_id == actor or e.recipient_id is None]


@pytest.mark.parametrize("line", [
    "ask Bell about the lanterns", "ask bell about lanterns", "talk to Bell", "examine Bell",
])
async def test_someone_elsewhere_is_said_to_be_elsewhere(loft, line):
    said = await _said(loft, line)
    assert said == ["Bell isn't here; Bell is in the Lantern Square just now."]
    assert not any("Tace" in s for s in said)


async def test_a_dreamer_elsewhere_or_resting_reads_the_same_way(loft):
    other = toons.create_toon_in_slot(2, "Vesper", "Vesper, a dreamer", "absent-test-2",
                                      owner_account="a-absent-2")
    objects.move(other.id, "r-cellar")
    toons.claim_slot(2, "s-vesper")
    said = await _said(loft, "talk to Vesper")
    assert said == ["Vesper isn't here; Vesper is dreaming in the Hour Cellar just now."]


async def test_someone_here_is_still_asked(loft, llm):
    said = await _said(loft, "ask Tace about the loft")
    assert said and "isn't here" not in said[0]


@pytest.mark.parametrize("line", ["take the hour", "touch the hour"])
async def test_a_glimpse_here_answers_before_someone_elsewhere(loft, line):
    """At the Dusk Road "the hour" is the drifting lights, authored, not the
    guest of that name (codereview 2026-09-30)."""
    objects.move(loft, "r-duskroad")
    said = await _said(loft, line)
    assert said == ["There are no lights just now. They drift down at dusk, the villagers say, "
                    "like slow snow."]


async def test_a_guest_not_yet_arrived_is_nowhere(loft):
    said = await _said(loft, "examine the extra hour")
    assert said == ["You don't see the extra hour here."]


async def test_a_world_without_voiced_residents_keeps_its_own_not_here(tmp_path, llm):
    """A character with neither voice sheet nor schedule is not placed for the
    player (codereview 2026-09-30: another world's wandering thief was)."""
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "bunny.db", migrations_dir=config.MIGRATIONS_DIR)
    try:
        said = await _said("t-wren", "examine iris")  # Iris is up in the attic
    finally:
        db.close_db()
        events.reset_subscribers()
    assert said == ["You don't see the iris here."]
