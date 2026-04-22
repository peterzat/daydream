"""Core skills: look, say, examine. Pure Python, no LLM, deterministic.

Each handler appends one or more events via the event log and returns them.
Args is the free-text remainder after the skill name (e.g., for
"examine the lantern", args is "the lantern").
"""

from daydream import events, items, rooms

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
