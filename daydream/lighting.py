"""Lighting: dark rooms, light sources, and the reduced dark scope (Zork
turn, SPEC 2026-07-02 criterion 6).

A room is dark when it authors `properties.dark: true`. Darkness is beaten
by any LIT light source in reach: a thing with `light: true` (can emit) AND
`lit: true` (currently on), sitting in the room, inside a see-through
container in the room, or carried by any toon present (one container level
deep — a lamp sealed inside a closed box lights nothing).

While a room is unlit: its description, scene panels, and art are veiled
behind the world's authored darkness text (`config.darkness.text`), and the
actor's scope shrinks to self + room + own inventory (objects.in_scope
consults room_lit). The seeded movement hazard lives in daydream.clock; the
authored death policy in the kill_actor effect."""

from __future__ import annotations

from daydream import objects, worldstate

DEFAULT_DARKNESS_TEXT = "It is pitch black."


def is_lit_source(o: objects.Object) -> bool:
    return (
        o.kind == "thing"
        and bool(o.properties.get("light"))
        and bool(o.properties.get("lit"))
    )


def room_lit(room_id: str | None) -> bool:
    """True unless the room is authored dark AND no lit source is in reach.
    Unknown/None rooms count as lit (never veil the world by accident)."""
    if not room_id:
        return True
    room = objects.get(room_id)
    if room is None or not room.properties.get("dark"):
        return True
    for o in objects.contents(room_id):
        if is_lit_source(o):
            return True
        if o.kind == "toon":
            for c in objects.contents(o.id, kind="thing"):
                if is_lit_source(c):
                    return True
        elif o.kind == "thing" and objects.contents_visible(o):
            for c in objects.contents(o.id, kind="thing"):
                if is_lit_source(c):
                    return True
    return False


def darkness_config(world_id: str) -> dict:
    cfg = worldstate.get(world_id, "config")
    d = cfg.get("darkness") if isinstance(cfg, dict) else None
    return d if isinstance(d, dict) else {}


def darkness_text(world_id: str) -> str:
    text = darkness_config(world_id).get("text")
    return text if isinstance(text, str) and text.strip() else DEFAULT_DARKNESS_TEXT
