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

    @classmethod
    def from_row(cls, row) -> "Toon":
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
