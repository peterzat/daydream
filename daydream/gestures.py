"""Gestures are social (spec 2026-09-29 criterion 2).

"hug the keeper" was heard as speech ("<you> says to <them>: "hug"") and
answered by the model. A gesture is an act the room sees: the actor reads it
in the second person ("You hug <them>."), everyone else in the third ("<you>
hugs <them>."), and a dreamer who is its target reads it addressed to them
("<you> hugs you."). A resident answers from its authored reaction pool
(`properties.reactions`: {gesture or "default": [{text, others}]}, loader-
validated), a guest or anyone else without one from the world's
`config.gestures.npc_default`, a thing with `config.gestures.thing`. No model
call anywhere.

The tellings here are plain English with no world names (the engine purity
gate reads this file); the world supplies every line a resident speaks."""

from __future__ import annotations

import re

from daydream import events, objects, variants

# gesture -> (you-form, they-form, alone: may it be done at no one?)
GESTURES: dict[str, tuple[str, str, bool]] = {
    "hug": ("hug", "hugs", False),
    "wave": ("wave to", "waves to", True),
    "thank": ("thank", "thanks", False),
    "bow": ("bow to", "bows to", True),
    "nod": ("nod to", "nods to", True),
    "smile": ("smile at", "smiles at", True),
    "wink": ("wink at", "winks at", True),
    "curtsy": ("curtsy to", "curtsies to", True),
    "salute": ("salute", "salutes", True),
    "high-five": ("high-five", "high-fives", False),
    "shake hands": ("shake hands with", "shakes hands with", False),
    "gesture": ("gesture to", "gestures to", True),
}

# The words players type for each gesture.
WORDS: dict[str, str] = {
    "hug": "hug", "embrace": "hug", "wave": "wave", "thank": "thank", "thanks": "thank",
    "thank you": "thank", "bow": "bow", "nod": "nod", "smile": "smile", "grin": "smile",
    "wink": "wink", "curtsy": "curtsy", "curtsey": "curtsy", "salute": "salute",
    "high five": "high-five", "high-five": "high-five", "hi five": "high-five",
    "hi-five": "high-five", "shake hands": "shake hands",
}
_WORD_RE = "|".join(sorted((re.escape(w) for w in WORDS), key=len, reverse=True))
_PLAIN = re.compile(rf"(?i)^(?P<g>{_WORD_RE})(?:\s+(?:to|at|with))?(?:,?\s+(?P<who>.+?))?[.!]*$")
_GIVE = re.compile(
    rf"(?i)^(?:give|offer)\s+(?P<who>.+?)\s+an?\s+(?P<g>{_WORD_RE})[.!]*$")
_GIVE_TO = re.compile(
    rf"(?i)^(?:give|offer)\s+an?\s+(?P<g>{_WORD_RE})\s+to\s+(?P<who>.+?)[.!]*$")


def match(text: str) -> tuple[str, str | None] | None:
    """(gesture, the name it was aimed at or None), or None when the line is
    not a gesture."""
    t = text.strip()
    for pattern in (_GIVE_TO, _GIVE, _PLAIN):
        m = pattern.match(t)
        if m:
            who = (m.group("who") or "").strip() or None
            return WORDS[m.group("g").lower()], who
    return None


def _say(room_id: str, text: str, *, to: str | None = None,
         leave_out: list[str] | None = None) -> None:
    payload: dict = {"text": text}
    if leave_out:
        payload["except"] = leave_out if len(leave_out) > 1 else leave_out[0]
    events.append("system", None, "narrate", payload, room_id=room_id, recipient_id=to)


def _the(obj: objects.Object) -> str:
    from daydream import verbs

    return verbs._the(obj)


def _config(world_id: str) -> dict:
    from daydream import worldstate

    cfg = worldstate.get(world_id, "config")
    g = cfg.get("gestures") if isinstance(cfg, dict) else None
    return g if isinstance(g, dict) else {}


def _reaction(npc: objects.Object, gesture: str, actor: objects.Object) -> dict | None:
    """The resident's reaction to this gesture ({text, others}), told in turn
    so it never repeats among the recent tellings; the world's default for
    an NPC with no pool of its own."""
    pool = npc.properties.get("reactions")
    options = None
    if isinstance(pool, dict):
        options = pool.get(gesture) or pool.get("default")
    if not options:
        options = _config(npc.world_id).get("npc_default")
    if not isinstance(options, list) or not options:
        return None
    texts = [o.get("text", "") for o in options if isinstance(o, dict)]
    chosen = variants.pick(npc.world_id, f"react:{npc.id}:{gesture}", texts, room_id=None)
    if chosen is None:
        return None
    entry = next(o for o in options if isinstance(o, dict) and o.get("text", "").strip() == chosen)
    fill = {"{actor}": actor.name, "{npc}": npc.name}

    def filled(s: str) -> str:
        for k, v in fill.items():
            s = s.replace(k, v)
        return s

    return {"text": filled(entry.get("text", "")), "others": filled(entry.get("others", ""))}


def perform(actor: objects.Object, room_id: str, gesture: str,
            target: objects.Object | None) -> None:
    """Tell a gesture to everyone it reaches, then its answer."""
    you, they, alone = GESTURES[gesture]
    if target is None or target.id == actor.id:
        if not alone:
            _say(room_id, f"{you[:1].upper()}{you[1:]} whom?", to=actor.id)
            return
        base_you, base_they = you.split()[0], they.split()[0]
        _say(room_id, f"You {base_you}.", to=actor.id)
        _say(room_id, f"{actor.name} {base_they}.", leave_out=[actor.id])
        return
    if target.kind == "thing":
        name = _the(target)
        lines = _config(actor.world_id).get("thing")
        text = f"You {you} {name}."
        if isinstance(lines, list) and lines:
            extra = variants.pick(actor.world_id, f"gesture-thing:{gesture}", [
                str(line).replace("{the_thing}", name) for line in lines])
            if extra:
                text = f"{text} {extra}"
        _say(room_id, text, to=actor.id)
        _say(room_id, f"{actor.name} {they} {name}.", leave_out=[actor.id])
        return
    # Someone.
    _say(room_id, f"You {you} {target.name}.", to=actor.id)
    if target.is_player:
        _say(room_id, f"{actor.name} {they} you.", to=target.id)
        _say(room_id, f"{actor.name} {they} {target.name}.", leave_out=[actor.id, target.id])
        from daydream.api import ws as ws_mod

        if ws_mod.is_dozing(target):
            _say(room_id, f"{target.name} is dozing, far off in a dream of their own, "
                 "and doesn't stir.", to=actor.id)
        return
    _say(room_id, f"{actor.name} {they} {target.name}.", leave_out=[actor.id])
    reaction = _reaction(target, gesture, actor)
    if reaction and reaction["text"].strip():
        _say(room_id, reaction["text"], to=actor.id)
        if reaction["others"].strip():
            _say(room_id, reaction["others"], leave_out=[actor.id])


def validate_reactions(pool, where: str) -> list[str]:
    """Named errors for an authored `reactions` pool (the loader)."""
    if not isinstance(pool, dict):
        return [f"{where} must be an object of gesture -> lines"]
    errors: list[str] = []
    if "default" not in pool:
        errors.append(f"{where} needs a 'default' list")
    for key, lines in pool.items():
        if key != "default" and key not in GESTURES:
            errors.append(f"{where}.{key}: unknown gesture (one of {sorted(GESTURES)} or default)")
        if not (isinstance(lines, list) and lines and all(
                isinstance(x, dict) and isinstance(x.get("text"), str) and x["text"].strip()
                and isinstance(x.get("others"), str) and "{actor}" in x["others"]
                for x in lines)):
            errors.append(f"{where}.{key} must be a list of {{text, others}} with {{actor}} "
                          "in each others line")
    return errors
