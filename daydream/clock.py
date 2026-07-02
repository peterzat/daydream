"""The world clock: one tick at the tail of every executed command (Zork
turn, SPEC 2026-07-02 criterion 5).

Tick order, deterministic under a pinned world `rng_seed`:

1. advance the world turn (worldstate `turn`)
2. burn fuel on every LIT light source — authored threshold warnings narrate
   privately to the holder; at zero the source goes out (`lit: false`,
   `burned_out: true`) with its authored burnout line
3. count down armed fuses (worldstate `fuse:<name>`) — one that reaches zero
   fires its authored `def:fuses[name].do` effects with the context captured
   when it was armed
4. run active daemons (worldstate `daemon:<name>` x `def:daemons[name]`) —
   the `script` kind evaluates rule conditions against the ticking actor and
   dispatches its effects; `wanderer` and `conveyor` land with the hostiles
   increment
5. the darkness beat for the ticking actor: entering an unlit room narrates
   the authored darkness text; a move that BEGAN and ENDED in unlit rooms
   rolls the authored seeded hazard (`config.darkness`), and a hit narrates
   the authored hazard text then applies `kill_actor` (the authored death
   policy). Standing still in the dark is safe.

Worlds that author no fuel/fuses/daemons/darkness pay one KV increment per
command and nothing else — the clockmakers world is behaviorally untouched.
All mutation flows through the same primitives as everything else; fuse and
daemon effects run under the RULE_KINDS allowlist with sigils resolved
against their captured context."""

from __future__ import annotations

import logging

from daydream import events, lighting, objects, rules, worldstate
from daydream.skills import effects

logger = logging.getLogger(__name__)


def tick(actor_id: str, from_room_id: str | None = None) -> None:
    """One world turn, driven by `actor_id`'s just-executed command.
    `from_room_id` is the actor's room BEFORE the command, so the darkness
    beat can tell a move from standing still."""
    actor = objects.get(actor_id)
    if actor is None or actor.kind != "toon":
        return
    world_id = actor.world_id
    turn = worldstate.advance_turn(world_id)
    _burn_fuel(world_id)
    _run_fuses(world_id, turn)
    _run_daemons(world_id, actor)
    _darkness_beat(world_id, actor, from_room_id)


# ---- fuel -----------------------------------------------------------------


def _holder_toon(thing: objects.Object) -> objects.Object | None:
    """The toon holding a thing (directly or through carried containers)."""
    cur = thing
    for _ in range(objects.CONTAINER_SCOPE_DEPTH + 1):
        if cur.location_id is None:
            return None
        parent = objects.get(cur.location_id)
        if parent is None:
            return None
        if parent.kind == "toon":
            return parent
        if parent.kind == "room":
            return None
        cur = parent
    return None


def _thing_room(thing: objects.Object) -> str | None:
    """The room a thing ultimately sits in (through holders/containers)."""
    cur = thing
    for _ in range(objects.CONTAINER_SCOPE_DEPTH + 2):
        if cur.location_id is None:
            return cur.id if cur.kind == "room" else None
        parent = objects.get(cur.location_id)
        if parent is None:
            return None
        if parent.kind == "room":
            return parent.id
        cur = parent
    return None


def _burn_fuel(world_id: str) -> None:
    """Fuel burns ONLY while lit (fidelity relaxation R6). A source with no
    `fuel` key is permanent (the torch). Warnings are authored per remaining
    value (`fuel_warnings: {"30": "..."}`) and narrate privately to the
    holder; burnout flips lit off, marks `burned_out` (authored relight rules
    gate on it), and narrates `burnout_text`."""
    for thing in objects.things_where_property(world_id, "lit", True):
        if not thing.properties.get("light"):
            continue
        fuel = thing.properties.get("fuel")
        if not isinstance(fuel, int):
            continue  # permanent source
        fuel -= 1
        objects.set_property(thing.id, "fuel", fuel)
        holder = _holder_toon(thing)
        room_id = _thing_room(thing)
        recipient = holder.id if holder is not None else None
        warnings = thing.properties.get("fuel_warnings")
        if isinstance(warnings, dict):
            warn = warnings.get(str(fuel))
            if isinstance(warn, str) and warn.strip() and fuel > 0:
                events.append("system", None, "narrate", {"text": warn.strip()},
                              room_id=room_id, recipient_id=recipient)
        if fuel <= 0:
            objects.set_property(thing.id, "lit", False)
            objects.set_property(thing.id, "burned_out", True)
            out_text = thing.properties.get("burnout_text")
            if not (isinstance(out_text, str) and out_text.strip()):
                out_text = f"The {thing.name} flickers and goes out."
            events.append("system", None, "narrate", {"text": out_text.strip()},
                          room_id=room_id, recipient_id=recipient)
            # A light dying can plunge its room into darkness: nudge every
            # connection there to re-snapshot (same trigger the state-flip
            # visibility path uses).
            events.append("system", None, "property_set",
                          {"target_id": thing.id, "key": "lit"}, room_id=room_id)


# ---- fuses ------------------------------------------------------------------


def _run_fuses(world_id: str, turn: int) -> None:
    for key in worldstate.keys(world_id, worldstate.FUSE_PREFIX):
        name = key[len(worldstate.FUSE_PREFIX):]
        state = worldstate.get(world_id, key)
        if not isinstance(state, dict):
            worldstate.delete(world_id, key)
            continue
        # A fuse armed during THIS command's execution (turn was still
        # turn-1) skips its arming tick, so "turns: N" means N further
        # commands pass before it fires.
        if state.get("armed_turn") == turn - 1:
            continue
        remaining = state.get("remaining")
        remaining = (remaining if isinstance(remaining, int) else 1) - 1
        if remaining > 0:
            state["remaining"] = remaining
            worldstate.set(world_id, key, state)
            continue
        worldstate.delete(world_id, key)
        _fire_fuse(world_id, name, state.get("context"))


def _fire_fuse(world_id: str, name: str, context) -> None:
    defs = worldstate.get(world_id, "def:fuses")
    d = defs.get(name) if isinstance(defs, dict) else None
    do = d.get("do") if isinstance(d, dict) else None
    if not isinstance(do, list) or not do:
        logger.warning("fuse %r fired with no authored do-effects", name)
        return
    ctx_actor_id = None
    ctx_room_id = None
    if isinstance(context, dict):
        ctx_actor_id = context.get("actor_id")
        ctx_room_id = context.get("room_id")
    actor = objects.get(ctx_actor_id) if ctx_actor_id else None
    ctx = rules._build_ctx(
        actor, None, None, ctx_room_id or "", None, f"fuse:{name}",
    ) if actor is not None else {
        "actor": None, "dobj": None, "iobj": None,
        "room_id": ctx_room_id or "", "world_id": world_id,
        "self": None, "rng_purpose": f"fuse:{name}",
    }
    effs = rules.resolve_sigils(do, ctx)
    effects.dispatch_effects(
        effs, actor_id=ctx_actor_id or "", room_id=ctx_room_id or "",
        world_id=world_id, allowed=effects.RULE_KINDS,
    )


# ---- daemons -----------------------------------------------------------------


def _run_daemons(world_id: str, actor: objects.Object) -> None:
    defs = worldstate.get(world_id, "def:daemons")
    if not isinstance(defs, dict):
        return
    for key in worldstate.keys(world_id, worldstate.DAEMON_PREFIX):
        name = key[len(worldstate.DAEMON_PREFIX):]
        state = worldstate.get(world_id, key)
        if not isinstance(state, dict) or not state.get("active"):
            continue
        d = defs.get(name)
        if not isinstance(d, dict):
            logger.warning("active daemon %r has no def:daemons entry", name)
            continue
        kind = d.get("kind", "script")
        if kind == "script":
            _run_script_daemon(world_id, name, d, actor)
        elif kind in ("wanderer", "conveyor"):
            # Land with the hostiles/river increment; an authored world can
            # already declare them, they just don't act yet.
            logger.debug("daemon %r kind %r not yet ticking", name, kind)
        else:
            logger.warning("daemon %r has unknown kind %r", name, kind)


def _run_script_daemon(
    world_id: str, name: str, d: dict, actor: objects.Object
) -> None:
    """Conditions + effects, evaluated against the ticking actor (a solo
    world's only player; in co-op, whoever's command advanced the clock).
    `once: true` deactivates the daemon after its first firing (the
    score-350 map reveal fires exactly once)."""
    room_id = actor.location_id or ""
    ctx = rules._build_ctx(actor, None, None, room_id, None, f"daemon:{name}")
    if not rules.conditions_hold(d.get("if"), ctx):
        return
    do = d.get("do")
    if not isinstance(do, list) or not do:
        return
    effs = rules.resolve_sigils(do, ctx)
    effects.dispatch_effects(
        effs, actor_id=actor.id, room_id=room_id,
        world_id=world_id, allowed=effects.RULE_KINDS,
    )
    if d.get("once"):
        key = worldstate.DAEMON_PREFIX + name
        state = worldstate.get(world_id, key)
        if isinstance(state, dict):
            state["active"] = False
            worldstate.set(world_id, key, state)


# ---- darkness -------------------------------------------------------------------


def _darkness_beat(
    world_id: str, actor: objects.Object, from_room_id: str | None
) -> None:
    """Entering an unlit room warns (the authored darkness text, privately);
    a move that started AND ended unlit rolls the authored hazard. Zork
    semantics: the warning move itself is safe, standing still is safe,
    pressing on in the dark is how the world eats you."""
    now_room = actor.location_id
    moved = bool(from_room_id) and from_room_id != now_room
    if not moved:
        return
    if lighting.room_lit(now_room):
        return
    cfg = lighting.darkness_config(world_id)
    events.append(
        "system", None, "narrate", {"text": lighting.darkness_text(world_id)},
        room_id=now_room, recipient_id=actor.id,
    )
    chance = cfg.get("hazard_chance")
    if not isinstance(chance, (int, float)) or chance <= 0:
        return
    if lighting.room_lit(from_room_id):
        return  # the move INTO darkness is the warned, safe one
    if worldstate.rng(world_id, "darkness-hazard").random() >= float(chance):
        return
    hazard_text = cfg.get("hazard_text")
    if isinstance(hazard_text, str) and hazard_text.strip():
        events.append("system", None, "narrate", {"text": hazard_text.strip()},
                      room_id=now_room, recipient_id=actor.id)
    effects.dispatch_effects(
        [{"kind": "kill_actor"}], actor_id=actor.id, room_id=now_room or "",
        world_id=world_id, allowed=effects.RULE_KINDS,
    )
