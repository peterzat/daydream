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
from dataclasses import dataclass
from typing import Any

from daydream import db


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


def max_seq() -> int:
    conn = db.get_conn()
    row = conn.execute("SELECT MAX(seq) FROM events").fetchone()
    return row[0] or 0


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _subscribers:
        _subscribers.remove(q)


def _broadcast(event: Event) -> None:
    """Fan out an event to every live subscriber. Unbounded queues, so
    put_nowait never blocks; the slow-consumer escape hatch lands in v2
    once we have real CCU to worry about."""
    for q in list(_subscribers):
        q.put_nowait(event)


def broadcast_world_changed() -> None:
    """Push the WORLD_CHANGED control signal to every live subscriber so each
    WS connection re-snapshots against the now-live world. Called by the
    in-process world hot-swap AFTER the live DB has been swapped and reopened.
    Sync (put_nowait never blocks); a no-op when there are no subscribers."""
    for q in list(_subscribers):
        q.put_nowait(WORLD_CHANGED)


def reset_subscribers() -> None:
    """Test helper: drop all subscribers. Not for production paths."""
    _subscribers.clear()


def subscriber_count() -> int:
    """Number of live WS subscribers. Read by daydream.drift to choose
    its idle vs busy cadence."""
    return len(_subscribers)
