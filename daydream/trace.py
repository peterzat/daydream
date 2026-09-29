"""Traces of dreamers: who was here, when, and what a resident knows of them
(beta rehearsal 2026-09-28).

The villagers remembered deeds (the Ledger) but not dreamers: asked where an
absent player was, the local model invented a room; a friend arriving after
friends found no signed trace of them. This module answers from what the
world records, deterministically: a dreamer's last-seen (the input log), their
state (here, awake elsewhere, dozing, resting), the deed facts a resident
knows about them, and two rosters an authored readable or fixture may show
(`properties.roster`): the keepers who have dreamed here, and the guest hours
waiting or gone home. Every name is the world's own; the engine's words name
nothing of any world.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from daydream import db, objects, rooms, story, toons, worldclock

logger = logging.getLogger(__name__)


# ---- last seen -----------------------------------------------------------------


def last_seen(toon_id: str) -> tuple[str | None, str | None]:
    """(ISO time, room id) of this dreamer's most recent input, or (None, None)."""
    row = db.get_conn().execute(
        "SELECT created_at, room_id FROM inputs WHERE toon_id = ? ORDER BY seq DESC LIMIT 1",
        (toon_id,)).fetchone()
    return (row["created_at"], row["room_id"]) if row else (None, None)


def when_phrase(iso: str | None, tz=None) -> str:
    """How long ago, in a village's words: "a moment ago", "an hour ago",
    "earlier today", "yesterday", "some days ago". Days are the village's
    calendar days (`tz`), so last evening is "yesterday" at breakfast."""
    if not iso:
        return "some time ago"
    try:
        then = worldclock.parse(iso)
    except (ValueError, TypeError):
        return "some time ago"
    now = worldclock.now()
    delta = now - then
    if delta < timedelta(minutes=5):
        return "a moment ago"
    if delta < timedelta(minutes=50):
        return "not long ago"
    if delta < timedelta(hours=2):
        return "an hour or so ago"
    days = (now.astimezone(tz).date() - then.astimezone(tz).date()).days if tz else None
    if days is None:
        days = 0 if delta < timedelta(hours=20) else 1 if delta < timedelta(hours=44) else 2
    if days <= 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return "some days ago"
    return "a long while ago"


def _tz(world_id: str):
    """The village's zone, for calendar days."""
    try:
        from zoneinfo import ZoneInfo

        from daydream import village

        name = (village.time_def(world_id) or {}).get("tz")
        return ZoneInfo(name) if isinstance(name, str) and name else None
    except Exception:
        return None


def state_of(toon: objects.Object) -> str:
    """"resting", "dozing", or "awake"."""
    if not toon.is_human_controlled:
        return "resting"
    try:
        from daydream.api import ws as ws_mod

        if ws_mod.is_dozing(toon):
            return "dozing"
    except Exception:
        pass
    return "awake"


def players(world_id: str) -> list[objects.Object]:
    out = []
    for t in toons._query("world_id = ? ORDER BY slot, id", (world_id,)):
        o = objects.get(t.id)
        if o is not None and o.is_player:
            out.append(o)
    return out


def find_player(world_id: str, name: str) -> objects.Object | None:
    want = (name or "").strip().lower()
    if not want:
        return None
    for p in players(world_id):
        if p.name.lower() == want:
            return p
    return None


def named_players(world_id: str, text: str, exclude: str | None = None) -> list[objects.Object]:
    """The dreamers a line of text names (whole words, any case)."""
    low = f" {re.sub(r'[^a-z0-9]+', ' ', (text or '').lower())} "
    out = []
    for p in players(world_id):
        if p.id == exclude:
            continue
        if f" {p.name.lower()} " in low:
            out.append(p)
    return out


def dreamer_line(target: objects.Object, viewer_id: str | None = None) -> str:
    """One sentence on where a dreamer was last, and how they are now."""
    at, room_id = last_seen(target.id)
    room = rooms.get_room(room_id) if room_id else None
    if room is None and target.location_id:
        room = rooms.get_room(target.location_id)
    where = f" in {toons.in_sentence(room.title)}" if room else ""
    state = state_of(target)
    if state == "awake":
        here = target.location_id and viewer_id and objects.get(viewer_id) is not None \
            and objects.get(viewer_id).location_id == target.location_id
        now = "here now" if here else "awake in the dream now"
    elif state == "dozing":
        now = "dozing now"
    else:
        now = "resting now, away from the dream"
    return f"{target.name} was last seen {when_phrase(at, _tz(target.world_id))}{where}, and is {now}."


def for_prompt(world_id: str, text: str, actor_id: str) -> list[str]:
    """The lines a resident's prompt gets about any dreamer the player names,
    so the model never invents a whereabouts."""
    return [dreamer_line(p, actor_id) for p in named_players(world_id, text, exclude=actor_id)]


# ---- who walked through today ------------------------------------------------------------


def dreamers_today(world_id: str) -> list[str]:
    """The dreamers who typed anything today, by the village's calendar,
    newest last."""
    from datetime import datetime, time, timezone

    tz = _tz(world_id)
    now_local = worldclock.now().astimezone(tz) if tz else worldclock.now()
    start = datetime.combine(now_local.date(), time.min, tzinfo=tz or timezone.utc)
    rows = db.get_conn().execute(
        "SELECT toon_id, MIN(created_at) AS first FROM inputs WHERE world_id = ? "
        "AND created_at >= ? GROUP BY toon_id ORDER BY first",
        (world_id, worldclock.iso(start))).fetchall()
    out: list[str] = []
    for r in rows:
        t = objects.get(r["toon_id"])
        if t is not None and t.is_player and t.name not in out:
            out.append(t.name)
    return out


def dreamers_today_clause(world_id: str) -> str:
    """A clause for an authored line's {dreamers_today}: "Wren and Vex came
    through today", "one dreamer, Halloran, came through today", "no
    dreamer came through today"."""
    names = dreamers_today(world_id)
    if not names:
        return "no dreamer came through today"
    if len(names) == 1:
        return f"one dreamer, {names[0]}, came through today"
    return f"{_join(names)} came through today"


# ---- what a resident tells about a dreamer ------------------------------------------


def report(npc: objects.Object, actor: objects.Object, target: objects.Object,
           room_id: str) -> None:
    """`ask <resident> about <dreamer>`: narration, private to the asker, of
    what the village knows: last seen and state, then up to two deeds this
    resident knows of theirs. Never a spoken line: the resident's voice is
    authored or the model's, and this is the record."""
    from daydream import knowledge

    parts = [dreamer_line(target, actor.id)]
    known = [f for f in knowledge.known_facts(npc, actor.id, limit=40)
             if f.get("kind") == "deed" and f.get("about") == target.id]
    for f in known[:2]:
        parts.append(f"{npc.name} knows that {f['text'].strip()}")
    if not known:
        parts.append(f"{npc.name} knows nothing more of them than that.")
    from daydream import events

    events.append("system", None, "narrate", {"text": " ".join(parts)},
                  room_id=room_id, recipient_id=actor.id)


# ---- rosters ---------------------------------------------------------------------------


def roster_text(holder: objects.Object, viewer_id: str | None) -> str | None:
    """The line an authored readable or fixture appends when its
    `properties.roster` says which roster to show:

        {"kind": "keepers", "text": "...{names}...", "empty": "..."}
        {"kind": "guests", "text": "...{waiting}...{home}...", "empty": "..."}

    keepers: every dreamer of this world, newest first, with how they are
    ("Wren (resting), Vex (here now)"). guests: the guest hours whose arcs
    are open (waiting) and those whose arcs have closed (home or kept)."""
    spec = holder.properties.get("roster")
    if not isinstance(spec, dict) or not isinstance(spec.get("text"), str):
        return None
    kind = spec.get("kind")
    world_id = holder.world_id
    if kind == "keepers":
        entries = []
        for p in players(world_id):
            at, _ = last_seen(p.id)
            state = state_of(p)
            here = (viewer_id and objects.get(viewer_id) is not None
                    and objects.get(viewer_id).location_id == p.location_id and state == "awake")
            how = ("here now" if here else "awake now" if state == "awake"
                   else "dozing" if state == "dozing"
                   else f"last here {when_phrase(at, _tz(world_id))}")
            entries.append((at or "", f"{p.name} ({how})"))
        if not entries:
            return spec.get("empty") if isinstance(spec.get("empty"), str) else None
        entries.sort(key=lambda e: e[0], reverse=True)
        return spec["text"].replace("{names}", _join([e[1] for e in entries]))
    if kind == "guests":
        waiting, home = [], []
        for arc_id, arc in story.arcs_def(world_id).items():
            if not isinstance(arc, dict) or arc.get("kind") != "guest":
                continue
            guest = objects.get(str(arc.get("guest") or ""))
            if guest is None:
                continue
            st = story.arc_state(world_id, arc_id)
            if st.get("status") == "open":
                waiting.append(guest.name)
            elif st.get("status") == "closed":
                home.append(guest.name)
        if not waiting and not home:
            return spec.get("empty") if isinstance(spec.get("empty"), str) else None
        return (spec["text"].replace("{waiting}", _join(waiting) or "no one just now")
                .replace("{home}", _join(home) or "no one yet"))
    return None


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
