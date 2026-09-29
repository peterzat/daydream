"""Letters between dreamers (beta rehearsal 2026-09-28).

A household playing on different schedules had no way to leave each other
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
    "parcel_text": "You leave the {item} to be kept for {to}. It will be there when they next come by.",
    "parcel_others": "{actor} leaves the {item} to be kept for {to}.",
    "inbox_text": "There is post for you, {name}: {count}, from {senders}. It waits here.",
    "inbox_empty_text": "Nothing has come for you, {name}. Not yet.",
    "dozing_hint": "",
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
    """An authored telling (a string, or a list of variants picked by the
    world's no-verbatim-repeat rule), with {fields} filled."""
    text = post.get(key)
    if isinstance(text, list):
        options = [t for t in text if isinstance(t, str) and t.strip()]
        if options:
            from daydream import variants

            text = variants.pick(_world_id_for(post), f"post:{key}", options, post.get("room"))
        else:
            text = None
    if not isinstance(text, str) or not text.strip():
        text = _DEFAULTS[key]
    for k, v in fields.items():
        text = text.replace("{" + k + "}", v)
    return text


def _world_id_for(post: dict) -> str:
    room = objects.get(str(post.get("room") or ""))
    return room.world_id if room is not None else toons.live_world_id()


_INBOX_RE = re.compile(
    r"\b(post|letters?|mail|anything|something|a note)\b[^.?!]*\bfor me\b"
    r"|\bmy (post|letters?|mail|pigeonhole)\b|\bpost for\b|\banything (in|come in) for\b", re.I)


def is_inbox_ask(text: str) -> bool:
    """"post for me", "my letters", "anything for me": an inbox question."""
    return bool(_INBOX_RE.search(text or ""))


def inbox(actor: objects.Object, npc: objects.Object, room_id: str) -> bool:
    """The post keeper, asked for the player's post: what waits, by sender,
    or that nothing does (beta rehearsal 2026-09-28: no way to ask). Private
    to the asker; authored `inbox_text` / `inbox_empty_text`."""
    post = config_for(actor.world_id)
    if post is None or post.get("keeper") != npc.id:
        return False
    waiting = letters_waiting(actor.id)
    if waiting:
        senders = []
        for o in waiting:
            letter = o.properties.get("letter") or {}
            name = letter.get("from_name") or "someone"
            if name not in senders:
                senders.append(name)
        text = _line(post, "inbox_text", name=actor.name, senders=_join(senders),
                     count=_count_word(len(waiting)))
    else:
        text = _line(post, "inbox_empty_text", name=actor.name)
    _narrate(room_id, text, to=actor.id)
    return True


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _count_word(n: int) -> str:
    words = ["none", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    return words[n] if n < len(words) else str(n)


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


_FOR_RE = re.compile(r"(?i)^\s*for\s+(\S.*?)\s*$")


def for_whom(args: str) -> str | None:
    """The someone in a give's "for <name>" (the parser's args), or None."""
    m = _FOR_RE.match(args or "")
    return m.group(1) if m else None


def file_parcel(actor: objects.Object, keeper: objects.Object, thing: objects.Object,
                to_name: str, room_id: str, allowed) -> bool:
    """`give <thing> to <post keeper> for <dreamer>`: the keeper files a
    thing the way a letter is filed, private to the one it is for, told on
    their arrival and listed in their threads (beta rehearsal 2026-09-28: a
    friend left a brass hand and a bookmark in the dead-letter drawer, and
    the world kept them but not who they were for). Returns False, and files
    nothing, on every refusal (told in the keeper's words)."""
    from daydream.skills import effects

    post = config_for(actor.world_id)
    if post is None or post.get("keeper") != keeper.id:
        return False
    if to_name.lower() == actor.name.lower() or to_name.lower() in ("me", "myself"):
        _narrate(room_id, _line(post, "self_text"), to=actor.id)
        return True
    to = next((p for p in _players(actor.world_id) if p.name.lower() == to_name.lower()), None)
    if to is None:
        _narrate(room_id, _line(post, "unknown_text", to=to_name), to=actor.id)
        return True
    if thing.properties.get("private_to"):
        _narrate(room_id, f"The {thing.name} is yours alone; it won't pass to other hands.",
                 to=actor.id)
        return True
    at = worldclock.iso()
    effects.dispatch_effects([
        {"kind": "move_object", "object_id": thing.id, "dest_id": post["room"]},
        {"kind": "set_property", "target_id": thing.id, "key": "private_to", "value": to.id},
        {"kind": "set_property", "target_id": thing.id, "key": "letter",
         "value": {"from": actor.id, "from_name": actor.name, "to": to.id, "at": at,
                   "parcel": True}},
        {"kind": "narrate", "to": "@actor",
         "text": _line(post, "parcel_text", item=thing.name, to=to.name),
         "others": _line(post, "parcel_others", item=thing.name, to=to.name)},
    ], actor_id=actor.id, room_id=room_id, world_id=actor.world_id,
        allowed=allowed | frozenset({"set_property", "move_object"}))
    logger.info("post: %s left %s for %s", actor.name, thing.name, to.name)
    _ring_for(to, post)
    return True


def on_taken(thing: objects.Object) -> None:
    """A parcel taken by the one it was for is theirs to do with as they
    like again: no longer private, no longer post. Letters stay private."""
    letter = thing.properties.get("letter")
    if isinstance(letter, dict) and letter.get("parcel"):
        objects.set_property(thing.id, "private_to", None)
        objects.set_property(thing.id, "letter", None)


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


def arrival_notes(toon_id: str) -> list[str]:
    """The waiting_text once per letter, on the first connection after it
    was filed (each letter is marked told; the thread keeps listing it until
    it is taken). Beta rehearsal 2026-09-28: the note printed on every
    reconnect, fourteen times in a morning."""
    fresh = [o for o in letters_waiting(toon_id) if not (o.properties.get("letter") or {}).get("told")]
    if not fresh:
        return []
    for o in fresh:
        letter = dict(o.properties.get("letter") or {})
        letter["told"] = True
        objects.set_property(o.id, "letter", letter)
    toon = objects.get(toon_id)
    post = config_for(toon.world_id) if toon is not None else None
    return [_line(post or {}, "waiting_text")]


def thread_lines(toon_id: str) -> list[str]:
    """What the satchel and "what now" add while post waits: the world's
    `waiting_text`, once."""
    waiting = letters_waiting(toon_id)
    if not waiting:
        return []
    toon = objects.get(toon_id)
    post = config_for(toon.world_id) if toon is not None else None
    return [_line(post or {}, "waiting_text")]
