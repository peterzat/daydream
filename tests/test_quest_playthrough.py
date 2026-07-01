"""Golden playthrough of The Clockmaker's Loft (SPEC 2026-07-01, criterion 1).

The deterministic integrity test the architecture was missing: load
worlds/clockmakers-loft.json into a temp live DB and drive the fixed quest
sequence through the real command executor --

    read ledger -> take gear -> give gear to Tace -> use case-key on
    clock-case -> open clock-case

-- asserting every transition (the clue surfaces; the gear moves into
inventory then reparents onto Tace exactly once; Tace's mood shifts; a use-able
case-key spawns; the case flips locked->unlocked->open; the payoff spawns
exactly once and a re-open does not double it). The whole path makes ZERO LLM
calls, asserted by a spy. A future change that breaks the loop fails here."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import admin, config, db, events, objects, verbs

pytestmark = pytest.mark.tier_medium

REPO = Path(__file__).resolve().parent.parent
WORLD = REPO / "worlds" / "clockmakers-loft.json"


@pytest.fixture()
def loft(tmp_path: Path):
    out = tmp_path / "live.db"
    assert admin.main(["load", str(WORLD), "--output", str(out)]) == 0
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=out, migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _id(kind: str, name: str) -> str:
    row = db.get_conn().execute(
        "SELECT id FROM objects WHERE kind = ? AND name = ?", (kind, name)
    ).fetchone()
    assert row is not None, f"missing {kind} {name!r}"
    return row["id"]


def _narrates() -> list[str]:
    return [e.payload["text"] for e in events.fetch_since(0) if e.kind == "narrate"]


def _last_narrate() -> str:
    texts = _narrates()
    assert texts, "no narration emitted"
    return texts[-1]


def _count_in_room(room_id: str, name: str) -> int:
    return sum(1 for o in objects.contents(room_id, "thing") if o.name == name)


@pytest.mark.asyncio
async def test_golden_quest_playthrough_zero_llm(loft, monkeypatch):
    # Any LLM call during the deterministic path is a bug: spy that fails loudly.
    spy = AsyncMock(side_effect=AssertionError("deterministic path hit the LLM"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)

    actor = _id("toon", "Wick")
    clocktower = objects.get(actor).location_id
    ledger = _id("thing", "repair ledger")
    case = _id("thing", "clock case")
    gear = _id("thing", "escapement gear")
    tace = _id("toon", "Tace")

    # 1. Read the ledger -> the authored clue surfaces (gear + the well).
    await verbs.execute_command(actor, "read", dobj_id=ledger)
    clue = _last_narrate().lower()
    assert "escapement gear" in clue and "well" in clue

    # examine the locked case -> the physical seed + the locked state line.
    await verbs.execute_command(actor, "examine", dobj_id=case)
    ex = _last_narrate().lower()
    assert "clock case" in ex and "lock" in ex

    # 2. Walk to the well and take the gear -> it leaves the ground, enters
    #    inventory (present in exactly one container).
    await verbs.execute_command(actor, "go", args="east")   # clocktower -> square
    await verbs.execute_command(actor, "go", args="south")  # square -> well
    well = objects.get(actor).location_id
    assert _count_in_room(well, "escapement gear") == 1
    await verbs.execute_command(actor, "take", dobj_id=gear)
    assert objects.get(gear).location_id == actor
    assert _count_in_room(well, "escapement gear") == 0

    # 3. Carry it to Tace in the loft and give it -> the gear reparents onto
    #    Tace (exactly one), her mood shifts, and a use-able case-key spawns
    #    into inventory with the authored gives_text.
    await verbs.execute_command(actor, "go", args="north")  # well -> square
    await verbs.execute_command(actor, "go", args="west")   # square -> clocktower
    await verbs.execute_command(actor, "go", args="up")     # clocktower -> loft
    mood_before = objects.get(tace).properties.get("mood")
    await verbs.execute_command(actor, "give", dobj_id=gear, iobj_id=tace)
    assert objects.get(gear).location_id == tace          # moved onto Tace
    assert sum(1 for o in objects.contents(tace, "thing") if o.id == gear) == 1
    assert objects.get(tace).properties.get("mood") != mood_before  # mood shifted
    keys = [o for o in objects.contents(actor, "thing") if o.name == "case key"]
    assert len(keys) == 1 and "use" in objects.verbs_for(keys[0])
    assert "case" in _last_narrate().lower()  # gives_text mentions the case

    # 4. Back at the clock, use the case-key on the case -> locked -> unlocked.
    await verbs.execute_command(actor, "go", args="down")   # loft -> clocktower
    assert objects.get(case).properties.get("state") == "locked"
    await verbs.execute_command(actor, "use", dobj_id=keys[0].id, iobj_id=case)
    assert objects.get(case).properties.get("state") == "unlocked"

    # 5. Open the case -> unlocked -> open, the payoff narrates, and the reward
    #    spawns exactly once. A re-open says so and does NOT double it.
    await verbs.execute_command(actor, "open", dobj_id=case)
    assert objects.get(case).properties.get("state") == "open"
    assert "clock" in _last_narrate().lower()  # the great clock ticks again
    assert _count_in_room(clocktower, "warm brass cog") == 1
    await verbs.execute_command(actor, "open", dobj_id=case)
    assert "already open" in _last_narrate().lower()
    assert _count_in_room(clocktower, "warm brass cog") == 1  # not doubled

    spy.assert_not_called()  # the whole quest was deterministic


@pytest.mark.asyncio
async def test_use_wrong_state_and_open_locked_are_soft_noops(loft, monkeypatch):
    """Integrity invariants: opening the still-locked case refuses (no payoff),
    and using the key before it's obtained can't happen — but using the WRONG
    item on the case changes nothing. Both are soft, mutation-free."""
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(side_effect=AssertionError("unexpected LLM")))
    actor = _id("toon", "Wick")
    clocktower = objects.get(actor).location_id
    case = _id("thing", "clock case")

    # Open while locked -> refused with the locked text, no payoff spawned.
    await verbs.execute_command(actor, "open", dobj_id=case)
    assert objects.get(case).properties.get("state") == "locked"
    assert "lock" in _last_narrate().lower()
    assert _count_in_room(clocktower, "warm brass cog") == 0

    # Read the ledger, then try to "use the ledger on the case" -> wrong item,
    # nothing happens, the case stays locked.
    ledger = _id("thing", "repair ledger")
    await verbs.execute_command(actor, "take", dobj_id=ledger)
    objects.set_property(ledger, "verbs", ["use", "read", "examine", "take", "drop"])
    await verbs.execute_command(actor, "use", dobj_id=ledger, iobj_id=case)
    assert objects.get(case).properties.get("state") == "locked"
    assert "nothing happens" in _last_narrate().lower()
