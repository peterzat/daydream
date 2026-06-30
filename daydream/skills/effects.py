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
- `add_item` / `set_mood` — retained aliases over spawn_object / set_property
                    for the existing data-skill author files.

Future-prepared (documented, not built): `spawn_room`, `link_exit`,
`destroy_object` — the vocabulary a future authored "build" verb would emit.
This is the explicit hook for user-created, LLM-driven world-building.

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
    # Retained aliases for existing data-skill author files.
    "add_item",
    "set_mood",
})


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
    a verb can only emit the effects it declares. None means "any ALLOWED_KIND"
    (the data-skill default).

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
        if (
            not isinstance(kind, str)
            or kind not in ALLOWED_KINDS
            or (allowed is not None and kind not in allowed)
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
    selects the readable prototype (examine/take/drop). Provenance fields
    (`generated_by`) ride along in properties for the future clutter-GC pass."""
    name = eff.get("name")
    seed = eff.get("seed", "")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(seed, str):
        return None
    location_id = eff.get("location_id", room_id)
    if not isinstance(location_id, str) or objects.get(location_id) is None:
        return None
    proto = objects.PROTO_READABLE if eff.get("readable") else objects.PROTO_THING
    aliases = eff.get("aliases") if isinstance(eff.get("aliases"), list) else []
    props: dict = {"seed": seed.strip(), "is_unique": 1}
    gen_by = eff.get("generated_by")
    if isinstance(gen_by, str) and gen_by.strip():
        props["generated_by"] = gen_by.strip()
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


_HANDLERS: dict[str, Callable[..., events.Event | None]] = {
    "narrate": _apply_narrate,
    "set_property": _apply_set_property,
    "spawn_object": _apply_spawn_object,
    "move_object": _apply_move_object,
    "add_item": _apply_add_item,
    "set_mood": _apply_set_mood,
}
