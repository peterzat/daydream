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
