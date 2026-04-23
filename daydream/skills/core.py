"""Core skills: look, say, examine, go. Pure Python, no LLM, deterministic.

Each handler appends one or more events via the event log and returns them.
Args is the free-text remainder after the skill name (e.g., for
"examine the lantern", args is "the lantern").
"""

from daydream import events, items, rooms, toons

_LEADING_ARTICLES = ("the ", "a ", "an ")


def _strip_article(text: str) -> str:
    t = text.strip().lower()
    for art in _LEADING_ARTICLES:
        if t.startswith(art):
            return t[len(art) :].strip()
    return t


def look(actor_id: str, room_id: str, args: str) -> list[events.Event]:
    """Describe the current room. Ignores args."""
    room = rooms.get_room(room_id)
    if room is None:
        return [
            events.append(
                "system", None, "narrate",
                {"text": "You are nowhere recognizable."},
                room_id=room_id,
            )
        ]
    text = room.description_cached or f"You are in {room.title}."
    item_list = items.get_items_in_room(room_id)
    if item_list:
        text += " You see: " + ", ".join(it.name for it in item_list) + "."
    return [events.append("system", None, "narrate", {"text": text}, room_id=room_id)]


def say(actor_id: str, room_id: str, args: str) -> list[events.Event]:
    """Speak text aloud. Empty args produces a gentle prompt rather than an event."""
    text = args.strip()
    if not text:
        return [
            events.append(
                "system", None, "narrate",
                {"text": "Say what?"},
                room_id=room_id,
            )
        ]
    return [events.append("toon", actor_id, "say", {"text": text}, room_id=room_id)]


def examine(actor_id: str, room_id: str, args: str) -> list[events.Event]:
    """Examine a named item in the current room.

    The item's stored seed is echoed in the narration so the LLM-free path
    remains deterministic (SPEC criterion 5 verifies a sentinel string in the
    seed reaches the player verbatim)."""
    target = _strip_article(args)
    if not target:
        return [
            events.append(
                "system", None, "narrate",
                {"text": "Examine what?"},
                room_id=room_id,
            )
        ]
    item = items.find_item_in_room_by_name(room_id, target)
    if item is None:
        return [
            events.append(
                "system", None, "narrate",
                {"text": f"You don't see {target} here."},
                room_id=room_id,
            )
        ]
    text = f"You examine the {item.name}: {item.seed}."
    return [events.append("system", None, "narrate", {"text": text}, room_id=room_id)]


def go(actor_id: str, room_id: str, args: str) -> list[events.Event]:
    """Move the toon through an exit. Args is a direction name.

    Happy path: `args` matches a key in the current room's exits_json
    (case-insensitive, whitespace-tolerated). The toon's
    current_room_id is updated to the target room and a `move` event
    is emitted with `from_room`, `to_room`, and `direction` in the
    payload. The event's `room_id` is the DEPARTURE room so broadcast
    filters in the WS layer route it correctly.

    Failure: unknown direction or empty args -> a `narrate` event and
    no state mutation. The room stays the same.

    The WS layer detects move events for the controlled toon and
    pushes a fresh state_snapshot so the client flips to the new
    room's title/description/exits without reconnecting."""
    direction = args.strip().lower()
    if not direction:
        return [
            events.append(
                "system", None, "narrate",
                {"text": "Go where?"},
                room_id=room_id,
            )
        ]
    room = rooms.get_room(room_id)
    if room is None:
        return [
            events.append(
                "system", None, "narrate",
                {"text": "You are nowhere recognizable."},
                room_id=room_id,
            )
        ]
    target_id = room.exits.get(direction)
    if target_id is None:
        return [
            events.append(
                "system", None, "narrate",
                {"text": f"You can't go {direction} from here."},
                room_id=room_id,
            )
        ]
    toons.set_current_room(actor_id, target_id)
    return [
        events.append(
            "toon", actor_id, "move",
            {"from_room": room_id, "to_room": target_id, "direction": direction},
            room_id=room_id,
        )
    ]
