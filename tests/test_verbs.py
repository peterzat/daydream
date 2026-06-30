"""Verb registry + structured command bus (daydream/verbs.py).

Covers the SPEC 2026-06-30 "verbs & dispatch" criteria: a closed verb registry
with arg-specs; MOO dispatch priority (a verb bound to an object wins over the
generic default — talk to Rook runs Rook's dialogue, not a stub); take/drop
move objects via the effect API and invalid targets are refused with narration
and no state change; and the command path issues zero LLM calls for the
deterministic verbs."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, verbs

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _last_narrate() -> str | None:
    for e in reversed(events.fetch_since(0)):
        if e.kind == "narrate":
            return e.payload["text"]
    return None


def _install_dialogue(name: str) -> None:
    """Install a minimal data skill bound (by the t-<name> convention) to an
    NPC, so `talk` has an object-bound handler to dispatch to."""
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES (?, ?, 'data', '{}', '{{ player_input }}', ?, ?, '{}', 1)",
        (f"skill-{name}", name, name.title(), f"Talk to {name}."),
    )


# ---- closed registry with arg-specs ------------------------------------


def test_closed_verb_registry_with_arg_specs():
    assert set(verbs.VERBS) == {"look", "examine", "take", "drop", "talk", "say", "go"}
    # Arg-specs: object-targeted verbs declare a dobj + valid kinds.
    assert verbs.VERBS["take"].needs_dobj
    assert verbs.VERBS["take"].valid_dobj_kinds == frozenset({"thing"})
    assert verbs.VERBS["talk"].valid_dobj_kinds == frozenset({"toon"})
    assert not verbs.VERBS["look"].needs_dobj
    # The verb bar offers exactly Examine / Take / Drop / Talk.
    assert [v.name for v in verbs.bar_verbs()] == ["examine", "take", "drop", "talk"]


def test_available_verbs_derive_from_kind_prototype():
    # A thing exposes examine/take/drop; an NPC exposes examine/talk — from the
    # prototype, with no per-object re-declaration.
    assert objects.verbs_for(objects.get("i-lantern")) == ["examine", "take", "drop"]
    assert objects.verbs_for(objects.get("t-rook")) == ["examine", "talk"]


# ---- take / drop move objects ------------------------------------------


@pytest.mark.asyncio
async def test_take_moves_thing_into_inventory():
    assert objects.get("i-lantern").location_id == "r-meadow"
    await verbs.execute_command("t-wren", "take", dobj_id="i-lantern")
    assert objects.get("i-lantern").location_id == "t-wren"
    assert "take the lantern" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_drop_moves_thing_to_room():
    await verbs.execute_command("t-wren", "take", dobj_id="i-lantern")
    await verbs.execute_command("t-wren", "drop", dobj_id="i-lantern")
    assert objects.get("i-lantern").location_id == "r-meadow"
    assert "drop the lantern" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_drop_thing_not_carried_is_refused():
    # The lantern is on the ground, not carried: drop refuses, no move.
    await verbs.execute_command("t-wren", "drop", dobj_id="i-lantern")
    assert objects.get("i-lantern").location_id == "r-meadow"
    assert "aren't carrying" in _last_narrate().lower()


# ---- invalid targets refused (no state change) -------------------------


@pytest.mark.asyncio
async def test_take_a_toon_is_refused():
    before = objects.get("t-rook").location_id
    # Move Wren to the forge so Rook is in scope, then try to take Rook.
    objects.move("t-wren", "r-forge")
    await verbs.execute_command("t-wren", "take", dobj_id="t-rook")
    assert objects.get("t-rook").location_id == before  # unmoved
    assert "can't take" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_talk_to_a_thing_is_refused():
    await verbs.execute_command("t-wren", "talk", dobj_id="i-lantern", args="hello")
    assert "can't talk" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_out_of_scope_target_is_refused():
    # Rook is in r-forge; Wren is in r-meadow, so Rook is out of scope.
    await verbs.execute_command("t-wren", "examine", dobj_id="t-rook")
    assert "don't see that here" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_unknown_verb_is_graceful():
    await verbs.execute_command("t-wren", "obliterate", dobj_id="i-lantern")
    assert _last_narrate() is not None  # a gentle "don't understand", no crash


# ---- MOO dispatch priority: bound dialogue wins over the stub ----------


@pytest.mark.asyncio
async def test_talk_to_npc_runs_bound_dialogue_not_stub(monkeypatch):
    _install_dialogue("rook")
    objects.move("t-wren", "r-forge")  # co-locate with Rook
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"effects": [{"kind": "narrate", "text": "Rook nods warmly."}]}),
    )
    await verbs.execute_command("t-wren", "talk", dobj_id="t-rook", args="hello")
    # The bound dialogue's narration reached the log (not the no-dialogue stub).
    assert _last_narrate() == "Rook nods warmly."


@pytest.mark.asyncio
async def test_talk_to_npc_without_dialogue_falls_back_to_stub():
    objects.move("t-wren", "r-forge")  # Rook present, but no dialogue installed
    await verbs.execute_command("t-wren", "talk", dobj_id="t-rook", args="hi")
    assert "doesn't have much to say" in _last_narrate().lower()


# ---- one executor, command path makes no LLM call ----------------------


@pytest.mark.asyncio
async def test_deterministic_command_path_makes_no_llm_call(monkeypatch):
    spy = AsyncMock(return_value={})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    await verbs.execute_command("t-wren", "examine", dobj_id="i-lantern")
    await verbs.execute_command("t-wren", "take", dobj_id="i-lantern")
    await verbs.execute_command("t-wren", "drop", dobj_id="i-lantern")
    await verbs.execute_command("t-wren", "look")
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_examine_thing_echoes_cached_detail():
    await verbs.execute_command("t-wren", "examine", dobj_id="i-lantern")
    assert "hairline crack" in _last_narrate()  # the seed sentinel, no LLM


# ---- go (movement stays a verb; not in the bar) ------------------------


@pytest.mark.asyncio
async def test_go_moves_through_exit():
    await verbs.execute_command("t-wren", "go", args="north")  # meadow -> forge
    assert objects.get("t-wren").location_id == "r-forge"


@pytest.mark.asyncio
async def test_go_invalid_direction_refused():
    await verbs.execute_command("t-wren", "go", args="sideways")
    assert objects.get("t-wren").location_id == "r-meadow"
    assert "can't go" in _last_narrate().lower()
