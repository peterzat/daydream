"""Append-only event log: the spine of all state mutations.

append() writes one row to the events table and notifies live subscribers.
fetch_since() pulls events newer than a given seq for hydration and reconnect.
subscribe() / unsubscribe() let websocket sessions get pushed events as they happen.

The event log is the canonical persistence target. Every state change writes
here first; derived state (rooms, toons, items) is updated by handlers that
read events. Snapshots are (db file, max(seq)).
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from daydream import db

logger = logging.getLogger("daydream.events")

# Per-subscriber queue bound. A WS connection whose client stops reading
# (backgrounded tab, dead socket mid-close, a bot that never drains) would
# otherwise grow its queue without limit as the world mutates. 256 is a
# generous backlog — far more than a live viewer is ever behind — so a
# healthy connection never hits it; a wedged one drops its OLDEST events
# (ring semantics) rather than ballooning memory. Safe because every
# observable mutation re-snapshots and a reconnect replays via ?since, so a
# lagged consumer self-heals to current truth on the next snapshot.
EVENT_QUEUE_MAXSIZE = 256

# Process-wide count of events dropped from full subscriber queues, for
# observability (surfaced by dropped_event_total(); read by the swarm
# harness). Only Event drops are counted here — a control signal is never
# dropped in favor of an Event (see _put_bounded for the one pathological
# exception, which is itself uncounted).
_dropped_total = 0


@dataclass(frozen=True)
class Event:
    seq: int
    created_at: str
    actor_type: str
    actor_id: str | None
    kind: str
    payload: dict[str, Any]
    room_id: str | None
    # NULL = broadcast (the default and every pre-014 row); a toon id makes
    # the event actor-private (migration 014): delivered and replayed only to
    # the connection controlling that toon.
    recipient_id: str | None = None

    @classmethod
    def from_row(cls, row) -> "Event":
        return cls(
            seq=row["seq"],
            created_at=row["created_at"],
            actor_type=row["actor_type"],
            actor_id=row["actor_id"],
            kind=row["kind"],
            payload=json.loads(row["payload_json"]),
            room_id=row["room_id"],
            recipient_id=row["recipient_id"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "created_at": self.created_at,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "kind": self.kind,
            "payload": self.payload,
            "room_id": self.room_id,
            "recipient_id": self.recipient_id,
        }


_subscribers: list[asyncio.Queue] = []


class _ControlSignal:
    """A non-Event sentinel pushed onto subscriber queues to drive a control
    action in the WS broadcast loop, out of band from the event stream. The
    loop dispatches on `is` identity, so these are module-level singletons,
    never per-instance. Today the only signal is WORLD_CHANGED (in-process
    world hot-swap): the loop re-snapshots the connection against the now-live
    world when it sees it."""

    __slots__ = ("kind",)

    def __init__(self, kind: str) -> None:
        self.kind = kind


# Singleton control signal, compared by identity in the WS broadcast loop.
WORLD_CHANGED = _ControlSignal("world_changed")


def append(
    actor_type: str,
    actor_id: str | None,
    kind: str,
    payload: dict[str, Any] | None = None,
    room_id: str | None = None,
    recipient_id: str | None = None,
) -> Event:
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO events(actor_type, actor_id, kind, payload_json, room_id, "
        "recipient_id) VALUES (?, ?, ?, ?, ?, ?)",
        (actor_type, actor_id, kind, json.dumps(payload or {}), room_id, recipient_id),
    )
    seq = cur.lastrowid
    row = conn.execute(
        "SELECT seq, created_at, actor_type, actor_id, kind, payload_json, room_id, "
        "recipient_id FROM events WHERE seq = ?",
        (seq,),
    ).fetchone()
    event = Event.from_row(row)
    _broadcast(event)
    return event


def fetch_since(
    last_seq: int = 0,
    room_id: str | None = None,
    limit: int | None = None,
    recipient_for: str | None = None,
) -> list[Event]:
    """Events newer than `last_seq`, optionally scoped to one room.

    `recipient_for` applies the private-event filter (migration 014): only
    broadcast rows (NULL recipient) and rows addressed to that toon are
    returned — the replay-side twin of the WS broadcast-loop filter. None
    (the default) returns everything, for admin/diagnostic readers."""
    conn = db.get_conn()
    sql = "SELECT * FROM events WHERE seq > ?"
    params: list = [last_seq]
    if room_id is not None:
        sql += " AND room_id = ?"
        params.append(room_id)
    if recipient_for is not None:
        sql += " AND (recipient_id IS NULL OR recipient_id = ?)"
        params.append(recipient_for)
    sql += " ORDER BY seq"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [Event.from_row(r) for r in rows]


def fetch_for_toon(toon_id: str, since: int = 0, limit: int = 50) -> list[Event]:
    """The toon's OWN recent events: rows it acted (actor_id) or was
    addressed by (recipient_id), newer than `since`, returned oldest-first
    and capped to the most recent `limit`. Feeds the dream-journal recap
    (SPEC 2026-07-07 criterion 3).

    Documented limitation: a room-broadcast NPC reply carries the NPC's
    actor_id and a NULL recipient, so it is not attributed to the player
    who prompted it and stays out of their recap window."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT * FROM ("
        "  SELECT * FROM events WHERE seq > ? AND (actor_id = ? OR recipient_id = ?)"
        "  ORDER BY seq DESC LIMIT ?"
        ") ORDER BY seq",
        (since, toon_id, toon_id, int(limit)),
    ).fetchall()
    return [Event.from_row(r) for r in rows]


def max_seq() -> int:
    conn = db.get_conn()
    row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
    return row[0] or 0


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=EVENT_QUEUE_MAXSIZE)
    # Per-queue drop count; the first drop WARNs once (see _put_bounded).
    q._dd_dropped = 0  # type: ignore[attr-defined]
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _subscribers:
        _subscribers.remove(q)


def _put_bounded(q: asyncio.Queue, item: Any) -> None:
    """Enqueue onto a bounded subscriber queue with drop-oldest ring
    semantics. On overflow the OLDEST Event is evicted so the freshest
    state still lands (a lagged consumer self-heals via the next
    re-snapshot / reconnect replay). Control signals (WORLD_CHANGED) are
    never dropped in favor of an Event — losing one strands a connection on
    a swapped-out world, which a reconnect can't recover as cheaply as a
    missed event. The lone exception is the pathological all-control-signals
    overflow (a full queue of 256 WORLD_CHANGED with nothing draining), which
    evicts the oldest to stay bounded; unreachable with the live draining
    consumer, and harmless anyway since WORLD_CHANGED is idempotent. The fast
    path (not full) and the common overflow (oldest is an Event) are O(1);
    the drain-refill only runs when a rare control signal sits at the head."""
    try:
        q.put_nowait(item)
        return
    except asyncio.QueueFull:
        pass
    # Full. Evict the oldest item.
    try:
        oldest = q.get_nowait()
    except asyncio.QueueEmpty:
        # Drained concurrently (shouldn't happen: single-threaded loop).
        q.put_nowait(item)
        return
    if not isinstance(oldest, _ControlSignal):
        # Common case: the head was an old event; dropping it is exactly
        # the ring behavior we want, and room now exists. O(1), order kept.
        q.put_nowait(item)
        _record_drop(q)
        return
    # Rare path: the head is an undroppable control signal. Drain the rest
    # and rebuild [head] + rest so the signal keeps its position, then drop
    # the oldest EVENT from that sequence instead.
    combined: list[Any] = [oldest]
    try:
        while True:
            combined.append(q.get_nowait())
    except asyncio.QueueEmpty:
        pass
    for i, it in enumerate(combined):
        if not isinstance(it, _ControlSignal):
            del combined[i]
            _record_drop(q)
            break
    else:
        # Pathological: queue is all control signals. Drop the oldest to
        # avoid unbounded growth (does not count as an event drop).
        if combined:
            del combined[0]
    for it in combined:
        q.put_nowait(it)
    q.put_nowait(item)


def _record_drop(q: asyncio.Queue) -> None:
    global _dropped_total
    _dropped_total += 1
    q._dd_dropped = getattr(q, "_dd_dropped", 0) + 1  # type: ignore[attr-defined]
    if q._dd_dropped == 1:  # type: ignore[attr-defined]
        logger.warning(
            "event subscriber queue full (%d); dropping oldest events for a "
            "lagged connection. It self-heals on the next re-snapshot / "
            "reconnect. (further drops on this connection are silent)",
            EVENT_QUEUE_MAXSIZE,
        )


def dropped_event_total() -> int:
    """Process-wide count of events dropped from full subscriber queues
    since boot. Observability for the swarm harness / future stats."""
    return _dropped_total


def _broadcast(event: Event) -> None:
    """Fan out an event to every live subscriber via the bounded, drop-oldest
    ring (see _put_bounded). A wedged consumer can never balloon memory or
    block the append path."""
    for q in list(_subscribers):
        _put_bounded(q, event)


def broadcast_world_changed() -> None:
    """Push the WORLD_CHANGED control signal to every live subscriber so each
    WS connection re-snapshots against the now-live world. Called by the
    in-process world hot-swap AFTER the live DB has been swapped and reopened.
    Sync; a no-op when there are no subscribers. Routed through the bounded
    ring like every event, but _put_bounded guarantees the control signal
    itself is never the item dropped."""
    for q in list(_subscribers):
        _put_bounded(q, WORLD_CHANGED)


def reset_subscribers() -> None:
    """Test helper: drop all subscribers and the drop counter. Not for
    production paths."""
    global _dropped_total
    _subscribers.clear()
    _dropped_total = 0


def subscriber_count() -> int:
    """Number of live WS subscribers. Read by daydream.drift to choose
    its idle vs busy cadence."""
    return len(_subscribers)
