"""The background director: which authored storylet happens (SPEC
2026-09-26 criterion 5).

The director never invents anything. It chooses among AUTHORED options:

- **Arrivals**: at dusk, one dormant arc whose `arrival` is eligible
  (conditions hold, `earliest_day` reached, `after_arcs` closed, fewer than
  `config.director.max_open_guests` guest arcs open) opens, placing its
  guest. An arrival authored `first: true` wins the world's first arrival
  outright (the prologue's first dusk brings the first guest).
- **Events** (`storylets` with `always` false): at most one per phase
  boundary, plus at most one per `config.director.event_minutes` slot while
  players are connected.
- **Rituals** (`storylets` with `always: true`): fire at every crossing of
  their phase (the lanterns at dusk). Not a choice.

Storylet shape (worldstate `def:storylets`):

    {"id", "at": "dusk" | ["dusk", "night"] | "any", "always"?, "if"?,
     "weight"?, "once"?, "cooldown_days"?, "room"?, "text"?, "variants"?,
     "do"?, "summary"?}

Choosing: with the LLM available (`DAYDREAM_DIRECTOR_LLM`, default on;
off in tests), ONE call in the arbiter's `background` class ranks the
eligible options (a JSON-schema enum of their ids) given a compact view of
the village. The background class never delays a player-facing call and
never starves a queued render (daydream/gpu/arbiter.py). An answer outside
the eligible set is treated exactly like an outage: nothing it named is
applied, and the seeded deterministic choice (`worldstate.rng_stable`,
keyed on date + phase + slot) stands.
"""

from __future__ import annotations

import asyncio
import logging
import os

from daydream import events, story, worldclock, worldstate

logger = logging.getLogger(__name__)

FIRED_PREFIX = "storylet:"
FIRST_DONE = "director:first_arrival_done"
# How long one ranking may take, arbiter queue included: the background slot
# waits behind steady player traffic, and the phase work must not wait on it.
RANK_WAIT_SECONDS = 30.0


def llm_enabled() -> bool:
    return os.environ.get("DAYDREAM_DIRECTOR_LLM", "1") != "0"


def _cfg(world_id: str) -> dict:
    cfg = worldstate.get(world_id, "config")
    d = cfg.get("director") if isinstance(cfg, dict) else None
    return d if isinstance(d, dict) else {}


def storylets(world_id: str) -> list[dict]:
    d = worldstate.get(world_id, "def:storylets")
    return [s for s in d if isinstance(s, dict) and isinstance(s.get("id"), str)] \
        if isinstance(d, list) else []


def _at(s: dict) -> set[str]:
    at = s.get("at", "any")
    if isinstance(at, str):
        return {at}
    return {a for a in at if isinstance(a, str)} if isinstance(at, list) else {"any"}


def _fired(world_id: str, sid: str) -> dict:
    v = worldstate.get(world_id, FIRED_PREFIX + sid)
    return v if isinstance(v, dict) else {}


def _eligible(world_id: str, s: dict, phase: str, date_str: str) -> bool:
    from daydream import rules, village

    at = _at(s)
    if "any" not in at and phase not in at:
        return False
    rec = _fired(world_id, s["id"])
    if s.get("once") and rec.get("n"):
        return False
    cd = s.get("cooldown_days")
    last = rec.get("last_date")
    if isinstance(cd, int) and isinstance(last, str) and last:
        if village.day_for_date(world_id, date_str) - village.day_for_date(world_id, last) < cd:
            return False
    ctx = rules.world_ctx(world_id, s.get("room"), f"storylet:{s['id']}")
    return rules.conditions_hold(s.get("if"), ctx)


def always_storylets(world_id: str, phase: str, date_str: str) -> list[dict]:
    return [s for s in storylets(world_id)
            if s.get("always") and _eligible(world_id, s, phase, date_str)]


def eligible_events(world_id: str, phase: str, date_str: str) -> list[dict]:
    return [s for s in storylets(world_id)
            if not s.get("always") and _eligible(world_id, s, phase, date_str)]


def fire_storylet(world_id: str, s: dict, date_str: str) -> events.Event | None:
    from daydream import rules
    from daydream.skills import effects

    room = s.get("room")
    rec = _fired(world_id, s["id"])
    worldstate.set(world_id, FIRED_PREFIX + s["id"],
                   {"n": int(rec.get("n") or 0) + 1, "last_date": date_str})
    if room and (s.get("text") or s.get("variants")):
        story._tell(world_id, f"storylet:{s['id']}", s, room)
    if isinstance(s.get("do"), list) and s["do"]:
        ctx = rules.world_ctx(world_id, room, f"storylet:{s['id']}")
        effects.dispatch_effects(
            rules.resolve_sigils(s["do"], ctx), actor_id="", room_id=room or "",
            world_id=world_id, allowed=effects.RULE_KINDS,
        )
    return events.append("system", None, "storylet", {"id": s["id"]}, room_id=room)


# ---- arrivals ---------------------------------------------------------------


def _open_guests(world_id: str) -> int:
    n = 0
    for arc_id, arc in story.arcs_def(world_id).items():
        if isinstance(arc, dict) and arc.get("kind") == "guest" \
                and story.arc_status(world_id, arc_id) == "open":
            n += 1
    return n


def eligible_arrivals(world_id: str, date_str: str) -> list[tuple[str, dict]]:
    from daydream import rules, village

    cap = _cfg(world_id).get("max_open_guests", 2)
    if isinstance(cap, int) and _open_guests(world_id) >= cap:
        return []
    today = village.day_for_date(world_id, date_str)
    out = []
    for arc_id, arc in sorted(story.arcs_def(world_id).items()):
        if not isinstance(arc, dict) or story.arc_status(world_id, arc_id) != "dormant":
            continue
        arr = arc.get("arrival")
        if not isinstance(arr, dict):
            continue
        ed = arr.get("earliest_day")
        if isinstance(ed, int) and today < ed:
            continue
        if any(story.arc_status(world_id, a) != "closed"
               for a in arr.get("after_arcs") or []):
            continue
        ctx = rules.world_ctx(world_id, arr.get("room"), f"arrival:{arc_id}")
        if not rules.conditions_hold(arr.get("if"), ctx):
            continue
        out.append((arc_id, arr))
    return out


def _seeded(world_id: str, purpose: str, options: list[tuple[str, float]]) -> str | None:
    options = [(i, w) for i, w in options if w > 0]
    if not options:
        return None
    rng = worldstate.rng_stable(world_id, f"director:{purpose}")
    return rng.choices([i for i, _ in options], weights=[w for _, w in options], k=1)[0]


def choose_arrival(world_id: str, date_str: str, pick: str | None = None) -> str | None:
    elig = eligible_arrivals(world_id, date_str)
    if not elig:
        return None
    if not worldstate.get(world_id, FIRST_DONE):
        firsts = [a for a, arr in elig if arr.get("first")]
        if firsts:
            return firsts[0]
    ids = [a for a, _ in elig]
    if pick in ids:
        return pick
    return _seeded(world_id, f"{date_str}:arrival",
                   [(a, float(arr.get("weight", 1))) for a, arr in elig])


def run_arrival(world_id: str, date_str: str, pick: str | None = None) -> str | None:
    arc_id = choose_arrival(world_id, date_str, pick)
    if arc_id is None:
        return None
    if story.open_arc(world_id, arc_id) is not None:
        worldstate.set(world_id, FIRST_DONE, True)
        return arc_id
    return None


def choose_event(world_id: str, date_str: str, phase: str, slot: str = "b",
                 pick: str | None = None) -> dict | None:
    elig = eligible_events(world_id, phase, date_str)
    if not elig:
        return None
    by_id = {s["id"]: s for s in elig}
    if pick in by_id:
        return by_id[pick]
    sid = _seeded(world_id, f"{date_str}:{phase}:{slot}",
                  [(s["id"], float(s.get("weight", 1))) for s in elig])
    return by_id.get(sid) if sid else None


def run_event(world_id: str, date_str: str, phase: str, pick: str | None = None,
              slot: str = "b") -> str | None:
    s = choose_event(world_id, date_str, phase, slot, pick)
    if s is None:
        return None
    fire_storylet(world_id, s, date_str)
    return s["id"]


# ---- LLM ranking (background arbiter class) --------------------------------

_SYSTEM = (
    "You are the quiet director of a cozy, gentle story village. Several "
    "small happenings are ready to occur. Choose the ONE that best fits this "
    "moment: prefer variety, prefer threads players have been touching, and "
    "never choose the same kind of moment twice in a row. Return strict JSON: "
    '{"choice": "<one of the listed ids>"}.'
)


def _context(world_id: str, phase: str) -> str:
    from daydream import village

    lines = [f"Village day {village.day(world_id)}, {phase}."]
    for arc_id, st in story.all_states(world_id).items():
        if st["status"] == "open":
            arc = story.arc_def(world_id, arc_id) or {}
            total = len(arc.get("beats") or {})
            lines.append(f"- open thread: {arc.get('title', arc_id)} "
                         f"({len(st['beats'])}/{total} steps taken, "
                         f"{len(st['helpers'])} helpers)")
    recent = story.chronicle(world_id)[-3:]
    for e in recent:
        lines.append(f"- recently: {e.get('text', '')[:120]}")
    return "\n".join(lines)


async def _rank(world_id: str, kind: str, options: list[tuple[str, str]],
                phase: str) -> str | None:
    """One background-class LLM call choosing among `options` [(id,
    summary)]. None on outage, refusal, or an answer outside the set."""
    from daydream.llm import client

    if len(options) < 2:
        return None
    ids = [i for i, _ in options]
    schema = {"type": "json_schema", "json_schema": {"name": "choice", "schema": {
        "type": "object", "properties": {"choice": {"type": "string", "enum": ids}},
        "required": ["choice"], "additionalProperties": False}}}
    user = (_context(world_id, phase) + f"\n\nReady {kind}s:\n"
            + "\n".join(f"- {i}: {summ}" for i, summ in options))
    try:
        result = await asyncio.wait_for(client.acompletion_json(
            system=_SYSTEM, user=user, purpose="director", gate="background",
            temperature=0.7, max_tokens=40, timeout=20.0, response_format=schema,
        ), RANK_WAIT_SECONDS)
    except (client.LLMUnavailable, asyncio.TimeoutError):
        return None  # the seeded choice stands
    choice = result.get("choice") if isinstance(result, dict) else None
    return choice if choice in ids else None


def _summary(d: dict, fallback: str) -> str:
    s = d.get("summary") or d.get("text") or fallback
    return str(s)[:140]


async def llm_picks(world_id: str, date_str: str, phase: str) -> dict:
    picks: dict = {}
    if phase == "dusk" and worldstate.get(world_id, FIRST_DONE):
        arr = eligible_arrivals(world_id, date_str)
        opts = [(a, _summary(story.arc_def(world_id, a) or {}, a)) for a, _ in arr]
        picks["arrival"] = await _rank(world_id, "arrival", opts, phase)
    ev = eligible_events(world_id, phase, date_str)
    picks["event"] = await _rank(world_id, "happening",
                                 [(s["id"], _summary(s, s["id"])) for s in ev], phase)
    return picks


async def maybe_small_event(world_id: str) -> str | None:
    """At most one small event per `event_minutes` slot of wall-clock time
    while at least one player is connected."""
    from daydream import village

    if events.subscriber_count() < 1 or not village.running(world_id):
        return None
    minutes = _cfg(world_id).get("event_minutes", 40)
    if not isinstance(minutes, int) or minutes <= 0:
        return None
    now = village.local_now(world_id)
    slot = (now.hour * 60 + now.minute) // minutes
    date_str = now.date().isoformat()
    key = f"director:slot:{date_str}:{slot}"
    if worldstate.get(world_id, key):
        return None
    worldstate.set(world_id, key, worldclock.iso())
    phase = village.phase(world_id)
    pick = None
    if llm_enabled():
        ev = eligible_events(world_id, phase, date_str)
        pick = await _rank(world_id, "happening",
                           [(s["id"], _summary(s, s["id"])) for s in ev], phase)
    return run_event(world_id, date_str, phase, pick, slot=f"s{slot}")
