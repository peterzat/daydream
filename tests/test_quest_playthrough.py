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


async def _drive_quest_to_open_case(actor: str) -> None:
    """Replay the quest beats (deterministic, zero LLM): fetch the gear, earn
    the key, unlock and open the case. Leaves the actor in the clocktower with
    the case open and its payload revealed."""
    gear = _id("thing", "escapement gear")
    tace = _id("toon", "Tace")
    case = _id("thing", "clock case")
    await verbs.execute_command(actor, "go", args="east")   # clocktower -> square
    await verbs.execute_command(actor, "go", args="south")  # square -> well
    await verbs.execute_command(actor, "take", dobj_id=gear)
    await verbs.execute_command(actor, "go", args="north")  # well -> square
    await verbs.execute_command(actor, "go", args="west")   # square -> clocktower
    await verbs.execute_command(actor, "go", args="up")     # clocktower -> loft
    await verbs.execute_command(actor, "give", dobj_id=gear, iobj_id=tace)
    key = next(o for o in objects.contents(actor, "thing") if o.name == "case key")
    await verbs.execute_command(actor, "go", args="down")   # loft -> clocktower
    await verbs.execute_command(actor, "use", dobj_id=key.id, iobj_id=case)
    await verbs.execute_command(actor, "open", dobj_id=case)


_PLANT_COMPOSITION = {
    "title": "The Quiet Orchard",
    "room_seed": "a small orchard of clock-fruit trees at dusk, each fruit "
                 "ticking softly under the leaves",
    "description": "Rows of low trees hold small brass fruit, and each one "
                   "ticks softly to itself under the leaves. The grass is "
                   "cool and blue with evening. Somewhere at the orchard's "
                   "edge, one tree keeps a different, older time.",
    "objects": [
        {"name": "clock-fruit", "seed": "a small brass fruit, warm and "
                                        "faintly ticking in the palm"},
    ],
}


@pytest.mark.asyncio
async def test_golden_dreamseed_plant_extension(loft, monkeypatch):
    """SPEC 2026-07-02 criterion 1 golden extension: the opened case reveals
    the dreamseed; bare plant asks the seed's authored question (zero LLM);
    the mocked-LLM plant grows exactly one room with exits both ways,
    provenance, the spent husk resting inside; a replant refuses; and the
    growth cap refuses in character. Deterministic, zero real GPU."""
    spy = AsyncMock(side_effect=AssertionError("unexpected LLM call"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)

    actor = _id("toon", "Wick")
    clocktower = objects.get(actor).location_id
    await _drive_quest_to_open_case(actor)

    # The case revealed BOTH payloads (quest golden above asserts the cog).
    assert _count_in_room(clocktower, "warm brass cog") == 1
    assert _count_in_room(clocktower, "dreamseed") == 1
    seed = next(o for o in objects.contents(clocktower, "thing")
                if o.name == "dreamseed")
    assert "plant" in objects.verbs_for(seed)
    assert isinstance(seed.properties.get("growth"), dict)

    # Take it; bare plant asks the seed's authored question — zero LLM.
    await verbs.execute_command(actor, "take", dobj_id=seed.id)
    await verbs.execute_command(actor, "plant", dobj_id=seed.id)
    assert _last_narrate() == "Where does the new way lead?"
    spy.assert_not_called()

    # Plant with a vision: ONE LLM call, the full atomic batch.
    grow_spy = AsyncMock(return_value=dict(_PLANT_COMPOSITION))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", grow_spy)
    phrase = "an orchard where the fruit keeps time"
    await verbs.execute_command(actor, "plant", dobj_id=seed.id, args=phrase)
    assert grow_spy.call_count == 1

    from daydream import rooms as rooms_mod
    grown = rooms_mod.get_room_by_slug("w-bunny", "the-quiet-orchard")
    assert grown is not None
    assert grown.description_cached == _PLANT_COMPOSITION["description"]
    # Clocktower exits were up + east; first free is north, reverse south.
    assert rooms_mod.get_room(clocktower).exits["north"] == grown.id
    assert grown.exits["south"] == clocktower
    props = objects.get(grown.id).properties
    assert props["generated_by"] == f"plant:{seed.id}"
    assert props["grown"]["planter_id"] == actor
    assert props["grown"]["phrase"] == phrase
    # The composed object + the spent husk rest in the grown room.
    names = {o.name for o in objects.contents(grown.id, "thing")}
    assert {"clock-fruit", "dreamseed"} <= names
    husk = objects.get(seed.id)
    assert husk.location_id == grown.id
    assert husk.properties["state"] == "spent"
    assert "plant" not in objects.verbs_for(husk)
    payoff = _last_narrate()
    assert "north" in payoff and "The Quiet Orchard" in payoff

    # Replant the husk: refused in character, no second call, no second room.
    await verbs.execute_command(actor, "go", args="north")
    await verbs.execute_command(actor, "take", dobj_id=seed.id)
    await verbs.execute_command(actor, "plant", dobj_id=seed.id, args=phrase)
    assert grow_spy.call_count == 1
    assert rooms_mod.grown_room_count("w-bunny") == 1

    # The growth cap refuses in character before any LLM call.
    monkeypatch.setenv("DAYDREAM_GROWTH_MAX_ROOMS", "1")
    second = objects.spawn(
        "w-bunny", "thing", "second dreamseed", actor,
        prototype_id=objects.PROTO_THING,
        properties={"seed": "another seed", "verbs": ["plant"],
                    "growth": seed.properties["growth"]},
    )
    await verbs.execute_command(actor, "plant", dobj_id=second.id,
                                args="a second orchard")
    assert grow_spy.call_count == 1
    assert rooms_mod.grown_room_count("w-bunny") == 1
    assert objects.get(second.id).properties.get("state") != "spent"


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
