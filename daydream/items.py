"""Item read helpers. Pickup/drop/transfer lands with the take/drop skills in v1."""

import json
from dataclasses import dataclass

from daydream import db


@dataclass(frozen=True)
class Item:
    id: str
    world_id: str
    name: str
    seed: str
    room_id: str | None
    toon_id: str | None
    properties: dict
    is_unique: bool

    @classmethod
    def from_row(cls, row) -> "Item":
        return cls(
            id=row["id"],
            world_id=row["world_id"],
            name=row["name"],
            seed=row["seed"],
            room_id=row["room_id"],
            toon_id=row["toon_id"],
            properties=json.loads(row["properties_json"]),
            is_unique=bool(row["is_unique"]),
        )


def get_items_in_room(room_id: str) -> list[Item]:
    rows = (
        db.get_conn()
        .execute("SELECT * FROM items WHERE room_id = ? ORDER BY name", (room_id,))
        .fetchall()
    )
    return [Item.from_row(r) for r in rows]


def find_item_in_room_by_name(room_id: str, name: str) -> Item | None:
    """Case-insensitive name match, trimmed. v0's matching is exact-name only;
    fuzzy matching is a v1 polish item if it ever bites."""
    needle = name.strip().lower()
    if not needle:
        return None
    for it in get_items_in_room(room_id):
        if it.name.lower() == needle:
            return it
    return None
