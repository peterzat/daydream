"""While you were away (beta rehearsal 2026-09-28).

A returning player is told, once, what changed since they last rested: who
else dreamed here, hours sent home (the chronicle), guests that came,
places that grew and whose seed they were, post waiting. Composed from
what the world records; nothing when nothing changed."""

from pathlib import Path

import pytest

from daydream import absence, config, db, events, inputs, objects, story, toons, worldclock, worldstate

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
    worldclock.set_fake_now("2026-10-01T18:00:00+00:00")
    yield
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _ivo():
    t = objects.spawn(W, "toon", "Ivo", "r-meadow", prototype_id=objects.PROTO_NPC,
                      properties={"seed": "a small man"})
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1, controller_session = 's-ivo', slot = 2 "
        "WHERE id = ?", (t.id,))
    return objects.get(t.id)


def _rest_wren():
    toons.kick_slot(1)


def _wake_wren():
    toons.claim_slot(1, "s-wren")


def test_nothing_changed_nothing_said():
    _rest_wren()
    worldclock.advance(hours=1)
    _wake_wren()
    assert absence.take_note("t-wren") is None


def test_the_note_names_who_came_what_closed_what_grew_and_the_post():
    ivo = _ivo()
    _rest_wren()
    worldclock.advance(hours=2)
    # Ivo dreamed here meanwhile.
    inputs.record(ivo.id, "text", text="look")
    # An hour went home (the chronicle).
    worldstate.set(W, story.CHRONICLE_KEY, [
        {"arc": "moth", "ending": "home", "day": 1, "at": worldclock.iso(),
         "helpers": ["Ivo"], "text": "Ivo lit a lamp for the moth hour."},
        {"arc": "old", "ending": "kept", "day": 0, "at": "2026-09-01T00:00:00+00:00",
         "helpers": [], "text": "Long ago, something else."},
    ])
    # A guest came.
    guest = objects.spawn(W, "toon", "the Moth Hour", "r-meadow", prototype_id=objects.PROTO_NPC)
    worldstate.set(W, "def:arcs", {"moth": {"kind": "guest", "guest": guest.id, "title": "The Moth"}})
    worldstate.set(W, "arc:moth", {"status": "open", "opened_at": worldclock.iso(),
                                   "beats": {}, "helpers": []})
    # A place grew north of the meadow, from Ivo's seed.
    objects.spawn(W, "room", "The Moss Stair", None, properties={
        "title": "The Moss Stair", "slug": "moss-stair", "exits": {"south": "r-meadow"},
        "grown": {"planter_id": ivo.id, "phrase": "a mossy stair", "at": worldclock.iso()}})
    # Post waits.
    worldstate.set(W, "config", {"post": {"room": "r-forge", "waiting_text": "Post waits at the forge."}})
    objects.spawn(W, "thing", "letter from Ivo", "r-forge", prototype_id=objects.PROTO_READABLE,
                  properties={"letter": {"from": ivo.id, "to": "t-wren"}, "private_to": "t-wren"})
    worldclock.advance(minutes=5)
    _wake_wren()
    note = absence.take_note("t-wren")
    assert note is not None and note["title"] == "While you were away"
    meadow = toons.in_sentence(objects.get("r-meadow").properties.get("title"))
    assert note["text"] == (
        "Ivo was here while you rested. Ivo lit a lamp for the moth hour. "
        f"the Moth Hour has come to the village and waits in {meadow}. "
        f"A new place grew to the north of {meadow}: the Moss Stair, from Ivo's dreamseed. "
        "Post waits at the forge."
    )
    # Once.
    assert absence.take_note("t-wren") is None


def test_only_what_happened_after_the_rest_counts():
    ivo = _ivo()
    inputs.record(ivo.id, "text", text="look")  # before Wren rests
    worldclock.advance(minutes=1)
    _rest_wren()
    worldclock.advance(hours=1)
    _wake_wren()
    assert absence.take_note("t-wren") is None
