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
        elif kind == "wanderer":
            _run_wanderer(world_id, name, d)
        elif kind == "conveyor":
            _run_conveyor(world_id, name, d)
        elif kind == "glow":
            _run_glow(world_id, name, d)
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


def _narrate_room(world_id: str, room_id: str | None, text, recipient=None) -> None:
    if not room_id or not isinstance(text, str) or not text.strip():
        return
    events.append("system", None, "narrate", {"text": text.strip()},
                  room_id=room_id, recipient_id=recipient)


def _players_in(room_id: str | None) -> list[objects.Object]:
    if not room_id:
        return []
    return [o for o in objects.contents(room_id, kind="toon")
            if o.is_human_controlled or o.controller_session]


def _run_wanderer(world_id: str, name: str, d: dict) -> None:
    """The roaming hostile (SPEC criterion 8): moves through its authored
    room set, steals qualifying loot from rooms and players into its own
    hands, and empties its pockets in its lair. Every roll seeded per turn.
    Authored: toon, rooms, move_chance, steal_from_room_chance,
    steal_from_player_chance, steal_filter {key, eq}, deposit_room,
    arrive_text, leave_text, steal_text (to the victim)."""
    toon = objects.get(d.get("toon", ""))
    if toon is None or toon.kind != "toon":
        return  # killed (or never authored): the daemon idles harmlessly
    rooms_set = [r for r in d.get("rooms", []) if isinstance(r, str)]
    rng = worldstate.rng(world_id, f"wanderer:{name}")
    here = toon.location_id

    def matches(thing: objects.Object) -> bool:
        f = d.get("steal_filter")
        if not isinstance(f, dict) or not isinstance(f.get("key"), str):
            return False
        return thing.properties.get(f["key"]) == f.get("eq", True)

    # Steal from the room it stands in (not its own lair).
    if here and here != d.get("deposit_room"):
        chance = d.get("steal_from_room_chance", 0)
        for thing in objects.contents(here, kind="thing"):
            if matches(thing) and rng.random() < float(chance or 0):
                objects.move(thing.id, toon.id)
                _narrate_room(world_id, here, d.get("steal_room_text"))
                break
    # Pick a co-located player's pocket.
    if here:
        chance = d.get("steal_from_player_chance", 0)
        for player in _players_in(here):
            stolen = False
            for thing in objects.contents(player.id, kind="thing"):
                if matches(thing) and rng.random() < float(chance or 0):
                    objects.move(thing.id, toon.id)
                    _narrate_room(world_id, here, d.get("steal_text"),
                                  recipient=player.id)
                    stolen = True
                    break
            if stolen:
                break
    # Empty its pockets in the lair.
    if here and here == d.get("deposit_room"):
        for thing in objects.contents(toon.id, kind="thing"):
            if matches(thing):
                objects.move(thing.id, here)
    # Roam.
    if rooms_set and rng.random() < float(d.get("move_chance", 0) or 0):
        dest = rooms_set[rng.randrange(len(rooms_set))]
        if dest != here and objects.get(dest) is not None:
            if _players_in(here):
                _narrate_room(world_id, here, d.get("leave_text"))
            objects.move(toon.id, dest)
            if _players_in(dest):
                _narrate_room(world_id, dest, d.get("arrive_text"))


def _run_conveyor(world_id: str, name: str, d: dict) -> None:
    """The current (SPEC criterion 7): carries an authored vehicle along an
    authored path with per-cell delays; riders (toons aboard it) ride along.
    State (per-cell progress) lives on the daemon's worldstate entry."""
    vehicle = objects.get(d.get("vehicle", ""))
    if vehicle is None or vehicle.kind != "thing":
        return
    path = [r for r in d.get("path", []) if isinstance(r, str)]
    delays = d.get("delays", [])
    here = vehicle.location_id
    if here not in path:
        return  # ashore: the current has no grip
    idx = path.index(here)
    if idx >= len(path) - 1:
        return  # the last cell: drift ends (land, or stay)
    delay = delays[idx] if idx < len(delays) and isinstance(delays[idx], int) else 1
    key = worldstate.DAEMON_PREFIX + name
    state = worldstate.get(world_id, key)
    if not isinstance(state, dict):
        state = {"active": True}
    progress = state.get("progress")
    progress = (progress if isinstance(progress, int) else 0) + 1
    if progress < delay:
        state["progress"] = progress
        worldstate.set(world_id, key, state)
        return
    state["progress"] = 0
    worldstate.set(world_id, key, state)
    dest = path[idx + 1]
    if objects.get(dest) is None:
        return
    riders = [t for t in objects.contents(here, kind="toon")
              if t.properties.get("aboard") == vehicle.id]
    objects.move(vehicle.id, dest)
    for rider in riders:
        objects.move(rider.id, dest)
        events.append(
            "toon", rider.id, "move",
            {"from_room": here, "to_room": dest, "teleport": True},
            room_id=here,
        )
        _narrate_room(world_id, dest, d.get("carry_text"), recipient=rider.id)


def _run_glow(world_id: str, name: str, d: dict) -> None:
    """The warning item (SPEC criterion 8): while a player carries the
    authored item, it glows bright with a hostile in the room, faint with
    one a single exit away, and dims when clear. Narrates only on CHANGE,
    privately to the holder; the level persists as properties.glow_level."""
    item = objects.get(d.get("item", ""))
    if item is None:
        return
    holder = _holder_toon(item)
    room_id = _thing_room(item)
    hostiles = [h for h in d.get("hostiles", []) if isinstance(h, str)]
    level = 0
    if holder is not None and room_id:
        here_ids = {o.id for o in objects.contents(room_id, kind="toon")}
        if any(h in here_ids for h in hostiles):
            level = 2
        else:
            room = objects.get(room_id)
            exits = room.properties.get("exits") if room else {}
            adjacent: set[str] = set()
            if isinstance(exits, dict):
                for value in exits.values():
                    dest = value if isinstance(value, str) else (
                        value.get("to") if isinstance(value, dict) else None
                    )
                    if isinstance(dest, str):
                        adjacent.update(
                            o.id for o in objects.contents(dest, kind="toon")
                        )
            if any(h in adjacent for h in hostiles):
                level = 1
    prior = item.properties.get("glow_level")
    prior = prior if isinstance(prior, int) else 0
    if level == prior:
        return
    objects.set_property(item.id, "glow_level", level)
    if holder is None:
        return
    texts = {2: d.get("bright_text"), 1: d.get("faint_text"),
             0: d.get("dim_text")}
    _narrate_room(world_id, room_id, texts.get(level), recipient=holder.id)


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
