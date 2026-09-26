"""Declarative rule engine: authored, deterministic verb behavior as world
data (platform turn, SPEC 2026-07-02 criterion 3).

A rule is a dict authored on an object or room (`properties.rules`) or on the
world (worldstate `def:rules`):

    {"on": "<verb>" | "enter", "as": "dobj" | "iobj",
     "if": [<conditions>], "do": [<effects>], "stop": true}

Dispatch order is dobj -> iobj -> room -> world; within each holder the rules
run in authored order and the FIRST rule whose conditions all hold fires.
Conditions AND together; there is no else — wrong-tool branches are written
as later rules with looser conditions (fallthrough). A fired rule stops
dispatch unless it authors `stop: false`. When no rule fires anywhere, the
caller falls through to the legacy engine handler (rules SHADOW legacy verb
Python, never replace it) or, for a world-declared verb, to its `fail_text`.

The condition vocabulary is CLOSED (unknown key = format-2 load error via
`validate_rules`; at runtime an unknown key evaluates false and logs, so a
hand-edited DB can never make a rule fire in a way the validator would have
refused):

    {"flag": NAME, "eq": bool?}                 world flag (eq defaults true)
    {"prop": KEY, "of": REF?, <op>: VALUE}      object property compare
    {"counter": NAME, <op>: N}                  world counter compare
    {"score": {<op>: N}}                        world score compare
    {"carrying_count": {<op>: N}}               how many things actor carries
    {"dobj": ID} / {"iobj": ID}                 slot identity (sigils ok)
    {"carried": ID}                             actor carries that object
    {"carried_filter": {"key": K, ...}}         actor carries a matching thing
    {"only_carrying": [ID, ...]}                actor carries exactly these
    {"empty_handed": true|false}                actor carries nothing (or not)
    {"in": ROOM_ID}                             actor is in that room
    {"chance": P, "purpose": NAME?}             seeded roll (worldstate.rng)
    {"present": ID}                             object in actor's room or hand
    {"contains": ID, "of": REF?}                container directly holds it
    {"in_vehicle": true | ID}                   actor is aboard (any/that one)

Story conditions (SPEC 2026-09-26; read per-player state for the actor):

    {"rel": NPC_ID, <op>: N}                    actor's relationship with NPC
    {"pflag": NAME, "eq": bool?}                actor's per-player flag
    {"pcounter": NAME, <op>: N}                 actor's per-player counter
    {"beat": "ARC/BEAT", "by": REF?}            beat done (by that toon)
    {"arc": ARC_ID, <op>: STATUS?}              arc status (no op = open)
    {"ending": "ARC/ENDING"}                    arc closed with that ending
    {"helped": ARC_ID}                          actor helped that arc
    {"helpers": ARC_ID, <op>: N}                how many players helped it
    {"phase": NAME | [NAME, ...]}               the village's time of day
    {"day": {<op>: N}}                          the village day
    {"knows": FACT_ID, "who": REF, "about": REF?}  an NPC knows a fact
    {"collected": {<op>: N}, "page": ID?}       actor's collectibles found

Any condition may add `"not": true` to invert itself ("passable only while
NOT carrying the coffin").

A rule authored `"after": true` is an AFTER-HOOK: it runs only once the
verb's normal handling has succeeded, and never suppresses it (the gear is
given as usual, and also the village hears of it). Before-rules (the
default) keep their replace-the-verb semantics exactly.

`<op>` is exactly one of eq / ne / lt / lte / gt / gte / in; a prop condition
with no op is a truthy check. REF and ID values accept the sigils `@self`
(the rule's holder), `@actor`, `@dobj`, `@iobj`, `@room`. Sigils in effect
dicts resolve to concrete ids before dispatch (effects stay id-only).

Effects run under the `effects.RULE_KINDS` allowlist — the rule vocabulary
plus the basic four — regardless of which verb hosted the rule. Authored
rules are design-time data; no LLM-facing path reaches this dispatcher.
"""

from __future__ import annotations

import copy
import logging

from daydream import objects, worldstate
from daydream.skills import effects

logger = logging.getLogger(__name__)

SIGILS = frozenset({"@self", "@actor", "@dobj", "@iobj", "@room"})
OPS = ("eq", "ne", "lt", "lte", "gt", "gte", "in")

# Condition discriminator keys, in evaluation-precedence order. `prop`,
# `counter`, `score` are checked before bare `in` because `in` doubles as
# their membership operator ({"prop": "state", "in": [...]}) and as the
# am-I-in-this-room form ({"in": "r-x"}).
CONDITION_KEYS = (
    "prop", "counter", "score", "carrying_count", "rel", "pcounter", "arc",
    "helpers", "flag", "dobj", "iobj",
    "carried", "carried_filter", "only_carrying", "empty_handed", "chance",
    "present", "contains", "in_vehicle",
    "pflag", "beat", "ending", "helped", "phase", "day", "knows", "collected",
    "in",
)
# Discriminators whose aux keys may include the `in` membership operator
# (so a bare `in` is theirs, not the am-I-in-this-room form).
_IN_OWNERS = ("prop", "counter", "rel", "pcounter", "arc", "helpers")


# ---- context + references ------------------------------------------------


def _build_ctx(
    actor: objects.Object,
    dobj: objects.Object | None,
    iobj: objects.Object | None,
    room_id: str,
    holder: objects.Object | None,
    rng_purpose: str,
) -> dict:
    return {
        "actor": actor,
        "dobj": dobj,
        "iobj": iobj,
        "room_id": room_id,
        "world_id": actor.world_id,
        "self": holder,
        "rng_purpose": rng_purpose,
    }


def world_ctx(world_id: str, room_id: str | None, rng_purpose: str) -> dict:
    """A condition context with no acting toon (the director, dusk, timed
    endings): world-level conditions evaluate normally; actor-bound ones
    (carried, rel, pflag...) read an empty stub and are simply false."""
    stub = objects.Object(
        id="", world_id=world_id, kind="toon", name="", aliases=[],
        location_id=room_id, prototype_id=None, properties={},
    )
    return {
        "actor": stub, "dobj": None, "iobj": None, "room_id": room_id or "",
        "world_id": world_id, "self": None, "rng_purpose": rng_purpose,
    }


def _ref_id(token, ctx: dict) -> str | None:
    """Resolve a reference token (a sigil or a literal id) to an object id."""
    if not isinstance(token, str):
        return None
    if token == "@self":
        return ctx["self"].id if ctx["self"] is not None else None
    if token == "@actor":
        return ctx["actor"].id
    if token == "@dobj":
        return ctx["dobj"].id if ctx["dobj"] is not None else None
    if token == "@iobj":
        return ctx["iobj"].id if ctx["iobj"] is not None else None
    if token == "@room":
        return ctx["room_id"] or None
    return token


def _ref_obj(token, ctx: dict) -> objects.Object | None:
    oid = _ref_id(token, ctx)
    return objects.get(oid) if oid else None


# ---- condition evaluation --------------------------------------------------


def _op_compare(cond: dict, value) -> bool:
    """Apply the single comparison operator present in `cond` to `value`;
    with no operator present, truthy-check the value. Type-mismatched
    ordering comparisons are false, never an exception."""
    for op in OPS:
        if op not in cond:
            continue
        expected = cond[op]
        try:
            if op == "eq":
                return value == expected
            if op == "ne":
                return value != expected
            if op == "lt":
                return value < expected
            if op == "lte":
                return value <= expected
            if op == "gt":
                return value > expected
            if op == "gte":
                return value >= expected
            if op == "in":
                return value in expected
        except TypeError:
            return False
    return bool(value)


def _carried_things(actor_id: str) -> list[objects.Object]:
    return objects.contents(actor_id, kind="thing")


def vehicle_of(actor: objects.Object) -> objects.Object | None:
    """The vehicle the actor is aboard, or None. `properties.aboard` names
    it; it counts only while co-located in the actor's room and still
    flagged `vehicle` (a boat that drifted off without you doesn't carry
    you). Single source of truth for the in_vehicle condition, the go
    handler, and the board/disembark verbs."""
    aboard = actor.properties.get("aboard")
    if not isinstance(aboard, str) or not aboard:
        return None
    v = objects.get(aboard)
    if (
        v is None or v.kind != "thing" or not v.properties.get("vehicle")
        or v.location_id != actor.location_id
    ):
        return None
    return v


def _eval_condition(cond: dict, ctx: dict) -> bool:
    # Generic negation: any condition may carry "not": true to invert
    # ("passable only while NOT carrying the coffin").
    if cond.get("not"):
        inner = {k: v for k, v in cond.items() if k != "not"}
        return not _eval_condition(inner, ctx)
    actor: objects.Object = ctx["actor"]
    world_id: str = ctx["world_id"]

    if "prop" in cond:
        obj = _ref_obj(cond.get("of", "@self"), ctx)
        if obj is None:
            return False
        return _op_compare(cond, obj.properties.get(cond["prop"]))
    if "counter" in cond:
        return _op_compare(cond, worldstate.counter(world_id, cond["counter"]))
    if "score" in cond:
        spec = cond["score"]
        return isinstance(spec, dict) and _op_compare(spec, worldstate.score(world_id))
    if "carrying_count" in cond:
        spec = cond["carrying_count"]
        return isinstance(spec, dict) and _op_compare(
            spec, len(_carried_things(actor.id))
        )
    if "flag" in cond:
        return worldstate.get_flag(world_id, cond["flag"]) == cond.get("eq", True)
    if "dobj" in cond:
        want = _ref_id(cond["dobj"], ctx)
        return ctx["dobj"] is not None and want is not None and ctx["dobj"].id == want
    if "iobj" in cond:
        want = _ref_id(cond["iobj"], ctx)
        return ctx["iobj"] is not None and want is not None and ctx["iobj"].id == want
    if "carried" in cond:
        obj = _ref_obj(cond["carried"], ctx)
        return obj is not None and obj.location_id == actor.id
    if "carried_filter" in cond:
        f = cond["carried_filter"]
        if not isinstance(f, dict) or not isinstance(f.get("key"), str):
            return False
        for thing in _carried_things(actor.id):
            if _op_compare(f, thing.properties.get(f["key"])):
                return True
        return False
    if "only_carrying" in cond:
        want = cond["only_carrying"]
        if not isinstance(want, list):
            return False
        have = sorted(t.id for t in _carried_things(actor.id))
        return have == sorted(str(x) for x in want)
    if "empty_handed" in cond:
        return (len(_carried_things(actor.id)) == 0) == bool(cond["empty_handed"])
    if "chance" in cond:
        try:
            p = float(cond["chance"])
        except (TypeError, ValueError):
            return False
        purpose = cond.get("purpose") or ctx["rng_purpose"]
        return worldstate.rng(world_id, str(purpose)).random() < p
    if "present" in cond:
        obj = _ref_obj(cond["present"], ctx)
        return obj is not None and obj.location_id in (ctx["room_id"], actor.id)
    if "contains" in cond:
        holder = _ref_obj(cond.get("of", "@self"), ctx)
        want = _ref_id(cond["contains"], ctx)
        if holder is None or want is None:
            return False
        return want in objects.content_ids(holder.id)
    if "in_vehicle" in cond:
        # Embarkation is the actor's `aboard` property (NOT containment —
        # location_id stays the room so every location read in the engine
        # keeps meaning "the room"). Valid only while the vehicle is
        # co-located and still a vehicle.
        vehicle = vehicle_of(actor)
        want = cond["in_vehicle"]
        if want is True:
            return vehicle is not None
        if want is False:
            return vehicle is None
        return vehicle is not None and vehicle.id == _ref_id(want, ctx)
    story_result = _eval_story_condition(cond, ctx)
    if story_result is not None:
        return story_result
    if "in" in cond:
        return actor.location_id == _ref_id(cond["in"], ctx)

    logger.warning("unknown rule condition %r evaluates false", cond)
    return False


def _split_ref(ref) -> tuple[str, str] | None:
    if isinstance(ref, str) and "/" in ref:
        a, b = ref.split("/", 1)
        if a and b:
            return a, b
    return None


def _eval_story_condition(cond: dict, ctx: dict) -> bool | None:
    """The story-layer conditions (SPEC 2026-09-26). None = not a story
    condition (fall through)."""
    from daydream import story

    actor: objects.Object = ctx["actor"]
    world_id: str = ctx["world_id"]
    if "rel" in cond:
        npc = _ref_id(cond["rel"], ctx)
        if not npc or not actor.id:
            return False
        return _op_compare(cond, story.rel(world_id, npc, actor.id))
    if "pcounter" in cond:
        if not actor.id:
            return False
        return _op_compare(cond, story.pcounter(world_id, actor.id, cond["pcounter"]))
    if "helpers" in cond:
        n = len(story.arc_state(world_id, str(cond["helpers"]))["helpers"])
        return _op_compare(cond, n)
    if "arc" in cond:
        status = story.arc_status(world_id, str(cond["arc"]))
        if not any(op in cond for op in OPS):
            return status == "open"
        return _op_compare(cond, status)
    if "pflag" in cond:
        if not actor.id:
            return cond.get("eq", True) is False
        return story.pflag(world_id, actor.id, cond["pflag"]) == cond.get("eq", True)
    if "beat" in cond:
        ref = _split_ref(cond["beat"])
        if ref is None:
            return False
        by = _ref_id(cond["by"], ctx) if "by" in cond else None
        if "by" in cond and not by:
            return False
        return story.beat_done(world_id, ref[0], ref[1], by=by)
    if "ending" in cond:
        ref = _split_ref(cond["ending"])
        return ref is not None and story.ending_of(world_id, ref[0]) == ref[1]
    if "helped" in cond:
        return bool(actor.id) and actor.id in story.arc_state(
            world_id, str(cond["helped"]))["helpers"]
    if "phase" in cond:
        from daydream import village

        want = cond["phase"]
        now = village.phase(world_id)
        return now in want if isinstance(want, list) else now == want
    if "day" in cond:
        from daydream import village

        spec = cond["day"]
        return isinstance(spec, dict) and _op_compare(spec, village.day(world_id))
    if "knows" in cond:
        from daydream import knowledge

        who = _ref_id(cond.get("who", "@self"), ctx)
        about = _ref_id(cond["about"], ctx) if "about" in cond else None
        if not who:
            return False
        return knowledge.npc_knows(world_id, who, str(cond["knows"]), about=about, ctx=ctx)
    if "collected" in cond:
        from daydream import collect

        spec = cond["collected"]
        if not isinstance(spec, dict) or not actor.id:
            return False
        return _op_compare(spec, collect.count(world_id, actor.id, cond.get("page")))
    return None


def conditions_hold(conds, ctx: dict) -> bool:
    """All conditions AND together; a malformed entry is false (the rule
    simply never fires — same fail-closed posture as the effect API)."""
    if conds is None:
        return True
    if not isinstance(conds, list):
        return False
    for cond in conds:
        if not isinstance(cond, dict) or not _eval_condition(cond, ctx):
            return False
    return True


# ---- sigil resolution -------------------------------------------------------


def resolve_sigils(effs: list, ctx: dict) -> list:
    """Deep-copy the effect list with every top-level string value that IS a
    sigil replaced by its concrete id. An unresolvable sigil (e.g. `@iobj`
    with no iobj) is left verbatim, which every effect handler then rejects
    as an unknown id — no mutation, matching the fail-closed contract."""
    out = []
    for eff in effs or []:
        if not isinstance(eff, dict):
            out.append(eff)
            continue
        eff = copy.deepcopy(eff)
        for k, v in list(eff.items()):
            if isinstance(v, str) and v in SIGILS:
                resolved = _ref_id(v, ctx)
                if resolved is not None:
                    eff[k] = resolved
        out.append(eff)
    return out


# ---- dispatch ----------------------------------------------------------------


def rules_on(obj: objects.Object | None) -> list[dict]:
    if obj is None:
        return []
    rules = obj.properties.get("rules")
    return [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []


def world_rules(world_id: str) -> list[dict]:
    rules = worldstate.get(world_id, "def:rules")
    return [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else []


async def dispatch(
    actor: objects.Object,
    verb_name: str,
    dobj: objects.Object | None,
    iobj: objects.Object | None,
    *,
    room_id: str,
    phase: str = "before",
) -> bool:
    """Run the first matching rule for `verb_name` (or the pseudo-event
    `enter`) across dobj -> iobj -> room -> world. Returns True if any rule
    fired (the caller then skips the legacy engine handler). Effects run
    under the RULE_KINDS allowlist with sigils resolved per holder.

    Async solely for the retell layer (criterion 13): a retell-enabled
    world may rephrase eligible narrate texts through the local LLM before
    dispatch, with the authored text as the unconditional fallback — a
    world with retell off (or the LLM absent) takes a zero-await path
    identical to the old sync dispatch. Fuses and daemons keep their own
    sync path (clock.tick) and are never retold.

    `phase="after"` runs only rules authored `"after": true` (after-hooks,
    called once the verb's normal handling succeeded); the default "before"
    phase runs only the rest, so an after-hook can never replace a verb."""
    want_after = phase == "after"
    room = objects.get(room_id) if room_id else None
    fired = False
    holders: list[tuple[objects.Object | None, str]] = [
        (dobj, "dobj"), (iobj, "iobj"), (room, "room"), (None, "world"),
    ]
    for holder, role in holders:
        if role in ("dobj", "iobj") and holder is None:
            continue
        # The room can also arrive as the dobj (examine-the-room shapes);
        # don't scan its rules twice.
        if role == "room" and holder is not None and dobj is not None \
                and holder.id == dobj.id:
            continue
        rule_list = world_rules(actor.world_id) if role == "world" else rules_on(holder)
        for idx, rule in enumerate(rule_list):
            if rule.get("on") != verb_name:
                continue
            if bool(rule.get("after", False)) != want_after:
                continue
            as_role = rule.get("as", "dobj")
            if role == "dobj" and as_role != "dobj":
                continue
            if role == "iobj" and as_role != "iobj":
                continue
            holder_tag = holder.id if holder is not None else "world"
            ctx = _build_ctx(
                actor, dobj, iobj, room_id, holder,
                rng_purpose=f"rule:{verb_name}:{holder_tag}:{idx}",
            )
            if not conditions_hold(rule.get("if"), ctx):
                continue
            effs = resolve_sigils(rule.get("do", []), ctx)
            from daydream import retell

            effs = await retell.retell_effects(actor.world_id, effs)
            effects.dispatch_effects(
                effs, actor_id=actor.id, room_id=room_id,
                world_id=actor.world_id, allowed=effects.RULE_KINDS,
            )
            fired = True
            if rule.get("stop", True):
                return True
    return fired


# ---- validation (format-2 load path; named errors, zero writes) -------------

# Aux keys permitted per discriminator, beyond the discriminator itself.
_CONDITION_AUX: dict[str, frozenset[str]] = {
    "flag": frozenset({"eq"}),
    "prop": frozenset({"of", *OPS}),
    "counter": frozenset(OPS),
    "score": frozenset(),
    "carrying_count": frozenset(),
    "dobj": frozenset(),
    "iobj": frozenset(),
    "carried": frozenset(),
    "carried_filter": frozenset(),
    "only_carrying": frozenset(),
    "empty_handed": frozenset(),
    "in": frozenset(),
    "chance": frozenset({"purpose"}),
    "present": frozenset(),
    "contains": frozenset({"of"}),
    "in_vehicle": frozenset(),
    "rel": frozenset(OPS),
    "pcounter": frozenset(OPS),
    "arc": frozenset(OPS),
    "helpers": frozenset(OPS),
    "pflag": frozenset({"eq"}),
    "beat": frozenset({"by"}),
    "ending": frozenset(),
    "helped": frozenset(),
    "phase": frozenset(),
    "day": frozenset(),
    "knows": frozenset({"who", "about"}),
    "collected": frozenset({"page"}),
}

# Effect-dict keys that reference objects/rooms and so must cross-validate
# against the world's known ids (sigils always pass).
_EFFECT_ID_FIELDS = ("object_id", "dest_id", "target_id", "room_id", "actor_id",
                     "location_id", "toon_id", "npc")


def _check_ref(value, known_ids: set[str], errors: list[str], where: str) -> None:
    if isinstance(value, str) and value not in SIGILS and value not in known_ids:
        errors.append(f"{where}: dangling reference {value!r}")


def validate_condition_list(
    conds, where: str, *, known_flags: set[str], known_ids: set[str],
    known_story: dict | None = None,
) -> list[str]:
    """Named errors for one authored condition list (a rule's `if`, an
    exit's `if`, a room's `enter_if`, a script daemon's `if`). With
    `known_story` ({arcs, beats, endings, facts, pflags, pcounters, pages}),
    story references are closed too."""
    errors: list[str] = []
    if conds is None:
        return errors
    if not isinstance(conds, list):
        return [f"{where}: must be a list"]
    for cidx, cond in enumerate(conds):
        cwhere = f"{where}[{cidx}]"
        if not isinstance(cond, dict):
            errors.append(f"{cwhere}: condition must be an object")
            continue
        discs = [k for k in CONDITION_KEYS if k in cond]
        # `in` doubles as prop/counter's membership operator; it is a
        # discriminator only when no higher-precedence form claimed it.
        if "in" in discs and any(d in cond for d in _IN_OWNERS):
            discs.remove("in")
        if len(discs) != 1:
            errors.append(
                f"{cwhere}: expected exactly one condition key, got {sorted(cond)}"
            )
            continue
        disc = discs[0]
        # "not" inverts any condition form.
        allowed_keys = {disc, "not"} | _CONDITION_AUX[disc]
        unknown = set(cond) - allowed_keys
        if unknown:
            errors.append(
                f"{cwhere}: unknown condition key(s) {sorted(unknown)} for {disc!r}"
            )
        if disc == "flag" and cond.get("flag") not in known_flags:
            errors.append(f"{cwhere}: undeclared flag {cond.get('flag')!r}")
        if disc in ("dobj", "iobj", "carried", "present", "in"):
            _check_ref(cond.get(disc), known_ids, errors, cwhere)
        if disc == "contains":
            _check_ref(cond.get("contains"), known_ids, errors, cwhere)
            _check_ref(cond.get("of", "@self"), known_ids, errors, cwhere)
        if disc == "prop":
            _check_ref(cond.get("of", "@self"), known_ids, errors, cwhere)
        if disc == "in_vehicle" and isinstance(cond.get("in_vehicle"), str):
            _check_ref(cond.get("in_vehicle"), known_ids, errors, cwhere)
        if disc in ("rel",):
            _check_ref(cond.get("rel"), known_ids, errors, cwhere)
        if disc == "knows":
            _check_ref(cond.get("who", "@self"), known_ids, errors, cwhere)
            if "about" in cond:
                _check_ref(cond["about"], known_ids, errors, cwhere)
        if disc in ("day", "collected") and not isinstance(cond.get(disc), dict):
            errors.append(f"{cwhere}: {disc!r} takes an {{op: N}} object")
        if known_story is not None:
            errors.extend(_story_ref_errors(disc, cond, known_story, cwhere))
    return errors


def _story_ref_errors(disc: str, cond: dict, ks: dict, where: str) -> list[str]:
    errs: list[str] = []
    if disc == "arc" and cond.get("arc") not in ks.get("arcs", set()):
        errs.append(f"{where}: unknown arc {cond.get('arc')!r}")
    if disc == "helpers" and cond.get("helpers") not in ks.get("arcs", set()):
        errs.append(f"{where}: unknown arc {cond.get('helpers')!r}")
    if disc == "helped" and cond.get("helped") not in ks.get("arcs", set()):
        errs.append(f"{where}: unknown arc {cond.get('helped')!r}")
    if disc == "beat" and cond.get("beat") not in ks.get("beats", set()):
        errs.append(f"{where}: unknown beat {cond.get('beat')!r} (use 'arc/beat')")
    if disc == "ending" and cond.get("ending") not in ks.get("endings", set()):
        errs.append(f"{where}: unknown ending {cond.get('ending')!r} (use 'arc/ending')")
    if disc == "knows" and cond.get("knows") not in ks.get("facts", set()):
        errs.append(f"{where}: unknown fact {cond.get('knows')!r}")
    if disc == "pflag" and cond.get("pflag") not in ks.get("pflags", set()):
        errs.append(f"{where}: undeclared player flag {cond.get('pflag')!r}")
    if disc == "pcounter" and cond.get("pcounter") not in ks.get("pcounters", set()):
        errs.append(f"{where}: undeclared player counter {cond.get('pcounter')!r}")
    if disc == "collected" and "page" in cond and cond["page"] not in ks.get("pages", set()):
        errs.append(f"{where}: unknown page {cond['page']!r}")
    if disc == "phase":
        ph = cond.get("phase")
        phases = ph if isinstance(ph, list) else [ph]
        for x in phases:
            if x not in ("dawn", "day", "dusk", "night", "stopped"):
                errs.append(f"{where}: unknown phase {x!r}")
    return errs


def validate_effect_list(
    effs, where: str, *,
    known_flags: set[str], known_ids: set[str],
    known_fuses: set[str], known_daemons: set[str],
    require_nonempty: bool = False,
    allow_inline_if: bool = False,
    known_story: dict | None = None,
) -> list[str]:
    """Named errors for one authored effect list (a rule's `do`, a fuse's
    `do`, a daemon's `do`, an exit's `on_traverse` — the last with inline
    per-effect `if` allowed)."""
    errors: list[str] = []
    if not isinstance(effs, list) or (require_nonempty and not effs):
        return [f"{where}: must be a non-empty list" if require_nonempty
                else f"{where}: must be a list"]
    for eidx, eff in enumerate(effs):
        ewhere = f"{where}[{eidx}]"
        if not isinstance(eff, dict):
            errors.append(f"{ewhere}: effect must be an object")
            continue
        if allow_inline_if and "if" in eff:
            errors.extend(validate_condition_list(
                eff["if"], f"{ewhere}.if",
                known_flags=known_flags, known_ids=known_ids,
                known_story=known_story,
            ))
        elif "if" in eff:
            errors.append(f"{ewhere}: inline 'if' not allowed here")
        kind = eff.get("kind")
        if kind not in effects.RULE_KINDS:
            errors.append(f"{ewhere}: effect kind {kind!r} not in RULE_KINDS")
            continue
        if kind == "set_flag" and eff.get("name") not in known_flags:
            errors.append(f"{ewhere}: undeclared flag {eff.get('name')!r}")
        if kind in ("start_fuse", "stop_fuse") and eff.get("name") not in known_fuses:
            errors.append(f"{ewhere}: undeclared fuse {eff.get('name')!r}")
        if kind in ("start_daemon", "stop_daemon") \
                and eff.get("name") not in known_daemons:
            errors.append(f"{ewhere}: undeclared daemon {eff.get('name')!r}")
        for field in _EFFECT_ID_FIELDS:
            if field in eff:
                _check_ref(eff[field], known_ids, errors, f"{ewhere}.{field}")
        errors.extend(_story_effect_errors(kind, eff, known_story, ewhere))
    return errors


def _story_effect_errors(kind: str, eff: dict, ks: dict | None, where: str) -> list[str]:
    """Shape + closure checks for the story effect kinds (SPEC 2026-09-26)."""
    errs: list[str] = []
    if kind == "narrate":
        has_text = isinstance(eff.get("text"), str) and eff["text"].strip()
        vs = eff.get("variants")
        has_vars = isinstance(vs, list) and vs and all(
            isinstance(v, str) and v.strip() for v in vs)
        if not has_text and not has_vars:
            errs.append(f"{where}: narrate needs 'text' or non-empty 'variants'")
    if kind in ("adjust_rel",):
        if not isinstance(eff.get("npc"), str):
            errs.append(f"{where}: adjust_rel needs 'npc'")
        if not isinstance(eff.get("delta"), int):
            errs.append(f"{where}: adjust_rel needs an int 'delta'")
    if kind in ("set_pflag", "adjust_pcounter"):
        name = eff.get("name")
        if not isinstance(name, str) or not name.strip():
            errs.append(f"{where}: {kind} needs 'name'")
        elif ks is not None:
            pool = ks.get("pflags" if kind == "set_pflag" else "pcounters", set())
            if name not in pool:
                errs.append(f"{where}: undeclared player "
                            f"{'flag' if kind == 'set_pflag' else 'counter'} {name!r}")
        if kind == "adjust_pcounter" and not isinstance(eff.get("delta"), int):
            errs.append(f"{where}: adjust_pcounter needs an int 'delta'")
    if kind in ("open_arc", "advance_beat", "close_arc"):
        arc = eff.get("arc")
        if not isinstance(arc, str):
            errs.append(f"{where}: {kind} needs 'arc'")
        elif ks is not None and arc not in ks.get("arcs", set()):
            errs.append(f"{where}: unknown arc {arc!r}")
        if kind == "advance_beat" and ks is not None \
                and f"{arc}/{eff.get('beat')}" not in ks.get("beats", set()):
            errs.append(f"{where}: unknown beat {arc}/{eff.get('beat')}")
        if kind == "close_arc" and ks is not None \
                and f"{arc}/{eff.get('ending')}" not in ks.get("endings", set()):
            errs.append(f"{where}: unknown ending {arc}/{eff.get('ending')}")
    if kind == "add_fact":
        if not isinstance(eff.get("id"), str) or not isinstance(eff.get("text"), str):
            errs.append(f"{where}: add_fact needs string 'id' and 'text'")
        kb = eff.get("known_by", [])
        if not (kb == "all" or isinstance(kb, list)):
            errs.append(f"{where}: add_fact known_by must be a list or 'all'")
        for st in eff.get("spread") or []:
            if not (isinstance(st, dict) and isinstance(st.get("after_minutes"), (int, float))
                    and (st.get("to") == "all" or isinstance(st.get("to"), list))):
                errs.append(f"{where}: add_fact spread stages are "
                            "{to: [ids]|'all', after_minutes: N}")
    if kind == "grant_collectible":
        cid = eff.get("id")
        if cid is not None and ks is not None and cid not in ks.get("collectibles", set()):
            errs.append(f"{where}: unknown collectible {cid!r}")
    if kind == "run_phase" and eff.get("phase") not in ("dawn", "day", "dusk", "night"):
        errs.append(f"{where}: run_phase needs a phase")
    if kind == "move_toon":
        if not isinstance(eff.get("toon_id"), str):
            errs.append(f"{where}: move_toon needs 'toon_id'")
        if "room_id" not in eff:
            errs.append(f"{where}: move_toon needs 'room_id' (null sends offstage)")
    if kind == "spawn_template":
        t = eff.get("template")
        if not isinstance(t, str):
            errs.append(f"{where}: spawn_template needs 'template'")
        elif ks is not None and t not in ks.get("templates", set()):
            errs.append(f"{where}: unknown template {t!r}")
    return errs


def validate_rules(
    rule_list,
    *,
    source: str,
    known_verbs: set[str],
    known_flags: set[str],
    known_ids: set[str],
    known_fuses: set[str],
    known_daemons: set[str],
    known_story: dict | None = None,
) -> list[str]:
    """Validate one authored rule list. Returns named errors (empty = valid);
    the format-2 loader refuses the world on any error, with zero writes.
    Closure checks: every `on` names a declared verb (or `enter`); every
    condition uses a known discriminator with only its allowed aux keys;
    flags, fuses, daemons, and object/room references must be declared."""
    errors: list[str] = []
    if not isinstance(rule_list, list):
        return [f"{source}: rules must be a list"]
    for idx, rule in enumerate(rule_list):
        where = f"{source}[{idx}]"
        if not isinstance(rule, dict):
            errors.append(f"{where}: rule must be an object")
            continue
        on = rule.get("on")
        if not isinstance(on, str) or (on not in known_verbs and on != "enter"):
            errors.append(f"{where}: unknown verb {on!r} in 'on'")
        if rule.get("as") not in (None, "dobj", "iobj"):
            errors.append(f"{where}: 'as' must be 'dobj' or 'iobj'")
        errors.extend(validate_condition_list(
            rule.get("if", []), f"{where}.if",
            known_flags=known_flags, known_ids=known_ids,
            known_story=known_story,
        ))
        errors.extend(validate_effect_list(
            rule.get("do", []), f"{where}.do",
            known_flags=known_flags, known_ids=known_ids,
            known_fuses=known_fuses, known_daemons=known_daemons,
            require_nonempty=True, known_story=known_story,
        ))
        for bkey in ("stop", "after"):
            if bkey in rule and not isinstance(rule[bkey], bool):
                errors.append(f"{where}: '{bkey}' must be a boolean")
        unknown_rule_keys = set(rule) - {"on", "as", "if", "do", "stop", "after"}
        if unknown_rule_keys:
            errors.append(f"{where}: unknown rule key(s) {sorted(unknown_rule_keys)}")
    return errors
