"""Room read helpers: a thin typed view over the unified `objects` table
(`daydream.objects`). A room is an object with `kind='room'`; its slug, title,
seed, cached description, and exits live in the object's `properties` bag."""

from dataclasses import dataclass

from daydream import db, objects


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
    def from_object(cls, obj: "objects.Object") -> "Room":
        p = obj.properties
        exits = p.get("exits")
        return cls(
            id=obj.id,
            world_id=obj.world_id,
            slug=p.get("slug", ""),
            title=p.get("title", obj.name),
            seed=p.get("seed", ""),
            description_cached=p.get("description_cached"),
            exits=exits if isinstance(exits, dict) else {},
            parent_id=p.get("parent_id"),
        )


def get_room(room_id: str) -> Room | None:
    obj = objects.get(room_id)
    return Room.from_object(obj) if obj is not None and obj.kind == "room" else None


def get_room_by_slug(world_id: str, slug: str) -> Room | None:
    obj = objects.by_slug(world_id, slug, kind="room")
    return Room.from_object(obj) if obj is not None else None


def starting_room_id(world_id: str) -> str | None:
    """The world's designated 'starting room' -- where a toon wakes after a
    rest and where a new toon spawns (migration 010, `worlds.starting_room_id`).
    Falls back to the world's first room object (by id) when the column is
    unset or points at a since-removed room, so every world resolves to SOME
    room. Returns None only for a world with no rooms at all."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT starting_room_id FROM worlds WHERE id = ?", (world_id,)
    ).fetchone()
    candidate = row["starting_room_id"] if row else None
    if candidate is not None and conn.execute(
        "SELECT 1 FROM objects WHERE id = ? AND world_id = ? AND kind = 'room'",
        (candidate, world_id),
    ).fetchone():
        return candidate
    row = conn.execute(
        "SELECT id FROM objects WHERE world_id = ? AND kind = 'room' ORDER BY id LIMIT 1",
        (world_id,),
    ).fetchone()
    return row["id"] if row else None
