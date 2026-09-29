"""Traces of dreamers (beta rehearsal 2026-09-28).

Residents remembered deeds but not dreamers: asked where an absent friend
was, the model invented a room; a friend arriving after friends found no
signed trace. Now `ask <resident> about <dreamer>` reads the record (last
seen, state, the deeds this resident knows), the model's prompt carries the
same record for any dreamer a line names, and an authored readable or
fixture can show a roster: the keepers who have dreamed here, or the guest
hours waiting and gone home."""

from pathlib import Path

import pytest

from daydream import config, db, events, inputs, knowledge, objects, story, trace, verbs, worldclock, worldstate
from daydream.api import ws as ws_mod

pytestmark = pytest.mark.tier_short

W = "w-bunny"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1, controller_session = 's-wren' "
        "WHERE id = 't-wren'")
    ws_mod._mark_session_live("s-wren")
    worldclock.set_fake_now("2026-10-01T18:00:00+00:00")
    yield
    worldclock.set_fake_now(None)
    ws_mod._unmark_session_live("s-wren")
    ws_mod._unmark_session_live("s-ivo")
    ws_mod._last_disconnect.pop("s-ivo", None)
    db.close_db()
    events.reset_subscribers()


def _ivo(room="r-forge", *, resting=False):
    t = objects.spawn(W, "toon", "Ivo", room, prototype_id=objects.PROTO_NPC,
                      properties={"seed": "a small man"})
    if resting:
        db.get_conn().execute(
            "UPDATE objects SET is_human_controlled = 0, kicked_at = '2026-10-01T10:00:00Z' "
            "WHERE id = ?", (t.id,))
    else:
        db.get_conn().execute(
            "UPDATE objects SET is_human_controlled = 1, controller_session = 's-ivo' WHERE id = ?",
            (t.id,))
    return objects.get(t.id)


def _narrates(since=0):
    return [e for e in events.fetch_since(since) if e.kind == "narrate"]


def test_when_phrases():
    now = worldclock.now()
    assert trace.when_phrase(None) == "some time ago"
    assert trace.when_phrase(worldclock.iso(now)) == "a moment ago"
    assert trace.when_phrase("2026-10-01T17:30:00+00:00") == "not long ago"
    assert trace.when_phrase("2026-10-01T16:30:00+00:00") == "an hour or so ago"
    assert trace.when_phrase("2026-10-01T08:00:00+00:00") == "earlier today"
    assert trace.when_phrase("2026-09-30T12:00:00+00:00") == "yesterday"
    assert trace.when_phrase("2026-09-26T12:00:00+00:00") == "some days ago"
    # By the village's calendar: the previous evening is "yesterday" at
    # breakfast, however few hours ago it was.
    from zoneinfo import ZoneInfo

    la = ZoneInfo("America/Los_Angeles")
    worldclock.set_fake_now("2026-10-01T16:30:00+00:00")  # 09:30 in the village
    assert trace.when_phrase("2026-10-01T02:00:00+00:00", la) == "yesterday"  # 19:00 the evening before
    assert trace.when_phrase("2026-10-01T13:00:00+00:00", la) == "earlier today"


@pytest.mark.asyncio
async def test_asking_a_resident_about_a_dreamer_reads_the_record():
    ivo = _ivo(resting=True)
    worldclock.set_fake_now("2026-10-01T16:40:00+00:00")
    inputs.record(ivo.id, "text", text="look")  # Ivo was in the forge then
    knowledge.add_fact(W, "lit-lamp", "{actor} lit a lamp for the moth hour.", ivo.id,
                       ["t-rook"], [])
    worldclock.set_fake_now("2026-10-01T18:00:00+00:00")
    objects.move("t-wren", "r-forge")
    before = events.max_seq()
    await verbs.execute_command("t-wren", "ask", dobj_id="t-rook", args="Ivo")
    lines = [e for e in _narrates(before)]
    assert len(lines) == 1 and lines[0].recipient_id == "t-wren"
    text = lines[0].payload["text"]
    assert text.startswith("Ivo was last seen an hour or so ago in the Quiet Forge, and is resting now")
    assert "Rook knows that Ivo lit a lamp for the moth hour." in text
    echo = [e for e in events.fetch_since(before) if e.kind == "echo"]
    assert echo and echo[0].payload["text"] == "You ask Rook about Ivo."


@pytest.mark.asyncio
async def test_asking_about_an_unknown_dreamer_says_so():
    _ivo()
    ws_mod._mark_session_live("s-ivo")
    objects.move("t-wren", "r-forge")
    before = events.max_seq()
    await verbs.execute_command("t-wren", "ask", dobj_id="t-rook", args="ivo")
    text = _narrates(before)[-1].payload["text"]
    assert "Rook knows nothing more of them than that." in text
    assert "here now" in text  # Ivo stands in the forge too


def test_the_prompt_carries_the_record_of_named_dreamers():
    from daydream import dialogue

    ivo = _ivo("r-meadow", resting=True)
    inputs.record(ivo.id, "text", text="look")
    objects.move("t-wren", "r-forge")
    _, user, _ = dialogue.build_prompt(objects.get("t-wren"), objects.get("t-rook"),
                                       "Have you seen Ivo? Where did ivo go?", "r-forge", [])
    assert "OTHER DREAMERS" in user
    assert "Ivo was last seen a moment ago in" in user and "resting now" in user
    _, user2, _ = dialogue.build_prompt(objects.get("t-wren"), objects.get("t-rook"),
                                        "How are the bellows today?", "r-forge", [])
    assert "OTHER DREAMERS" not in user2


def test_the_prompt_weaves_grounding():
    from daydream import dialogue

    objects.move("t-wren", "r-forge")
    _, user, _ = dialogue.build_prompt(objects.get("t-wren"), objects.get("t-rook"),
                                       "Tell me about the forge and about my friend", "r-forge", [],
                                       grounding=["Rook pats the anvil. 'Warm as ever.'"])
    assert "WOULD SAY ABOUT WHAT WAS MENTIONED" in user and "Warm as ever" in user


def test_rosters_on_a_readable_and_a_fixture():
    ivo = _ivo(resting=True)
    worldclock.set_fake_now("2026-10-01T08:00:00+00:00")
    inputs.record(ivo.id, "text", text="look")
    worldclock.set_fake_now("2026-10-01T18:00:00+00:00")
    inputs.record("t-wren", "text", text="look")
    book = objects.spawn(W, "thing", "blue book", "r-meadow", prototype_id=objects.PROTO_READABLE,
                         properties={"seed": "a blue book", "text": "Deeds.",
                                     "roster": {"kind": "keepers",
                                                "text": "Signed: {names}.", "empty": "Unsigned."}})
    assert trace.roster_text(book, "t-wren") == "Signed: Wren (here now) and Ivo (last here earlier today)."
    board = objects.spawn(W, "thing", "key board", "r-meadow", prototype_id=objects.PROTO_THING,
                          properties={"seed": "a board of keys",
                                      "roster": {"kind": "guests",
                                                 "text": "Waiting: {waiting}. Home: {home}.",
                                                 "empty": "Clean."}})
    assert trace.roster_text(board, "t-wren") == "Clean."
    guest = objects.spawn(W, "toon", "the Moth Hour", "r-meadow", prototype_id=objects.PROTO_NPC)
    gone = objects.spawn(W, "toon", "the Rain", None, prototype_id=objects.PROTO_NPC)
    worldstate.set(W, "def:arcs", {"moth": {"kind": "guest", "guest": guest.id},
                                   "rain": {"kind": "guest", "guest": gone.id}})
    worldstate.set(W, "arc:moth", {"status": "open", "beats": {}, "helpers": []})
    worldstate.set(W, "arc:rain", {"status": "closed", "ending": "home", "beats": {}, "helpers": []})
    assert trace.roster_text(board, "t-wren") == "Waiting: the Moth Hour. Home: the Rain."


@pytest.mark.asyncio
async def test_reading_and_examining_show_the_roster():
    inputs.record("t-wren", "text", text="look")
    book = objects.spawn(W, "thing", "blue book", "r-meadow", prototype_id=objects.PROTO_READABLE,
                         properties={"seed": "a blue book", "text": "Deeds.", "verbs": ["read"],
                                     "roster": {"kind": "keepers", "text": "Signed: {names}."}})
    before = events.max_seq()
    await verbs.execute_command("t-wren", "read", dobj_id=book.id)
    assert _narrates(before)[-1].payload["text"] == "Deeds.\nSigned: Wren (here now)."
    before = events.max_seq()
    await verbs.execute_command("t-wren", "examine", dobj_id=book.id)
    assert _narrates(before)[-1].payload["text"].endswith("Signed: Wren (here now).")
