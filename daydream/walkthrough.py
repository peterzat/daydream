"""Walkthroughs: the contract every arc ending ships (SPEC 2026-09-26
criteria 2, 3, 14; docs/PIVOT.md section 9).

A walkthrough is a command dataset replayed through the real parser and
executor, with a fake clock, ending at asserted world state. The same
replayer serves the tier_medium tests (a fresh world per dataset, zero LLM
calls enforced by the caller's spy) and the dream rehearsal (a patched fresh
world, or a side copy of the live world with fresh rehearsal players).

Dataset shape:

    {"name": "pim-home",
     "players": [{"as": "A", "name": "Wren"}],        # joined at the start
     "clock": "2026-10-01T10:00:00+00:00",            # optional start time
     "segments": [{"name": "...", "commands": [step, ...]}]}

A step is one of:

    {"cmd": "read ledger", "as"?: "A", "expect"?: {...}}   typed text
    {"command": {"verb", "dobj_id"?, "iobj_id"?, "args"?}, "as"?, "expect"?}
    {"clock": ISO | "+30m" | "+2h" | "+1d" | "@dusk" | "@dawn" | ...}
    {"summon": "<arc id>"}      open an arc directly (tests the arc, not the
                                director's choice)
    {"join": {"as": "B", "name": "Tamsin"}}   a new player arrives
    {"expect": {...}}           assertions only

A step may also carry `"at": ISO` (an exported real session's own
timestamps): on a fresh replay the fake clock moves to it first, so a
recorded session replays with its original timing.

`expect` keys (all optional, all must hold):

    room, carrying [names], not_carrying [names], flag {NAME: bool},
    pflag {NAME: bool}, arc {id: status}, ending {arc: ending},
    beats [arc/beat], rel {npc: {op: n}}, collected {op: n},
    phase, day {op: n}, knows {npc: fact}, located {object: room|null},
    narrate_contains str | [str], narrate_lacks str | [str], chronicle_contains str
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from daydream import (
    collect,
    db,
    events,
    knowledge,
    objects,
    parser,
    story,
    toons,
    verbs,
    village,
    worldclock,
    worldstate,
)

_REL = re.compile(r"^\+(\d+)([mhd])$")
_OPS = ("eq", "ne", "lt", "lte", "gt", "gte")


class WalkthroughError(AssertionError):
    pass


@dataclass
class Run:
    name: str
    actors: dict[str, str] = field(default_factory=dict)
    steps: int = 0
    transcript: list[str] = field(default_factory=list)


def load_dataset(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _cmp(spec: dict, value) -> bool:
    for op in _OPS:
        if op in spec:
            want = spec[op]
            return {"eq": value == want, "ne": value != want, "lt": value < want,
                    "lte": value <= want, "gt": value > want,
                    "gte": value >= want}[op]
    return bool(value)


def _world_id() -> str:
    return toons.live_world_id()


def set_clock(spec: str) -> None:
    """Absolute ISO, relative '+Nm/+Nh/+Nd', or '@<phase>' (5 minutes past
    the next boundary of that phase). Then process any crossed boundaries."""
    world_id = _world_id()
    m = _REL.match(spec)
    if spec.startswith("@"):
        phase = spec[1:]
        now = worldclock.now()
        nxt = [b for b in village.boundaries_between(world_id, now, now + timedelta(days=2))
               if b[1] == phase]
        if not nxt:
            raise WalkthroughError(f"no upcoming {phase!r} boundary")
        worldclock.set_fake_now(nxt[0][2] + timedelta(minutes=5))
    elif m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n),
                 "d": timedelta(days=n)}[unit]
        worldclock.set_fake_now(worldclock.now() + delta)
    else:
        worldclock.set_fake_now(spec)
    village.catch_up(world_id)


def join(run: Run, who: str, name: str, slot: int | None = None) -> str:
    """A new player arrives in the world's starting room (the first free
    human slot unless one is named)."""
    slots = [slot] if slot else list(range(1, 9))
    for s in slots:
        if toons.get_toon_in_slot(s) is None:
            t = toons.create_toon_in_slot(s, name, f"{name}, a dreamer",
                                          f"walkthrough-{run.name}-{who}")
            if t is not None:
                run.actors[who] = t.id
                return t.id
    raise WalkthroughError(f"no free player slot for {name!r}")


async def run_step(run: Run, step: dict, *, honor_at: bool = True) -> None:
    world_id = _world_id()
    if honor_at and isinstance(step.get("at"), str):
        worldclock.set_fake_now(step["at"])
        village.catch_up(world_id)
    if "clock" in step:
        set_clock(step["clock"])
    if "summon" in step:
        if story.open_arc(world_id, step["summon"]) is None \
                and story.arc_status(world_id, step["summon"]) != "open":
            raise WalkthroughError(f"summon {step['summon']!r}: arc did not open")
    if "join" in step:
        j = step["join"]
        join(run, j.get("as", "B"), j.get("name", "Dreamer"), j.get("slot"))
    actor = run.actors.get(step.get("as", "A"))
    before = events.max_seq()
    label = step.get("cmd") or json.dumps(step.get("command") or {})
    if "cmd" in step:
        if actor is None:
            raise WalkthroughError(f"no actor {step.get('as', 'A')!r}")
        lp = await parser.parse_line(actor, step["cmd"])
        if lp.error:
            raise WalkthroughError(f"{step['cmd']!r}: parse error {lp.error}")
        if not (lp.commands or lp.clarify or lp.message):
            raise WalkthroughError(f"{step['cmd']!r} parsed to nothing")
        for p in lp.commands:
            if p.verb == "none":
                raise WalkthroughError(f"{step['cmd']!r} fell to chatter")
            await verbs.execute_command(actor, p.verb, p.dobj_id, p.iobj_id, p.args,
                                        dobj_name=p.dobj_name)
    elif "command" in step:
        c = step["command"]
        await verbs.execute_command(actor, c["verb"], c.get("dobj_id"), c.get("iobj_id"),
                                    c.get("args", ""))
    run.steps += 1
    said = [e.payload.get("text", "") for e in events.fetch_since(before)
            if e.kind == "narrate" and (e.recipient_id in (None, actor))]
    if "cmd" in step or "command" in step:
        run.transcript.append(f"> [{step.get('as', 'A')}] {label}")
        run.transcript.extend(f"  {t}" for t in said)
    if "expect" in step:
        check(run, step["expect"], step.get("as", "A"), " ".join(said), label)


def check(run: Run, expect: dict, who: str, said: str, label: str) -> None:
    world_id = _world_id()
    actor = run.actors.get(who)
    where = f"[{run.name}] after {label!r}"

    def fail(msg):
        raise WalkthroughError(f"{where}: {msg}")

    me = objects.get(actor) if actor else None
    if "room" in expect and (me is None or me.location_id != expect["room"]):
        fail(f"in {me.location_id if me else None}, wanted {expect['room']}")
    carried = {o.name for o in objects.contents(actor, kind="thing")} if actor else set()
    for n in expect.get("carrying", []):
        if n not in carried:
            fail(f"not carrying {n!r} (carrying {sorted(carried)})")
    for n in expect.get("not_carrying", []):
        if n in carried:
            fail(f"still carrying {n!r}")
    for f, v in (expect.get("flag") or {}).items():
        if worldstate.get_flag(world_id, f) is not v:
            fail(f"flag {f} != {v}")
    for f, v in (expect.get("pflag") or {}).items():
        if story.pflag(world_id, actor, f) is not v:
            fail(f"pflag {f} != {v}")
    for a, st in (expect.get("arc") or {}).items():
        if story.arc_status(world_id, a) != st:
            fail(f"arc {a} is {story.arc_status(world_id, a)}, wanted {st}")
    for a, e in (expect.get("ending") or {}).items():
        if story.ending_of(world_id, a) != e:
            fail(f"arc {a} ending {story.ending_of(world_id, a)}, wanted {e}")
    for ref in expect.get("beats", []):
        a, b = ref.split("/", 1)
        if not story.beat_done(world_id, a, b):
            fail(f"beat {ref} not done")
    for npc, spec in (expect.get("rel") or {}).items():
        if not _cmp(spec, story.rel(world_id, npc, actor)):
            fail(f"rel {npc} = {story.rel(world_id, npc, actor)}, wanted {spec}")
    if "collected" in expect and not _cmp(expect["collected"], collect.count(world_id, actor)):
        fail(f"collected {collect.count(world_id, actor)}, wanted {expect['collected']}")
    if "phase" in expect and village.phase(world_id) != expect["phase"]:
        fail(f"phase {village.phase(world_id)}, wanted {expect['phase']}")
    if "day" in expect and not _cmp(expect["day"], village.day(world_id)):
        fail(f"day {village.day(world_id)}, wanted {expect['day']}")
    for npc, fact in (expect.get("knows") or {}).items():
        if not knowledge.npc_knows(world_id, npc, fact):
            fail(f"{npc} does not know {fact}")
    for obj, room in (expect.get("located") or {}).items():
        o = objects.get(obj)
        if o is None or o.location_id != room:
            fail(f"{obj} at {o.location_id if o else 'nowhere'}, wanted {room}")
    wants = expect.get("narrate_contains", [])
    for w in [wants] if isinstance(wants, str) else wants:
        if w not in said:
            fail(f"narration lacks {w!r}: {said[:400]!r}")
    lacks = expect.get("narrate_lacks", [])
    for w in [lacks] if isinstance(lacks, str) else lacks:
        if w in said:
            fail(f"narration has {w!r}")
    if "chronicle_contains" in expect:
        text = " ".join(e.get("text", "") for e in story.chronicle(world_id))
        if expect["chronicle_contains"] not in text:
            fail(f"chronicle lacks {expect['chronicle_contains']!r}")


async def replay(dataset: dict, *, on_live_copy: bool = False) -> Run:
    """Replay one dataset against the world open in the live connection.
    `on_live_copy` (the dream rehearsal): the clock starts at the real now
    and absolute `clock` steps are refused, since the side copy's time has
    already moved on."""
    run = Run(name=dataset.get("name", "walkthrough"))
    if not on_live_copy and dataset.get("clock"):
        worldclock.set_fake_now(dataset["clock"])
    elif on_live_copy:
        worldclock.set_fake_now(worldclock.now())
    for p in dataset.get("players", [{"as": "A", "name": "Wren"}]):
        join(run, p.get("as", "A"), p.get("name", "Wren"), p.get("slot"))
    if dataset.get("actor") and "A" not in run.actors:
        join(run, "A", "Replayer")
    for seg in dataset.get("segments", []):
        for step in seg.get("commands", []):
            if on_live_copy and isinstance(step.get("clock"), str) \
                    and not (step["clock"].startswith("+") or step["clock"].startswith("@")):
                raise WalkthroughError("absolute clock steps cannot replay on a live copy")
            await run_step(run, step, honor_at=not on_live_copy)
    if dataset.get("final"):
        check(run, dataset["final"], "A", "", "(final)")
    return run


def fresh_world(env: dict, path: Path, patches: list[dict] | None = None) -> None:
    """Build `env` (+ any dream patches, in order) into a fresh DB at `path`
    and open it as the live connection."""
    from daydream import config
    from daydream.llm import bootstrap

    db.close_db()
    events.reset_subscribers()
    bootstrap.load_world("walkthrough", env, path, force=True)
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    if patches:
        from daydream import dream

        for patch in patches:
            dream.apply_patch(patch)
