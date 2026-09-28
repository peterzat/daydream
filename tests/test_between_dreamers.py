"""What passes between dreamers (beta rehearsal 2026-09-28).

A family playing on different schedules had no way to hand anything to
each other but drop-and-take, and the giver was told the other "leaves it
with you". Now a carried thing goes to a dreamer standing here, awake; a
thing that exists for one player alone stays; a resting or dozing dreamer
is not here to take it."""

from pathlib import Path

import pytest

from daydream import config, db, events, objects, verbs
from daydream.api import ws as ws_mod

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    # The fixture's Wren is a seeded toon; a giver is a player.
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1, controller_session = 's-wren' "
        "WHERE id = 't-wren'")
    ws_mod._mark_session_live("s-wren")
    # The fixture's things are the old bunny prototype (no give); the
    # canonical loader's things can be given.
    objects.set_property("i-lantern", "verbs", ["give"])
    ws_mod._last_disconnect.pop("s-ivo", None)
    yield
    ws_mod._unmark_session_live("s-wren")
    ws_mod._last_disconnect.pop("s-ivo", None)
    ws_mod._last_disconnect.pop("s-wren", None)
    db.close_db()
    events.reset_subscribers()


def _ivo(*, awake: bool = True, resting: bool = False):
    """A second dreamer in the meadow: awake at their page, or dozing (a
    claimed toon whose session never connected), or resting."""
    t = objects.spawn("w-bunny", "toon", "Ivo", "r-meadow", prototype_id=objects.PROTO_NPC,
                      properties={"seed": "a small man"})
    if resting:
        db.get_conn().execute(
            "UPDATE objects SET is_human_controlled = 0, kicked_at = '2026-09-28T00:00:00Z' "
            "WHERE id = ?", (t.id,))
    else:
        db.get_conn().execute(
            "UPDATE objects SET is_human_controlled = 1, controller_session = 's-ivo' "
            "WHERE id = ?", (t.id,))
        if awake:
            ws_mod._mark_session_live("s-ivo")
    return objects.get(t.id)


def _narrates(since: int = 0):
    return [e for e in events.fetch_since(since) if e.kind == "narrate"]


@pytest.mark.asyncio
async def test_a_carried_thing_goes_to_a_dreamer_standing_here():
    ivo = _ivo()
    try:
        await verbs.execute_command("t-wren", "take", dobj_id="i-lantern")
        before = events.max_seq()
        await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id=ivo.id)
        assert objects.get("i-lantern").location_id == ivo.id
        lines = _narrates(before)
        mine = [e for e in lines if e.recipient_id == "t-wren"]
        room = [e for e in lines if e.recipient_id is None]
        assert [e.payload["text"] for e in mine] == ["You hand the lantern to Ivo."]
        assert [e.payload["text"] for e in room] == ["Wren hands the lantern to Ivo."]
        assert room[0].payload["except"] == "t-wren"
    finally:
        ws_mod._unmark_session_live("s-ivo")


@pytest.mark.asyncio
async def test_a_thing_for_one_player_alone_stays_with_them():
    ivo = _ivo()
    try:
        glint = objects.spawn("w-bunny", "thing", "stray minute", "t-wren",
                              prototype_id=objects.PROTO_THING,
                              properties={"seed": "a glint", "private_to": "t-wren",
                                          "verbs": ["give"]})
        await verbs.execute_command("t-wren", "give", dobj_id=glint.id, iobj_id=ivo.id)
        assert objects.get(glint.id).location_id == "t-wren"
        last = _narrates()[-1]
        assert last.recipient_id == "t-wren" and "yours alone" in last.payload["text"]
    finally:
        ws_mod._unmark_session_live("s-ivo")


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["dozing", "resting"])
async def test_a_dreamer_not_at_their_page_is_not_here_to_take_it(how):
    ivo = _ivo(awake=False, resting=(how == "resting"))
    await verbs.execute_command("t-wren", "take", dobj_id="i-lantern")
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id=ivo.id)
    assert objects.get("i-lantern").location_id == "t-wren"
    last = _narrates()[-1]
    assert last.recipient_id == "t-wren"
    assert "far off in a dream of their own" in last.payload["text"]


def test_a_page_closed_a_moment_ago_is_not_yet_dozing(monkeypatch):
    """A phone switching to its messages drops the socket for a moment and
    picks the room's missed lines back up: within the grace a dreamer still
    reads as here."""
    import time

    ivo = _ivo(awake=False)
    assert ws_mod.is_dozing(ivo) is True  # a session that never connected
    monkeypatch.setitem(ws_mod._last_disconnect, "s-ivo", time.monotonic() - 5)
    assert ws_mod.is_dozing(ivo) is False
    monkeypatch.setitem(ws_mod._last_disconnect, "s-ivo",
                        time.monotonic() - ws_mod.DOZE_GRACE_S - 1)
    assert ws_mod.is_dozing(ivo) is True
