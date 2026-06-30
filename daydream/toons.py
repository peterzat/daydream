"""Toon read + write helpers: a thin typed view over the unified `objects`
table (`daydream.objects`). A toon is an object with `kind='toon'`. Its
auth/slot fields (slot, controller_session, is_human_controlled, kicked_at)
are promoted columns; seed / appearance_seed / mood / presence_text live in
the object's `properties` bag; its current room is the object's `location_id`;
its inventory is the things located on it."""

import uuid
from dataclasses import dataclass

from daydream import db, objects


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
    # One-line greeting fired by the WS broadcast loop when the controlled
    # toon walks into this toon's room. NULL / empty / whitespace = silent.
    presence_text: str | None = None

    @classmethod
    def from_object(cls, obj: "objects.Object", inventory: list | None = None) -> "Toon":
        p = obj.properties
        return cls(
            id=obj.id,
            world_id=obj.world_id,
            slot=obj.slot,
            name=obj.name,
            seed=p.get("seed", ""),
            appearance_seed=p.get("appearance_seed", ""),
            current_room_id=obj.location_id,
            is_human_controlled=obj.is_human_controlled,
            controller_session=obj.controller_session,
            inventory=inventory if inventory is not None else [],
            mood=p.get("mood", "curious"),
            kicked_at=obj.kicked_at,
            presence_text=p.get("presence_text"),
        )


def _toon(obj: "objects.Object | None") -> Toon | None:
    """Build a Toon (with its inventory filled) from an object, or None."""
    if obj is None or obj.kind != "toon":
        return None
    return Toon.from_object(obj, inventory=objects.content_ids(obj.id, "thing"))


def _query(where: str, params: tuple) -> list[Toon]:
    rows = db.get_conn().execute(
        f"SELECT * FROM objects WHERE kind = 'toon' AND {where}", params
    ).fetchall()
    return [_toon(objects.Object.from_row(r)) for r in rows]  # type: ignore[misc]


def get_toon(toon_id: str) -> Toon | None:
    return _toon(objects.get(toon_id))


def get_toons_in_room(room_id: str) -> list[Toon]:
    return _query(
        "location_id = ? AND kicked_at IS NULL ORDER BY slot", (room_id,)
    )


def find_toon_in_room_by_name(room_id: str, name: str) -> Toon | None:
    """Case-insensitive exact-name match within a room. Kicked toons are
    excluded (mirrors `get_toons_in_room`)."""
    needle = name.strip().lower()
    if not needle:
        return None
    for t in get_toons_in_room(room_id):
        if t.name.lower() == needle:
            return t
    return None


def get_npcs() -> list[Toon]:
    """All NPCs (non-human-controlled, not kicked), ordered by slot. The drift
    loop's source of truth for who can speak."""
    return _query(
        "is_human_controlled = 0 AND kicked_at IS NULL ORDER BY slot", ()
    )


def set_current_room(toon_id: str, room_id: str) -> None:
    """Move a toon into `room_id` (updates the object's location_id)."""
    objects.move(toon_id, room_id)


def set_mood(toon_id: str, mood: str) -> None:
    """Update a toon's mood (a key in its properties bag). An unknown toon_id
    is a no-op (set_property returns False)."""
    objects.set_property(toon_id, "mood", mood)


# ---- slot-picker helpers ----------------------------------------------
#
# The slot system is for HUMAN-controllable toons in slots 1-5 only.
# Hand-authored NPCs in slots 100+ are excluded from every slot-picker query
# so they never appear in the UI's slot list nor get claimed/kicked.

HUMAN_SLOT_RANGE = range(1, 6)  # slots 1..5 inclusive
DEFAULT_HUMAN_WORLD_ID = "w-bunny"
DEFAULT_HUMAN_ROOM_ID = "r-meadow"


def get_toon_by_session(session_id: str) -> Toon | None:
    """The toon currently controlled by `session_id` (controller match AND not
    kicked AND human-controlled), or None. Empty session returns None."""
    if not session_id:
        return None
    rows = _query(
        "controller_session = ? AND kicked_at IS NULL AND is_human_controlled = 1 "
        "LIMIT 1",
        (session_id,),
    )
    return rows[0] if rows else None


def get_human_slots(session_id: str | None = None) -> list[dict]:
    """Return 5 slot descriptors for slots 1..5. Each entry is
    `{"slot": N, "toon": <toon-dict>|None}` with `claimed_by_me` derived
    against `session_id`. Slot 100+ NPCs are excluded."""
    found = _query(
        "slot BETWEEN 1 AND 5 AND world_id = ? ORDER BY slot, id",
        (DEFAULT_HUMAN_WORLD_ID,),
    )
    by_slot: dict[int, Toon] = {}
    for t in found:
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
    """The toon (if any) currently in `slot` for the default world."""
    rows = _query(
        "slot = ? AND world_id = ? ORDER BY id LIMIT 1",
        (slot, DEFAULT_HUMAN_WORLD_ID),
    )
    return rows[0] if rows else None


def create_toon_in_slot(
    slot: int, name: str, appearance_seed: str, session_id: str
) -> Toon | None:
    """Create a new human-controlled toon in `slot` claimed by `session_id`.
    Returns the new Toon, or None if the slot is already occupied. Spawns in
    the world's starting room. Caller range-checks `slot` first."""
    if _slot_occupied(slot) is not None:
        return None
    from daydream import rooms

    spawn = rooms.starting_room_id(DEFAULT_HUMAN_WORLD_ID) or DEFAULT_HUMAN_ROOM_ID
    toon_id = f"t-slot{slot}-{uuid.uuid4().hex[:8]}"
    db.get_conn().execute(
        "INSERT INTO objects (id, world_id, kind, name, aliases_json, "
        "location_id, prototype_id, properties_json, slot, controller_session, "
        "is_human_controlled, kicked_at) "
        "VALUES (?, ?, 'toon', ?, '[]', ?, ?, ?, ?, ?, 1, NULL)",
        (
            toon_id,
            DEFAULT_HUMAN_WORLD_ID,
            name,
            spawn,
            objects.PROTO_NPC,
            _toon_properties(appearance_seed=appearance_seed),
            slot,
            session_id,
        ),
    )
    return get_toon(toon_id)


def _toon_properties(*, appearance_seed: str, mood: str = "curious") -> str:
    import json

    return json.dumps(
        {"seed": "", "appearance_seed": appearance_seed, "mood": mood,
         "presence_text": None}
    )


def claim_slot(
    slot: int, session_id: str, *, can_take_over=None
) -> tuple[Toon | None, str | None]:
    """Adopt a kicked-NPC toon as the human player. Returns `(toon, None)` on
    success, `(None, reason)` on failure where reason is 'empty' or
    'controlled'. Wakes the toon in the world's starting room.

    `can_take_over(controller_session) -> bool` (optional): when the slot is
    controlled by ANOTHER session, adopt it anyway if this returns True -- used
    to reclaim a toon whose controlling session has no live WS connection (an
    abandoned claim). Default refuses any controlled toon."""
    t = _slot_occupied(slot)
    if t is None:
        return (None, "empty")
    if t.is_human_controlled and t.kicked_at is None:
        controller = t.controller_session
        takeover = bool(can_take_over and controller and can_take_over(controller))
        if not takeover:
            return (None, "controlled")
    from daydream import rooms

    spawn = rooms.starting_room_id(t.world_id) or t.current_room_id
    db.get_conn().execute(
        "UPDATE objects SET controller_session = ?, is_human_controlled = 1, "
        "kicked_at = NULL, location_id = ? WHERE id = ?",
        (session_id, spawn, t.id),
    )
    return (get_toon(t.id), None)


def kick_slot(slot: int) -> Toon | None:
    """Release `slot` to a non-drifting NPC (controller_session NULL,
    is_human_controlled 0, kicked_at <UTC ISO>). The toon keeps its room,
    inventory, mood, and memories. Returns the kicked Toon, or None if empty."""
    t = _slot_occupied(slot)
    if t is None:
        return None
    db.get_conn().execute(
        "UPDATE objects SET controller_session = NULL, is_human_controlled = 0, "
        "kicked_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
        (t.id,),
    )
    return get_toon(t.id)


def release_session_toon(session_id: str) -> Toon | None:
    """Rest (kick) the toon controlled by `session_id`, if any. 'Leave the
    dream' calls this. Returns the released toon, or None."""
    t = get_toon_by_session(session_id)
    if t is None:
        return None
    return kick_slot(t.slot)


def delete_slot(slot: int) -> Toon | None:
    """Permanently delete the human toon in `slot`, freeing it. Removes the
    toon object plus its dependent rows (things it carries, its memories);
    its events stay as append-only history. Returns the deleted toon, or None
    if the slot is empty."""
    t = _slot_occupied(slot)
    if t is None:
        return None
    conn = db.get_conn()
    # Carried things FK the toon via location_id; remove them first.
    conn.execute(
        "DELETE FROM objects WHERE location_id = ? AND kind = 'thing'", (t.id,)
    )
    conn.execute("DELETE FROM memories WHERE npc_id = ?", (t.id,))
    objects.delete(t.id)
    return t
