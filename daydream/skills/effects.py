"""World-mutation effect API: the allowlisted vocabulary through which ALL
runtime state change flows (engine verbs and LLM-driven dialogue alike).

A verb handler or a data skill's LLM response produces an `effects` list;
`dispatch_effects()` applies each one in order. Only effect kinds enumerated
in `ALLOWED_KINDS` execute. A caller may additionally pass a per-verb `allowed`
subset; a kind outside that subset is rejected exactly like an unknown kind
(dropped, a narrate fallback emitted, NO state mutation) — this is the per-verb
allowlist gate (SPEC 2026-06-30): a verb can only emit the effects it declares.

The vocabulary:
- `narrate`       — emit narration text.
- `set_property`  — set one key on an object's properties (cache examine text,
                    set mood, mark last_accessed_at, ...).
- `spawn_object`  — create one persistent clickable thing (generative objects).
- `move_object`   — reparent an object (take = into inventory; drop = to room).
- `spawn_room`    — create one persistent room (world growth; SPEC 2026-07-02).
- `link_exit`     — link two rooms with a bidirectional exit pair.
- `add_item` / `set_mood` — retained aliases over spawn_object / set_property
                    for the existing data-skill author files.

The world-shaping kinds (`spawn_room`, `link_exit`) are emittable ONLY by a
verb that declares them in its per-verb allowlist: a caller passing
`allowed=None` (the data-skill default) gets `DEFAULT_KINDS`, which excludes
them, so an NPC dialogue or standalone data skill attempting either is
rejected exactly like an unknown kind. `plant` is the sole consumer today.

Future-prepared (documented, not built): `destroy_object` — reserved for the
future clutter-GC / unmaking vocabulary.

The dispatcher stays closed to dynamic dispatch — there is no plugin mechanism,
by design. Out of scope (BACKLOG `skills-authoring-and-security`): strict
per-effect jsonschema validation, per-player rate limits, an `audit` table,
`bin/game world undo`."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from daydream import events, objects

logger = logging.getLogger(__name__)


ALLOWED_KINDS: frozenset[str] = frozenset({
    "narrate",
    "set_property",
    "spawn_object",
    "move_object",
    # World-shaping (SPEC 2026-07-02): explicit per-verb declaration only.
    "spawn_room",
    "link_exit",
    # Retained aliases for existing data-skill author files.
    "add_item",
    "set_mood",
})

# The kinds a caller gets when it passes no per-verb allowlist (allowed=None,
# the data-skill default). World-shaping kinds are deliberately absent: growing
# a room or linking an exit requires a verb that DECLARES the capability, so an
# NPC dialogue or a standalone data skill can never world-build by omission.
WORLD_SHAPING_KINDS: frozenset[str] = frozenset({"spawn_room", "link_exit"})
DEFAULT_KINDS: frozenset[str] = ALLOWED_KINDS - WORLD_SHAPING_KINDS


@dataclass(frozen=True)
class AppliedEffect:
    """Record of one dispatched effect: the kind we saw (even if
    unknown) and the Event that was emitted (or None if the effect
    was malformed in a way that produced no event at all). Tests
    assert against this structure so they can check both what
    happened and in what order without re-reading the event log."""

    kind: str
    event: events.Event | None


_FALLBACK_TEXT = "the dream won't hold that thought"


def _fallback_narrate(room_id: str, text: str = _FALLBACK_TEXT) -> events.Event:
    return events.append("system", None, "narrate", {"text": text}, room_id=room_id)


def dispatch_effects(
    effects_list: list,
    *,
    actor_id: str,
    room_id: str,
    world_id: str,
    allowed: frozenset[str] | None = None,
) -> list[AppliedEffect]:
    """Apply each effect in `effects_list` in order.

    `allowed`, when given, is the per-verb allowlist: a kind not in it is
    rejected exactly like an unknown kind (no mutation, narrate fallback), so
    a verb can only emit the effects it declares. None means DEFAULT_KINDS
    (the data-skill default) — the standard vocabulary WITHOUT the
    world-shaping kinds, which are opt-in-only by construction.

    Malformed entries (non-dicts) get a narrate fallback and are logged;
    unknown / disallowed kinds likewise get a fallback. Allowed kinds with
    invalid shapes (e.g. missing required fields) return `event=None` — tests
    assert nothing was mutated. Handler exceptions are caught and converted to
    a soft fallback so one bad effect doesn't poison the whole batch."""
    applied: list[AppliedEffect] = []
    for eff in effects_list:
        if not isinstance(eff, dict):
            logger.warning("dropping malformed effect entry: %r", eff)
            applied.append(AppliedEffect("(malformed)", _fallback_narrate(room_id)))
            continue
        kind = eff.get("kind")
        effective_allowed = allowed if allowed is not None else DEFAULT_KINDS
        if (
            not isinstance(kind, str)
            or kind not in ALLOWED_KINDS
            or kind not in effective_allowed
        ):
            logger.warning("dropping unknown/disallowed effect kind: %r", kind)
            applied.append(AppliedEffect(str(kind), _fallback_narrate(room_id)))
            continue
        handler = _HANDLERS[kind]
        try:
            event = handler(eff, actor_id=actor_id, room_id=room_id, world_id=world_id)
        except Exception as e:
            logger.exception("effect %r failed during dispatch: %s", kind, e)
            event = _fallback_narrate(room_id, "the dream wavers and the moment passes")
        applied.append(AppliedEffect(kind, event))
    return applied


def _apply_narrate(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    text = eff.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return events.append(
        "system", None, "narrate", {"text": text.strip()}, room_id=room_id
    )


def _apply_add_item(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    name = eff.get("name")
    seed = eff.get("seed", "")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(seed, str):
        return None
    thing = objects.spawn(
        world_id,
        "thing",
        name.strip(),
        location_id=room_id,
        prototype_id=objects.PROTO_THING,
        properties={"seed": seed.strip(), "is_unique": 0},
    )
    return events.append(
        "system",
        None,
        "item_added",
        {"item_id": thing.id, "name": thing.name, "room_id": room_id},
        room_id=room_id,
    )


def _apply_set_mood(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    # Default the target toon to the actor so a skill can update the
    # player's own mood without the LLM having to know the toon id.
    toon_id = eff.get("toon_id", actor_id)
    mood = eff.get("mood")
    if not isinstance(toon_id, str) or not isinstance(mood, str):
        return None
    if not mood.strip():
        return None
    target = objects.get(toon_id)
    if target is None or target.kind != "toon":
        return None
    objects.set_property(toon_id, "mood", mood.strip())
    return events.append(
        "system",
        None,
        "mood_set",
        {"toon_id": toon_id, "mood": mood.strip()},
        room_id=room_id,
    )


def _apply_set_property(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Set one key on an object's properties. Defaults the target to the actor
    so a verb can update the player without naming an id. `value` is required
    (any JSON value, including false / 0 / "")."""
    target_id = eff.get("target_id", actor_id)
    key = eff.get("key")
    if not isinstance(target_id, str) or not isinstance(key, str) or not key.strip():
        return None
    if "value" not in eff:
        return None
    if objects.get(target_id) is None:
        return None
    objects.set_property(target_id, key.strip(), eff["value"])
    return events.append(
        "system", None, "property_set",
        {"target_id": target_id, "key": key.strip()}, room_id=room_id,
    )


def _apply_spawn_object(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Create one persistent clickable thing. Defaults its location to the
    current room; pass `location_id` to drop it on an NPC instead. `readable`
    selects the readable prototype (examine/take/drop). An optional `verbs` list
    is written to the spawned object's `properties.verbs`, so a spawn can grant
    per-object affordances beyond its prototype (a given case-key becomes
    `use`-able). An optional `properties` dict passes through as the base of
    the spawned object's properties (an authored payload can carry state /
    growth blocks); the computed keys (seed, is_unique, generated_by, verbs)
    win on collision. Provenance fields (`generated_by`) ride along in
    properties for the future clutter-GC pass."""
    name = eff.get("name")
    seed = eff.get("seed", "")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(seed, str):
        return None
    location_id = eff.get("location_id", room_id)
    if not isinstance(location_id, str) or objects.get(location_id) is None:
        return None
    gen_by = eff.get("generated_by")
    # Idempotency: a generative spawn (one carrying provenance) does not
    # duplicate — re-running the verb that emits it finds the existing object
    # in the same location by name and skips. Narration is never auto-scanned;
    # an object becomes real only on an explicit spawn_object, exactly once.
    if isinstance(gen_by, str) and gen_by.strip():
        for existing in objects.contents(location_id):
            if existing.name == name.strip() and existing.properties.get("generated_by"):
                return None
    proto = objects.PROTO_READABLE if eff.get("readable") else objects.PROTO_THING
    aliases = eff.get("aliases") if isinstance(eff.get("aliases"), list) else []
    # Optional authored-properties passthrough; computed keys win on collision.
    extra = eff.get("properties")
    props: dict = dict(extra) if isinstance(extra, dict) else {}
    props["seed"] = seed.strip()
    props["is_unique"] = 1
    if isinstance(gen_by, str) and gen_by.strip():
        props["generated_by"] = gen_by.strip()
    # Per-object verb additions (e.g. a given key becomes use-able). Only
    # non-empty strings are kept; an absent / malformed list is simply ignored.
    verbs = eff.get("verbs")
    if isinstance(verbs, list):
        cleaned = [v for v in verbs if isinstance(v, str) and v.strip()]
        if cleaned:
            props["verbs"] = cleaned
    thing = objects.spawn(
        world_id, "thing", name.strip(), location_id,
        prototype_id=proto, properties=props, aliases=aliases,
    )
    return events.append(
        "system", None, "object_spawned",
        {"object_id": thing.id, "name": thing.name, "location_id": location_id},
        room_id=room_id,
    )


def _apply_move_object(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Reparent an object (take = into the actor's inventory; drop = to the
    room). Both ends must exist; an unknown object or destination is a no-op."""
    object_id = eff.get("object_id")
    dest_id = eff.get("dest_id")
    if not isinstance(object_id, str) or not isinstance(dest_id, str):
        return None
    if objects.get(object_id) is None or objects.get(dest_id) is None:
        return None
    objects.move(object_id, dest_id)
    return events.append(
        "system", None, "object_moved",
        {"object_id": object_id, "dest_id": dest_id}, room_id=room_id,
    )


def _apply_spawn_room(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Create one persistent room (world growth, SPEC 2026-07-02). The effect's
    `room_id` is the NEW room's id (caller-generated, `r-<slug>`); the handler's
    `room_id` kwarg is the acting room where the event lands. Writes the exact
    property shape `rooms.Room.from_object` reads (slug / title / seed /
    description_cached / exits / parent_id), so a grown room is first-class to
    every existing reader with zero changes. An optional `properties` dict
    passes through as the base (provenance: `generated_by`, `grown`); the
    computed room keys win on collision. Rejects (event=None, NO mutation) on a
    missing/duplicate id, a duplicate slug, or a missing title/seed."""
    new_room_id = eff.get("room_id")
    slug = eff.get("slug")
    title = eff.get("title")
    seed = eff.get("seed")
    for v in (new_room_id, slug, title, seed):
        if not isinstance(v, str) or not v.strip():
            return None
    new_room_id, slug, title, seed = (
        new_room_id.strip(), slug.strip(), title.strip(), seed.strip()
    )
    if objects.get(new_room_id) is not None:
        return None  # id collision: never overwrite an existing object
    if objects.by_slug(world_id, slug) is not None:
        return None  # slug collision: slugs are the world's room namespace
    description = eff.get("description")
    extra = eff.get("properties")
    props: dict = dict(extra) if isinstance(extra, dict) else {}
    props.update({
        "slug": slug,
        "title": title,
        "seed": seed,
        "description_cached": description.strip()
        if isinstance(description, str) and description.strip() else None,
        "exits": {},
        "parent_id": None,
    })
    room = objects.spawn(
        world_id, "room", title, location_id=None,
        prototype_id=objects.PROTO_ROOM, properties=props, object_id=new_room_id,
    )
    return events.append(
        "system", None, "room_grown",
        {"room_id": room.id, "slug": slug, "title": title}, room_id=room_id,
    )


# The exits map is directional; a link writes one direction on each side.
def _apply_link_exit(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Link two rooms with a bidirectional exit pair: `direction` on the `from`
    room and `reverse_direction` on the `to` room. Validates EVERYTHING before
    writing EITHER side — both rooms exist and are rooms, both direction slots
    are free, the rooms are distinct — so a rejected link never leaves a
    one-way exit behind. Directions are normalized to lowercase (the `go`
    handler lowercases player input before the exits lookup)."""
    from_id = eff.get("from_room_id")
    to_id = eff.get("to_room_id")
    direction = eff.get("direction")
    reverse = eff.get("reverse_direction")
    for v in (from_id, to_id, direction, reverse):
        if not isinstance(v, str) or not v.strip():
            return None
    direction = direction.strip().lower()
    reverse = reverse.strip().lower()
    if from_id == to_id:
        return None  # a room never links to itself
    from_room = objects.get(from_id)
    to_room = objects.get(to_id)
    if from_room is None or from_room.kind != "room":
        return None
    if to_room is None or to_room.kind != "room":
        return None
    from_exits = from_room.properties.get("exits")
    to_exits = to_room.properties.get("exits")
    from_exits = dict(from_exits) if isinstance(from_exits, dict) else {}
    to_exits = dict(to_exits) if isinstance(to_exits, dict) else {}
    if direction in from_exits or reverse in to_exits:
        return None  # a direction slot is taken: never overwrite an exit
    from_exits[direction] = to_id
    to_exits[reverse] = from_id
    objects.set_property(from_id, "exits", from_exits)
    objects.set_property(to_id, "exits", to_exits)
    return events.append(
        "system", None, "exit_linked",
        {"from_room_id": from_id, "to_room_id": to_id,
         "direction": direction, "reverse_direction": reverse},
        room_id=room_id,
    )


_HANDLERS: dict[str, Callable[..., events.Event | None]] = {
    "narrate": _apply_narrate,
    "set_property": _apply_set_property,
    "spawn_object": _apply_spawn_object,
    "move_object": _apply_move_object,
    "spawn_room": _apply_spawn_room,
    "link_exit": _apply_link_exit,
    "add_item": _apply_add_item,
    "set_mood": _apply_set_mood,
}
