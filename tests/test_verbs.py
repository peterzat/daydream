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
        "look", "examine", "take", "drop", "talk", "give", "use",
        "open", "close", "put", "read", "plant", "say", "go", "inventory",
    }
    # Arg-specs: object-targeted verbs declare a dobj + valid kinds.
    assert verbs.VERBS["take"].needs_dobj
    assert verbs.VERBS["take"].valid_dobj_kinds == frozenset({"thing"})
    assert verbs.VERBS["talk"].valid_dobj_kinds == frozenset({"toon"})
    assert not verbs.VERBS["look"].needs_dobj
    # Two-object verbs declare a dobj AND an iobj with valid kinds for each.
    assert verbs.VERBS["give"].needs_dobj and verbs.VERBS["give"].needs_iobj
    assert verbs.VERBS["give"].valid_dobj_kinds == frozenset({"thing"})
    assert verbs.VERBS["give"].valid_iobj_kinds == frozenset({"toon"})
    assert verbs.VERBS["use"].valid_dobj_kinds == frozenset({"thing"})
    assert verbs.VERBS["use"].valid_iobj_kinds == frozenset({"thing"})
    # plant: single-object, free-text vision args, and the SOLE declarer of
    # the restricted effect kinds (SPEC 2026-07-02 + the husk rename).
    assert verbs.VERBS["plant"].needs_dobj and not verbs.VERBS["plant"].needs_iobj
    assert verbs.VERBS["plant"].valid_dobj_kinds == frozenset({"thing"})
    assert verbs.VERBS["plant"].free_text
    restricted = {"spawn_room", "link_exit", "rename_object"}
    assert restricted <= verbs.VERBS["plant"].allowed_effects
    for name, spec in verbs.VERBS.items():
        if name != "plant":
            assert not (restricted & spec.allowed_effects), (
                f"{name} must not declare restricted effects"
            )
    # The verb bar offers the interaction verbs, verb-then-object.
    assert [v.name for v in verbs.bar_verbs()] == [
        "examine", "take", "drop", "talk", "give", "use", "open", "close",
        "put", "read", "plant",
    ]


def test_available_verbs_derive_from_kind_prototype():
    # A thing exposes examine/take/drop; an NPC exposes examine/talk — from the
    # prototype, with no per-object re-declaration.
    assert objects.verbs_for(objects.get("i-lantern")) == ["examine", "take", "drop", "put"]
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


# ---- two-object verbs: give (dobj thing -> iobj toon) -------------------


def _make_giveable_lantern_carried() -> str:
    """Give the seeded lantern the `give` verb and put it in Wren's hands.
    Returns the lantern's display name for `wants` matching."""
    objects.set_property("i-lantern", "verbs", ["give"])
    objects.move("i-lantern", "t-wren")
    return objects.get("i-lantern").name


@pytest.mark.asyncio
async def test_give_wanted_item_moves_shifts_mood_and_rewards():
    name = _make_giveable_lantern_carried()
    objects.move("t-wren", "r-forge")  # co-locate with Rook
    objects.set_property("t-rook", "wants", name)
    objects.set_property("t-rook", "gives_mood", "delighted")
    objects.set_property("t-rook", "gives", {
        "name": "brass key", "seed": "a small warm key",
        "aliases": ["key"], "verbs": ["use"]})
    objects.set_property("t-rook", "gives_text", "Rook presses a brass key into your palm.")
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id="t-rook")
    # The gift reparents onto Rook (present in exactly one container).
    assert objects.get("i-lantern").location_id == "t-rook"
    # Rook's mood shifts (a visible, deterministic change).
    assert objects.get("t-rook").properties.get("mood") == "delighted"
    # The reward spawns into Wren's inventory, use-able, exactly once.
    keys = [o for o in objects.contents("t-wren", "thing") if o.name == "brass key"]
    assert len(keys) == 1 and "use" in objects.verbs_for(keys[0])
    assert "brass key" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_give_reward_does_not_double_on_replay():
    # The reward carries provenance; a second give (were the gear back) never
    # spawns a second key. Here we call the reward-spawn path twice by re-giving
    # a still-wanted item to confirm the dedup.
    name = _make_giveable_lantern_carried()
    objects.move("t-wren", "r-forge")
    objects.set_property("t-rook", "wants", name)
    objects.set_property("t-rook", "gives", {"name": "brass key", "seed": "a key"})
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id="t-rook")
    # Put the gift back in hand and give again (simulates a re-run of the beat).
    objects.move("i-lantern", "t-wren")
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id="t-rook")
    keys = [o for o in objects.contents("t-wren", "thing") if o.name == "brass key"]
    assert len(keys) == 1  # deduped by provenance


@pytest.mark.asyncio
async def test_give_unwanted_item_declined_no_move():
    _make_giveable_lantern_carried()
    objects.move("t-wren", "r-forge")
    objects.set_property("t-rook", "wants", "silver thimble")  # not the lantern
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id="t-rook")
    assert objects.get("i-lantern").location_id == "t-wren"  # stays carried
    assert _last_narrate() is not None  # a soft decline


@pytest.mark.asyncio
async def test_give_thing_not_carried_is_refused():
    objects.set_property("i-lantern", "verbs", ["give"])
    objects.move("t-wren", "r-forge")
    objects.move("i-lantern", "r-forge")  # on the ground, in scope, not carried
    objects.set_property("t-rook", "wants", objects.get("i-lantern").name)
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id="t-rook")
    assert "aren't carrying" in _last_narrate().lower()
    assert objects.get("i-lantern").location_id == "r-forge"  # unmoved


@pytest.mark.asyncio
async def test_give_to_self_is_refused():
    _make_giveable_lantern_carried()
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id="t-wren")
    assert "yourself" in _last_narrate().lower()
    assert objects.get("i-lantern").location_id == "t-wren"  # unmoved


@pytest.mark.asyncio
async def test_give_without_iobj_asks_to_whom():
    _make_giveable_lantern_carried()
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern")
    assert "whom" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_give_to_a_thing_is_refused_by_kind_gate():
    _make_giveable_lantern_carried()
    cup = objects.spawn("w-bunny", "thing", "clay cup", "r-meadow",
                        prototype_id=objects.PROTO_THING)
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id=cup.id)
    assert "can't give" in _last_narrate().lower()
    assert objects.get("i-lantern").location_id == "t-wren"  # unmoved


# ---- two-object verbs: use (dobj thing -> iobj thing) -------------------


def _spawn_lockbox(state: str = "locked") -> str:
    """A stateful thing in the meadow whose `use` rule accepts the 'case key'."""
    box = objects.spawn("w-bunny", "thing", "clock case", "r-meadow",
        prototype_id=objects.PROTO_THING, properties={"state": state, "use": {
            "with": "case key", "from_state": "locked", "to_state": "unlocked",
            "text": "The lock gives with a soft click."}})
    return box.id


def _spawn_carried_key() -> str:
    key = objects.spawn("w-bunny", "thing", "case key", "t-wren",
        prototype_id=objects.PROTO_THING, properties={"verbs": ["use"]})
    return key.id


@pytest.mark.asyncio
async def test_use_correct_item_in_right_state_transitions():
    box = _spawn_lockbox("locked")
    key = _spawn_carried_key()
    await verbs.execute_command("t-wren", "use", dobj_id=key, iobj_id=box)
    assert objects.get(box).properties.get("state") == "unlocked"
    assert "click" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_use_wrong_item_changes_nothing():
    box = _spawn_lockbox("locked")
    objects.set_property("i-lantern", "verbs", ["use"])  # a use-able but wrong item
    await verbs.execute_command("t-wren", "use", dobj_id="i-lantern", iobj_id=box)
    assert objects.get(box).properties.get("state") == "locked"  # unchanged
    assert "nothing happens" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_use_right_item_wrong_state_changes_nothing():
    box = _spawn_lockbox("unlocked")  # already past from_state
    key = _spawn_carried_key()
    await verbs.execute_command("t-wren", "use", dobj_id=key, iobj_id=box)
    assert objects.get(box).properties.get("state") == "unlocked"  # unchanged
    assert "nothing happens" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_use_on_a_toon_is_refused_by_kind_gate():
    key = _spawn_carried_key()
    objects.move("t-wren", "r-forge")  # co-locate with Rook
    await verbs.execute_command("t-wren", "use", dobj_id=key, iobj_id="t-rook")
    line = _last_narrate()
    assert "can't use" in line.lower()
    # Articles read naturally: things take 'the', named toons take none
    # (playtest 2026-07-02: 'You can't use the case key on the Tace.').
    assert line == "You can't use the case key on Rook."


@pytest.mark.asyncio
async def test_refusal_articles_for_things_and_toons():
    # A thing without the verb: 'the' before the thing's name.
    await verbs.execute_command("t-wren", "open", dobj_id="i-lantern")
    assert _last_narrate() == "You can't open the lantern."
    # A toon target: bare name, never 'the Rook'.
    objects.move("t-wren", "r-forge")
    await verbs.execute_command("t-wren", "take", dobj_id="t-rook")
    assert _last_narrate() == "You can't take Rook."


@pytest.mark.asyncio
async def test_give_and_use_make_no_llm_call(monkeypatch):
    spy = AsyncMock(return_value={})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    name = _make_giveable_lantern_carried()
    objects.move("t-wren", "r-forge")
    objects.set_property("t-rook", "wants", name)
    objects.set_property("t-rook", "gives", {"name": "brass key", "seed": "a key"})
    await verbs.execute_command("t-wren", "give", dobj_id="i-lantern", iobj_id="t-rook")
    # A lockbox co-located with Wren (in the forge) so `use` actually runs.
    box = objects.spawn("w-bunny", "thing", "clock case", "r-forge",
        prototype_id=objects.PROTO_THING, properties={"state": "locked", "use": {
            "with": "case key", "from_state": "locked", "to_state": "unlocked",
            "text": "The lock gives with a soft click."}})
    key = _spawn_carried_key()
    await verbs.execute_command("t-wren", "use", dobj_id=key, iobj_id=box.id)
    assert objects.get(box.id).properties.get("state") == "unlocked"
    spy.assert_not_called()


# ---- open (state-gated) + read + state-aware examine -------------------


def _spawn_clock_case(state: str = "locked") -> str:
    """A stateful openable thing in the meadow: a lock, an authored payoff, and
    a state_text map for examine."""
    box = objects.spawn("w-bunny", "thing", "clock case", "r-meadow",
        prototype_id=objects.PROTO_THING, properties={
            "state": state, "verbs": ["open"],
            "seed": "a tall glass-fronted clock case",
            "locked_text": "The clock case is locked tight.",
            "open_text": "The case swings open and the pendulum catches the light.",
            "state_text": {
                "locked": "A small brass lock holds it shut.",
                "unlocked": "The lock hangs open; the case is still closed.",
                "open": "The case stands open.",
            },
            "contains": {"name": "warm brass cog", "seed": "a small warm cog"},
        })
    return box.id


@pytest.mark.asyncio
async def test_open_locked_refuses_with_locked_text_and_no_payoff():
    box = _spawn_clock_case("locked")
    await verbs.execute_command("t-wren", "open", dobj_id=box)
    assert objects.get(box).properties.get("state") == "locked"  # stays shut
    assert "locked" in _last_narrate().lower()
    assert not any(o.name == "warm brass cog" for o in objects.contents("r-meadow", "thing"))


@pytest.mark.asyncio
async def test_open_unlocked_transitions_spawns_payoff_once():
    box = _spawn_clock_case("unlocked")
    await verbs.execute_command("t-wren", "open", dobj_id=box)
    assert objects.get(box).properties.get("state") == "open"
    cogs = [o for o in objects.contents("r-meadow", "thing") if o.name == "warm brass cog"]
    assert len(cogs) == 1
    # The authored payoff narrates AND the engine announces the reveal by name
    # (playtest 2026-07-02: a payload must never materialize silently).
    texts = [e.payload["text"] for e in events.fetch_since(0) if e.kind == "narrate"]
    assert any("pendulum" in t.lower() for t in texts)
    assert texts[-1] == "Inside, you find: warm brass cog."
    # Re-open: says already-open and does NOT re-spawn the payoff.
    await verbs.execute_command("t-wren", "open", dobj_id=box)
    assert "already open" in _last_narrate().lower()
    cogs = [o for o in objects.contents("r-meadow", "thing") if o.name == "warm brass cog"]
    assert len(cogs) == 1


@pytest.mark.asyncio
async def test_open_reveals_list_payload_with_properties():
    """`contains` as a LIST (SPEC 2026-07-02): every entry spawns, per-entry
    `verbs` + `properties` ride into the spawned objects (the dreamseed keeps
    its growth block and offers plant), and a re-open doubles nothing."""
    growth = {"question": "Where does the new way lead?", "theme": ["dusk"],
              "palette": "amber", "exemplars": [
                  {"title": "T", "seed": "s", "description": "d"}]}
    box = objects.spawn("w-bunny", "thing", "clock case", "r-meadow",
        prototype_id=objects.PROTO_THING, properties={
            "state": "unlocked", "verbs": ["open"], "seed": "a tall case",
            "contains": [
                {"name": "warm brass cog", "seed": "a small warm cog"},
                {"name": "dreamseed", "seed": "a seed like a folded lantern",
                 "verbs": ["plant"], "properties": {"growth": growth}},
            ]})
    await verbs.execute_command("t-wren", "open", dobj_id=box.id)
    things = objects.contents("r-meadow", "thing")
    assert sum(1 for o in things if o.name == "warm brass cog") == 1
    seeds = [o for o in things if o.name == "dreamseed"]
    assert len(seeds) == 1
    assert seeds[0].properties["growth"] == growth
    assert "plant" in objects.verbs_for(seeds[0])
    # The engine's reveal line names every payload entry.
    assert _last_narrate() == "Inside, you find: warm brass cog, dreamseed."
    # Re-open says already-open and re-spawns nothing.
    await verbs.execute_command("t-wren", "open", dobj_id=box.id)
    things = objects.contents("r-meadow", "thing")
    assert sum(1 for o in things if o.name in ("warm brass cog", "dreamseed")) == 2


@pytest.mark.asyncio
async def test_read_surfaces_authored_text():
    ledger = objects.spawn("w-bunny", "thing", "repair ledger", "r-meadow",
        prototype_id=objects.PROTO_READABLE,
        properties={"verbs": ["read"], "seed": "a worn leather ledger",
                    "text": "The escapement gear is lost; return it to Tace."})
    await verbs.execute_command("t-wren", "read", dobj_id=ledger.id)
    assert "escapement gear" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_read_without_text_degrades_gently():
    plain = objects.spawn("w-bunny", "thing", "blank slate", "r-meadow",
        prototype_id=objects.PROTO_THING,
        properties={"verbs": ["read"], "seed": "a smooth grey slate"})
    await verbs.execute_command("t-wren", "read", dobj_id=plain.id)
    assert "nothing" in _last_narrate().lower()


@pytest.mark.asyncio
async def test_examine_appends_state_without_overwriting_seed():
    box = _spawn_clock_case("locked")
    await verbs.execute_command("t-wren", "examine", dobj_id=box)
    line = _last_narrate().lower()
    assert "glass-fronted clock case" in line  # the physical seed survives
    assert "brass lock" in line                # the current-state line appended


# ---- plant (verb-level gates; the pipeline itself is tests/test_growth.py) --


@pytest.mark.asyncio
async def test_plant_non_growth_thing_refused_by_verb_gate(monkeypatch):
    """The lantern doesn't offer `plant`, so the existing verbs_for gate
    refuses before the growth pipeline (or any LLM) is reached."""
    spy = AsyncMock(return_value={})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    await verbs.execute_command("t-wren", "plant", dobj_id="i-lantern",
                                args="a moonlit orchard")
    assert "can't plant" in _last_narrate().lower()
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_bare_plant_asks_plant_what():
    await verbs.execute_command("t-wren", "plant")
    assert "plant what" in _last_narrate().lower()


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
