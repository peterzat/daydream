"""The living day: wall-clock phases, the village day, the restart-safe
catch-up pass, and NPC schedules (SPEC 2026-09-26 criteria 3, 4, 5).

Authored config (worldstate `def:time`, format-2 top-level `time`):

    {"tz": "America/Los_Angeles",
     "start_flag": "CLOCK-STARTED",
     "phases": {"dawn": "06:00", "day": "08:00", "dusk": "18:00",
                "night": "21:30"},
     "catch_up_days": 7}

Before `start_time` runs (the prologue's clock-mending moment), the village
has no day cycle: `phase()` is "stopped", `day()` is 0, and nothing here
fires. After it, every phase boundary crossed on the wall clock is processed
exactly once, in order, by `catch_up` (the background loop in production;
the head of every command when no loop runs, e.g. tests and walkthroughs).
The processed high-water mark is worldstate `time:last`, so a restart
neither skips a missed boundary (it catches up, capped at `catch_up_days`)
nor re-fires one. Dusk is additionally keyed by local date
(`dusk_done:<date>`), so an authored early dusk (the `run_phase` effect,
the prologue's first dusk) and the wall-clock dusk of that same day can
never both fire.

What a boundary does is `run_phase`: at dusk, timed arc endings come due,
the always-on storylets for the phase fire (the lanterns), the director
picks one arrival and at most one small event; other phases fire their
always-on storylets and at most one event. Then NPC schedules settle:
an NPC with `properties.schedule` = {phase: room} walks to its room for the
current phase, with its authored leave/arrive lines.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from daydream import events, objects, worldclock, worldstate

logger = logging.getLogger(__name__)

PHASE_ORDER = ("dawn", "day", "dusk", "night")
DEFAULT_PHASES = {"dawn": "06:00", "day": "08:00", "dusk": "18:00", "night": "21:30"}
KEY_START = "time:start_date"
KEY_LAST = "time:last"
KEY_OVERRIDE = "time:override"
DUSK_DONE = "dusk_done:"


# ---- config ---------------------------------------------------------------


def time_def(world_id: str) -> dict | None:
    d = worldstate.get(world_id, "def:time")
    return d if isinstance(d, dict) else None


def _tz(world_id: str) -> ZoneInfo:
    d = time_def(world_id) or {}
    try:
        return ZoneInfo(d.get("tz") or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _phases(world_id: str) -> list[tuple[str, time]]:
    d = (time_def(world_id) or {}).get("phases") or DEFAULT_PHASES
    out = []
    for name in PHASE_ORDER:
        hhmm = d.get(name) if isinstance(d, dict) else None
        if not isinstance(hhmm, str):
            continue
        h, m = hhmm.split(":")
        out.append((name, time(int(h), int(m))))
    out.sort(key=lambda p: p[1])
    return out


def local_now(world_id: str, at: datetime | None = None) -> datetime:
    return (at or worldclock.now()).astimezone(_tz(world_id))


def local_date(world_id: str, at: datetime | None = None) -> str:
    return local_now(world_id, at).date().isoformat()


def running(world_id: str) -> bool:
    return time_def(world_id) is not None and \
        isinstance(worldstate.get(world_id, KEY_START), str)


# ---- phase + day ----------------------------------------------------------


def wall_phase(world_id: str, at: datetime | None = None) -> str:
    """The phase the wall clock says it is (ignores overrides)."""
    now = local_now(world_id, at)
    phases = _phases(world_id)
    if not phases:
        return "day"
    current = phases[-1][0]  # before the first boundary: last phase of yesterday
    for name, t in phases:
        if now.time() >= t:
            current = name
    return current


def phase(world_id: str, at: datetime | None = None) -> str:
    """The village's phase now: "stopped" before time starts; an authored
    early phase (the prologue's first dusk) holds until the next wall-clock
    boundary; otherwise the wall clock."""
    if not running(world_id):
        return "stopped"
    ov = worldstate.get(world_id, KEY_OVERRIDE)
    if isinstance(ov, dict) and isinstance(ov.get("until"), str):
        try:
            if (at or worldclock.now()) < worldclock.parse(ov["until"]):
                return str(ov.get("phase"))
        except ValueError:
            pass
    return wall_phase(world_id, at)


def day(world_id: str, at: datetime | None = None) -> int:
    """The village day: 1 on the local date time started, +1 per local date
    since. 0 before time starts."""
    start = worldstate.get(world_id, KEY_START)
    if not isinstance(start, str):
        return 0
    try:
        d0 = date.fromisoformat(start)
    except ValueError:
        return 0
    return (local_now(world_id, at).date() - d0).days + 1


def day_for_date(world_id: str, date_str: str) -> int:
    start = worldstate.get(world_id, KEY_START)
    try:
        return (date.fromisoformat(date_str) - date.fromisoformat(start)).days + 1
    except (TypeError, ValueError):
        return 0


def status(world_id: str) -> dict:
    """The snapshot `time` block: {running, phase, day, label}."""
    ph = phase(world_id)
    d = day(world_id)
    labels = ((time_def(world_id) or {}).get("labels") or {})
    word = labels.get(ph) if isinstance(labels, dict) else None
    return {"running": ph != "stopped", "phase": ph, "day": d,
            "label": (word if isinstance(word, str) else ph)}


# ---- boundaries -------------------------------------------------------------


def _boundary_dt(world_id: str, d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=_tz(world_id))


def _latest_boundary(world_id: str, at: datetime) -> datetime | None:
    phases = _phases(world_id)
    if not phases:
        return None
    local = local_now(world_id, at)
    for back in range(0, 3):
        d = local.date() - timedelta(days=back)
        for _name, t in reversed(phases):
            bdt = _boundary_dt(world_id, d, t)
            if bdt <= local:
                return bdt
    return None


def boundaries_between(world_id: str, after: datetime, until: datetime,
                       cap: int = 200) -> list[tuple[str, str, datetime]]:
    """Every (local date, phase, instant) boundary with after < instant <=
    until, oldest first, capped."""
    phases = _phases(world_id)
    out: list[tuple[str, str, datetime]] = []
    if not phases:
        return out
    a = local_now(world_id, after)
    u = local_now(world_id, until)
    d = a.date()
    while d <= u.date() and len(out) < cap:
        for name, t in phases:
            bdt = _boundary_dt(world_id, d, t)
            if a < bdt <= u:
                out.append((d.isoformat(), name, bdt))
        d += timedelta(days=1)
    return out[:cap]


def start_time(world_id: str, room_id: str | None = None) -> events.Event | None:
    """Time begins (the prologue's mended clock): stamp the start date and
    the processed high-water mark at the latest boundary already past (so
    nothing earlier today retro-fires), and set the authored start flag.
    Starting twice changes nothing."""
    if time_def(world_id) is None or running(world_id):
        return None
    now = worldclock.now()
    worldstate.set(world_id, KEY_START, local_date(world_id, now))
    last = _latest_boundary(world_id, now) or now
    worldstate.set(world_id, KEY_LAST, worldclock.iso(last))
    flag = (time_def(world_id) or {}).get("start_flag")
    if isinstance(flag, str) and flag.strip():
        worldstate.set_flag(world_id, flag.strip(), True)
    return events.append("system", None, "time_started",
                         {"date": local_date(world_id, now)}, room_id=room_id)


def run_phase_now(world_id: str, phase_name: str, room_id: str | None = None) -> events.Event | None:
    """An authored early phase (the prologue's first dusk): run that phase's
    processing for TODAY right now, and hold the village in that phase until
    the next wall-clock boundary. Dusk stays once-per-date: if today's dusk
    already ran, this changes nothing."""
    if not running(world_id) or phase_name not in PHASE_ORDER:
        return None
    today = local_date(world_id)
    if phase_name == "dusk" and worldstate.get(world_id, DUSK_DONE + today):
        return None
    run_phase(world_id, today, phase_name)
    now = worldclock.now()
    nxt = boundaries_between(world_id, now, now + timedelta(days=2), cap=1)
    if nxt:
        worldstate.set(world_id, KEY_OVERRIDE,
                       {"phase": phase_name, "until": worldclock.iso(nxt[0][2])})
    apply_schedules(world_id)
    return events.append("system", None, "phase_began",
                         {"phase": phase_name, "date": today}, room_id=room_id)


# ---- processing -------------------------------------------------------------


def run_phase(world_id: str, date_str: str, phase_name: str,
              picks: dict | None = None) -> None:
    """Process one boundary. `picks` carries the director's LLM-ranked
    choices from the async path ({"arrival": arc id, "event": storylet id});
    anything absent or no longer eligible falls back to the seeded choice."""
    from daydream import director, story

    picks = picks or {}
    if phase_name == "dusk":
        if worldstate.get(world_id, DUSK_DONE + date_str):
            return
        worldstate.set(world_id, DUSK_DONE + date_str, True)
        today = day_for_date(world_id, date_str)
        for arc_id, ending_id in story.timed_endings_due(world_id, today):
            story.close_arc(world_id, arc_id, ending_id)
    for s in director.always_storylets(world_id, phase_name, date_str):
        director.fire_storylet(world_id, s, date_str)
    if phase_name == "dusk":
        director.run_arrival(world_id, date_str, picks.get("arrival"))
    director.run_event(world_id, date_str, phase_name, picks.get("event"))


def _pending(world_id: str) -> list[tuple[str, str, datetime]]:
    if not running(world_id):
        return []
    now = worldclock.now()
    last_raw = worldstate.get(world_id, KEY_LAST)
    try:
        last = worldclock.parse(last_raw) if isinstance(last_raw, str) else now
    except ValueError:
        last = now
    cap_days = (time_def(world_id) or {}).get("catch_up_days", 7)
    floor = now - timedelta(days=cap_days if isinstance(cap_days, int) else 7)
    if last < floor:
        last = floor
    return boundaries_between(world_id, last, now)


def catch_up(world_id: str) -> int:
    """Process every wall-clock boundary crossed since the high-water mark,
    in order, with the seeded director (no LLM). Returns how many ran."""
    pending = _pending(world_id)
    for date_str, name, bdt in pending:
        run_phase(world_id, date_str, name)
        worldstate.set(world_id, KEY_LAST, worldclock.iso(bdt))
    if running(world_id):
        apply_schedules(world_id)
    return len(pending)


async def catch_up_async(world_id: str, use_llm: bool = True) -> int:
    """The background loop's catch-up: like `catch_up`, but each boundary's
    director choices may be ranked by the local LLM first (background arbiter
    class; an out-of-set answer is ignored and the seeded choice stands)."""
    from daydream import director

    pending = _pending(world_id)
    for date_str, name, bdt in pending:
        picks = await director.llm_picks(world_id, date_str, name) if use_llm else {}
        # The mark may have moved while we awaited (a command-head catch-up).
        if _pending(world_id)[:1] != [(date_str, name, bdt)]:
            continue
        run_phase(world_id, date_str, name, picks)
        worldstate.set(world_id, KEY_LAST, worldclock.iso(bdt))
    if running(world_id):
        apply_schedules(world_id)
    return len(pending)


def apply_schedules(world_id: str) -> int:
    """Walk every scheduled NPC to its room for the current phase. Offstage
    toons and players are never moved. Returns how many moved."""
    from daydream import story

    ph = phase(world_id)
    if ph == "stopped":
        return 0
    moved = 0
    for t in _npcs(world_id):
        sched = t.properties.get("schedule")
        if not isinstance(sched, dict) or t.location_id is None:
            continue
        target = sched.get(ph)
        if not isinstance(target, str) or target == t.location_id:
            continue
        texts = t.properties.get("schedule_text")
        texts = texts if isinstance(texts, dict) else {}
        if story.place_toon(t.id, target, leave_text=texts.get("leave"),
                            arrive_text=texts.get("arrive")) is not None:
            moved += 1
    return moved


def _npcs(world_id: str) -> list[objects.Object]:
    from daydream import db

    rows = db.get_conn().execute(
        "SELECT * FROM objects WHERE world_id = ? AND kind = 'toon' "
        "AND is_human_controlled = 0 AND kicked_at IS NULL ORDER BY id",
        (world_id,),
    ).fetchall()
    return [objects.Object.from_row(r) for r in rows]


# ---- the background loop ------------------------------------------------------

_handle: asyncio.Task | None = None


def enabled() -> bool:
    return os.environ.get("DAYDREAM_VILLAGE_ENABLED", "1") != "0"


def loop_running() -> bool:
    return _handle is not None and not _handle.done()


def _tick_seconds() -> float:
    try:
        return float(os.environ.get("DAYDREAM_VILLAGE_TICK_SECONDS", "30"))
    except ValueError:
        return 30.0


async def _loop() -> None:
    from daydream import director, toons

    while True:
        try:
            await asyncio.sleep(_tick_seconds())
            world_id = toons.live_world_id()
            if running(world_id):
                await catch_up_async(world_id, use_llm=director.llm_enabled())
                await director.maybe_small_event(world_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("village tick failed", exc_info=True)


def start_loop() -> asyncio.Task | None:
    global _handle
    if not enabled():
        return None
    _handle = asyncio.create_task(_loop(), name="daydream-village")
    return _handle


async def stop_loop() -> None:
    global _handle
    if _handle is None or _handle.done():
        _handle = None
        return
    _handle.cancel()
    try:
        await _handle
    except asyncio.CancelledError:
        pass
    _handle = None
