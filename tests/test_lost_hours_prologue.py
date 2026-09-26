"""The Village of Lost Hours' prologue beyond its walkthrough (ports the
retired loft goldens, SPEC 2026-07-01/07-02, to the canonical world): the
opened case's dreamseed plants one grown room through the real pipeline
(mocked compose, one LLM call), a husk refuses a replant, the cap refuses in
character; wrong-item and locked-case actions are soft no-ops."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import db, events, objects, rooms, verbs, walkthrough, worldclock, worldstate

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())
PROLOGUE = json.loads((ROOT / "worlds/lost-hours/walkthroughs/prologue.json").read_text())
WORLD = "w-lost-hours"

_PLANT = {
    "title": "The Quiet Orchard",
    "room_seed": "a small orchard of clock-fruit trees at dusk, each fruit ticking softly under the leaves",
    "description": "Rows of low trees hold small brass fruit, and each one ticks softly to itself "
                   "under the leaves. The grass is cool and blue with evening. Somewhere at the "
                   "orchard's edge, one tree keeps a different, older time.",
    "objects": [{"name": "clock-fruit", "seed": "a small brass fruit, warm and faintly ticking in the palm"}],
}


@pytest.fixture()
def village(tmp_path, monkeypatch):
    spy = AsyncMock(side_effect=AssertionError("unexpected LLM call"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    walkthrough.fresh_world(json.loads(json.dumps(ENV)), tmp_path / "w.db")
    yield spy
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _last_narrate() -> str:
    return [e.payload["text"] for e in events.fetch_since(0) if e.kind == "narrate"][-1]


async def test_the_dreamseed_grows_one_room(village, monkeypatch):
    run = await walkthrough.replay(PROLOGUE)
    actor = run.actors["A"]
    seed = next(o for o in objects.contents(actor, kind="thing") if o.name == "dreamseed")
    assert "plant" in objects.verbs_for(seed)
    await verbs.execute_command(actor, "plant", dobj_id=seed.id)
    assert _last_narrate() == "Where does the new way lead?"
    grow = AsyncMock(return_value=dict(_PLANT))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", grow)
    here = objects.get(actor).location_id
    phrase = "an orchard where the fruit keeps time"
    await verbs.execute_command(actor, "plant", dobj_id=seed.id, args=phrase)
    assert grow.call_count == 1
    grown = rooms.get_room_by_slug(WORLD, "the-quiet-orchard")
    assert grown is not None
    back = next(d for d, v in grown.exits.items() if v == here)
    assert back
    props = objects.get(grown.id).properties
    assert props["grown"]["phrase"] == phrase and props["grown"]["planter_id"] == actor
    names = {o.name for o in objects.contents(grown.id, "thing")}
    assert {"clock-fruit", "spent dreamseed"} <= names
    # The world's first grown room closes the chapter in the planter's journal.
    assert "deliberate tick" in _last_narrate()
    assert worldstate.get(WORLD, "first_bloom")["planter_id"] == actor
    # The husk refuses a replant; the cap refuses in character, no call.
    husk = objects.get(seed.id)
    assert husk.properties["state"] == "spent"
    monkeypatch.setenv("DAYDREAM_GROWTH_MAX_ROOMS", "1")
    second = objects.spawn(WORLD, "thing", "second dreamseed", actor,
                           prototype_id=objects.PROTO_THING,
                           properties={"seed": "another", "verbs": ["plant"],
                                       "growth": seed.properties["growth"]})
    await verbs.execute_command(actor, "plant", dobj_id=second.id, args="a second orchard")
    assert grow.call_count == 1 and rooms.grown_room_count(WORLD) == 1


async def test_locked_case_and_wrong_item_are_soft_noops(village):
    run = walkthrough.Run(name="noop")
    walkthrough.join(run, "A", "Wren")
    actor = run.actors["A"]
    await verbs.execute_command(actor, "open", dobj_id="o-clock-case")
    assert objects.get("o-clock-case").properties["state"] == "locked"
    assert "lock" in _last_narrate().lower()
    assert not [o for o in objects.contents("r-clocktower", "thing") if o.name == "warm brass cog"]
    objects.move("o-paper-lantern", actor)
    objects.set_property("o-paper-lantern", "verbs", ["use"])
    await verbs.execute_command(actor, "use", dobj_id="o-paper-lantern", iobj_id="o-clock-case")
    assert objects.get("o-clock-case").properties["state"] == "locked"
    assert "nothing happens" in _last_narrate().lower()
