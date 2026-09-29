"""What the page offers (playtest 2026-09-29): the ask-about chips show only
subjects the player has come across in the fiction, or that are authored
open; typing still reaches every available topic (daydream.heard;
DESIGN.md "What the page offers"). Over the canonical world, zero LLM."""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import db, events, heard, objects, parser, story, toons, verbs, walkthrough, worldclock
from daydream.llm import format2

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())
WORLD = "w-lost-hours"


@pytest.fixture()
def village(tmp_path, monkeypatch):
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(side_effect=AssertionError("no LLM here")))
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    yield
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _player(name="Wren") -> str:
    t = toons.create_toon_in_slot(1, name, f"{name}, a dreamer", "heard-test",
                                  owner_account="a-heard")
    return t.id


def _labels(npc_id: str, actor: str) -> list[str]:
    return [t["label"] for t in story.offered_topics(objects.get(npc_id), actor)]


async def _do(actor: str, line: str) -> None:
    lp = await parser.parse_line(actor, line)
    for p in lp.commands:
        await verbs.execute_command(actor, p.verb, p.dobj_id, p.iobj_id, p.args,
                                    dobj_name=p.dobj_name)


def test_matching_is_forgiving_but_names_are_names(village):
    found = heard.subjects_in(WORLD, "Bell says to ask Tace about turning clocks back.")
    assert {"^bell", "^tace", "turning the clocks back"} <= found
    # A common noun never stands in for a person: "a bell" is not Bell.
    assert "^bell" not in heard.subjects_in(WORLD, "a bell rings over the door")
    # Articles, plurals, possessives and -ing fall away on both sides.
    assert "sitting down" in heard.subjects_in(WORLD, "someone who never sits down")
    assert "^wend" in heard.subjects_in(WORLD, "It was Wend's ladder.")


async def test_first_meeting_offers_only_what_you_have_come_across(village):
    me = _player()
    objects.move(me, "r-loft")
    chips = _labels("t-tace", me)
    assert "clockmaking" in chips  # authored open: the clockmaker's own trade
    assert "the loft" in chips  # the room you stand in names it
    for unheard in ("Wend", "Mott", "Umber", "the Winding Balcony"):
        assert unheard not in chips, chips


async def test_a_line_you_hear_names_its_subjects(village):
    me = _player()
    objects.move(me, "r-loft")
    assert "Wend" not in _labels("t-tace", me)
    events.append("system", None, "narrate", {"text": "Somebody mentions Wend."},
                  room_id="r-loft")
    assert "Wend" in _labels("t-tace", me)
    # A line kept from you teaches you nothing.
    events.append("system", None, "narrate",
                  {"text": "Mott waves from the stair.", "except": me}, room_id="r-loft")
    assert "Mott" not in _labels("t-tace", me)


async def test_typing_reaches_an_unmet_topic_and_then_it_is_a_chip(village):
    me = _player()
    objects.move(me, "r-loft")
    before = events.max_seq()
    await _do(me, "ask tace about wend")
    said = " ".join(e.payload.get("text", "") for e in events.fetch_since(before)
                    if e.kind == "narrate")
    assert "Wend" in said  # answered, from the authored topic
    assert "Wend" in _labels("t-tace", me)


def test_every_talk_beat_is_an_invitation_or_named_somewhere():
    """A beat's chip waits until the fiction names its topic, so every beat
    must be `topic_open` (the story reaching out) or named in some line a
    player can read other than its own: a telling, a thread, another
    topic's answer, a room, a thing. Otherwise only a guess could find it."""
    corpus: list[tuple[str, str]] = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("hint", "summary", "comment", "facts", "aliases",
                         "topic_aliases", "topic_mentions", "mentions", "voice"):
                    continue
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str) and len(node) > 12:
            corpus.append((path, node))

    walk(ENV, "")
    missing = []
    for arc_id, arc in ENV["arcs"].items():
        for beat_id, beat in arc["beats"].items():
            if "npc" not in beat or beat.get("topic_open"):
                continue
            own = f".arcs.{arc_id}.beats.{beat_id}."
            forms = [f for f in (heard.form_of("k", x) for x in
                                 [beat["topic"], *beat.get("topic_mentions", [])]) if f]
            if not any(heard.names(text, forms) for path, text in corpus
                       if not path.startswith(own)):
                missing.append(f"{arc_id}/{beat_id} ({beat['topic']})")
    assert not missing, missing


@pytest.mark.parametrize("mutate,needle", [
    (lambda e: e["toons"][0]["properties"]["topics"][0].update(open="yes"), "open must be"),
    (lambda e: e["toons"][0]["properties"]["topics"][0].update(mentions="x"), "mentions must"),
    (lambda e: e["arcs"]["pim"]["beats"]["bell-notices"].update(topic_open=1),
     "topic_open must"),
])
def test_disclosure_fields_fail_loud(mutate, needle):
    env = copy.deepcopy(ENV)
    mutate(env)
    with pytest.raises(format2.Format2ValidationError, match=needle):
        format2.validate_envelope2(env)
