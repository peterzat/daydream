"""Gestures are social (spec 2026-09-29 criterion 2). "hug Tace" was heard as
speech ("says to Tace: "hug"") and answered by the model. Now the actor reads
it in the second person, everyone else in the third, a dreamer who is its
target reads it addressed to them, and a resident answers from its authored
reactions, with zero model calls."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import (
    db,
    events,
    gestures,
    heard,
    objects,
    parser,
    toons,
    verbs,
    walkthrough,
    worldclock,
)
from daydream.api import ws as ws_module
from daydream.llm import format2

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())


@pytest.fixture()
def loft(tmp_path, monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(side_effect=AssertionError("no model call for a gesture")))
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    ids = {}
    for slot, name in ((1, "Wren"), (2, "Vesper"), (3, "Juniper")):
        t = toons.create_toon_in_slot(slot, name, f"{name}, a dreamer", f"s-{name.lower()}",
                                      owner_account=f"a-{name.lower()}")
        ws_module._mark_session_live(f"s-{name.lower()}")  # at their pages, awake
        objects.move(t.id, "r-loft")
        ids[name] = t.id
    yield ids
    for name in ids:
        ws_module._unmark_session_live(f"s-{name.lower()}")
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


async def _do(actor: str, line: str) -> int:
    before = events.max_seq()
    lp = await parser.parse_line(actor, line)
    for p in lp.commands:
        await verbs.execute_command(actor, p.verb, p.dobj_id, p.iobj_id, p.args,
                                    dobj_name=p.dobj_name)
    if lp.message:
        events.append("system", None, "narrate", {"text": lp.message},
                      room_id=objects.get(actor).location_id, recipient_id=actor)
    return before


def _seen(toon: str, since: int) -> list[str]:
    return [e.payload.get("text", "") for e in events.fetch_since(since)
            if e.recipient_id in (None, toon) and not events.excepted(e.payload, toon)
            and e.kind in ("narrate", "say")]


async def test_a_hug_is_told_to_each_in_their_person_and_the_keeper_answers(loft):
    wren, vesper = loft["Wren"], loft["Vesper"]
    before = await _do(wren, "hug Tace")
    mine, theirs = _seen(wren, before), _seen(vesper, before)
    assert mine[0] == "You hug Tace."
    assert theirs[0] == "Wren hugs Tace."
    tace_hugs = [r["text"] for r in objects.get("t-tace").properties["reactions"]["hug"]]
    assert mine[1] in tace_hugs
    assert "Wren" in theirs[1] and theirs[1] not in tace_hugs  # the others telling
    assert not any("says" in s for s in mine + theirs)


async def test_between_dreamers_three_tellings(loft):
    wren, vesper, juniper = loft["Wren"], loft["Vesper"], loft["Juniper"]
    before = await _do(wren, "wave to Vesper")
    assert _seen(wren, before) == ["You wave to Vesper."]
    assert _seen(vesper, before) == ["Wren waves to you."]
    assert _seen(juniper, before) == ["Wren waves to Vesper."]


async def test_a_dozing_dreamer_doesnt_stir(loft):
    import time

    ws_module._unmark_session_live("s-vesper")
    ws_module._last_disconnect["s-vesper"] = time.monotonic() - 1000  # long past the grace
    before = await _do(loft["Wren"], "hug Vesper")
    assert _seen(loft["Wren"], before)[-1].endswith("doesn't stir.")
    ws_module._mark_session_live("s-vesper")


@pytest.mark.parametrize("line", ["give Tace a hug", "give a hug to Tace", "embrace Tace"])
async def test_the_ways_to_say_a_hug(loft, line):
    before = await _do(loft["Wren"], line)
    assert _seen(loft["Wren"], before)[0] == "You hug Tace."


async def test_alone_to_a_thing_and_with_no_one_named(loft):
    wren = loft["Wren"]
    before = await _do(wren, "wave")
    assert _seen(wren, before) == ["You wave."]
    assert _seen(loft["Vesper"], before) == ["Wren waves."]
    before = await _do(wren, "hug the workbench")
    assert _seen(wren, before)[0].startswith("You hug the workbench. ")
    for other in ("Vesper", "Juniper"):
        objects.move(loft[other], "r-cellar")
    before = await _do(wren, "thank you")  # Tace is the one other person here
    said = _seen(wren, before)
    assert said[:2] == ["(Tace)", "You thank Tace."]


async def test_someone_elsewhere_is_elsewhere(loft):
    objects.move("t-bell", "r-square")
    before = await _do(loft["Wren"], "wave to Bell")
    assert _seen(loft["Wren"], before) == ["Bell isn't here; Bell is in the Lantern Square just now."]


def test_every_keeper_and_guest_answers_in_its_own_words():
    for t in ENV["toons"]:
        assert "default" in t["properties"]["reactions"], t["id"]


@pytest.mark.parametrize("pool,needle", [
    ({"hug": [{"text": "x", "others": "{actor} y"}]}, "needs a 'default'"),
    ({"default": [{"text": "x", "others": "no name"}]}, "with {actor}"),
    ({"default": [{"text": "x", "others": "{actor} y"}], "juggle": []}, "unknown gesture"),
])
def test_reaction_pools_fail_loud(pool, needle):
    env = copy.deepcopy(ENV)
    env["toons"][0]["properties"]["reactions"] = pool
    with pytest.raises(format2.Format2ValidationError, match=needle):
        format2.validate_envelope2(env)


def test_gesture_words_are_matched():
    assert gestures.match("hug Tace") == ("hug", "Tace")
    assert gestures.match("wave to Bell") == ("wave", "Bell")
    assert gestures.match("thank you, Tace") == ("thank", "Tace")
    assert gestures.match("give Mott a hug") == ("hug", "Mott")
    assert gestures.match("take the lantern") is None


async def test_a_gesture_then_a_move_does_both(loft):
    """A gesture opens a command of its own, so the line goes on past it
    (codereview 2026-09-30: "You don't see Bell and go west here")."""
    wren = loft["Wren"]
    before = await _do(wren, "hug Tace and go down")
    assert _seen(wren, before)[0] == "You hug Tace."
    assert objects.get(wren).location_id == "r-clocktower"


@pytest.mark.parametrize("line,told", [
    ("smile warmly", "You smile."), ("wave goodbye", "You wave."), ("bow deeply", "You bow.")])
async def test_a_word_that_says_how_is_not_a_name(loft, line, told):
    before = await _do(loft["Wren"], line)
    assert _seen(loft["Wren"], before) == [told]


async def test_thanks_for_something_thanks_the_one_here(loft):
    for other in ("Vesper", "Juniper"):
        objects.move(loft[other], "r-cellar")
    before = await _do(loft["Wren"], "thanks for the tea")
    assert _seen(loft["Wren"], before)[:2] == ["(Tace)", "You thank Tace."]


async def test_a_gesture_at_the_scenery_reads_the_scenery(loft):
    objects.move(loft["Wren"], "r-square")
    before = await _do(loft["Wren"], "hug the cobbles")
    assert _seen(loft["Wren"], before) == [
        "The cobbles are worn smooth and very much part of the square; they stay where they are."]


async def test_a_resting_dreamer_is_not_here_for_a_gesture(loft):
    """Criterion 2: a resting dreamer isn't here, as the target of a gesture
    or as the one it aims at (codereview 2026-09-30)."""
    wren = loft["Wren"]
    toons.kick_slot(2)  # Vesper rests where she stands
    before = await _do(wren, "hug Vesper")
    assert _seen(wren, before) == ["Vesper isn't here; Vesper is resting, out of the dream just now."]
    assert _seen(loft["Juniper"], before) == []
    objects.move(loft["Juniper"], "r-cellar")
    before = await _do(wren, "thank you")  # Tace is the one other person awake here
    assert _seen(wren, before)[:2] == ["(Tace)", "You thank Tace."]
