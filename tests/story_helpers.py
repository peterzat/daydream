"""Shared helpers for the story-layer tests: load a format-2 world into a
temp live DB, make player toons, run typed commands through the real parser
and executor, and read what they narrated."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from daydream import config, db, events, objects, parser, pronouns, toons, verbs, worldclock
from daydream.llm import bootstrap

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests/data/story_fixture.json").read_text())
WORLD = "w-fixture"


def load(tmp_path: Path, env: dict | None = None, name: str = "story") -> None:
    db.close_db()
    events.reset_subscribers()
    pronouns.reset()
    out = tmp_path / f"{name}.db"
    bootstrap.load_world(name, copy.deepcopy(env or FIXTURE), out, force=True)
    db.init_live(path=out, migrations_dir=config.MIGRATIONS_DIR)


def player(slot: int, name: str, room: str | None = None) -> str:
    t = toons.create_toon_in_slot(slot, name, f"{name}, a traveler", f"sess-{name}")
    if room:
        objects.move(t.id, room)
    return t.id


async def say(actor: str, text: str) -> list[str]:
    """Type one line as `actor`; return the narration it caused (all texts,
    in order, including private ones addressed to anyone)."""
    before = events.max_seq()
    lp = await parser.parse_line(actor, text)
    assert lp.error is None, lp.error
    for p in lp.commands:
        await verbs.execute_command(actor, p.verb, p.dobj_id, p.iobj_id, p.args,
                                    dobj_name=p.dobj_name)
    if lp.message:
        return [lp.message]
    return narrations(before)


def narrations(since: int, room: str | None = None) -> list[str]:
    return [e.payload.get("text", "") for e in events.fetch_since(since, room_id=room)
            if e.kind == "narrate"]


def at(iso: str) -> None:
    worldclock.set_fake_now(iso)
