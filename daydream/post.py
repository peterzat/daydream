"""Letters between dreamers (beta rehearsal 2026-09-28).

A family playing on different schedules had no way to leave each other
anything: speech is live and room-scoped, a dropped thing carries no words,
and a grown room never names its planter. This module is the engine half of
a world's post: at the room the world's `config.post` names, `write to
<dreamer>: <words>` files a letter for another dreamer, which waits there
as a thing only they can see, take and read (a keepsake: no home). The
recipient is told on their next arrival and in their threads, and at once,
privately, if they are awake somewhere in the dream.

Every line a player reads is authored in `config.post` (the room, who
keeps it, and the tellings); the engine's own fallbacks name nothing of any
world. A world with no `config.post` has no post: `write` says so.

    config.post = {
      "room": "r-post",                 # where letters are written and wait
      "write_text": "...{to}...",       # the writer's line (private)
      "write_others": "{actor} ...",    # what the room sees
      "elsewhere_text": "...",          # writing anywhere else
      "unknown_text": "...{to}...",     # no dreamer by that name
      "self_text": "...",               # a letter to yourself
      "resident_text": "...{to}...",    # a letter to a character
      "off_tone_text": "...",           # the tone banlist refused it
      "waiting_text": "...",            # the recipient's thread / arrival note
      "rings_text": "...",              # the recipient, awake elsewhere, at once
      "letter_name": "letter from {from}",
      "letter_seed": "...{from}...{to}...",
      "read_text": "...{from}...{to}...{text}..."
    }
"""

from __future__ import annotations

import logging
import re
import uuid

from daydream import events, objects, toons, worldclock, worldstate
from daydream.llm import safety

logger = logging.getLogger(__name__)

MAX_LETTER_CHARS = 500

_DEFAULTS = {
    "write_text": "You write it out, fold it twice, and leave it to be found. "
                  "It will be there when {to} next comes by.",
    "write_others": "{actor} writes something out, folds it twice, and leaves it "
                    "to be found.",
    "elsewhere_text": "There's nowhere to leave a letter here.",
    "unknown_text": "No dreamer here goes by {to}.",
    "self_text": "A letter to yourself would only find you here.",
    "resident_text": "{to} lives here; you can tell them yourself.",
    "off_tone_text": "That won't go in the post here.",
    "waiting_text": "A letter is waiting for you.",
    "rings_text": "Somewhere a bell rings twice: there is post for you.",
    "letter_name": "letter from {from}",
    "letter_seed": "a letter folded twice, addressed to {to} in {from}'s hand",
    "read_text": "From {from}, to {to}:\n\n{text}",
}

_NO_POST = "There's nowhere to post a letter in this dream."
_WRITE_WHAT = ("Write to whom, and what? Name a dreamer and your words, like this: "
               "write to <name>: <your words>.")
_TOO_LONG = "That is more than one letter can hold; say it in fewer words."

_LEAD = re.compile(r"^(?:a\s+)?(?:letter|note|message)?\s*(?:to|for)\s+", re.I)


def config_for(world_id: str) -> dict | None:
    cfg = worldstate.get(world_id, "config")
    post = cfg.get("post") if isinstance(cfg, dict) else None
    if not isinstance(post, dict) or not isinstance(post.get("room"), str):
        return None
    return post


def _line(post: dict, key: str, **fields: str) -> str:
    text = post.get(key)
    if not isinstance(text, str) or not text.strip():
        text = _DEFAULTS[key]
    for k, v in fields.items():
        text = text.replace("{" + k + "}", v)
    return text


def _players(world_id: str) -> list[objects.Object]:
    rows = toons._query("world_id = ? ORDER BY slot, id", (world_id,))
    out = []
    for t in rows:
        o = objects.get(t.id)
        if o is not None and o.is_player:
            out.append(o)
    return out


def split_address(args: str) -> tuple[str, str]:
    """`to Wren: hello` / `Wren, hello` / `a letter to Wren hello there` ->
    ("Wren", "hello ..."). The name is the first word or two before a colon
    or comma, else the first word."""
    text = (args or "").strip()
    text = _LEAD.sub("", text)
    for sep in (":", ",", " - ", " -- "):
        head, found, tail = text.partition(sep)
        if found and 0 < len(head.split()) <= 3:
            return head.strip(), tail.strip()
    words = text.split()
    if not words:
        return "", ""
    return words[0].strip(".!?"), " ".join(words[1:]).strip()


def _narrate(room_id: str, text: str, *, to: str | None, others: str | None = None,
             actor_id: str | None = None) -> None:
    from daydream.skills import effects

    events.append("system", None, "narrate", {"text": text}, room_id=room_id, recipient_id=to)
    if to is not None and others and actor_id:
        effects.tell_others(others, actor_id, room_id)


def write_letter(actor: objects.Object, room_id: str, args: str, allowed) -> bool:
    """The `write` verb: file a letter for another dreamer at the post room.
    Returns False on every refusal (nothing written)."""
    from daydream.skills import effects

    post = config_for(actor.world_id)
    if post is None:
        _narrate(room_id, _NO_POST, to=actor.id)
        return False
    if room_id != post["room"]:
        _narrate(room_id, _line(post, "elsewhere_text"), to=actor.id)
        return False
    name, text = split_address(args)
    if not name or not text:
        _narrate(room_id, _WRITE_WHAT, to=actor.id)
        return False
    if len(text) > MAX_LETTER_CHARS:
        _narrate(room_id, _TOO_LONG, to=actor.id)
        return False
    if name.lower() == actor.name.lower() or name.lower() in ("me", "myself"):
        _narrate(room_id, _line(post, "self_text"), to=actor.id)
        return False
    to = next((p for p in _players(actor.world_id) if p.name.lower() == name.lower()), None)
    if to is None:
        who = objects.find_all_in_scope_by_name(actor.id, name)
        resident = next((o for o in who if o.kind == "toon" and not o.is_player), None)
        if resident is None:
            for t in toons._query("world_id = ? AND is_human_controlled = 0 AND kicked_at IS NULL",
                                  (actor.world_id,)):
                if t.name.lower() == name.lower():
                    resident = objects.get(t.id)
                    break
        if resident is not None:
            _narrate(room_id, _line(post, "resident_text", to=resident.name), to=actor.id)
        else:
            _narrate(room_id, _line(post, "unknown_text", to=name), to=actor.id)
        return False
    if safety.first_banned(text) is not None:
        _narrate(room_id, _line(post, "off_tone_text"), to=actor.id)
        return False

    at = worldclock.iso()
    effects.dispatch_effects([
        {"kind": "spawn_object",
         "name": _line(post, "letter_name", **{"from": actor.name, "to": to.name}),
         "seed": _line(post, "letter_seed", **{"from": actor.name, "to": to.name}),
         "location_id": post["room"],
         "aliases": ["letter", "note", "post", f"{actor.name}'s letter",
                     f"letter from {actor.name}"],
         "verbs": ["read", "give"],
         "readable": True,
         # Unique per letter: the spawn dedup keys on name + place +
         # provenance, and two letters in one minute must both wait.
         "generated_by": f"post:{actor.id}:{uuid.uuid4().hex[:8]}",
         "properties": {
             "text": _line(post, "read_text", **{"from": actor.name, "to": to.name, "text": text}),
             "private_to": to.id,
             "home": None,
             "letter": {"from": actor.id, "from_name": actor.name, "to": to.id, "at": at},
         }},
        {"kind": "narrate", "to": "@actor",
         "text": _line(post, "write_text", to=to.name),
         "others": _line(post, "write_others", to=to.name)},
    ], actor_id=actor.id, room_id=room_id, world_id=actor.world_id, allowed=allowed)
    logger.info("post: %s wrote to %s (%d chars)", actor.name, to.name, len(text))
    _ring_for(to, post)
    return True


def _ring_for(to: objects.Object, post: dict) -> None:
    """The recipient, awake somewhere in the dream, hears at once (privately,
    in their own room). A resting or dozing dreamer is told on arrival."""
    try:
        from daydream.api import ws as ws_mod

        if not to.is_human_controlled or ws_mod.is_dozing(to) or not to.location_id:
            return
    except Exception:  # the WS layer is optional (tools, tests)
        return
    events.append("system", None, "narrate", {"text": _line(post, "rings_text")},
                  room_id=to.location_id, recipient_id=to.id)


def letters_waiting(toon_id: str) -> list[objects.Object]:
    """Letters filed for this dreamer that they have not yet taken."""
    toon = objects.get(toon_id)
    if toon is None:
        return []
    post = config_for(toon.world_id)
    if post is None:
        return []
    out = []
    for o in objects.contents_for(post["room"], toon_id, kind="thing"):
        letter = o.properties.get("letter")
        if isinstance(letter, dict) and letter.get("to") == toon_id:
            out.append(o)
    return out


def thread_lines(toon_id: str) -> list[str]:
    """What the satchel and "what now" add while post waits: the world's
    `waiting_text`, once."""
    waiting = letters_waiting(toon_id)
    if not waiting:
        return []
    toon = objects.get(toon_id)
    post = config_for(toon.world_id) if toon is not None else None
    return [_line(post or {}, "waiting_text")]
