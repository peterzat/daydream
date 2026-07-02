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

from daydream import events, objects, rooms, rules
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
    # Indirect-object target kinds for a two-object verb (give X to a toon, use
    # X on a thing). Mirrors valid_dobj_kinds; the iobj gate in execute_command
    # enforces it. Empty for single-object verbs.
    valid_iobj_kinds: frozenset[str] = field(default_factory=frozenset)
    # Per-verb effect allowlist (passed to dispatch_effects).
    allowed_effects: frozenset[str] = field(default_factory=frozenset)
    # Does this verb appear in the UI verb bar (Examine/Take/Drop/Talk)?
    on_bar: bool = False
    # Args are free text that may itself name a target (e.g. "say hi to rook"),
    # so the parser's deterministic fast-path must NOT claim "<verb> <args>" —
    # it hands such input to the LLM to disambiguate say-vs-talk.
    free_text: bool = False
    # ---- platform-turn fields (SPEC 2026-07-02) ----
    # Alternate words that resolve to this verb ("get" -> take; "douse" ->
    # a world verb). Parser fast-path + resolve() honor them.
    aliases: tuple[str, ...] = ()
    # Prepositions that split "verb DOBJ <prep> IOBJ" for this verb ("put X
    # in Y", "turn X with Y"). Generalizes the old parser two-target table.
    preps: tuple[str, ...] = ()
    # UI free-text prompting: when a click stages this verb, the SPA opens a
    # text prompt with `text_prompt` as its placeholder (drives talk/plant
    # today; world verbs author their own — no verb-name hardcode in main.js).
    needs_text: bool = False
    text_prompt: str = ""
    # World verbs only: narrated to the actor when no rule matches anywhere.
    fail_text: str = ""
    # GWIM slot-default filters ({"key": ..., "eq"/...}): when the player
    # omits a slot, the parser fills it iff exactly one in-scope object
    # matches ("light match" finds the matchbook). Data for the parser.
    dobj_default: dict | None = None
    iobj_default: dict | None = None
    # True for world-declared (data) verbs, which execute only through rules.
    world: bool = False


VERBS: dict[str, VerbSpec] = {
    "look": VerbSpec(
        name="look", ui_hint="Look",
        description="Describe the current room and what's in it. No target.",
        allowed_effects=frozenset({"narrate"}), aliases=("l",),
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
        # adjust_score is rule-only in general; take declares it explicitly
        # for the authored first-take treasure award (score_take property).
        allowed_effects=frozenset({"move_object", "narrate", "adjust_score"}),
        on_bar=True, aliases=("get",),
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
        needs_text=True, text_prompt="What do you say?",
    ),
    "give": VerbSpec(
        name="give", ui_hint="Give",
        description="Give a thing you're carrying to someone. Target: the thing, then the toon.",
        needs_dobj=True, needs_iobj=True,
        valid_dobj_kinds=frozenset({"thing"}), valid_iobj_kinds=frozenset({"toon"}),
        allowed_effects=frozenset({"move_object", "set_mood", "spawn_object", "narrate"}),
        on_bar=True, preps=("to",),
    ),
    "use": VerbSpec(
        name="use", ui_hint="Use",
        description="Use a thing on another thing. Target: the thing, then what to use it on.",
        needs_dobj=True, needs_iobj=True,
        valid_dobj_kinds=frozenset({"thing"}), valid_iobj_kinds=frozenset({"thing"}),
        allowed_effects=frozenset({"set_property", "spawn_object", "move_object", "narrate"}),
        on_bar=True, preps=("on", "with"),
    ),
    "open": VerbSpec(
        name="open", ui_hint="Open",
        description="Open a thing (a case, a box, a door). Target: the thing.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"thing"}),
        allowed_effects=frozenset({"set_property", "spawn_object", "narrate"}),
        on_bar=True,
    ),
    "close": VerbSpec(
        name="close", ui_hint="Close",
        description="Close an open thing (a lid, a case). Target: the thing.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"thing"}),
        allowed_effects=frozenset({"set_property", "narrate"}),
        on_bar=True, aliases=("shut",),
    ),
    "put": VerbSpec(
        name="put", ui_hint="Put",
        description="Put a thing you're carrying in or on another thing. "
                    "Target: the thing, then the container.",
        needs_dobj=True, needs_iobj=True,
        valid_dobj_kinds=frozenset({"thing"}), valid_iobj_kinds=frozenset({"thing"}),
        # adjust_score: the authored deposit award (score_case property into
        # a score_deposits container), mirroring take's declaration.
        allowed_effects=frozenset({"move_object", "narrate", "adjust_score"}),
        on_bar=True, preps=("in", "into", "inside", "on", "onto"),
    ),
    "read": VerbSpec(
        name="read", ui_hint="Read",
        description="Read a thing's writing (a ledger, a letter). Target: the thing.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"thing"}),
        allowed_effects=frozenset({"narrate"}), on_bar=True,
    ),
    "plant": VerbSpec(
        name="plant", ui_hint="Plant",
        description="Plant a dreamseed you're carrying to grow a new place. "
                    "Target: the seed. Args: your vision of where it leads.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"thing"}),
        # The first (and sole) consumer of the restricted effect kinds —
        # this allowlist is what makes spawn_room/link_exit/rename_object
        # reachable at all.
        allowed_effects=frozenset({"spawn_room", "link_exit", "rename_object",
                                   "spawn_object", "move_object",
                                   "set_property", "narrate"}),
        on_bar=True, free_text=True,
        needs_text=True, text_prompt="What do you see growing there?",
    ),
    "attack": VerbSpec(
        name="attack", ui_hint="Attack",
        description="Attack someone with a weapon you carry. "
                    "Target: the foe, then the weapon.",
        needs_dobj=True, needs_iobj=True,
        valid_dobj_kinds=frozenset({"toon"}), valid_iobj_kinds=frozenset({"thing"}),
        # destroy_object / kill_actor are rule-only in general; combat is the
        # explicit opt-in (the villain's fall, the villain's counterblow).
        allowed_effects=frozenset({"narrate", "set_property", "destroy_object",
                                   "kill_actor"}),
        preps=("with",),
        aliases=("kill", "hit", "strike", "fight", "stab", "slay"),
    ),
    "diagnose": VerbSpec(
        name="diagnose", ui_hint="Diagnose",
        description="Take stock of yourself. No target.",
        allowed_effects=frozenset({"narrate"}),
    ),
    "board": VerbSpec(
        name="board", ui_hint="Board",
        description="Climb into a vehicle (a boat, a basket). Target: the vehicle.",
        needs_dobj=True, valid_dobj_kinds=frozenset({"thing"}),
        allowed_effects=frozenset({"set_property", "narrate"}),
        aliases=("embark",),
    ),
    "disembark": VerbSpec(
        name="disembark", ui_hint="Disembark",
        description="Climb out of the vehicle you're aboard. No target.",
        allowed_effects=frozenset({"set_property", "narrate"}),
        aliases=("debark",),
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
        allowed_effects=frozenset({"narrate"}), aliases=("i", "inv"),
    ),
}

# Engine alias -> canonical name, derived once from the declarations above.
_ALIAS_TO_NAME: dict[str, str] = {
    alias: spec.name for spec in VERBS.values() for alias in spec.aliases
}


def get(name: str) -> VerbSpec | None:
    n = name.strip().lower()
    spec = VERBS.get(n)
    if spec is not None:
        return spec
    canonical = _ALIAS_TO_NAME.get(n)
    return VERBS.get(canonical) if canonical else None


def resolve(world_id: str | None, name: str) -> VerbSpec | None:
    """Resolve a verb word to its spec: engine verbs (name or alias) first,
    then the world's declared verbs (`daydream.worldverbs`). Engine wins on
    collision by construction — and the format-2 validator refuses a world
    verb that would collide, so the shadowing case never loads."""
    spec = get(name)
    if spec is not None:
        return spec
    if world_id:
        from daydream import worldverbs

        return worldverbs.get(world_id, name)
    return None


def bar_verbs(world_id: str | None = None) -> list[VerbSpec]:
    """The verbs the UI verb bar offers: engine verbs in declaration order,
    then the world's authored bar verbs."""
    out = [v for v in VERBS.values() if v.on_bar]
    if world_id:
        from daydream import worldverbs

        out.extend(worldverbs.bar_verbs(world_id))
    return out


# ---- the executor ------------------------------------------------------


async def execute_command(
    actor_id: str,
    verb: str,
    dobj_id: str | None = None,
    iobj_id: str | None = None,
    args: str = "",
    dobj_name: str | None = None,
) -> None:
    """Validate scope + verb applicability, then dispatch (MOO priority).

    The single execution path for both UI commands and parsed free text. Emits
    events (narration / effects) as side effects; mutates only through the
    world-mutation effect API. A validation failure emits a graceful narration
    and mutates nothing.

    `dobj_name` is the name the player typed for a target the parser could NOT
    ground to an in-scope id ("take the moon"); it lets a missing-but-named
    target read "you don't see the moon here", distinct from the no-target
    "Take what?". The click path never sets it (clicks always carry an id)."""
    actor = objects.get(actor_id)
    if actor is None:
        return
    room_id = actor.location_id or ""
    spec = resolve(actor.world_id, verb)
    if spec is None:
        # An unrecognized verb is a parse-level miss: no turn passes
        # (matching the original's "I don't know that word" behavior).
        _narrate(room_id, _DONT_UNDERSTAND, recipient_id=actor_id)
        return
    try:
        await _execute_resolved(
            actor, room_id, spec, dobj_id, iobj_id, args, dobj_name
        )
    finally:
        # The world clock (SPEC 2026-07-02 criterion 5): every executed
        # command — including an in-world refusal — advances the turn.
        # room_id is the pre-command room, so the darkness beat can tell a
        # move from standing still.
        from daydream import clock

        clock.tick(actor_id, from_room_id=room_id)


async def _execute_resolved(
    actor: objects.Object,
    room_id: str,
    spec: VerbSpec,
    dobj_id: str | None,
    iobj_id: str | None,
    args: str,
    dobj_name: str | None,
) -> None:
    actor_id = actor.id

    dobj = None
    if spec.needs_dobj:
        # Validation refusals are actor-private (migration 014): your typo
        # or out-of-reach grab never spams a co-located player's log.
        if not dobj_id:
            if dobj_name:
                _narrate(room_id, f"You don't see the {dobj_name} here.",
                         recipient_id=actor_id)
            else:
                _narrate(room_id, f"{spec.ui_hint} what?", recipient_id=actor_id)
            return
        dobj = _resolve_in_scope(actor_id, dobj_id)
        if dobj is None:
            _narrate(room_id, "You don't see that here.", recipient_id=actor_id)
            return
        if spec.name not in objects.verbs_for(dobj):
            _narrate(room_id, f"You can't {spec.name} {_the(dobj)}.",
                     recipient_id=actor_id)
            return

    iobj = _resolve_in_scope(actor_id, iobj_id) if iobj_id else None
    if spec.needs_iobj:
        # Indirect-object gate, symmetric to the dobj gate above. A missing or
        # out-of-scope iobj asks "…to whom?/on what?"; a wrong-kind iobj (give
        # to a thing, use on a toon) is refused by name. Either way: no mutation.
        prep = _iobj_prep(spec)
        if iobj is None:
            whom = "whom" if prep == "to" else "what"
            _narrate(room_id, f"{spec.ui_hint} it {prep} {whom}?",
                     recipient_id=actor_id)
            return
        dn = _the(dobj) if dobj is not None else "that"
        if spec.valid_iobj_kinds and iobj.kind not in spec.valid_iobj_kinds:
            _narrate(room_id, f"You can't {spec.name} {dn} {prep} {_the(iobj)}.",
                     recipient_id=actor_id)
            return

    # MOO dispatch priority (SPEC 2026-07-02 criterion 3): authored
    # declarative rules run FIRST, scanned dobj -> iobj -> room -> world,
    # ordered first-match. A fired rule consumes the command; legacy engine
    # handlers (and the talk dialogue special-case) run only when no rule
    # fires — rules SHADOW legacy verb Python, so a world that authors no
    # rules behaves byte-identically to before.
    if await rules.dispatch(actor, spec.name, dobj, iobj, room_id=room_id):
        return

    if spec.name == "talk" and dobj is not None:
        await _handle_talk(actor, room_id, dobj, args, spec)
        return

    handler = _ENGINE_HANDLERS.get(spec.name)
    if handler is None:
        # A world-declared verb with no matching rule: its authored fail_text
        # (actor-private, like every refusal). Engine verbs always have a
        # handler, so reaching here without one otherwise is a bug narrated
        # gently rather than raised.
        if spec.world:
            _narrate(room_id, spec.fail_text or "Nothing happens.",
                     recipient_id=actor_id)
        else:
            _narrate(room_id, _DONT_UNDERSTAND, recipient_id=actor_id)
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


def _narrate(room_id: str, text: str, recipient_id: str | None = None) -> None:
    events.append(
        "system", None, "narrate", {"text": text},
        room_id=room_id, recipient_id=recipient_id,
    )


def _dispatch(actor: objects.Object, room_id: str, effs: list, spec: VerbSpec) -> None:
    """Route a verb's effects through the allowlisted world-mutation API,
    constrained to the verb's own allowlist."""
    effects.dispatch_effects(
        effs, actor_id=actor.id, room_id=room_id, world_id=actor.world_id,
        allowed=spec.allowed_effects,
    )


def _matches_name(obj: objects.Object, needle: str | None) -> bool:
    """True if `needle` case-insensitively equals the object's name or any of
    its aliases. Authored cross-references (`wants`, a `use` rule's `with`) name
    the target by string, matching the engine's name-resolution grain rather
    than juggling ids."""
    n = (needle or "").strip().lower()
    if not n:
        return False
    names = [obj.name.lower()] + [str(a).lower() for a in obj.aliases]
    return n in names


def _iobj_prep(spec: VerbSpec) -> str:
    """The natural preposition for a two-object verb's indirect object, from its
    valid iobj kinds: a toon target reads 'give X to Y'; a thing target reads
    'use X on Y'. Drives the missing/wrong-kind narration."""
    return "to" if spec.valid_iobj_kinds == frozenset({"toon"}) else "on"


def _the(obj: objects.Object) -> str:
    """Display reference with the natural article: things take 'the' ('the
    lantern'); named toons take none ('Tace', never 'the Tace' — playtest
    2026-07-02)."""
    return obj.name if obj.kind == "toon" else f"the {obj.name}"


# ---- engine handlers (deterministic unless noted) ----------------------


async def _handle_look(actor, room_id, dobj, iobj, args, spec) -> None:
    # Self-narration: `look` describes the room to the looker only (SPEC
    # 2026-07-02 criterion 12); co-located players don't see your reading.
    room = rooms.get_room(room_id)
    if room is None:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": "You are nowhere recognizable.", "to": "@actor"}], spec)
        return
    from daydream import lighting

    if not lighting.room_lit(room_id):
        # Darkness suppresses the description behind the authored line
        # (criterion 6); scope is already reduced to self + inventory.
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": lighting.darkness_text(actor.world_id), "to": "@actor"}], spec)
        return
    text = room.description_cached or f"You are in {room.title}."
    things = objects.contents(room_id, kind="thing")
    if things:
        text += " You see: " + ", ".join(t.name for t in things) + "."
    # Visible container contents compose into the look (criterion 4): an
    # open sack on the floor reads out what it holds; a closed one doesn't.
    for t in things:
        inner = objects.visible_contents(t)
        if inner:
            text += f" The {t.name} holds: " + ", ".join(o.name for o in inner) + "."
    _dispatch(actor, room_id, [{"kind": "narrate", "text": text, "to": "@actor"}], spec)


def _terminate(text: str) -> str:
    """Trim and ensure exactly one terminal stop, so a detail that already ends
    in . ! ? (or an ellipsis) doesn't yield a doubled '..' (SPEC 2026-06-30)."""
    text = (text or "").strip()
    if not text:
        return text
    return text if text[-1] in ".!?…" else text + "."


def _examine_line(dobj: objects.Object, detail: str) -> str:
    detail = (detail or "").strip()
    if not detail:
        return f"You examine the {dobj.name}."
    return f"You examine the {dobj.name}: {_terminate(detail)}"


def _container_glance(dobj: objects.Object) -> str:
    """Examine's container suffix: what a see-through container holds, that
    it's empty, or that it's closed. Empty string for non-containers."""
    if not objects.is_container(dobj):
        return ""
    if not objects.contents_visible(dobj):
        return f" The {dobj.name} is closed."
    inner = objects.contents(dobj.id, kind="thing")
    if not inner:
        return f" The {dobj.name} is empty."
    return f" The {dobj.name} holds: " + ", ".join(o.name for o in inner) + "."


def _detail_with_state(dobj: objects.Object) -> str:
    """The physical seed, plus the current-state line when the object carries
    both a `state` and a `state_text` map for it. Appends (never overwrites) the
    seed, so a stateful object reads e.g. 'a heavy oak case. The lock has given;
    the case stands open.' Backward-compatible: a stateless thing returns its
    seed unchanged."""
    seed = dobj.seed
    state = dobj.properties.get("state")
    state_text = dobj.properties.get("state_text")
    if isinstance(state, str) and isinstance(state_text, dict):
        extra = state_text.get(state)
        if isinstance(extra, str) and extra.strip():
            return f"{_terminate(seed)} {extra.strip()}"
    return seed


async def _handle_examine(actor, room_id, dobj, iobj, args, spec) -> None:
    """Examine an object. Cached text or a toon's appearance or a thing's seed
    are echoed deterministically (NO LLM). A spawned generative object with no
    seed and no cached text triggers a single LLM call, persists the result as
    `examined_text` (via the effect API), and shows it; later examines hit the
    cache."""
    cached = dobj.properties.get("examined_text")
    if isinstance(cached, str) and cached.strip():
        _dispatch(actor, room_id, [{"kind": "narrate", "text": _examine_line(dobj, cached) + _container_glance(dobj), "to": "@actor"}], spec)
        return
    if dobj.kind == "toon":
        appearance = dobj.properties.get("appearance_seed", "")
        parts = [p for p in (appearance, dobj.seed) if p and p.strip()]
        body = " ".join(_terminate(p) for p in parts)
        line = f"You see {dobj.name}: {body}" if body else f"You see {dobj.name}."
        _dispatch(actor, room_id, [{"kind": "narrate", "text": line, "to": "@actor"}], spec)
        return
    if dobj.seed and dobj.seed.strip():
        _dispatch(actor, room_id, [{"kind": "narrate", "text": _examine_line(dobj, _detail_with_state(dobj)) + _container_glance(dobj), "to": "@actor"}], spec)
        return
    if objects.is_container(dobj):
        # A seedless authored container still answers with its contents
        # instead of burning an LLM call on emptiness.
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": _examine_line(dobj, "") + _container_glance(dobj), "to": "@actor"}], spec)
        return
    # Lazy-cache generation (one LLM call, then cached).
    detail = await _generate_examine(dobj)
    if detail is None:
        _dispatch(actor, room_id, [{"kind": "narrate", "to": "@actor",
            "text": f"You look at the {dobj.name}, but the dream is too foggy to make out the details just now."}], spec)
        return
    _dispatch(actor, room_id, [
        {"kind": "set_property", "target_id": dobj.id, "key": "examined_text", "value": detail},
        {"kind": "narrate", "text": _examine_line(dobj, detail), "to": "@actor"},
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


def _carry_capacity(actor: objects.Object) -> int | None:
    """The actor's carry limit in size units: per-toon `properties.capacity`
    first, else the world config's `carry_capacity`. None = unlimited (every
    pre-the original game world)."""
    cap = actor.properties.get("capacity")
    if isinstance(cap, int):
        return cap
    from daydream import worldstate

    cfg = worldstate.get(actor.world_id, "config")
    wcap = cfg.get("carry_capacity") if isinstance(cfg, dict) else None
    return wcap if isinstance(wcap, int) else None


async def _handle_take(actor, room_id, dobj, iobj, args, spec) -> None:
    if dobj.location_id == actor.id:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": f"You're already carrying the {dobj.name}."}], spec)
        return
    # Container gate: reaching INTO a closed container is refused. This only
    # bites for closed TRANSPARENT ones — a closed opaque container's
    # contents are already out of scope entirely (criterion 4).
    holder = objects.get(dobj.location_id) if dobj.location_id else None
    if holder is not None and holder.kind == "thing" and not objects.container_open(holder):
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"The {holder.name} is closed.", "to": "@actor"}], spec)
        return
    cap = _carry_capacity(actor)
    if cap is not None and objects.load_of(actor.id) + objects.size_of(dobj) > cap:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": "You're carrying too much already.", "to": "@actor"}], spec)
        return
    effs: list = [
        {"kind": "move_object", "object_id": dobj.id, "dest_id": actor.id},
        {"kind": "narrate", "text": f"You take the {dobj.name}."},
    ]
    # Authored first-take treasure value (platform turn): awarded exactly once,
    # and only on a take that actually succeeded (gates above returned).
    score_take = dobj.properties.get("score_take")
    if isinstance(score_take, int) and score_take:
        effs.append({"kind": "adjust_score", "delta": score_take,
                     "once": f"take:{dobj.id}"})
    _dispatch(actor, room_id, effs, spec)


async def _handle_drop(actor, room_id, dobj, iobj, args, spec) -> None:
    if dobj.location_id != actor.id:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": f"You aren't carrying the {dobj.name}."}], spec)
        return
    _dispatch(actor, room_id, [
        {"kind": "move_object", "object_id": dobj.id, "dest_id": room_id},
        {"kind": "narrate", "text": f"You drop the {dobj.name}."},
    ], spec)


async def _handle_give(actor, room_id, dobj, iobj, args, spec) -> None:
    """Give a carried thing (dobj) to an NPC (iobj). If the NPC `wants` it
    (name/alias match), the thing reparents onto them, their mood shifts to the
    authored `gives_mood`, their authored `gives` reward spawns into the actor's
    inventory (deduped by provenance so a re-give never doubles it), and the
    authored `gives_text` narrates. Otherwise the item stays carried and the NPC
    gently declines. Deterministic; every string is pre-baked (no LLM)."""
    if dobj.location_id != actor.id:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"You aren't carrying the {dobj.name}."}], spec)
        return
    if iobj.id == actor.id:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": "You can't give something to yourself."}], spec)
        return
    if not _matches_name(dobj, iobj.properties.get("wants")):
        decline = iobj.properties.get("declines_text")
        if not (isinstance(decline, str) and decline.strip()):
            decline = f"{iobj.name} smiles and gently sets the {dobj.name} back in your hands."
        _dispatch(actor, room_id, [{"kind": "narrate", "text": decline}], spec)
        return

    effs: list = [{"kind": "move_object", "object_id": dobj.id, "dest_id": iobj.id}]
    mood = iobj.properties.get("gives_mood")
    if isinstance(mood, str) and mood.strip():
        effs.append({"kind": "set_mood", "toon_id": iobj.id, "mood": mood.strip()})
    reward = iobj.properties.get("gives")
    if isinstance(reward, dict) and isinstance(reward.get("name"), str) and reward["name"].strip():
        spawn: dict = {
            "kind": "spawn_object", "name": reward["name"],
            "seed": reward["seed"] if isinstance(reward.get("seed"), str) else "",
            "location_id": actor.id, "generated_by": f"give:{iobj.id}",
        }
        if isinstance(reward.get("aliases"), list):
            spawn["aliases"] = reward["aliases"]
        if isinstance(reward.get("verbs"), list):
            spawn["verbs"] = reward["verbs"]
        if reward.get("readable"):
            spawn["readable"] = True
        effs.append(spawn)
    gives_text = iobj.properties.get("gives_text")
    if isinstance(gives_text, str) and gives_text.strip():
        effs.append({"kind": "narrate", "text": gives_text.strip()})
    else:
        effs.append({"kind": "narrate",
            "text": f"{iobj.name} takes the {dobj.name} with quiet thanks."})
    _dispatch(actor, room_id, effs, spec)
    _remember_give(actor, iobj, dobj)


def _remember_give(actor: objects.Object, iobj: objects.Object, dobj: objects.Object) -> None:
    """Best-effort NPC memory of a gift so a later `talk` can reflect it. CPU-only
    and fail-closed by contract (and disabled in tests), wrapped defensively so a
    memory hiccup never perturbs the deterministic give path."""
    try:
        from daydream import memories
        memories.capture(iobj.id, iobj.world_id, f"{actor.name} gave me the {dobj.name}.")
    except Exception:
        logger.debug("give-memory capture skipped", exc_info=True)


async def _handle_use(actor, room_id, dobj, iobj, args, spec) -> None:
    """Use one thing (dobj) on another (iobj). The TARGET (iobj) carries the
    authored `use` rule {with, from_state, to_state, text}: when the applied
    thing matches `with` and the target is in `from_state`, the target's `state`
    property transitions to `to_state` with the authored text. Any mismatch
    (wrong item, wrong state, or no rule) is a soft 'nothing happens' with no
    mutation. Deterministic (no LLM)."""
    rule = iobj.properties.get("use")
    if (
        isinstance(rule, dict)
        and _matches_name(dobj, rule.get("with"))
        and iobj.properties.get("state") == rule.get("from_state")
    ):
        text = rule.get("text")
        if not (isinstance(text, str) and text.strip()):
            text = f"You use the {dobj.name} on the {iobj.name}."
        _dispatch(actor, room_id, [
            {"kind": "set_property", "target_id": iobj.id, "key": "state",
             "value": rule.get("to_state")},
            {"kind": "narrate", "text": text},
        ], spec)
        return
    wrong = rule.get("wrong_text") if isinstance(rule, dict) else None
    if not (isinstance(wrong, str) and wrong.strip()):
        wrong = f"You try the {dobj.name} on the {iobj.name}, but nothing happens."
    _dispatch(actor, room_id, [{"kind": "narrate", "text": wrong}], spec)


async def _handle_open(actor, room_id, dobj, iobj, args, spec) -> None:
    """Open a stateful thing, gated on its `properties.state`:

      locked  -> refuse with the authored `locked_text`; stays shut.
      open    -> "already open"; does NOT re-spawn its payload.
      else    -> transition state to 'open', narrate `open_text`, and reveal the
                 authored `contains` payload into the room (deduped by
                 provenance so a re-open never doubles it).

    `contains` is a single object or a list of them (SPEC 2026-07-02); each
    entry's optional `properties` dict is forwarded into the spawn so an
    authored payload can carry state / growth blocks. Deterministic; all text
    is pre-baked (no LLM). A plain thing with no state just opens with a
    generic line."""
    state = dobj.properties.get("state")
    if state == "locked":
        locked = dobj.properties.get("locked_text")
        if not (isinstance(locked, str) and locked.strip()):
            locked = f"The {dobj.name} is locked."
        _dispatch(actor, room_id, [{"kind": "narrate", "text": locked}], spec)
        return
    if state == "open":
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"The {dobj.name} is already open."}], spec)
        return
    effs: list = [
        {"kind": "set_property", "target_id": dobj.id, "key": "state", "value": "open"},
    ]
    open_text = dobj.properties.get("open_text")
    if isinstance(open_text, str) and open_text.strip():
        effs.append({"kind": "narrate", "text": open_text.strip()})
    else:
        effs.append({"kind": "narrate", "text": f"You open the {dobj.name}."})
    contains = dobj.properties.get("contains")
    entries = contains if isinstance(contains, list) else [contains]
    revealed: list[str] = []
    for entry in entries:
        if not (isinstance(entry, dict) and isinstance(entry.get("name"), str)
                and entry["name"].strip()):
            continue
        spawn: dict = {
            "kind": "spawn_object", "name": entry["name"],
            "seed": entry["seed"] if isinstance(entry.get("seed"), str) else "",
            "location_id": room_id, "generated_by": f"open:{dobj.id}",
        }
        if isinstance(entry.get("aliases"), list):
            spawn["aliases"] = entry["aliases"]
        if isinstance(entry.get("verbs"), list):
            spawn["verbs"] = entry["verbs"]
        if entry.get("readable"):
            spawn["readable"] = True
        if isinstance(entry.get("properties"), dict):
            spawn["properties"] = entry["properties"]
        effs.append(spawn)
        revealed.append(entry["name"].strip())
    if revealed:
        # The ENGINE announces what the payload holds, by name, so a reveal is
        # never silent — authors write the payoff (`open_text`) for the moment
        # and the engine handles the inventory-of-what-appeared (playtest
        # 2026-07-02: the dreamseed materialized without a word).
        effs.append({"kind": "narrate",
                     "text": "Inside, you find: " + ", ".join(revealed) + "."})
    _dispatch(actor, room_id, effs, spec)


async def _handle_close(actor, room_id, dobj, iobj, args, spec) -> None:
    """Close an open stateful thing (the machine lid, a sack). Only a thing
    whose `state` is literally 'open' closes; anything else is already shut
    (or was never openable — an always-open basket doesn't offer `close`)."""
    if dobj.properties.get("state") != "open":
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"The {dobj.name} is already closed.", "to": "@actor"}], spec)
        return
    close_text = dobj.properties.get("close_text")
    if not (isinstance(close_text, str) and close_text.strip()):
        close_text = f"You close the {dobj.name}."
    _dispatch(actor, room_id, [
        {"kind": "set_property", "target_id": dobj.id, "key": "state", "value": "closed"},
        {"kind": "narrate", "text": close_text},
    ], spec)


async def _handle_put(actor, room_id, dobj, iobj, args, spec) -> None:
    """Put a carried thing (dobj) in/on a container or surface (iobj), with
    the criterion-4 gates: must be carrying it; the target must be a
    container; a closed container refuses; no putting a thing inside itself
    (or inside its own contents); authored `capacity` versus item sizes.
    Deterministic; every string pre-baked (no LLM)."""
    if dobj.location_id != actor.id:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"You aren't carrying the {dobj.name}.", "to": "@actor"}], spec)
        return
    surface = bool(iobj.properties.get("surface"))
    prep = "on" if surface else "in"
    if dobj.id == iobj.id:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"You can't put the {dobj.name} inside itself.", "to": "@actor"}], spec)
        return
    if not objects.is_container(iobj):
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"You can't put things {prep} the {iobj.name}.", "to": "@actor"}], spec)
        return
    if not objects.container_open(iobj):
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"The {iobj.name} is closed.", "to": "@actor"}], spec)
        return
    # Containment-cycle gate: walking up from the target, the carried thing
    # must not appear (putting the sack into the box inside the sack).
    cur = iobj
    for _ in range(objects.CONTAINER_SCOPE_DEPTH + 1):
        if cur.location_id is None:
            break
        if cur.location_id == dobj.id:
            _dispatch(actor, room_id, [{"kind": "narrate",
                "text": f"You can't put the {dobj.name} inside itself.", "to": "@actor"}], spec)
            return
        parent = objects.get(cur.location_id)
        if parent is None:
            break
        cur = parent
    cap = iobj.properties.get("capacity")
    if isinstance(cap, int) and objects.load_of(iobj.id) + objects.size_of(dobj) > cap:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"The {dobj.name} won't fit {prep} the {iobj.name}.",
            "to": "@actor"}], spec)
        return
    effs: list = [
        {"kind": "move_object", "object_id": dobj.id, "dest_id": iobj.id},
        {"kind": "narrate", "text": f"You put the {dobj.name} {prep} the {iobj.name}."},
    ]
    # Authored deposit value (platform turn): a treasure's score_case awards once
    # when it lands in a container that declares score_deposits (the trophy
    # case), only on a put that actually succeeded.
    score_case = dobj.properties.get("score_case")
    if iobj.properties.get("score_deposits") and isinstance(score_case, int) \
            and score_case:
        effs.append({"kind": "adjust_score", "delta": score_case,
                     "once": f"case:{dobj.id}"})
    _dispatch(actor, room_id, effs, spec)


async def _handle_read(actor, room_id, dobj, iobj, args, spec) -> None:
    """Narrate a readable's authored `text` (the words on the page), distinct
    from `examine`'s physical description. Degrades gently when there is no
    text. Deterministic (no LLM)."""
    text = dobj.properties.get("text")
    if isinstance(text, str) and text.strip():
        _dispatch(actor, room_id, [{"kind": "narrate", "text": text.strip(), "to": "@actor"}], spec)
        return
    _dispatch(actor, room_id, [{"kind": "narrate", "to": "@actor",
        "text": f"There's nothing written on the {dobj.name} to read."}], spec)


async def _handle_plant(actor, room_id, dobj, iobj, args, spec) -> None:
    """Plant a dreamseed (SPEC 2026-07-02): thin delegate to the growth
    pipeline, mirroring `_handle_talk`'s lazy-import dispatch shape. All the
    gates, the single LLM call, and the synchronous commit block live in
    `daydream.growth`; the verb's allowlist rides along so every mutation
    stays inside what `plant` declares."""
    from daydream import growth

    await growth.execute_plant(actor, room_id, dobj, args, spec.allowed_effects)


async def _handle_say(actor, room_id, dobj, iobj, args, spec) -> None:
    text = args.strip()
    if not text:
        _narrate(room_id, "Say what?", recipient_id=actor.id)
        return
    # `say` is the actor speaking, not system narration: emit a `say` event
    # keyed to the actor. Carry the speaker's display NAME in the payload so the
    # client attributes by name and never falls back to a raw id (SPEC
    # 2026-06-30: no object/toon ids in player-visible text).
    events.append(
        "toon", actor.id, "say", {"text": text, "name": actor.name}, room_id=room_id
    )


# Compass + movement vocabulary (platform turn, criterion 9). Exits are authored
# with canonical names; the parser and `go` accept the abbreviations.
DIRECTION_ALIASES: dict[str, str] = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
    "u": "up", "d": "down",
}
CANONICAL_DIRECTIONS: frozenset[str] = frozenset({
    "north", "south", "east", "west", "northeast", "northwest", "southeast",
    "southwest", "up", "down", "in", "out", "land", "launch", "cross",
    "climb", "enter", "exit",
})
DIRECTION_WORDS: frozenset[str] = CANONICAL_DIRECTIONS | frozenset(DIRECTION_ALIASES)


def canonical_direction(word: str) -> str:
    w = word.strip().lower()
    return DIRECTION_ALIASES.get(w, w)


# ---- exits (platform turn, SPEC 2026-07-02 criterion 7) ---------------------
#
# An exits-map value is one of:
#   "r-forge"                                   legacy plain destination
#   {"to": "r-x", "if": [conds], "blocked_text": "...",
#    "on_traverse": [effects, each with optional inline "if"],
#    "secret": true}                            conditional / secret exit
#   {"text": "The door is boarded."}            message-only non-exit
#
# All three producers (go, the parser fast-path, the UI exit buttons) route
# through `go`; visibility for snapshots comes from `visible_exits` (secret
# exits hidden until currently passable; blocked and message-only exits
# stay visible and refuse with their text on use).


def _exit_ctx(actor: objects.Object, room_id: str, direction: str) -> dict:
    return rules._build_ctx(actor, None, None, room_id, None, f"exit:{direction}")


def _exit_outcome(
    actor: objects.Object, room_id: str, direction: str, value
) -> tuple[str | None, str | None, list]:
    """Evaluate one exit value for this actor NOW. Returns
    (dest_id, refusal_text, on_traverse): dest_id None means no passage —
    refusal_text carries the authored message."""
    if isinstance(value, str):
        return value, None, []
    if not isinstance(value, dict):
        return None, None, []
    if "to" not in value:
        text = value.get("text")
        return None, (text if isinstance(text, str) and text.strip()
                      else "You can't go that way."), []
    conds = value.get("if")
    if conds and not rules.conditions_hold(conds, _exit_ctx(actor, room_id, direction)):
        blocked = value.get("blocked_text")
        return None, (blocked if isinstance(blocked, str) and blocked.strip()
                      else "Something bars the way."), []
    traverse = value.get("on_traverse")
    return value["to"], None, traverse if isinstance(traverse, list) else []


def _exit_dest(value) -> str | None:
    """An exit value's destination id, ignoring conditions (for place-name
    resolution and integrity checks). None for message-only entries."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        to = value.get("to")
        return to if isinstance(to, str) else None
    return None


def visible_exits(room: "rooms.Room", actor: objects.Object) -> dict:
    """The exits map as the snapshot should present it: `{direction:
    dest-or-None}`. Secret exits appear only while currently passable;
    ordinary blocked exits stay visible (clicking narrates the refusal);
    message-only entries appear with a null destination."""
    out: dict = {}
    for direction, value in room.exits.items():
        if isinstance(value, dict) and value.get("secret"):
            dest, refusal, _ = _exit_outcome(actor, room.id, direction, value)
            if dest is None:
                continue
            out[direction] = dest
        else:
            out[direction] = _exit_dest(value)
    return out


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
    for direction, value in room.exits.items():
        dest_id = _exit_dest(value)
        if dest_id is None:
            continue
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
        _narrate(room_id, "Go where?", recipient_id=actor.id)
        return
    room = rooms.get_room(room_id)
    if room is None:
        _narrate(room_id, "You are nowhere recognizable.", recipient_id=actor.id)
        return
    direction = canonical_direction(raw)
    exit_value = room.exits.get(direction)
    if exit_value is None:
        # Not a literal direction: try "go to <place>" / "go <place>" by
        # resolving the place name/alias/slug to an ADJACENT exit (one hop, no
        # pathfinding). SPEC 2026-06-30.
        resolved = _exit_direction_for_place(room, raw)
        if resolved is not None:
            direction = resolved
            exit_value = room.exits.get(direction)
    if exit_value is None:
        _narrate(room_id, f"You can't go {raw} from here.", recipient_id=actor.id)
        return
    # Conditional / secret / message-only exits (criterion 7). A refusal
    # narrates the authored text and still ticks the clock (the tick lives
    # in execute_command's tail, which this return path reaches).
    target_id, refusal, on_traverse = _exit_outcome(actor, room_id, direction, exit_value)
    if target_id is None:
        _narrate(room_id, refusal or f"You can't go {raw} from here.",
                 recipient_id=actor.id)
        return
    dest = objects.get(target_id)
    if dest is None or dest.kind != "room":
        _narrate(room_id, "The way shimmers closed.", recipient_id=actor.id)
        return
    # Destination entry gate: a room can require conditions to enter (a
    # water room refuses foot entry: enter_if [{"in_vehicle": true}]).
    enter_if = dest.properties.get("enter_if")
    if enter_if and not rules.conditions_hold(
        enter_if, _exit_ctx(actor, room_id, direction)
    ):
        blocked = dest.properties.get("enter_blocked_text")
        _narrate(room_id,
                 blocked if isinstance(blocked, str) and blocked.strip()
                 else f"You can't go {raw} from here.",
                 recipient_id=actor.id)
        return
    # The vehicle rides along: while aboard, going somewhere moves the
    # vehicle (and, by co-location, keeps the aboard flag valid there).
    vehicle = rules.vehicle_of(actor)
    objects.move(actor.id, target_id)
    if vehicle is not None:
        objects.move(vehicle.id, target_id)
    # The move event's room_id is the DEPARTURE room so the WS broadcast filter
    # routes it to the leaving connection (mirrors the prior `go` core skill).
    events.append(
        "toon", actor.id, "move",
        {"from_room": room_id, "to_room": target_id, "direction": direction},
        room_id=room_id,
    )
    # Authored traversal beats ("You slide down the coal chute...") run
    # after the move, in the destination, each with an optional inline "if".
    if on_traverse:
        ctx = rules._build_ctx(actor, None, None, target_id, None,
                               f"traverse:{direction}")
        effs = []
        for eff in on_traverse:
            if not isinstance(eff, dict):
                continue
            conds = eff.get("if")
            if conds and not rules.conditions_hold(conds, ctx):
                continue
            eff = {k: v for k, v in eff.items() if k != "if"}
            effs.append(eff)
        if effs:
            effects.dispatch_effects(
                rules.resolve_sigils(effs, ctx),
                actor_id=actor.id, room_id=target_id,
                world_id=actor.world_id, allowed=effects.RULE_KINDS,
            )
    # Room/world "enter" rules: authored arrival behavior (first-visit room
    # bonuses score here via adjust_score's once-key).
    await rules.dispatch(actor, "enter", None, None, room_id=target_id)


async def _handle_attack(actor, room_id, dobj, iobj, args, spec) -> None:
    """Seeded outcome-faithful combat: thin delegate to daydream.combat,
    which reads the villain's authored `properties.combat` block."""
    from daydream import combat

    await combat.execute_attack(actor, room_id, dobj, iobj, args, spec)


async def _handle_diagnose(actor, room_id, dobj, iobj, args, spec) -> None:
    """Self-assessment (actor-private): fidelity relaxation R2 surfaces the
    world-shared deaths counter here in place of permadeath."""
    from daydream import worldstate

    deaths = worldstate.counter(actor.world_id, "deaths")
    if deaths == 0:
        line = "You are in perfect health."
    elif deaths == 1:
        line = "You are in perfect health, all things considered. You have died once."
    else:
        line = (f"You are in perfect health, all things considered. "
                f"You have died {deaths} times.")
    _dispatch(actor, room_id, [{"kind": "narrate", "text": line, "to": "@actor"}], spec)


async def _handle_board(actor, room_id, dobj, iobj, args, spec) -> None:
    """Board a vehicle: sets the actor's `aboard` property (NOT containment —
    the actor's location stays the room, so every location read in the
    engine keeps meaning 'the room'). The vehicle must be one, and be here
    on the ground (you can't board a boat you're carrying)."""
    if not dobj.properties.get("vehicle"):
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"You can't board the {dobj.name}.", "to": "@actor"}], spec)
        return
    if dobj.location_id != room_id:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"Put the {dobj.name} down first.", "to": "@actor"}], spec)
        return
    current = rules.vehicle_of(actor)
    if current is not None:
        if current.id == dobj.id:
            _dispatch(actor, room_id, [{"kind": "narrate",
                "text": f"You're already aboard the {dobj.name}.", "to": "@actor"}], spec)
            return
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": f"You're already aboard the {current.name}.", "to": "@actor"}], spec)
        return
    board_text = dobj.properties.get("board_text")
    if not (isinstance(board_text, str) and board_text.strip()):
        board_text = f"You climb into the {dobj.name}."
    _dispatch(actor, room_id, [
        {"kind": "set_property", "target_id": actor.id, "key": "aboard",
         "value": dobj.id},
        {"kind": "narrate", "text": board_text},
    ], spec)


async def _handle_disembark(actor, room_id, dobj, iobj, args, spec) -> None:
    vehicle = rules.vehicle_of(actor)
    if vehicle is None:
        _dispatch(actor, room_id, [{"kind": "narrate",
            "text": "You aren't aboard anything.", "to": "@actor"}], spec)
        return
    out_text = vehicle.properties.get("disembark_text")
    if not (isinstance(out_text, str) and out_text.strip()):
        out_text = f"You climb out of the {vehicle.name}."
    _dispatch(actor, room_id, [
        {"kind": "set_property", "target_id": actor.id, "key": "aboard",
         "value": None},
        {"kind": "narrate", "text": out_text},
    ], spec)


async def _handle_inventory(actor, room_id, dobj, iobj, args, spec) -> None:
    """List the things the actor is carrying (things located on the toon). Built
    on the existing containment model; deterministic, no LLM. A clear line when
    empty so the player always gets an answer."""
    carried = objects.contents(actor.id, kind="thing")
    if not carried:
        _dispatch(actor, room_id, [{"kind": "narrate", "text": "You're carrying nothing.", "to": "@actor"}], spec)
        return
    names = ", ".join(o.name for o in carried)
    _dispatch(actor, room_id, [{"kind": "narrate", "text": f"You're carrying: {names}.", "to": "@actor"}], spec)


_ENGINE_HANDLERS = {
    "look": _handle_look,
    "examine": _handle_examine,
    "take": _handle_take,
    "drop": _handle_drop,
    "give": _handle_give,
    "use": _handle_use,
    "open": _handle_open,
    "close": _handle_close,
    "put": _handle_put,
    "read": _handle_read,
    "plant": _handle_plant,
    "attack": _handle_attack,
    "diagnose": _handle_diagnose,
    "board": _handle_board,
    "disembark": _handle_disembark,
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
    stub when the NPC has no bound dialogue. The NPC object rides along so the
    pipeline speaks in the dialogue voice (third person, by name) and binds
    memory to this toon directly (playtest fix 2026-07-02)."""
    from daydream.skills import data as data_skills

    skill_name = _bound_dialogue_skill(dobj)
    pair = data_skills.find(skill_name) if skill_name else None
    if pair is None:
        _narrate(room_id, f"{dobj.name} doesn't have much to say just now.")
        return
    sspec, body = pair
    await data_skills.execute(
        sspec, body, actor.id, room_id, args, allowed=spec.allowed_effects,
        npc=dobj,
    )
