"""Item (thing) read helpers: a thin typed view over the unified `objects`
table (`daydream.objects`). An item is an object with `kind='thing'`; its seed,
the `is_unique` flag, and any kind-specific properties (e.g. `lit`) live in the
object's `properties` bag, and its containment (room on the ground, or toon in
inventory) is the object's `location_id`."""

from dataclasses import dataclass

from daydream import objects


@dataclass(frozen=True)
class Item:
    id: str
    world_id: str
    name: str
    seed: str
    location_id: str | None
    room_id: str | None
    toon_id: str | None
    properties: dict
    is_unique: bool

    @classmethod
    def from_object(cls, obj: "objects.Object", parent_kind: str | None) -> "Item":
        """Build an Item from a thing object. `parent_kind` is the kind of the
        object's container ('room' or 'toon'), used to split `location_id`
        back into the legacy `room_id` / `toon_id` view fields. Pass None when
        the container kind is unknown / irrelevant."""
        p = obj.properties
        room_id = obj.location_id if parent_kind == "room" else None
        toon_id = obj.location_id if parent_kind == "toon" else None
        return cls(
            id=obj.id,
            world_id=obj.world_id,
            name=obj.name,
            seed=p.get("seed", ""),
            location_id=obj.location_id,
            room_id=room_id,
            toon_id=toon_id,
            properties={k: v for k, v in p.items() if k not in ("seed", "is_unique")},
            is_unique=bool(p.get("is_unique", 0)),
        )


def get_items_in_room(room_id: str) -> list[Item]:
    """Things sitting on the ground in `room_id` (location = the room),
    excluding carried inventory. Ordered by name."""
    return [
        Item.from_object(o, parent_kind="room")
        for o in objects.contents(room_id, kind="thing")
    ]


def find_item_in_room_by_name(room_id: str, name: str) -> Item | None:
    """Case-insensitive name match, trimmed, against things on the ground in
    `room_id`. Exact-name only (matching aliases is the in-scope resolver's
    job; this keeps the legacy core-skill lookup shape)."""
    needle = name.strip().lower()
    if not needle:
        return None
    for it in get_items_in_room(room_id):
        if it.name.lower() == needle:
            return it
    return None
