"""Someone named who isn't here (spec 2026-09-29 criterion 1).

Asking after a resident who was in another room fell to the model parser,
which can only ground to who is present, and the resident standing here
answered in the absent one's place. A name that belongs to a toon of this world who
is not in scope now answers that they aren't here, and where they are just
now: a resident's room, a dreamer's dream or rest. No model call; the ask
fast path and the executor's named-but-not-here branch both come here."""

from __future__ import annotations

import re

from daydream import objects

_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _norm(name: str) -> str:
    return _ARTICLE.sub("", re.sub(r"\s+", " ", (name or "").strip().lower())).strip(" .,!?")


def elsewhere(actor: objects.Object, name: str) -> objects.Object | None:
    """The one toon of the actor's world named `name` (its name or an alias,
    exactly) who is not in scope; None when there is none, or more than one,
    or they are here."""
    want = _norm(name)
    if not want:
        return None
    here = {o.id for o in objects.in_scope(actor.id)}
    found = [t for t in objects.all_of_kind(actor.world_id, "toon")
             if t.id != actor.id and t.id not in here
             and want in {t.name.lower(), *(str(a).lower() for a in t.aliases)}]
    return found[0] if len(found) == 1 else None


def _where(room_id: str | None) -> str | None:
    room = objects.get(room_id) if room_id else None
    if room is None or room.kind != "room":
        return None
    from daydream import toons

    at = room.properties.get("at")
    at = at if at in ("in", "on", "at") else "in"
    return f"{at} {toons.in_sentence(room.properties.get('title', room.name))}"


def line(who: objects.Object) -> str:
    """Where they are, told plainly: "<Name> isn't here; <Name> is in the
    <room> just now." A guest not yet arrived, or gone home, isn't here."""
    if who.is_player:
        if who.kicked_at is not None or not who.is_human_controlled:
            return f"{who.name} isn't here; {who.name} is resting, out of the dream just now."
        where = _where(who.location_id)
        return (f"{who.name} isn't here; {who.name} is dreaming {where} just now." if where
                else f"{who.name} isn't here.")
    where = _where(who.location_id)
    return f"{who.name} isn't here; {who.name} is {where} just now." if where \
        else f"{who.name} isn't here."
