"""Event log: append, fetch_since, subscribe/unsubscribe, room filter."""

from pathlib import Path

import pytest

from daydream import config, db, events


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def test_append_returns_event_with_seq():
    e = events.append("toon", "t-wren", "say", {"text": "hello"}, room_id="r-meadow")
    assert e.seq >= 1
    assert e.kind == "say"
    assert e.payload == {"text": "hello"}
    assert e.room_id == "r-meadow"
    assert e.actor_id == "t-wren"
    assert e.actor_type == "toon"


def test_append_assigns_monotonic_seq():
    e1 = events.append("toon", "t-wren", "say", {"text": "one"}, room_id="r-meadow")
    e2 = events.append("toon", "t-wren", "say", {"text": "two"}, room_id="r-meadow")
    e3 = events.append("toon", "t-wren", "say", {"text": "three"}, room_id="r-meadow")
    assert e1.seq < e2.seq < e3.seq


def test_append_with_no_payload_defaults_empty():
    e = events.append("system", None, "world_drift")
    assert e.payload == {}
    assert e.actor_id is None
    assert e.room_id is None


def test_fetch_since_returns_only_newer():
    e1 = events.append("toon", "t-wren", "say", {"text": "one"}, room_id="r-meadow")
    e2 = events.append("toon", "t-wren", "say", {"text": "two"}, room_id="r-meadow")
    fetched = events.fetch_since(last_seq=e1.seq)
    assert [e.seq for e in fetched] == [e2.seq]


def test_fetch_since_filters_by_room():
    events.append("toon", "t-wren", "say", {"text": "in meadow"}, room_id="r-meadow")
    events.append("toon", "t-other", "say", {"text": "elsewhere"}, room_id="r-other")
    fetched = events.fetch_since(last_seq=0, room_id="r-meadow")
    assert len(fetched) == 1
    assert fetched[0].payload == {"text": "in meadow"}


def test_max_seq_starts_zero_then_climbs():
    assert events.max_seq() == 0
    events.append("system", None, "world_drift")
    assert events.max_seq() == 1
    events.append("system", None, "world_drift")
    assert events.max_seq() == 2


def test_subscribe_receives_appended_events():
    q = events.subscribe()
    e = events.append("toon", "t-wren", "say", {"text": "hi"}, room_id="r-meadow")
    received = q.get_nowait()
    assert received.seq == e.seq
    assert received.payload == {"text": "hi"}


def test_unsubscribe_stops_receiving():
    q = events.subscribe()
    events.unsubscribe(q)
    events.append("toon", "t-wren", "say", {"text": "hi"})
    assert q.empty()


def test_multiple_subscribers_all_receive():
    q1 = events.subscribe()
    q2 = events.subscribe()
    events.append("toon", "t-wren", "say", {"text": "hi"})
    e1 = q1.get_nowait()
    e2 = q2.get_nowait()
    assert e1.seq == e2.seq


def test_event_to_dict_round_trip():
    e = events.append("toon", "t-wren", "look", {"target": "lantern"}, room_id="r-meadow")
    d = e.to_dict()
    assert d["seq"] == e.seq
    assert d["kind"] == "look"
    assert d["payload"] == {"target": "lantern"}
    assert d["room_id"] == "r-meadow"


def test_persists_across_reconnect(tmp_path: Path):
    """Events survive a connection close/reopen — the spine of SPEC criterion 8."""
    path = tmp_path / "live.db"
    db.close_db()
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    e1 = events.append("toon", "t-wren", "say", {"text": "hello"}, room_id="r-meadow")
    db.close_db()
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    fetched = events.fetch_since(last_seq=0)
    assert any(e.seq == e1.seq and e.payload == {"text": "hello"} for e in fetched)
