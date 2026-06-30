"""Effect allowlist + dispatcher for data skills.

A data skill's LLM response includes an `effects` list. The executor
calls `dispatch_effects()` to apply each one in order. Only effect
kinds enumerated in `ALLOWED_KINDS` are executed; any other kind is
dropped with a log warning and a narrate fallback is emitted in its
place so the player still sees *something* happen instead of silence.

v1 allowlist is deliberately small (narrate, add_item, set_mood).
Adding a new kind means: (1) append to `ALLOWED_KINDS`, (2) add a
handler to `_HANDLERS`, (3) extend the authored skill's
`effects_schema_json` so the LLM knows about it. The dispatcher
stays closed to dynamic dispatch — there is no plugin mechanism,
by design (SPEC criterion 4).

Out of scope for v1 (lands in BACKLOG `skills-authoring-and-security`):
strict per-effect jsonschema validation, per-player effect rate limits,
an `audit` table, and `bin/game world undo`. v1 trusts the allowlist +
the safety filter to keep things bounded."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from daydream import events, objects

logger = logging.getLogger(__name__)


ALLOWED_KINDS: frozenset[str] = frozenset({
    "narrate",
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
) -> list[AppliedEffect]:
    """Apply each effect in `effects_list` in order.

    Malformed entries (non-dicts) get a narrate fallback and are
    logged; unknown kinds (not in ALLOWED_KINDS) likewise get a
    fallback. Allowed kinds with invalid shapes (e.g. missing
    required fields) return `event=None` — tests assert nothing was
    mutated. Handler exceptions are caught and converted to a soft
    fallback so one bad effect doesn't poison the whole batch."""
    applied: list[AppliedEffect] = []
    for eff in effects_list:
        if not isinstance(eff, dict):
            logger.warning("dropping malformed effect entry: %r", eff)
            applied.append(AppliedEffect("(malformed)", _fallback_narrate(room_id)))
            continue
        kind = eff.get("kind")
        if not isinstance(kind, str) or kind not in ALLOWED_KINDS:
            logger.warning("dropping unknown effect kind: %r", kind)
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


_HANDLERS: dict[str, Callable[..., events.Event | None]] = {
    "narrate": _apply_narrate,
    "add_item": _apply_add_item,
    "set_mood": _apply_set_mood,
}
