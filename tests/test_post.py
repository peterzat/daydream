"""Letters between dreamers (beta rehearsal 2026-09-28).

At the room a world's `config.post` names, `write to <dreamer>: <words>`
files a letter only that dreamer can see, take and read; they are told on
arrival and in their threads, and at once if awake elsewhere. Every
refusal is the writer's alone. A world with no post has none."""

from pathlib import Path

import pytest

from daydream import config, db, events, objects, post, story, verbs, worldstate
from daydream.api import ws as ws_mod
from daydream.parser import parse

pytestmark = pytest.mark.tier_short

POST = {
    "room": "r-forge",
    "write_text": "You write it out and Rook files it. It will keep for {to}.",
    "write_others": "{actor} writes something out and hands it to Rook.",
    "elsewhere_text": "Nothing to write on here; Rook keeps paper at the forge.",
    "unknown_text": "Rook shakes his head: no dreamer called {to}.",
    "self_text": "Rook laughs: a letter to yourself?",
    "resident_text": "Rook points: {to} is right there, tell them.",
    "off_tone_text": "Rook slides it back: not that.",
    "waiting_text": "A letter waits for you at the forge.",
    "rings_text": "The forge bell rings twice: post for you.",
    "letter_name": "letter from {from}",
    "letter_seed": "a folded letter for {to} in {from}'s hand",
    "read_text": "To {to}, from {from}: {text}",
}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1, controller_session = 's-wren' "
        "WHERE id = 't-wren'")
    ws_mod._mark_session_live("s-wren")
    worldstate.set("w-bunny", "config", {"post": dict(POST)})
    yield
    ws_mod._unmark_session_live("s-wren")
    ws_mod._unmark_session_live("s-ivo")
    ws_mod._last_disconnect.pop("s-ivo", None)
    ws_mod._last_disconnect.pop("s-wren", None)
    db.close_db()
    events.reset_subscribers()


def _ivo(*, room: str = "r-meadow", awake: bool = False):
    t = objects.spawn("w-bunny", "toon", "Ivo", room, prototype_id=objects.PROTO_NPC,
                      properties={"seed": "a small man"})
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1, controller_session = 's-ivo' WHERE id = ?",
        (t.id,))
    if awake:
        ws_mod._mark_session_live("s-ivo")
    return objects.get(t.id)


def _wren():
    return objects.get("t-wren")


def _narrates(since: int = 0):
    return [e for e in events.fetch_since(since) if e.kind == "narrate"]


def _go(room: str):
    objects.move("t-wren", room)


@pytest.mark.asyncio
async def test_a_letter_waits_for_its_dreamer_alone_and_reads_whole():
    ivo = _ivo()
    _go("r-forge")
    before = events.max_seq()
    await verbs.execute_command("t-wren", "write", args="to Ivo: meet me by the well at dusk. bring the cog.")
    lines = _narrates(before)
    mine = [e for e in lines if e.recipient_id == "t-wren"]
    room = [e for e in lines if e.recipient_id is None]
    assert [e.payload["text"] for e in mine] == ["You write it out and Rook files it. It will keep for Ivo."]
    assert [e.payload["text"] for e in room] == ["Wren writes something out and hands it to Rook."]
    # The letter waits at the post room, for Ivo alone.
    letters = [o for o in objects.contents("r-forge", kind="thing") if o.properties.get("letter")]
    assert len(letters) == 1
    letter = letters[0]
    assert letter.name == "letter from Wren"
    assert objects.visible_to(letter, ivo.id) and not objects.visible_to(letter, "t-wren")
    assert letter.properties["home"] is None  # a keepsake once taken
    assert post.letters_waiting(ivo.id) == [letter]
    assert post.letters_waiting("t-wren") == []
    # Ivo's threads say so; Wren's do not.
    assert story.threads_for(ivo.id) == ["A letter waits for you at the forge."]
    assert story.threads_for("t-wren") == []
    # Ivo reads it whole, in Wren's words.
    objects.move(ivo.id, "r-forge")
    before = events.max_seq()
    await verbs.execute_command(ivo.id, "take", dobj_id=letter.id)
    await verbs.execute_command(ivo.id, "read", dobj_id=letter.id)
    read = [e for e in _narrates(before) if e.recipient_id == ivo.id and "meet me" in e.payload["text"]]
    assert read and read[0].payload["text"] == (
        "To Ivo, from Wren: meet me by the well at dusk. bring the cog.")
    assert post.letters_waiting(ivo.id) == []
    assert story.threads_for(ivo.id) == []


@pytest.mark.asyncio
async def test_two_letters_from_the_same_hand_both_wait():
    ivo = _ivo()
    _go("r-forge")
    await verbs.execute_command("t-wren", "write", args="Ivo: first")
    await verbs.execute_command("t-wren", "write", args="Ivo: second")
    texts = sorted(o.properties["text"] for o in post.letters_waiting(ivo.id))
    assert texts == ["To Ivo, from Wren: first", "To Ivo, from Wren: second"]


@pytest.mark.asyncio
async def test_a_dreamer_awake_elsewhere_hears_the_bell_at_once():
    ivo = _ivo(room="r-meadow", awake=True)
    _go("r-forge")
    before = events.max_seq()
    await verbs.execute_command("t-wren", "write", args="to Ivo: hello")
    rung = [e for e in _narrates(before) if e.recipient_id == ivo.id]
    assert [e.payload["text"] for e in rung] == ["The forge bell rings twice: post for you."]
    assert rung[0].room_id == "r-meadow"


@pytest.mark.asyncio
async def test_refusals_are_the_writers_alone_and_write_nothing():
    _ivo()
    cases = [
        ("r-meadow", "to Ivo: hi", "Nothing to write on here"),
        ("r-forge", "", "Write to whom"),
        ("r-forge", "to Ivo", "Write to whom"),
        ("r-forge", "to Nobody: hi", "no dreamer called Nobody"),
        ("r-forge", "to Wren: hi", "letter to yourself"),
        ("r-forge", "to me: hi", "letter to yourself"),
        ("r-forge", "to Rook: hi", "Rook is right there"),
        ("r-forge", "to Ivo: " + "x" * (post.MAX_LETTER_CHARS + 1), "fewer words"),
        ("r-forge", "to Ivo: you must hurry, the deadline is now", "not that"),
    ]
    for room, args, expect in cases:
        _go(room)
        before = events.max_seq()
        ok = await verbs.execute_command("t-wren", "write", args=args)
        lines = _narrates(before)
        assert len(lines) == 1 and lines[0].recipient_id == "t-wren", (args, lines)
        assert expect in lines[0].payload["text"], (args, lines[0].payload["text"])
    assert not [o for o in objects.contents("r-forge", kind="thing") if o.properties.get("letter")]


@pytest.mark.asyncio
async def test_a_world_with_no_post_has_none():
    worldstate.set("w-bunny", "config", {})
    _go("r-forge")
    before = events.max_seq()
    await verbs.execute_command("t-wren", "write", args="to Ivo: hi")
    lines = _narrates(before)
    assert len(lines) == 1 and "nowhere to post" in lines[0].payload["text"]


def test_split_address_reads_the_ways_people_write_it():
    assert post.split_address("to Ivo: hello there") == ("Ivo", "hello there")
    assert post.split_address("a letter to Ivo: hello") == ("Ivo", "hello")
    assert post.split_address("Ivo, hello, and goodbye") == ("Ivo", "hello, and goodbye")
    assert post.split_address("for Ivo hello") == ("Ivo", "hello")
    assert post.split_address("Ivo") == ("Ivo", "")
    assert post.split_address("") == ("", "")


@pytest.mark.asyncio
async def test_a_typed_letter_is_the_writers_words_whole(monkeypatch):
    """`write to Ivo: ...` never reaches the model: a letter's words are kept
    whole, periods and all (a period splits command chains otherwise)."""
    from unittest.mock import AsyncMock

    spy = AsyncMock(return_value={"verb": "none"})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    p = await parse("t-wren", "write to Ivo: I found the gear. Meet me at dusk. Bring the cog!")
    assert p.verb == "write"
    assert p.args == "to Ivo: I found the gear. Meet me at dusk. Bring the cog!"
    spy.assert_not_called()
