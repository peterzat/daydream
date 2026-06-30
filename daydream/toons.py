"""Toon read helpers. Slot CRUD + kick-to-NPC promotion lands in v1."""

import json
from dataclasses import dataclass

from daydream import db


@dataclass(frozen=True)
class Toon:
    id: str
    world_id: str
    slot: int
    name: str
    seed: str
    appearance_seed: str
    current_room_id: str | None
    is_human_controlled: bool
    controller_session: str | None
    inventory: list
    mood: str
    kicked_at: str | None
    # Optional one-line greeting fired by the WS broadcast loop when
    # the controlled toon walks into this toon's room. NULL / empty /
    # whitespace-only = silent presence (no greeting). Added in
    # migration 007 alongside Rook's value; pre-007 rows load as None.
    presence_text: str | None = None

    @classmethod
    def from_row(cls, row) -> "Toon":
        # row is a sqlite3.Row; use a safe accessor so this code can
        # load from a legacy DB that hasn't applied migration 007 yet.
        try:
            presence_text = row["presence_text"]
        except (IndexError, KeyError):
            presence_text = None
        return cls(
            id=row["id"],
            world_id=row["world_id"],
            slot=row["slot"],
            name=row["name"],
            seed=row["seed"],
            appearance_seed=row["appearance_seed"],
            current_room_id=row["current_room_id"],
            is_human_controlled=bool(row["is_human_controlled"]),
            controller_session=row["controller_session"],
            inventory=json.loads(row["inventory_json"]),
            mood=row["mood"],
            kicked_at=row["kicked_at"],
            presence_text=presence_text,
        )


def get_toon(toon_id: str) -> Toon | None:
    row = db.get_conn().execute("SELECT * FROM toons WHERE id = ?", (toon_id,)).fetchone()
    return Toon.from_row(row) if row else None


def get_toons_in_room(room_id: str) -> list[Toon]:
    rows = (
        db.get_conn()
        .execute(
            "SELECT * FROM toons WHERE current_room_id = ? AND kicked_at IS NULL ORDER BY slot",
            (room_id,),
        )
        .fetchall()
    )
    return [Toon.from_row(r) for r in rows]


def find_toon_in_room_by_name(room_id: str, name: str) -> Toon | None:
    """Case-insensitive exact-name match within a room. Mirrors
    items.find_item_in_room_by_name so the examine core skill can try
    both lookups with the same shape. Kicked toons are excluded (they
    have been promoted to NPC-carrier-sentinel status but their
    current_room_id may still be set; kicked_at IS NOT NULL filters
    them out in get_toons_in_room)."""
    needle = name.strip().lower()
    if not needle:
        return None
    for t in get_toons_in_room(room_id):
        if t.name.lower() == needle:
            return t
    return None


def set_current_room(toon_id: str, room_id: str) -> None:
    """Move a toon into `room_id`. No FK enforcement beyond SQLite's
    default (REFERENCES rooms(id)); if `room_id` doesn't exist the
    UPDATE fails loud with IntegrityError, which is what we want —
    a caller passing an unknown room is a programming bug, not a
    runtime condition. Callers that parse user input (go skill)
    validate the direction against the source room's exits_json
    before calling this."""
    db.get_conn().execute(
        "UPDATE toons SET current_room_id = ? WHERE id = ?",
        (room_id, toon_id),
    )


def set_mood(toon_id: str, mood: str) -> None:
    """Update a toon's mood. Parameterized UPDATE; an unknown
    `toon_id` matches zero rows and is a no-op (no exception). The
    `mood` column has no FK or check-constraint, so any string is
    persisted as-is. Currently used by the drift loop's
    mood-affecting branch (`daydream/drift.py`) and by the
    `set_mood` data-skill effect handler (`daydream/skills/effects.py`)."""
    db.get_conn().execute(
        "UPDATE toons SET mood = ? WHERE id = ?",
        (mood, toon_id),
    )


# ---- slot-picker helpers (toon-slot-management spec, 2026-05-07) -------
#
# The slot system is for HUMAN-controllable toons in slots 1-5 only.
# Hand-authored NPCs in slots 100+ (Rook, Iris) are excluded from
# every slot-picker query so they never appear in the UI's slot list
# nor get accidentally claimed/kicked by the API.

HUMAN_SLOT_RANGE = range(1, 6)  # slots 1..5 inclusive
DEFAULT_HUMAN_WORLD_ID = "w-bunny"
DEFAULT_HUMAN_ROOM_ID = "r-meadow"


def get_toon_by_session(session_id: str) -> Toon | None:
    """Return the toon currently controlled by the given session, or
    None if no slot is claimed. A toon is 'controlled' when its
    controller_session matches AND kicked_at IS NULL AND
    is_human_controlled = 1. An empty / falsy session_id returns
    None (the caller treats this as 'no claim, fall back to
    legacy default')."""
    if not session_id:
        return None
    row = (
        db.get_conn()
        .execute(
            "SELECT * FROM toons "
            "WHERE controller_session = ? "
            "AND kicked_at IS NULL "
            "AND is_human_controlled = 1 "
            "LIMIT 1",
            (session_id,),
        )
        .fetchone()
    )
    return Toon.from_row(row) if row else None


def get_human_slots(session_id: str | None = None) -> list[dict]:
    """Return a list of 5 slot descriptors for slots 1..5. Each entry is
    `{"slot": N, "toon": <toon-dict>|None}`. The toon-dict includes
    `claimed_by_me` derived against `session_id` (False when session_id
    is None or doesn't match). Slot 100+ NPCs are excluded.

    Slots are listed in order 1..5; an empty slot returns
    `{"slot": N, "toon": None}`. When multiple rows share a slot due to
    a kicked-then-recreated history (shouldn't happen at v1 since create
    is gated on slot vacancy, but defense-in-depth), the most-recently
    created row wins."""
    rows = (
        db.get_conn()
        .execute(
            "SELECT * FROM toons "
            "WHERE slot BETWEEN 1 AND 5 "
            "AND world_id = ? "
            "ORDER BY slot, id",
            (DEFAULT_HUMAN_WORLD_ID,),
        )
        .fetchall()
    )
    by_slot: dict[int, Toon] = {}
    for row in rows:
        t = Toon.from_row(row)
        # Keep first-seen per slot — rows are ORDER BY slot, id so this
        # is deterministic. v1 invariant: at most one row per slot.
        by_slot.setdefault(t.slot, t)
    out: list[dict] = []
    for n in HUMAN_SLOT_RANGE:
        t = by_slot.get(n)
        if t is None:
            out.append({"slot": n, "toon": None})
            continue
        out.append({
            "slot": n,
            "toon": {
                "id": t.id,
                "name": t.name,
                "appearance_seed": t.appearance_seed,
                "current_room_id": t.current_room_id,
                "is_human_controlled": t.is_human_controlled,
                "kicked_at": t.kicked_at,
                "mood": t.mood,
                "claimed_by_me": (
                    bool(session_id)
                    and t.controller_session == session_id
                    and t.kicked_at is None
                    and t.is_human_controlled
                ),
            },
        })
    return out


def _slot_occupied(slot: int) -> Toon | None:
    """Return the toon (if any) currently in `slot` for the default
    world. Returns None for empty slots. Used by the create / claim /
    kick endpoints to make their precondition checks against the same
    slice the listing uses."""
    row = (
        db.get_conn()
        .execute(
            "SELECT * FROM toons "
            "WHERE slot = ? AND world_id = ? "
            "ORDER BY id LIMIT 1",
            (slot, DEFAULT_HUMAN_WORLD_ID),
        )
        .fetchone()
    )
    return Toon.from_row(row) if row else None


def create_toon_in_slot(
    slot: int, name: str, appearance_seed: str, session_id: str
) -> Toon | None:
    """Create a new human-controlled toon in `slot` claimed by
    `session_id`. Returns the new Toon, or None if the slot is already
    occupied (precondition gate; caller turns this into 409). Toon id
    is `t-slot{N}-<short-uuid>` for stability + uniqueness; the row's
    starting state mirrors the v0 Wren seed (empty inventory, mood
    'curious', current_room_id 'r-meadow'). Caller is responsible for
    range-checking `slot` against HUMAN_SLOT_RANGE before calling."""
    import uuid as _uuid

    if _slot_occupied(slot) is not None:
        return None
    from daydream import rooms

    # Spawn in the world's starting room (resolves to a room that actually
    # exists -- important for `world load`ed worlds, which have no r-meadow).
    spawn = rooms.starting_room_id(DEFAULT_HUMAN_WORLD_ID) or DEFAULT_HUMAN_ROOM_ID
    toon_id = f"t-slot{slot}-{_uuid.uuid4().hex[:8]}"
    db.get_conn().execute(
        "INSERT INTO toons "
        "(id, world_id, slot, name, seed, appearance_seed, current_room_id, "
        " is_human_controlled, controller_session, inventory_json, mood, kicked_at) "
        "VALUES (?, ?, ?, ?, '', ?, ?, 1, ?, '[]', 'curious', NULL)",
        (
            toon_id,
            DEFAULT_HUMAN_WORLD_ID,
            slot,
            name,
            appearance_seed,
            spawn,
            session_id,
        ),
    )
    return get_toon(toon_id)


def claim_slot(slot: int, session_id: str) -> tuple[Toon | None, str | None]:
    """Adopt a kicked-NPC toon as the human player. Returns
    `(toon, None)` on success, `(None, reason)` on failure where
    reason is one of: 'empty' (no toon in slot), 'controlled'
    (toon is currently human-controlled and not kicked).

    Atomicity: SELECT-then-UPDATE under SQLite's single-writer
    semantics is fine for v1. Two simultaneous claims hit the same
    underlying file lock; one succeeds first, the second sees the
    new controller_session and returns 'controlled'."""
    t = _slot_occupied(slot)
    if t is None:
        return (None, "empty")
    if t.is_human_controlled and t.kicked_at is None:
        return (None, "controlled")
    from daydream import rooms

    # Wake in the world's starting room (you "wake up" there after any rest),
    # not wherever the toon happened to rest.
    spawn = rooms.starting_room_id(t.world_id) or t.current_room_id
    db.get_conn().execute(
        "UPDATE toons SET controller_session = ?, "
        "is_human_controlled = 1, kicked_at = NULL, current_room_id = ? "
        "WHERE id = ?",
        (session_id, spawn, t.id),
    )
    return (get_toon(t.id), None)


def kick_slot(slot: int) -> Toon | None:
    """Release `slot` to a non-drifting NPC. Sets
    controller_session=NULL, is_human_controlled=0, kicked_at=<UTC ISO>.
    The toon stays in its current_room_id carrying inventory_json,
    mood, and any accrued memories. Returns the kicked Toon, or None
    if the slot is empty.

    No per-session ownership check at v1 (friend-scope; any
    authenticated session can kick any slot). v2 multi-user-shared-world
    will tighten this once the threat model lands."""
    t = _slot_occupied(slot)
    if t is None:
        return None
    db.get_conn().execute(
        "UPDATE toons SET controller_session = NULL, "
        "is_human_controlled = 0, "
        "kicked_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
        "WHERE id = ?",
        (t.id,),
    )
    return get_toon(t.id)


def release_session_toon(session_id: str) -> Toon | None:
    """Rest (kick) the toon currently controlled by `session_id`, if any.
    'Leave the dream' calls this so the session releases its toon back to a
    claimable resting state. Returns the released toon, or None when the
    session controlled none."""
    t = get_toon_by_session(session_id)
    if t is None:
        return None
    return kick_slot(t.slot)


def delete_slot(slot: int) -> Toon | None:
    """Permanently delete the human toon in `slot`, freeing it. Returns the
    deleted toon, or None if the slot is empty. Unlike kick (which rests the
    toon, keeping its row), this removes the row and its dependent rows so the
    slot reads empty afterward: items it carries (items.toon_id FKs toons(id),
    so they would otherwise block the delete) and its per-NPC memories. The
    toon's events stay as append-only history (events.actor_id is an un-FK'd
    tag that must outlive the row)."""
    t = _slot_occupied(slot)
    if t is None:
        return None
    conn = db.get_conn()
    conn.execute("DELETE FROM items WHERE toon_id = ?", (t.id,))
    conn.execute("DELETE FROM memories WHERE npc_id = ?", (t.id,))
    conn.execute("DELETE FROM toons WHERE id = ?", (t.id,))
    return t
