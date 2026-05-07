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
