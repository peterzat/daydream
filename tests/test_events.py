"""Event log: append, fetch_since, subscribe/unsubscribe, room filter."""

from pathlib import Path

import pytest

from daydream import config, db, events

pytestmark = pytest.mark.tier_short


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


# ---- bounded subscriber queues (drop-oldest ring, control-safe) -----------


def _mk_event(seq: int) -> events.Event:
    return events.Event(
        seq=seq, created_at="t", actor_type="toon", actor_id="t-x",
        kind="say", payload={"n": seq}, room_id="r-x", recipient_id=None,
    )


def test_subscribe_queue_is_bounded():
    q = events.subscribe()
    assert q.maxsize == events.EVENT_QUEUE_MAXSIZE


def test_full_queue_drops_oldest_event():
    """Past the cap, the OLDEST event is evicted so the freshest lands;
    the queue never grows beyond the bound."""
    q = events.subscribe()
    n = events.EVENT_QUEUE_MAXSIZE
    for i in range(n + 5):  # 5 past the cap
        events._put_bounded(q, _mk_event(i))
    assert q.qsize() == n
    drained = [q.get_nowait() for _ in range(q.qsize())]
    seqs = [e.seq for e in drained]
    # Oldest 5 dropped; newest present; FIFO order preserved.
    assert seqs[0] == 5
    assert seqs[-1] == n + 4
    assert events.dropped_event_total() == 5


def test_control_signal_never_dropped_on_overflow():
    """A WORLD_CHANGED pushed onto a full queue evicts an EVENT, not itself."""
    q = events.subscribe()
    n = events.EVENT_QUEUE_MAXSIZE
    for i in range(n):  # exactly full
        events._put_bounded(q, _mk_event(i))
    events._put_bounded(q, events.WORLD_CHANGED)
    items = [q.get_nowait() for _ in range(q.qsize())]
    assert events.WORLD_CHANGED in items
    assert q.maxsize == n and len(items) == n
    # Exactly one event was dropped to make room for the control signal.
    assert events.dropped_event_total() == 1


def test_control_signal_at_head_preserved_when_evicting():
    """When a control signal sits at the head of a full queue, an incoming
    event drops the oldest EVENT (drain-refill path), not the signal."""
    q = events.subscribe()
    n = events.EVENT_QUEUE_MAXSIZE
    events._put_bounded(q, events.WORLD_CHANGED)  # head is the signal
    for i in range(n - 1):  # fill to exactly full
        events._put_bounded(q, _mk_event(i))
    assert q.qsize() == n
    events._put_bounded(q, _mk_event(999))  # overflow: must drop an event
    items = [q.get_nowait() for _ in range(q.qsize())]
    assert events.WORLD_CHANGED is items[0]  # signal still at head
    assert items[-1].seq == 999
    assert 0 not in [getattr(e, "seq", None) for e in items]  # oldest event gone


def test_healthy_consumer_never_drops():
    q = events.subscribe()
    for i in range(events.EVENT_QUEUE_MAXSIZE):
        events._put_bounded(q, _mk_event(i))
    assert events.dropped_event_total() == 0
    assert q._dd_dropped == 0
