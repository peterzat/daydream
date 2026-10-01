"""What the page offers (playtest 2026-09-29): the ask-about chips show only
subjects the player has come across in the fiction, or that are authored
open; typing still reaches every available topic (daydream.heard;
DESIGN.md "What the page offers"). Over the canonical world, zero LLM."""

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
    story,
    toons,
    verbs,
    walkthrough,
    worldclock,
)
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
    assert "the Winding Balcony" in chips  # "Stairs go ... up to the balcony" (a mention)
    for unheard in ("Wend", "Mott", "Umber", "the highest shelf"):
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


async def test_a_line_the_model_wrote_introduces_nothing(village):
    """Playtest 2026-09-30: an improvised greeting ("the dusk is turning amber
    just as Wend liked to see it") made Wend a chip before any authored line
    had named Wend. Only what an author wrote introduces a subject."""
    me = _player()
    objects.move(me, "r-loft")
    events.append("system", None, "narrate",
                  {"text": "Tace smiles. 'Just as Wend liked to see it.'", "src": "local"},
                  room_id="r-loft", recipient_id=me)
    assert "Wend" not in _labels("t-tace", me)
    events.append("system", None, "narrate", {"text": "Mott mentions Wend.", "src": "local"},
                  room_id="r-loft")
    assert "Wend" not in _labels("t-tace", me)
    events.append("system", None, "narrate", {"text": "Somebody mentions Wend."},
                  room_id="r-loft", recipient_id=me)
    assert "Wend" in _labels("t-tace", me)


async def test_typing_reaches_an_unmet_topic_and_then_it_is_a_chip(village):
    me = _player()
    objects.move(me, "r-loft")
    before = events.max_seq()
    await _do(me, "ask tace about wend")
    said = " ".join(e.payload.get("text", "") for e in events.fetch_since(before)
                    if e.kind == "narrate")
    assert "Wend" in said  # answered, from the authored topic
    assert "Wend" in _labels("t-tace", me)


async def test_a_thread_names_its_subject_only_once_the_satchel_is_read(village):
    """An unopened satchel made its threads' names chips: Tace offered "the
    first winding" and Bell "Linden" to a player who had read neither
    (playthrough 2026-10-01c). A thread counts once its player reads it."""
    from daydream.api import ws

    me = _player()
    objects.move(me, "r-loft")
    from daydream import worldstate

    worldstate.set(WORLD, "flag:CLOCK-STARTED", True)
    assert any("first winding" in t for t in story.threads_for(me))
    assert "the first winding" not in _labels("t-tace", me)
    ws.saw_threads(me)
    assert "the first winding" in _labels("t-tace", me)


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


async def test_a_draft_that_introduces_someone_ranks_last(village, monkeypatch):
    """The same greeting, n-best: the draft that names a person this player
    has not come across loses to one that doesn't, even when it scores
    better on everything else; once the player has heard the name, or says
    it themself, it competes on its merits."""
    me = _player()
    objects.move(me, "r-loft")
    monkeypatch.setenv("DAYDREAM_DIALOGUE_NBEST", "2")
    drops = {"gesture": "Tace looks up from the bench.",
             "say": "The dusk is amber, just as Wend liked it.", "advance": "none"}
    plain = {"gesture": "Tace nods at you over the loupe.",  # "you": a worse score
             "say": "Come in, and mind the top step.", "advance": "none"}

    async def two(**kw):
        two.n += 1
        return drops if two.n % 2 else plain
    two.n = 0
    monkeypatch.setattr("daydream.llm.client.acompletion_json", two)

    async def reply(line: str) -> str:
        before = events.max_seq()
        await verbs.execute_command(me, "talk", dobj_id="t-tace", args=line)
        said = [e.payload for e in events.fetch_since(before)
                if e.kind == "narrate" and e.recipient_id == me]
        assert said and all(p.get("src") == "local" for p in said), said  # the model's
        return " ".join(p.get("text", "") for p in said)

    assert "Wend" not in await reply("hello there")
    assert "Wend" not in await reply("good evening to you")
    # The player names Wend (past the topic-select length, so the model answers).
    assert "Wend" in await reply("I keep wondering, on a dusk this amber, what Wend "
                                 "would have made of it")
    events.append("system", None, "narrate", {"text": "Somebody mentions Wend."},
                  room_id="r-loft", recipient_id=me)
    assert "Wend" in await reply("good evening")  # heard of now: on its merits
