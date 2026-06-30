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

from daydream import config, db, events, objects, rooms, verbs

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
    assert set(verbs.VERBS) == {
        "look", "examine", "take", "drop", "talk", "say", "go", "inventory"
    }
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


# ---- clean verb narration (C9, SPEC 2026-06-30) ------------------------


@pytest.mark.asyncio
async def test_examine_detail_is_not_double_punctuated():
    # The lantern seed ends in terminal punctuation; the examine line must not
    # yield "..".
    await verbs.execute_command("t-wren", "examine", dobj_id="i-lantern")
    assert ".." not in _last_narrate()


def test_examine_line_single_terminal_stop():
    lantern = objects.get("i-lantern")
    assert verbs._examine_line(lantern, "a small thing.").endswith("thing.")
    assert ".." not in verbs._examine_line(lantern, "a small thing.")
    assert verbs._examine_line(lantern, "a small thing").endswith("thing.")
    # Empty detail degrades to a clean line, no stray colon.
    assert verbs._examine_line(lantern, "") == "You examine the lantern."


@pytest.mark.asyncio
async def test_named_but_absent_target_says_dont_see():
    # "take the moon": a named target not in scope -> "you don't see ...",
    # distinct from the no-target "Take what?".
    await verbs.execute_command("t-wren", "take", dobj_name="moon")
    line = _last_narrate().lower()
    assert "don't see" in line and "moon" in line


@pytest.mark.asyncio
async def test_no_target_named_says_verb_what():
    # No dobj at all -> the bare "Take what?" prompt.
    await verbs.execute_command("t-wren", "take")
    assert "take what" in _last_narrate().lower()


# ---- inventory (lists carried things; not in the bar) ------------------


@pytest.mark.asyncio
async def test_inventory_empty_says_so():
    await verbs.execute_command("t-wren", "inventory")
    assert "carrying nothing" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_inventory_lists_carried_things():
    await verbs.execute_command("t-wren", "take", dobj_id="i-lantern")
    await verbs.execute_command("t-wren", "inventory")
    line = _last_narrate().lower()
    assert "carrying" in line and "lantern" in line


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


# ---- navigate by place name (C6, SPEC 2026-06-30) ----------------------


@pytest.mark.asyncio
async def test_go_to_place_name_moves_to_adjacent_room():
    # "go to bridge": the place resolves to the meadow's east exit (one hop).
    await verbs.execute_command("t-wren", "go", args="to bridge")
    assert objects.get("t-wren").location_id == "r-bridge"


@pytest.mark.asyncio
async def test_go_to_nonadjacent_place_is_refused():
    # The attic is up from the forge -- two hops, not one exit from the meadow.
    await verbs.execute_command("t-wren", "go", args="to attic")
    assert objects.get("t-wren").location_id == "r-meadow"  # no move
    assert "can't go" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_go_to_unknown_place_is_refused():
    await verbs.execute_command("t-wren", "go", args="to narnia")
    assert objects.get("t-wren").location_id == "r-meadow"
    assert "can't go" in _last_narrate().lower()


def test_exit_direction_for_place_resolves_adjacent_only():
    # Deterministic place-name -> exit-direction resolution (no LLM, no move).
    meadow = rooms.get_room("r-meadow")
    assert verbs._exit_direction_for_place(meadow, "bridge") == "east"
    assert verbs._exit_direction_for_place(meadow, "the forge") == "north"
    assert verbs._exit_direction_for_place(meadow, "attic") is None  # not adjacent
    assert verbs._exit_direction_for_place(meadow, "narnia") is None  # unknown
