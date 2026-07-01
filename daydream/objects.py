"""Unified object access layer (MOO-style object model, migration 011).

One `objects` table holds rooms, toons, things, and prototypes, discriminated
by `kind`. This module is the single read/write surface over it: resolve an id
to an `Object`, list a container's contents, compute an actor's in-scope set,
move objects between containers, get/set properties, spawn new things, and
read a kind/prototype's verb set.

The kind-specific view modules (`daydream.rooms`, `daydream.toons`,
`daydream.items`) are thin typed wrappers over this layer; every other module
goes through one of those or through here. No code outside this module and the
three views issues raw SQL against `objects`.

Containment: a toon's `location_id` is its current room; a thing's is the room
it sits in OR the toon carrying it; a room's is NULL (top-level). Inheritance:
`prototype_id` points at a `kind='prototype'` row whose `properties.verbs` are
the default verb set for objects of that archetype.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from daydream import db

# Prototype ids are bare (single-world-per-DB at v0; every reference hardcodes
# w-bunny). Map an archetype name to its seeded prototype row.
PROTO_ROOM = "proto-room"
PROTO_NPC = "proto-npc"
PROTO_THING = "proto-thing"
PROTO_READABLE = "proto-readable"
# Immovable furniture (a town clock, a fixed case): examine only, no take/drop.
# Per-object `open`/`use` verbs are layered on by the author.
PROTO_FIXTURE = "proto-fixture"


@dataclass(frozen=True)
class Object:
    """One row of the `objects` table, with JSON columns parsed.

    `seed` and the kind-specific fields live in `properties`; the promoted
    columns (slot / controller_session / is_human_controlled / kicked_at) are
    surfaced as attributes for the toon auth/slot paths."""

    id: str
    world_id: str
    kind: str  # 'room' | 'toon' | 'thing' | 'prototype'
    name: str
    aliases: list[str]
    location_id: str | None
    prototype_id: str | None
    properties: dict
    slot: int | None = None
    controller_session: str | None = None
    is_human_controlled: bool = False
    kicked_at: str | None = None

    @property
    def seed(self) -> str:
        s = self.properties.get("seed")
        return s if isinstance(s, str) else ""

    @classmethod
    def from_row(cls, row) -> Object:
        return cls(
            id=row["id"],
            world_id=row["world_id"],
            kind=row["kind"],
            name=row["name"],
            aliases=_loads_list(row["aliases_json"]),
            location_id=row["location_id"],
            prototype_id=row["prototype_id"],
            properties=_loads_dict(row["properties_json"]),
            slot=row["slot"],
            controller_session=row["controller_session"],
            is_human_controlled=bool(row["is_human_controlled"]),
            kicked_at=row["kicked_at"],
        )


def _loads_dict(text: str | None) -> dict:
    try:
        v = json.loads(text or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return v if isinstance(v, dict) else {}


def _loads_list(text: str | None) -> list:
    try:
        v = json.loads(text or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return v if isinstance(v, list) else []


# ---- reads -------------------------------------------------------------


def get(object_id: str) -> Object | None:
    """Resolve any id to an Object, or None if absent."""
    row = db.get_conn().execute(
        "SELECT * FROM objects WHERE id = ?", (object_id,)
    ).fetchone()
    return Object.from_row(row) if row else None


def contents(container_id: str, kind: str | None = None) -> list[Object]:
    """Objects whose location is `container_id` (a room's contents, or a
    toon's inventory). Optionally filter to one kind. Ordered by name for
    determinism."""
    conn = db.get_conn()
    if kind is None:
        rows = conn.execute(
            "SELECT * FROM objects WHERE location_id = ? ORDER BY name",
            (container_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM objects WHERE location_id = ? AND kind = ? ORDER BY name",
            (container_id, kind),
        ).fetchall()
    return [Object.from_row(r) for r in rows]


def content_ids(container_id: str, kind: str | None = None) -> list[str]:
    """Just the ids of a container's contents (cheap; used to fill a toon's
    inventory without materializing every contained Object)."""
    conn = db.get_conn()
    if kind is None:
        rows = conn.execute(
            "SELECT id FROM objects WHERE location_id = ? ORDER BY name",
            (container_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id FROM objects WHERE location_id = ? AND kind = ? ORDER BY name",
            (container_id, kind),
        ).fetchall()
    return [r["id"] for r in rows]


def by_slug(world_id: str, slug: str, kind: str = "room") -> Object | None:
    """Find an object by its `properties.slug` within a world. Rooms carry a
    slug; this is the slug→room resolver the view layer needs."""
    row = db.get_conn().execute(
        "SELECT * FROM objects WHERE world_id = ? AND kind = ? "
        "AND json_extract(properties_json, '$.slug') = ?",
        (world_id, kind, slug),
    ).fetchone()
    return Object.from_row(row) if row else None


def in_scope(actor_id: str) -> list[Object]:
    """The objects an actor can currently refer to: the actor itself, its
    room, the room's contents (co-located toons + things on the ground), and
    the actor's own inventory. Deduplicated by id, prototypes excluded.

    This is the grounding set handed to the natural-language parser and the
    scope gate `execute_command` validates a target against."""
    actor = get(actor_id)
    if actor is None:
        return []
    seen: dict[str, Object] = {actor.id: actor}
    room_id = actor.location_id
    if room_id is not None:
        room = get(room_id)
        if room is not None and room.kind != "prototype":
            seen.setdefault(room.id, room)
        for o in contents(room_id):
            if o.kind != "prototype":
                seen.setdefault(o.id, o)
    for o in contents(actor_id):
        if o.kind != "prototype":
            seen.setdefault(o.id, o)
    return list(seen.values())


def find_in_scope_by_name(actor_id: str, name: str) -> Object | None:
    """Case-insensitive exact match of `name` against the name or any alias of
    an in-scope object. The actor itself is excluded (you don't `take` or
    `examine`-by-name yourself). Returns None on no match or ambiguity-free
    miss; the first match in scope order wins."""
    needle = name.strip().lower()
    if not needle:
        return None
    for o in in_scope(actor_id):
        if o.id == actor_id:
            continue
        names = [o.name.lower()] + [str(a).lower() for a in o.aliases]
        if needle in names:
            return o
    return None


def verbs_for(obj: Object) -> list[str]:
    """The verb set available on an object: its prototype's default verbs
    unioned with any per-object `properties.verbs`. Order preserved
    (prototype defaults first), deduplicated."""
    out: list[str] = []
    if obj.prototype_id is not None:
        proto = get(obj.prototype_id)
        if proto is not None:
            for v in proto.properties.get("verbs", []):
                if isinstance(v, str) and v not in out:
                    out.append(v)
    for v in obj.properties.get("verbs", []):
        if isinstance(v, str) and v not in out:
            out.append(v)
    return out


# ---- writes ------------------------------------------------------------


def move(object_id: str, dest_id: str | None) -> None:
    """Reparent an object: set its `location_id` to `dest_id` (or NULL to make
    it top-level). The single containment mutation; take/drop/go all funnel
    here via the move_object effect."""
    db.get_conn().execute(
        "UPDATE objects SET location_id = ? WHERE id = ?", (dest_id, object_id)
    )


def get_property(object_id: str, key: str, default=None):
    obj = get(object_id)
    if obj is None:
        return default
    return obj.properties.get(key, default)


def set_property(object_id: str, key: str, value) -> bool:
    """Set one key in an object's `properties_json` (read-modify-write).
    Returns False if the object does not exist. Used to cache examine text,
    set mood, mark `last_accessed_at`, etc."""
    obj = get(object_id)
    if obj is None:
        return False
    props = dict(obj.properties)
    props[key] = value
    db.get_conn().execute(
        "UPDATE objects SET properties_json = ? WHERE id = ?",
        (json.dumps(props), object_id),
    )
    return True


def spawn(
    world_id: str,
    kind: str,
    name: str,
    location_id: str | None,
    *,
    prototype_id: str | None = None,
    properties: dict | None = None,
    aliases: list[str] | None = None,
    object_id: str | None = None,
) -> Object:
    """Create a new object and return it. `object_id` defaults to a kind-tagged
    short-uuid id (`o-<8hex>` for things). The single creation path for
    runtime-spawned objects (generative `spawn_object` effect)."""
    if object_id is None:
        prefix = {"thing": "o", "toon": "t", "room": "r"}.get(kind, "o")
        object_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    db.get_conn().execute(
        "INSERT INTO objects (id, world_id, kind, name, aliases_json, "
        "location_id, prototype_id, properties_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            object_id,
            world_id,
            kind,
            name,
            json.dumps(aliases or []),
            location_id,
            prototype_id,
            json.dumps(properties or {}),
        ),
    )
    obj = get(object_id)
    assert obj is not None
    return obj


def delete(object_id: str) -> None:
    """Remove one object row. Caller is responsible for any dependent rows
    (memories, carried things) per its own integrity needs."""
    db.get_conn().execute("DELETE FROM objects WHERE id = ?", (object_id,))


def delete_world_objects(world_id: str) -> None:
    """Remove every object (rooms, toons, things, prototypes) for a world.
    Used by the admin world-delete cascade. Self-referential FKs (location_id,
    prototype_id) are satisfied because the whole world goes at once."""
    db.get_conn().execute("DELETE FROM objects WHERE world_id = ?", (world_id,))
