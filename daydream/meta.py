"""Questions about the game, answered from state (spec 2026-09-29 criterion 4).

"what time is it", "who am I", "where can I go" used to reach the model
parser, which has no verb for them, and came back as a thought drifting by
(or, before the village opted out of it, a health report). They are
questions about the game, not actions in it, and the answers are already in
the state: the village's day and phase, the dreamer, the ways out. The
common phrasings are matched here with no model call; the parser's triage
sends paraphrases to the same answers (criterion 3)."""

from __future__ import annotations

import re

from daydream import objects, rooms

TIME_RE = re.compile(
    r"(?i)^(what('s| is)? the time|what time is it|what time|what day is it|what day|"
    r"how late is it|is it (day|night|dusk|dawn|morning|evening)( yet)?|what phase is it)[?.!]*$")
WHERE_RE = re.compile(
    r"(?i)^(where am i|where are we|where is this|what is this place|what place is this|"
    r"what's this place)[?.!]*$")
WHO_RE = re.compile(
    r"(?i)^(who am i|what am i|what do i look like|who is this|what('s| is) my name)[?.!]*$")
WAYS_RE = re.compile(
    r"(?i)^(where can i go|where can we go|which way|which ways|what are the exits|exits|"
    r"ways( out)?|ways from here|how do i get out|go somewhere else|where to|"
    r"where does this go|run|run away|walk|walk around|wander|wander off|stroll|explore)[?.!]*$")


def kind(text: str) -> str | None:
    """Which question a line is: "time", "where", "who", "ways", or None."""
    t = text.strip()
    for name, pattern in (("time", TIME_RE), ("where", WHERE_RE), ("who", WHO_RE),
                          ("ways", WAYS_RE)):
        if pattern.match(t):
            return name
    return None


def time_line(world_id: str) -> str:
    """The village's time as the page's folio shows it, in a sentence."""
    from daydream import village

    if not village.time_def(world_id):
        return "The dream keeps no clock you can read; it is simply now."
    st = village.status(world_id)
    if not st.get("running"):
        return "Time stands still here."
    return f"Day {st.get('day')} of the dream, and it's {st.get('label') or st.get('phase')}."


def _place(room_id: str | None) -> str | None:
    room = rooms.get_room(room_id) if room_id else None
    if room is None:
        return None
    title = room.title
    return "the " + title[4:] if title.startswith("The ") else title


def ways_line(toon_id: str) -> str:
    """The ways out of the dreamer's room, and where each leads."""
    from daydream import verbs

    actor = objects.get(toon_id)
    room = rooms.get_room(actor.location_id) if actor is not None else None
    if room is None:
        return "There's no way out that you can see just now."
    ways = []
    for direction, dest in verbs.visible_exits(room, actor).items():
        place = _place(dest) if isinstance(dest, str) else None
        ways.append(f"{direction} to {place}" if place else direction)
    if not ways:
        return "There's no way out that you can see just now."
    listed = ways[0] if len(ways) == 1 else ", ".join(ways[:-1]) + " or " + ways[-1]
    return f"From here you can go {listed}."
