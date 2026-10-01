"""While you were away (beta rehearsal 2026-09-28).

Nothing told a returning player what had changed since they last rested
unless the operator had run a dream: who else dreamed here, an hour sent
home, a place that grew, a guest that came. A household on different
schedules lives on exactly that. This composes it deterministically from
what the world already records (the raw input log, the chronicle, arc
state, grown rooms, the post), once, on the first connection after a rest,
and the page shows it as the same leaf a dream's note uses. Every name is
the world's own; the engine's words name nothing of any world.
"""

from __future__ import annotations

import logging

from daydream import db, objects, rooms, story, toons, worldclock

logger = logging.getLogger(__name__)

TITLE = "While you were away"

_WHERE = {"up": "above", "down": "below"}


def _after(stamp, since) -> bool:
    try:
        return worldclock.parse(str(stamp)) > worldclock.parse(str(since))
    except (ValueError, TypeError):
        return False


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _dreamers_since(world_id: str, toon_id: str, since: str) -> list[str]:
    rows = db.get_conn().execute(
        "SELECT DISTINCT toon_id FROM inputs WHERE world_id = ? AND toon_id != ? "
        "AND created_at > ? ORDER BY seq", (world_id, toon_id, since)).fetchall()
    out: list[str] = []
    for r in rows:
        t = objects.get(r["toon_id"])
        if t is not None and t.is_player and t.name not in out:
            out.append(t.name)
    return out


def _grown_since(world_id: str, since: str) -> list[str]:
    from daydream.growth import _REVERSE

    out: list[str] = []
    rows = db.get_conn().execute(
        "SELECT id FROM objects WHERE world_id = ? AND kind = 'room' "
        "AND json_extract(properties_json, '$.grown') IS NOT NULL ORDER BY rowid",
        (world_id,)).fetchall()
    for r in rows:
        obj = objects.get(r["id"])
        room = rooms.get_room(r["id"])
        grown = obj.properties.get("grown") if obj is not None else None
        if room is None or not (isinstance(grown, dict) and _after(grown.get("at"), since)):
            continue
        planter = objects.get(str(grown.get("planter_id") or ""))
        back, parent_id = next(iter(room.exits.items()), (None, None))
        parent = rooms.get_room(parent_id) if parent_id else None
        direction = _REVERSE.get(back or "", None)
        where = (f" {_WHERE.get(direction, 'to the ' + direction + ' of')} "
                 f"{toons.in_sentence(parent.title)}" if parent and direction else "")
        whose = f", from {planter.name}'s dreamseed" if planter is not None else ""
        out.append(f"A new place grew{where}: {toons.in_sentence(room.title)}{whose}.")
    return out


def _arrived_since(world_id: str, since: str) -> list[str]:
    out: list[str] = []
    for arc_id, arc in story.arcs_def(world_id).items():
        if not isinstance(arc, dict) or arc.get("kind") != "guest":
            continue
        st = story.arc_state(world_id, arc_id)
        if st.get("status") != "open" or not _after(st.get("opened_at"), since):
            continue
        guest = objects.get(str(arc.get("guest") or ""))
        if guest is None or not guest.location_id:
            continue
        here = rooms.get_room(guest.location_id)
        where = f" and waits in {toons.in_sentence(here.title)}" if here else ""
        out.append(f"{guest.name} has come to the village{where}.")
    return out


def _chronicle_since(world_id: str, since: str) -> list[str]:
    # A planted place is told by _grown_since, with whose seed it was.
    return [str(e.get("text", "")).strip() for e in story.chronicle(world_id)
            if _after(e.get("at"), since) and str(e.get("text", "")).strip()
            and e.get("kind") != "planted"]


def take_note(toon_id: str) -> dict | None:
    """The note for a player's first connection after a rest, once (the
    rest's stamp is read and cleared), or None when nothing changed."""
    toon = objects.get(toon_id)
    if toon is None or not toon.is_human_controlled:
        # A rested dreamer's own still-open page re-snapshots after the
        # leave (codereview 2026-09-29): the stamp keeps for their return.
        return None
    since = objects.get_property(toon_id, "away_since")
    if not isinstance(since, str) or not since:
        return None
    objects.set_property(toon_id, "away_since", None)
    world_id = toon.world_id
    try:
        lines: list[str] = []
        who = _dreamers_since(world_id, toon_id, since)
        if who:
            verb = "was" if len(who) == 1 else "were"
            lines.append(f"{_join(who)} {verb} here while you rested.")
        lines.extend(_chronicle_since(world_id, since))
        lines.extend(_arrived_since(world_id, since))
        lines.extend(_grown_since(world_id, since))
        from daydream import post

        lines.extend(post.thread_lines(toon_id))
    except Exception:  # a note is a courtesy; never a failed connection
        logger.warning("absence note failed", exc_info=True)
        return None
    if not lines:
        return None
    return {"id": f"away:{since}", "title": TITLE, "text": " ".join(lines)}


def stamp(toon_id: str) -> None:
    """Remember when this player rested (the world's clock, so a faked clock
    still reads right)."""
    objects.set_property(toon_id, "away_since", worldclock.iso())

