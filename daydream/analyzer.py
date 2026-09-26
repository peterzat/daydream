"""The static world analyzer (SPEC 2026-09-26 criterion 1).

Runs over a format-2 envelope (the committed world, or a world merged with
dream patches) and proves, statically:

- every room is reachable from the start room (conditions treated as
  satisfiable; the walkthroughs prove the conditions themselves);
- every arc is solvable: it can open (an arrival in a reachable room, an
  `open_arc` somewhere, or `opens: "start"`); every beat has a deterministic
  producer (a talk beat's topic on an NPC a player can reach, or an
  `advance_beat` effect in some rule / topic / beat / ending / storylet /
  page reward whose holder a player can reach); `after` prerequisites exist
  and never form a cycle; every ending has a producer (`close_arc`
  somewhere, or a timed `after_days`);
- every object a producer's conditions need is obtainable: placed in a
  reachable room (directly, in a container, or held by a reachable NPC), or
  moved into play by some effect.

Returns named problems (empty = sound). It is data-only and never touches a
database, so it runs in tier_short and inside the dream rehearsal.
"""

from __future__ import annotations

from collections import deque

_ID_CONDS = ("carried", "present", "dobj", "iobj", "contains")


def _exit_dests(room: dict):
    for _d, v in (room.get("exits") or {}).items():
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict) and isinstance(v.get("to"), str):
            yield v["to"]


def reachable_rooms(env: dict) -> set[str]:
    rooms = {r["id"]: r for r in env.get("rooms", []) if isinstance(r, dict)}
    start = env.get("start_room")
    seen = {start} if start in rooms else set()
    q = deque(seen)
    while q:
        here = q.popleft()
        for dest in _exit_dests(rooms[here]):
            if dest in rooms and dest not in seen:
                seen.add(dest)
                q.append(dest)
    return seen


def _walk(node, path: tuple, out: list) -> None:
    """Every effect dict with its holder context: (effect, path)."""
    if isinstance(node, dict):
        if isinstance(node.get("kind"), str):
            out.append((node, path))
        for k, v in node.items():
            _walk(v, path + (k,), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, path + (i,), out)


def _toon_rooms(env: dict) -> dict[str, set[str]]:
    """Where each toon can be found: its start room, its scheduled rooms,
    and (for guests) its arc's arrival room."""
    out: dict[str, set[str]] = {}
    for t in env.get("toons", []):
        if not isinstance(t, dict):
            continue
        rs = set()
        if t.get("room") and t["room"] != "offstage":
            rs.add(t["room"])
        sched = (t.get("properties") or {}).get("schedule")
        if isinstance(sched, dict):
            rs.update(v for v in sched.values() if isinstance(v, str))
        out[t["id"]] = rs
    for arc in (env.get("arcs") or {}).values():
        if isinstance(arc, dict) and isinstance(arc.get("guest"), str):
            arr = arc.get("arrival") if isinstance(arc.get("arrival"), dict) else {}
            if isinstance(arr.get("room"), str):
                out.setdefault(arc["guest"], set()).add(arr["room"])
    return out


def analyze(env: dict) -> list[str]:
    problems: list[str] = []
    rooms = {r["id"]: r for r in env.get("rooms", []) if isinstance(r, dict)}
    reach = reachable_rooms(env)
    for rid in rooms:
        if rid not in reach:
            problems.append(f"room {rid} is unreachable from {env.get('start_room')}")

    toon_rooms = _toon_rooms(env)
    toon_ok = {tid for tid, rs in toon_rooms.items() if rs & reach}

    effects: list = []
    _walk(env, (), effects)
    moved_in = {e.get("object_id") for e, _ in effects if e.get("kind") == "move_object"}

    # Thing placement (fixpoint over containment).
    things = {t["id"]: t for t in env.get("things", []) if isinstance(t, dict)}
    placed: set[str] = set()
    changed = True
    while changed:
        changed = False
        for tid, t in things.items():
            if tid in placed:
                continue
            loc = t.get("location")
            ok = False
            if loc == "offstage":
                ok = tid in moved_in
            elif isinstance(loc, dict) and len(loc) == 1:
                (kind, ref), = loc.items()
                ok = ((kind == "room" and ref in reach)
                      or (kind == "in" and ref in placed)
                      or (kind == "toon" and ref in toon_ok))
            if ok:
                placed.add(tid)
                changed = True
    for tid in things:
        if tid not in placed:
            problems.append(f"thing {tid} is never obtainable (not placed in a "
                            "reachable place, and nothing moves it into play)")

    def holder_ok(path: tuple) -> bool:
        """Is the holder of an effect at `path` somewhere a player can act?"""
        if not path:
            return True
        head = path[0]
        if head in ("rooms", "things", "toons") and len(path) > 1:
            item = env[head][path[1]]
            iid = item.get("id")
            if head == "rooms":
                return iid in reach
            if head == "things":
                return iid in placed
            return iid in toon_ok
        return True  # world rules, fuses, arcs, storylets, pages: world-level

    def needed_ok(conds, where: str) -> None:
        for c in conds if isinstance(conds, list) else []:
            if not isinstance(c, dict) or c.get("not"):
                continue
            for k in _ID_CONDS:
                ref = c.get(k)
                if isinstance(ref, str) and not ref.startswith("@"):
                    if ref in things and ref not in placed:
                        problems.append(f"{where}: needs {ref}, which is never obtainable")
                    if ref in toon_rooms and ref not in toon_ok:
                        problems.append(f"{where}: needs {ref}, who is never reachable")
            if isinstance(c.get("in"), str) and c["in"] in rooms and c["in"] not in reach:
                problems.append(f"{where}: needs unreachable room {c['in']}")

    def enclosing_rule(path: tuple):
        """The rule dict containing the effect at `path`, if any."""
        node = env
        rule = None
        for key in path:
            node = node[key]
            if isinstance(node, dict) and "on" in node and "do" in node:
                rule = node
        return rule

    producers_beat: dict[str, list[tuple]] = {}
    producers_end: dict[str, list[tuple]] = {}
    openers: set[str] = set()
    for e, path in effects:
        k = e.get("kind")
        if k == "advance_beat":
            producers_beat.setdefault(f"{e.get('arc')}/{e.get('beat')}", []).append(path)
        elif k == "close_arc":
            producers_end.setdefault(f"{e.get('arc')}/{e.get('ending')}", []).append(path)
        elif k == "open_arc":
            openers.add(e.get("arc"))

    arcs = env.get("arcs") or {}
    for aid, arc in arcs.items():
        if not isinstance(arc, dict):
            continue
        arr = arc.get("arrival") if isinstance(arc.get("arrival"), dict) else None
        can_open = (arr is not None and arr.get("room") in reach) or aid in openers \
            or arc.get("opens") == "start"
        if not can_open:
            problems.append(f"arc {aid} can never open (no reachable arrival, no open_arc)")
        beats = arc.get("beats") or {}
        # after-graph cycle check
        graph = {b: [p if "/" in p else f"{aid}/{p}" for p in (bd.get("after") or [])]
                 for b, bd in beats.items() if isinstance(bd, dict)}
        for b in graph:
            seen, stack = set(), [f"{aid}/{x}" if "/" not in x else x for x in [b]]
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                ca, cb = cur.split("/", 1)
                if ca == aid and cb in graph:
                    for nxt in graph[cb]:
                        if nxt == f"{aid}/{b}":
                            problems.append(f"arc {aid}: beat {b} is in an 'after' cycle")
                        stack.append(nxt)
        for bid, beat in beats.items():
            if not isinstance(beat, dict):
                continue
            ref = f"{aid}/{bid}"
            where = f"arc {aid} beat {bid}"
            ok = False
            npc = beat.get("npc")
            if isinstance(npc, str) and beat.get("topic"):
                if npc in toon_ok:
                    ok = True
                else:
                    problems.append(f"{where}: its NPC {npc} is never reachable")
            for path in producers_beat.get(ref, []):
                if holder_ok(path):
                    ok = True
                    rule = enclosing_rule(path)
                    if rule is not None:
                        needed_ok(rule.get("if"), f"{where} (rule producer)")
            if not ok:
                problems.append(f"{where}: no deterministic producer a player can reach")
            needed_ok(beat.get("if"), where)
        for eid, ending in (arc.get("endings") or {}).items():
            if not isinstance(ending, dict):
                continue
            ref = f"{aid}/{eid}"
            if isinstance(ending.get("after_days"), int):
                continue
            paths = [p for p in producers_end.get(ref, []) if holder_ok(p)]
            if not paths:
                problems.append(f"arc {aid} ending {eid}: nothing can bring it about")
            for path in paths:
                rule = enclosing_rule(path)
                if rule is not None:
                    needed_ok(rule.get("if"), f"arc {aid} ending {eid} (rule producer)")
    return problems
