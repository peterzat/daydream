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

The rule-only kinds (platform turn, SPEC 2026-07-02) — `set_flag`,
`adjust_counter`, `adjust_score`, `destroy_object`, `teleport_actor`,
`start_fuse`/`stop_fuse`, `start_daemon`/`stop_daemon`, `win` — are likewise
restricted: they execute only under the declarative rule engine's
`RULE_KINDS` allowlist. No LLM-facing path can emit them.

The dispatcher stays closed to dynamic dispatch — there is no plugin mechanism,
by design. Out of scope (BACKLOG `skills-authoring-and-security`): strict
per-effect jsonschema validation, per-player rate limits, an `audit` table,
`bin/game world undo`."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from daydream import events, objects, worldstate

logger = logging.getLogger(__name__)


ALLOWED_KINDS: frozenset[str] = frozenset({
    "narrate",
    "set_property",
    "spawn_object",
    "move_object",
    # World-shaping (SPEC 2026-07-02): explicit per-verb declaration only.
    "spawn_room",
    "link_exit",
    # Engine housekeeping (explicit per-verb declaration only): rename an
    # object's display name (the spent dreamseed husk).
    "rename_object",
    # Rule-engine vocabulary (platform turn, SPEC 2026-07-02): emitted only by
    # authored world/object rules — never by an LLM-facing path.
    "set_flag",
    "adjust_counter",
    "adjust_score",
    "destroy_object",
    "teleport_actor",
    "kill_actor",
    "start_fuse",
    "stop_fuse",
    "start_daemon",
    "stop_daemon",
    "win",
    # Retained aliases for existing data-skill author files.
    "add_item",
    "set_mood",
})

# The kinds a caller gets when it passes no per-verb allowlist (allowed=None,
# the data-skill default). Restricted kinds are deliberately absent: growing a
# room, linking an exit, or renaming an object requires a verb that DECLARES
# the capability, so an NPC dialogue or a standalone data skill can never
# world-build (or vandalize a name) by omission.
WORLD_SHAPING_KINDS: frozenset[str] = frozenset({"spawn_room", "link_exit"})
# Kinds reachable ONLY through the declarative rule engine's allowlist
# (RULE_KINDS below). No LLM-emitted effects list can contain them: every
# LLM-facing dispatch passes allowed=None (DEFAULT_KINDS) or a verb allowlist
# that never includes these. Authored rule text is design-time data, so a
# rule scoring points or starting a fuse is the author speaking, not a model.
RULE_ONLY_KINDS: frozenset[str] = frozenset({
    "set_flag", "adjust_counter", "adjust_score", "destroy_object",
    "teleport_actor", "kill_actor", "start_fuse", "stop_fuse",
    "start_daemon", "stop_daemon", "win",
})
RESTRICTED_KINDS: frozenset[str] = (
    WORLD_SHAPING_KINDS | {"rename_object"} | RULE_ONLY_KINDS
)
DEFAULT_KINDS: frozenset[str] = ALLOWED_KINDS - RESTRICTED_KINDS
# The rule engine's dispatch allowlist: the basic vocabulary plus the
# rule-only kinds. Deliberately excludes the world-shaping kinds (a rule
# never grows rooms — exits with conditions are authored statically) and the
# legacy aliases.
RULE_KINDS: frozenset[str] = RULE_ONLY_KINDS | frozenset({
    "narrate", "set_property", "spawn_object", "move_object",
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
    """Emit narration. Two optional routing fields (platform turn):

    `to: "@actor"` (or an explicit toon id) makes the line actor-private
    (events.recipient_id, migration 014) — self-narrations and refusals
    reach only the acting player. `room: <id>` overrides which room's log
    the line lands in (a daemon narrating into its own room)."""
    text = eff.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    to = eff.get("to")
    recipient: str | None = None
    if isinstance(to, str) and to.strip():
        recipient = actor_id if to.strip() == "@actor" else to.strip()
    target_room = eff.get("room")
    if not (isinstance(target_room, str) and target_room.strip()):
        target_room = room_id
    return events.append(
        "system", None, "narrate", {"text": text.strip()},
        room_id=target_room, recipient_id=recipient,
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


def _apply_rename_object(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Rename one object's display name (and optionally replace its aliases):
    engine housekeeping, restricted to verbs that declare it (the plant
    pipeline renaming the consumed seed to its husk). Rejects (event=None, no
    mutation) on a missing target or empty name."""
    object_id = eff.get("object_id")
    name = eff.get("name")
    if not isinstance(object_id, str) or not isinstance(name, str) or not name.strip():
        return None
    aliases = eff.get("aliases")
    if aliases is not None and not (
        isinstance(aliases, list) and all(isinstance(a, str) for a in aliases)
    ):
        return None
    if not objects.rename(object_id, name.strip(), aliases):
        return None
    return events.append(
        "system", None, "object_renamed",
        {"object_id": object_id, "name": name.strip()}, room_id=room_id,
    )


# ---- rule-only kinds (platform turn, SPEC 2026-07-02) ------------------------


def _apply_set_flag(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Set one world flag (worldstate `flag:<NAME>`). `value` defaults true."""
    name = eff.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    value = bool(eff.get("value", True))
    worldstate.set_flag(world_id, name.strip(), value)
    return events.append(
        "system", None, "flag_set",
        {"name": name.strip(), "value": value}, room_id=room_id,
    )


def _apply_adjust_counter(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    name = eff.get("name")
    delta = eff.get("delta")
    if not isinstance(name, str) or not name.strip() or not isinstance(delta, int):
        return None
    value = worldstate.adjust_counter(world_id, name.strip(), delta)
    return events.append(
        "system", None, "counter_adjusted",
        {"name": name.strip(), "value": value}, room_id=room_id,
    )


def _apply_adjust_score(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Adjust the world-shared score. An optional `once: "<key>"` makes the
    award fire exactly once per world (taking a treasure scores on FIRST take
    only): the second and later dispatches are no-ops (event=None, no
    mutation), tracked via the worldstate `once:<key>` marker."""
    delta = eff.get("delta")
    if not isinstance(delta, int):
        return None
    once = eff.get("once")
    if isinstance(once, str) and once.strip():
        marker = "once:" + once.strip()
        if worldstate.get(world_id, marker):
            return None
        worldstate.set(world_id, marker, True)
    score = worldstate.adjust_score(world_id, delta)
    return events.append(
        "system", None, "score_changed",
        {"delta": delta, "score": score}, room_id=room_id,
    )


def _apply_destroy_object(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Remove one object from the world. Its contents (a destroyed container's
    payload, a dead hostile's hoard) drop to ITS location first, so nothing is
    ever silently lost. Refuses (no mutation) on rooms, prototypes, and
    human-controlled toons — a rule can unmake a thing or an NPC, never a
    player or the world's geometry."""
    object_id = eff.get("object_id")
    if not isinstance(object_id, str) or not object_id.strip():
        return None
    target = objects.get(object_id.strip())
    if target is None or target.kind in ("room", "prototype"):
        return None
    if target.kind == "toon" and (
        target.is_human_controlled or target.controller_session
    ):
        return None
    dest = target.location_id
    for held in objects.contents(target.id):
        objects.move(held.id, dest)
    objects.delete(target.id)
    return events.append(
        "system", None, "object_destroyed",
        {"object_id": target.id, "name": target.name}, room_id=room_id,
    )


def _apply_teleport_actor(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Relocate a toon (default: the acting toon) to `room_id`. Emits a `move`
    event keyed to the toon — the same kind `go` emits — so the WS layer's
    controlled-move branch re-snapshots and kicks image gen exactly as for a
    walked move. The event's room_id is the DEPARTURE room (broadcast-filter
    contract), with `teleport: true` so the client can narrate it differently."""
    target_room = eff.get("room_id")
    toon_id = eff.get("actor_id", actor_id)
    if not isinstance(target_room, str) or not isinstance(toon_id, str):
        return None
    toon = objects.get(toon_id)
    dest = objects.get(target_room)
    if toon is None or toon.kind != "toon" or dest is None or dest.kind != "room":
        return None
    from_room = toon.location_id
    objects.move(toon.id, dest.id)
    return events.append(
        "toon", toon.id, "move",
        {"from_room": from_room, "to_room": dest.id, "teleport": True},
        room_id=from_room,
    )


def _apply_start_fuse(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Arm one authored fuse (worldstate `fuse:<name>`): it fires after its
    turn count with the context captured HERE (actor + room at arm time — the
    exorcism candles warn the ritual-runner, not whoever walks by later).
    `turns` overrides the authored `def:fuses` count. Re-arming an active
    fuse resets its timer (relighting a candle restarts its burn window)."""
    name = eff.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    turns = eff.get("turns")
    if not isinstance(turns, int):
        defs = worldstate.get(world_id, "def:fuses")
        d = defs.get(name) if isinstance(defs, dict) else None
        turns = d.get("turns") if isinstance(d, dict) else None
    if not isinstance(turns, int) or turns < 1:
        return None
    worldstate.set(world_id, worldstate.FUSE_PREFIX + name, {
        "remaining": turns,
        # The clock skips a fuse's own arming tick (same-turn guard), so
        # "turns: N" means N further commands pass before it fires.
        "armed_turn": worldstate.turn(world_id),
        "context": {"actor_id": actor_id, "room_id": room_id},
    })
    return events.append(
        "system", None, "fuse_started",
        {"name": name, "turns": turns}, room_id=room_id,
    )


def _apply_stop_fuse(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Disarm a fuse. Stopping an inactive fuse is a quiet no-op (event=None):
    rules stop fuses defensively ('the bell quiets whatever was counting')."""
    name = eff.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    key = worldstate.FUSE_PREFIX + name.strip()
    if worldstate.get(world_id, key) is None:
        return None
    worldstate.delete(world_id, key)
    return events.append(
        "system", None, "fuse_stopped", {"name": name.strip()}, room_id=room_id,
    )


def _apply_start_daemon(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Activate one authored daemon (worldstate `daemon:<name>`); the world
    clock runs it each turn. Restarting an active daemon preserves its
    accumulated runtime state (a conveyor keeps its position)."""
    name = eff.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    key = worldstate.DAEMON_PREFIX + name
    state = worldstate.get(world_id, key)
    if not isinstance(state, dict):
        state = {}
    state["active"] = True
    worldstate.set(world_id, key, state)
    return events.append(
        "system", None, "daemon_started", {"name": name}, room_id=room_id,
    )


def _apply_stop_daemon(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Deactivate a daemon, preserving its state dict (a stopped conveyor
    holds its position). Stopping an inactive daemon is a quiet no-op."""
    name = eff.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    key = worldstate.DAEMON_PREFIX + name.strip()
    state = worldstate.get(world_id, key)
    if not isinstance(state, dict) or not state.get("active"):
        return None
    state["active"] = False
    worldstate.set(world_id, key, state)
    return events.append(
        "system", None, "daemon_stopped", {"name": name.strip()}, room_id=room_id,
    )


def _scatter_destination(
    thing: objects.Object, scatter: dict, room_id: str, rng
) -> str:
    """Where one carried thing lands on death: an exact `special` mapping
    first (the lamp goes home), then the first matching `filters` entry
    (treasures scatter into a seeded-random pick from its room list), then a
    seeded pick from `default_rooms`, else the death room itself."""
    special = scatter.get("special")
    if isinstance(special, dict):
        dest = special.get(thing.id)
        if isinstance(dest, str):
            return dest
    for f in scatter.get("filters") or []:
        if not isinstance(f, dict):
            continue
        key = f.get("key")
        rooms = f.get("rooms")
        if not isinstance(key, str) or not isinstance(rooms, list) or not rooms:
            continue
        if thing.properties.get(key) == f.get("eq", True):
            return str(rng.choice(rooms))
    defaults = scatter.get("default_rooms")
    if isinstance(defaults, list) and defaults:
        return str(rng.choice(defaults))
    return room_id


def _apply_kill_actor(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Apply the world's authored death policy (`config.death`) to a toon
    (default: the acting one): score penalty, deaths counter, inventory
    scatter (special-case destinations, property-filtered room sets, seeded
    random picks), authored flag resets, fuse/daemon stops, respawn, and an
    escalating authored message (fidelity relaxation R2: no permadeath — the
    counter and the messages carry the weight). Emits the respawn as a
    `move` event flagged died+teleport so the client can play its death
    moment before the fresh snapshot. Play continues cleanly: same toon,
    same session, standing in the respawn room. No authored policy = warn +
    no-op (a world without death shouldn't reach this)."""
    toon_id = eff.get("actor_id", actor_id)
    toon = objects.get(toon_id) if isinstance(toon_id, str) else None
    if toon is None or toon.kind != "toon":
        return None
    cfg = worldstate.get(world_id, "config")
    policy = cfg.get("death") if isinstance(cfg, dict) else None
    if not isinstance(policy, dict):
        logger.warning("kill_actor with no config.death policy; no-op")
        return None
    penalty = policy.get("penalty")
    if isinstance(penalty, int) and penalty:
        score = worldstate.adjust_score(world_id, -penalty)
        events.append("system", None, "score_changed",
                      {"delta": -penalty, "score": score}, room_id=room_id)
    deaths = worldstate.adjust_counter(world_id, "deaths", 1)
    scatter = policy.get("scatter")
    if isinstance(scatter, dict):
        rng = worldstate.rng(world_id, f"death-scatter:{deaths}")
        for thing in objects.contents(toon.id, kind="thing"):
            dest = _scatter_destination(thing, scatter, room_id, rng)
            if objects.get(dest) is not None:
                objects.move(thing.id, dest)
    flags = policy.get("set_flags")
    if isinstance(flags, dict):
        for name, value in flags.items():
            if isinstance(name, str) and name.strip():
                worldstate.set_flag(world_id, name.strip(), bool(value))
    for name in policy.get("stop_fuses") or []:
        if isinstance(name, str):
            worldstate.delete(world_id, worldstate.FUSE_PREFIX + name)
    for name in policy.get("stop_daemons") or []:
        if isinstance(name, str):
            state = worldstate.get(world_id, worldstate.DAEMON_PREFIX + name)
            if isinstance(state, dict) and state.get("active"):
                state["active"] = False
                worldstate.set(world_id, worldstate.DAEMON_PREFIX + name, state)
    messages = policy.get("messages")
    if isinstance(messages, list) and messages:
        text = messages[min(deaths - 1, len(messages) - 1)]
    else:
        text = "You have died."
    from_room = toon.location_id
    respawn = policy.get("respawn_room")
    dest = objects.get(respawn) if isinstance(respawn, str) else None
    if dest is not None and dest.kind == "room":
        objects.move(toon.id, dest.id)
    events.append("system", None, "narrate", {"text": str(text)},
                  room_id=toon.location_id if dest else from_room,
                  recipient_id=toon.id)
    return events.append(
        "toon", toon.id, "move",
        {"from_room": from_room, "to_room": objects.get(toon.id).location_id,
         "teleport": True, "died": True, "deaths": deaths},
        room_id=from_room,
    )


def _apply_win(
    eff: dict, *, actor_id: str, room_id: str, world_id: str
) -> events.Event | None:
    """Record the world as won (worldstate `won`) and broadcast the authored
    moment. Idempotent: a world wins once; later dispatches no-op."""
    if worldstate.get(world_id, "won") is not None:
        return None
    worldstate.set(world_id, "won", {
        "actor_id": actor_id, "turn": worldstate.turn(world_id),
    })
    text = eff.get("text")
    payload: dict = {"actor_id": actor_id}
    if isinstance(text, str) and text.strip():
        payload["text"] = text.strip()
    return events.append("system", None, "game_won", payload, room_id=room_id)


_HANDLERS: dict[str, Callable[..., events.Event | None]] = {
    "narrate": _apply_narrate,
    "set_property": _apply_set_property,
    "spawn_object": _apply_spawn_object,
    "move_object": _apply_move_object,
    "spawn_room": _apply_spawn_room,
    "link_exit": _apply_link_exit,
    "rename_object": _apply_rename_object,
    "set_flag": _apply_set_flag,
    "adjust_counter": _apply_adjust_counter,
    "adjust_score": _apply_adjust_score,
    "destroy_object": _apply_destroy_object,
    "teleport_actor": _apply_teleport_actor,
    "kill_actor": _apply_kill_actor,
    "start_fuse": _apply_start_fuse,
    "stop_fuse": _apply_stop_fuse,
    "start_daemon": _apply_start_daemon,
    "stop_daemon": _apply_stop_daemon,
    "win": _apply_win,
    "add_item": _apply_add_item,
    "set_mood": _apply_set_mood,
}
