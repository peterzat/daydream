"""Closed verb registry + the structured command bus.

Verbs are engine-implemented — a closed set (`look`, `examine`, `take`, `drop`,
`talk`, `say`, `go`). Each declares an arg-spec (does it need a direct object?
which target kinds are valid? which effects may it emit?). An object's
*available* verbs derive from its kind/prototype (`objects.verbs_for`).

UI clicks and the natural-language parser both produce the same structured
command `{verb, dobj_id?, iobj_id?, args?}`; `execute_command` is the single
executor. Validation: the verb must be known; a required direct object must be
in the actor's scope and the verb must be applicable to it (`verb in
verbs_for(dobj)` — this is what rejects "take a toon" / "talk to a rock").

MOO dispatch priority: the handler is resolved by searching
player -> room -> direct-object -> indirect-object, first match wins. v1 has
one engine handler per verb, but a verb bound to a specific object (an NPC's
`talk` dialogue) is selected over the generic default — so `talk` to Rook runs
Rook's bound dialogue, not a stub.

The LLM never mutates state. Deterministic verbs (look/examine-cached/take/
drop/go/say) make NO LLM call; only `talk` invokes the dialogue LLM. All
mutation flows through the allowlisted world-mutation effect API
(`daydream.skills.effects`), each verb constrained to the effects it declares.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from daydream import events, objects, rooms
from daydream.llm import client, safety
from daydream.skills import effects

logger = logging.getLogger(__name__)

_DONT_UNDERSTAND = "The dream isn't sure what you mean by that."


@dataclass(frozen=True)
class VerbSpec:
    name: str
    ui_hint: str
    description: str
    needs_dobj: bool = False
    needs_iobj: bool = False
    # Target kinds the parser/UI should offer; the execution gate is
    # `verb in objects.verbs_for(dobj)`, which this mirrors.
    valid_dobj_kinds: frozenset[str] = field(default_factory=frozenset)
    # Per-verb effect allowlist (passed to dispatch_effects).
    allowed_effects: frozenset[str] = field(default_factory=frozenset)
    # Does this verb appear in the UI verb bar (Examine/Take/Drop/Talk)?
    on_bar: bool = False
    # Args are free text that may itself name a target (e.g. "say hi to rook"),
    # so the parser's deterministic fast-path must NOT claim "<verb> <args>" —
    # it hands such input to the LLM to disambiguate say-vs-talk.
    free_text: bool = False


VERBS: dict[str, VerbSpec] = {
    "look": VerbSpec(
        name="look", ui_hint="Look",
        description="Describe the current room and what's in it. No target.",
        allowed_effects=frozenset({"narrate"}),
    ),
    "examine": VerbSpec(
        name="examine", ui_hint="Examine",
        description="Look closely at a toon or thing. Target: the object.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"toon", "thing"}),
        allowed_effects=frozenset({"narrate", "set_property"}), on_bar=True,
    ),
    "take": VerbSpec(
        name="take", ui_hint="Take",
        description="Pick up a thing from the room. Target: the thing.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"thing"}),
        allowed_effects=frozenset({"move_object", "narrate"}), on_bar=True,
    ),
    "drop": VerbSpec(
        name="drop", ui_hint="Drop",
        description="Put a thing you're carrying down in the room. Target: the thing.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"thing"}),
        allowed_effects=frozenset({"move_object", "narrate"}), on_bar=True,
    ),
    "talk": VerbSpec(
        name="talk", ui_hint="Talk",
        description="Talk to someone. Target: the toon. Args: what you say.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"toon"}),
        allowed_effects=frozenset({"narrate", "set_property", "set_mood", "spawn_object"}),
        on_bar=True, free_text=True,
    ),
    "say": VerbSpec(
        name="say", ui_hint="Say",
        description="Speak something aloud to the room. Args: the text to say.",
        allowed_effects=frozenset({"narrate"}), free_text=True,
    ),
    "go": VerbSpec(
        name="go", ui_hint="Go",
        description="Move through an exit. Args: a direction (e.g. 'north').",
        allowed_effects=frozenset(),
    ),
    "inventory": VerbSpec(
        name="inventory", ui_hint="Inventory",
        description="List what you're carrying. No target.",
        allowed_effects=frozenset({"narrate"}),
    ),
}


def get(name: str) -> VerbSpec | None:
    return VERBS.get(name.strip().lower())


def bar_verbs() -> list[VerbSpec]:
    """The verbs the UI verb bar offers, in declaration order."""
    return [v for v in VERBS.values() if v.on_bar]


# ---- the executor ------------------------------------------------------


async def execute_command(
    actor_id: str,
    verb: str,
    dobj_id: str | None = None,
    iobj_id: str | None = None,
    args: str = "",
) -> None:
    """Validate scope + verb applicability, then dispatch (MOO priority).

    The single execution path for both UI commands and parsed free text. Emits
    events (narration / effects) as side effects; mutates only through the
    world-mutation effect API. A validation failure emits a graceful narration
    and mutates nothing."""
    actor = objects.get(actor_id)
    if actor is None:
        return
    room_id = actor.location_id or ""
    spec = get(verb)
    if spec is None:
        _narrate(room_id, _DONT_UNDERSTAND)
        return

    dobj = None
    if spec.needs_dobj:
        if not dobj_id:
            _narrate(room_id, f"{spec.ui_hint} what?")
            return
        dobj = _resolve_in_scope(actor_id, dobj_id)
        if dobj is None:
            _narrate(room_id, "You don't see that here.")
            return
        if spec.name not in objects.verbs_for(dobj):
            _narrate(room_id, f"You can't {spec.name} {dobj.name}.")
            return

    iobj = _resolve_in_scope(actor_id, iobj_id) if iobj_id else None

    # MOO dispatch priority: the handler is resolved by searching player ->
    # room -> dobj -> iobj, first match wins. v1 has one engine handler per
    # verb, but a verb bound to a specific object (an NPC's `talk` dialogue,
    # found on the dobj) is selected over the generic default. The talk
    # special-case below IS that resolution for v1; per-object / per-room
    # overrides slot into the same order later.
    if spec.name == "talk" and dobj is not None:
        await _handle_talk(actor, room_id, dobj, args, spec)
        return

    handler = _ENGINE_HANDLERS.get(spec.name)
    if handler is None:  # defensive: every verb has an engine handler
        _narrate(room_id, _DONT_UNDERSTAND)
        return
    await handler(actor, room_id, dobj, iobj, args, spec)


def _resolve_in_scope(actor_id: str, object_id: str | None) -> objects.Object | None:
    """An object is a valid command target only if it is in the actor's scope
    (its room, the room's contents, or the actor's inventory). This is the gate
    that stops a stale or out-of-scope id from acting at a distance."""
    if not object_id:
        return None
    for o in objects.in_scope(actor_id):
        if o.id == object_id:
            return o
    return None


def _narrate(room_id: str, text: str) -> None:
    events.append("system", None, "narrate", {"text": text}, room_id=room_id)


def _dispatch(actor: objects.Object, room_id: str, effs: list, spec: VerbSpec) -> None:
    """Route a verb's effects through the allowlisted world-mutation API,
    constrained to the verb's own allowlist."""
    effects.dispatch_effects(
        effs, actor_id=actor.id, room_id=room_id, world_id=actor.world_id,
        allowed=spec.allowed_effects,
    )


# ---- engine handlers (deterministic unless noted) ----------------------


async def _handle_look(actor, room_id, dobj, iobj, args, spec) -> None:
    room = rooms.get_room(room_id)
    if room is None:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": "You are nowhere recognizable."}], spec)
        return
    text = room.description_cached or f"You are in {room.title}."
    things = objects.contents(room_id, kind="thing")
    if things:
        text += " You see: " + ", ".join(t.name for t in things) + "."
    _dispatch(actor, room_id, [{"kind": "narrate", "text": text}], spec)


def _examine_line(dobj: objects.Object, detail: str) -> str:
    return f"You examine the {dobj.name}: {detail}.".replace(" .", ".")


async def _handle_examine(actor, room_id, dobj, iobj, args, spec) -> None:
    """Examine an object. Cached text or a toon's appearance or a thing's seed
    are echoed deterministically (NO LLM). A spawned generative object with no
    seed and no cached text triggers a single LLM call, persists the result as
    `examined_text` (via the effect API), and shows it; later examines hit the
    cache."""
    cached = dobj.properties.get("examined_text")
    if isinstance(cached, str) and cached.strip():
        _dispatch(actor, room_id, [{"kind": "narrate", "text": _examine_line(dobj, cached)}], spec)
        return
    if dobj.kind == "toon":
        appearance = dobj.properties.get("appearance_seed", "")
        line = f"You see {dobj.name}: {appearance}. {dobj.seed}.".replace(" .", ".")
        _dispatch(actor, room_id, [{"kind": "narrate", "text": line}], spec)
        return
    if dobj.seed and dobj.seed.strip():
        _dispatch(actor, room_id, [{"kind": "narrate", "text": _examine_line(dobj, dobj.seed)}], spec)
        return
    # Lazy-cache generation (one LLM call, then cached).
    detail = await _generate_examine(dobj)
    if detail is None:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"You look at the {dobj.name}, but the dream is too foggy to make out the details just now."}], spec)
        return
    _dispatch(actor, room_id, [
        {"kind": "set_property", "target_id": dobj.id, "key": "examined_text", "value": detail},
        {"kind": "narrate", "text": _examine_line(dobj, detail)},
    ], spec)


_EXAMINE_SYSTEM = (
    "You are the describer for a cozy watercolor text-adventure. Given an "
    "object's name, write ONE or two soft, painterly sentences a player reads "
    "when they look closely at it. Return STRICT JSON: {\"text\": \"...\"}. "
    "Tone: cozy, soft, Spiritfarer / A Short Hike. No urgency, no modern tech, "
    "no harsh edges, no quoted dialogue. JSON only."
)


async def _generate_examine(dobj: objects.Object) -> str | None:
    """One LLM call to describe an object with no cached/seed detail. Returns
    the cozy description, or None on LLM outage / banlist hit (the caller shows
    a gentle 'too foggy' line). Local model only, behind the GPU arbiter."""
    try:
        result = await client.acompletion_json(
            system=_EXAMINE_SYSTEM, user=f"Object: {dobj.name}\nDescribe it."
        )
    except client.LLMUnavailable:
        return None
    if not isinstance(result, dict):
        return None
    text = result.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    if safety.first_banned(text) is not None:
        return None
    return text.strip()


async def _handle_take(actor, room_id, dobj, iobj, args, spec) -> None:
    if dobj.location_id == actor.id:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": f"You're already carrying the {dobj.name}."}], spec)
        return
    _dispatch(actor, room_id, [
        {"kind": "move_object", "object_id": dobj.id, "dest_id": actor.id},
        {"kind": "narrate", "text": f"You take the {dobj.name}."},
    ], spec)


async def _handle_drop(actor, room_id, dobj, iobj, args, spec) -> None:
    if dobj.location_id != actor.id:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": f"You aren't carrying the {dobj.name}."}], spec)
        return
    _dispatch(actor, room_id, [
        {"kind": "move_object", "object_id": dobj.id, "dest_id": room_id},
        {"kind": "narrate", "text": f"You drop the {dobj.name}."},
    ], spec)


async def _handle_say(actor, room_id, dobj, iobj, args, spec) -> None:
    text = args.strip()
    if not text:
        _narrate(room_id, "Say what?")
        return
    # `say` is the actor speaking, not system narration: emit a `say` event
    # keyed to the actor. Carry the speaker's display NAME in the payload so the
    # client attributes by name and never falls back to a raw id (SPEC
    # 2026-06-30: no object/toon ids in player-visible text).
    events.append(
        "toon", actor.id, "say", {"text": text, "name": actor.name}, room_id=room_id
    )


_PLACE_ARTICLES = ("the ", "a ", "an ")


def _normalize_place(text: str) -> str:
    """Lowercase, drop a leading 'to ' ('go to the bridge') and a leading
    article, so 'to the Bridge' -> 'bridge' for place-name matching."""
    t = text.strip().lower()
    if t.startswith("to "):
        t = t[3:].strip()
    for art in _PLACE_ARTICLES:
        if t.startswith(art):
            return t[len(art):].strip()
    return t


def _exit_direction_for_place(room: "rooms.Room", place: str) -> str | None:
    """Map a place name / alias / slug to the direction of an ADJACENT exit of
    `room`, or None. One hop only -- no multi-room pathfinding (SPEC 2026-06-30):
    only rooms one exit away from `room` are considered."""
    needle = _normalize_place(place)
    if not needle:
        return None
    for direction, dest_id in room.exits.items():
        dest = objects.get(dest_id)
        if dest is None or dest.kind != "room":
            continue
        names = {dest.name.lower()}
        names.update(a.lower() for a in (dest.aliases or []))
        for key in ("slug", "title"):
            v = dest.properties.get(key)
            if isinstance(v, str) and v:
                names.add(v.lower())
        if needle in names:
            return direction
    return None


async def _handle_go(actor, room_id, dobj, iobj, args, spec) -> None:
    raw = args.strip()
    if not raw:
        _narrate(room_id, "Go where?")
        return
    room = rooms.get_room(room_id)
    if room is None:
        _narrate(room_id, "You are nowhere recognizable.")
        return
    direction = raw.lower()
    target_id = room.exits.get(direction)
    if target_id is None:
        # Not a literal direction: try "go to <place>" / "go <place>" by
        # resolving the place name/alias/slug to an ADJACENT exit (one hop, no
        # pathfinding). SPEC 2026-06-30.
        resolved = _exit_direction_for_place(room, raw)
        if resolved is not None:
            direction = resolved
            target_id = room.exits.get(direction)
    if target_id is None:
        _narrate(room_id, f"You can't go {raw} from here.")
        return
    objects.move(actor.id, target_id)
    # The move event's room_id is the DEPARTURE room so the WS broadcast filter
    # routes it to the leaving connection (mirrors the prior `go` core skill).
    events.append(
        "toon", actor.id, "move",
        {"from_room": room_id, "to_room": target_id, "direction": direction},
        room_id=room_id,
    )


async def _handle_inventory(actor, room_id, dobj, iobj, args, spec) -> None:
    """List the things the actor is carrying (things located on the toon). Built
    on the existing containment model; deterministic, no LLM. A clear line when
    empty so the player always gets an answer."""
    carried = objects.contents(actor.id, kind="thing")
    if not carried:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": "You're carrying nothing."}], spec)
        return
    names = ", ".join(o.name for o in carried)
    _dispatch(actor, room_id, [{"kind": "narrate", "text": f"You're carrying: {names}."}], spec)


_ENGINE_HANDLERS = {
    "look": _handle_look,
    "examine": _handle_examine,
    "take": _handle_take,
    "drop": _handle_drop,
    "say": _handle_say,
    "go": _handle_go,
    "inventory": _handle_inventory,
}


# ---- talk: object-bound dialogue (MOO override) ------------------------


def _bound_dialogue_skill(dobj: objects.Object) -> str | None:
    """The data-skill name bound to an NPC for `talk`, or None. v1 binding:
    the legacy `t-<skill>` convention inverted (t-rook -> 'rook'); a future
    `properties.dialogue` reference takes precedence when present."""
    explicit = dobj.properties.get("dialogue")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if dobj.id.startswith("t-"):
        return dobj.id[2:]
    return None


async def _handle_talk(actor, room_id, dobj, args, spec) -> None:
    """Run the NPC's bound dialogue (the existing safety + LLM + memory + effect
    pipeline), constrained to `talk`'s effect allowlist. Falls back to a gentle
    stub when the NPC has no bound dialogue."""
    from daydream.skills import data as data_skills

    skill_name = _bound_dialogue_skill(dobj)
    pair = data_skills.find(skill_name) if skill_name else None
    if pair is None:
        _narrate(room_id, f"{dobj.name} doesn't have much to say just now.")
        return
    sspec, body = pair
    await data_skills.execute(
        sspec, body, actor.id, room_id, args, allowed=spec.allowed_effects
    )
