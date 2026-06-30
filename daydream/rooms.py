"""Room read helpers. Mutations land in v1 with multi-room navigation."""

import json
from dataclasses import dataclass

from daydream import db


@dataclass(frozen=True)
class Room:
    id: str
    world_id: str
    slug: str
    title: str
    seed: str
    description_cached: str | None
    exits: dict
    parent_id: str | None

    @classmethod
    def from_row(cls, row) -> "Room":
        return cls(
            id=row["id"],
            world_id=row["world_id"],
            slug=row["slug"],
            title=row["title"],
            seed=row["seed"],
            description_cached=row["description_cached"],
            exits=json.loads(row["exits_json"]),
            parent_id=row["parent_id"],
        )


def get_room(room_id: str) -> Room | None:
    row = db.get_conn().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    return Room.from_row(row) if row else None


def get_room_by_slug(world_id: str, slug: str) -> Room | None:
    row = (
        db.get_conn()
        .execute("SELECT * FROM rooms WHERE world_id = ? AND slug = ?", (world_id, slug))
        .fetchone()
    )
    return Room.from_row(row) if row else None


def starting_room_id(world_id: str) -> str | None:
    """The world's designated 'starting room' -- where a toon wakes after a
    rest and where a new toon spawns (migration 010, `worlds.starting_room_id`).
    Falls back to the world's first room (by id) when the column is unset or
    points at a since-removed room, so every world resolves to SOME room.
    Returns None only for a world with no rooms at all."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT starting_room_id FROM worlds WHERE id = ?", (world_id,)
    ).fetchone()
    candidate = row["starting_room_id"] if row else None
    if candidate is not None and conn.execute(
        "SELECT 1 FROM rooms WHERE id = ? AND world_id = ?", (candidate, world_id)
    ).fetchone():
        return candidate
    row = conn.execute(
        "SELECT id FROM rooms WHERE world_id = ? ORDER BY id LIMIT 1", (world_id,)
    ).fetchone()
    return row["id"] if row else None
