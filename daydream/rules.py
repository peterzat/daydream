"""Declarative rule engine: authored, deterministic verb behavior as world
data (Zork turn, SPEC 2026-07-02 criterion 3).

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
    "prop", "counter", "score", "carrying_count", "flag", "dobj", "iobj",
    "carried", "carried_filter", "only_carrying", "empty_handed", "chance",
    "present", "contains", "in_vehicle", "in",
)


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
    if "in" in cond:
        return actor.location_id == _ref_id(cond["in"], ctx)

    logger.warning("unknown rule condition %r evaluates false", cond)
    return False


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


def dispatch(
    actor: objects.Object,
    verb_name: str,
    dobj: objects.Object | None,
    iobj: objects.Object | None,
    *,
    room_id: str,
) -> bool:
    """Run the first matching rule for `verb_name` (or the pseudo-event
    `enter`) across dobj -> iobj -> room -> world. Returns True if any rule
    fired (the caller then skips the legacy engine handler). Effects run
    under the RULE_KINDS allowlist with sigils resolved per holder."""
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
}

# Effect-dict keys that reference objects/rooms and so must cross-validate
# against the world's known ids (sigils always pass).
_EFFECT_ID_FIELDS = ("object_id", "dest_id", "target_id", "room_id", "actor_id", "location_id")


def _check_ref(value, known_ids: set[str], errors: list[str], where: str) -> None:
    if isinstance(value, str) and value not in SIGILS and value not in known_ids:
        errors.append(f"{where}: dangling reference {value!r}")


def validate_condition_list(
    conds, where: str, *, known_flags: set[str], known_ids: set[str]
) -> list[str]:
    """Named errors for one authored condition list (a rule's `if`, an
    exit's `if`, a room's `enter_if`, a script daemon's `if`)."""
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
        if "in" in discs and any(d in cond for d in ("prop", "counter")):
            discs.remove("in")
        if len(discs) != 1:
            errors.append(
                f"{cwhere}: expected exactly one condition key, got {sorted(cond)}"
            )
            continue
        disc = discs[0]
        allowed_keys = {disc} | _CONDITION_AUX[disc]
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
    return errors


def validate_effect_list(
    effs, where: str, *,
    known_flags: set[str], known_ids: set[str],
    known_fuses: set[str], known_daemons: set[str],
    require_nonempty: bool = False,
    allow_inline_if: bool = False,
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
    return errors


def validate_rules(
    rule_list,
    *,
    source: str,
    known_verbs: set[str],
    known_flags: set[str],
    known_ids: set[str],
    known_fuses: set[str],
    known_daemons: set[str],
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
        ))
        errors.extend(validate_effect_list(
            rule.get("do", []), f"{where}.do",
            known_flags=known_flags, known_ids=known_ids,
            known_fuses=known_fuses, known_daemons=known_daemons,
            require_nonempty=True,
        ))
        if "stop" in rule and not isinstance(rule["stop"], bool):
            errors.append(f"{where}: 'stop' must be a boolean")
        unknown_rule_keys = set(rule) - {"on", "as", "if", "do", "stop"}
        if unknown_rule_keys:
            errors.append(f"{where}: unknown rule key(s) {sorted(unknown_rule_keys)}")
    return errors
