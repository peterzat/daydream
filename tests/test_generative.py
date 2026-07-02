"""Generative objects: explicit spawn + lazy-cache examine (daydream/verbs.py +
effects.py).

Covers the SPEC 2026-06-30 "generative objects" criteria with a MOCKED LLM:
a talk verb whose dialogue emits `spawn_object` creates exactly one persistent
clickable thing (Rook's papers) with no narration-noun-scan and no duplicate on
re-run; and examining an object with no cached detail generates it via one LLM
call, persists it, and serves the cache (zero LLM) on the next examine."""

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
    objects.move("t-wren", "r-forge")  # co-locate Wren with Rook
    yield
    db.close_db()
    events.reset_subscribers()


def _last_narrate() -> str | None:
    for e in reversed(events.fetch_since(0)):
        if e.kind == "narrate":
            return e.payload["text"]
    return None


def _install_rook_dialogue() -> None:
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES ('skill-rook', 'rook', 'data', '{}', '{{ player_input }}', "
        "'Rook', 'Talk to Rook.', '{}', 1)"
    )


def _papers_in(room_id: str) -> list:
    return [o for o in objects.contents(room_id, "thing") if o.name == "a sheaf of papers"]


# ---- explicit-spawn generative objects ---------------------------------


@pytest.mark.asyncio
async def test_talk_dialogue_spawns_one_clickable_thing(monkeypatch):
    _install_rook_dialogue()
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"effects": [
            {"kind": "narrate", "text": "Rook spreads a sheaf of papers on the bench."},
            {"kind": "spawn_object", "name": "a sheaf of papers",
             "seed": "loose pages, edges soft with handling", "readable": True,
             "aliases": ["papers", "sheaf"], "generated_by": "talk:t-rook"},
        ]}),
    )
    await verbs.execute_command("t-wren", "talk", dobj_id="t-rook", args="show me your work")
    papers = _papers_in("r-forge")
    assert len(papers) == 1
    p = papers[0]
    # Persistent, clickable (carries inheritable verbs), and readable-typed.
    assert p.kind == "thing"
    assert objects.verbs_for(p) == ["examine", "take", "drop", "put"]
    assert "papers" in p.aliases
    assert p.properties.get("generated_by") == "talk:t-rook"


@pytest.mark.asyncio
async def test_rerunning_the_verb_does_not_duplicate(monkeypatch):
    _install_rook_dialogue()
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"effects": [
            {"kind": "spawn_object", "name": "a sheaf of papers", "seed": "loose pages",
             "readable": True, "generated_by": "talk:t-rook"},
        ]}),
    )
    await verbs.execute_command("t-wren", "talk", dobj_id="t-rook", args="again")
    await verbs.execute_command("t-wren", "talk", dobj_id="t-rook", args="and again")
    assert len(_papers_in("r-forge")) == 1  # exactly one, never duplicated


@pytest.mark.asyncio
async def test_narration_is_never_auto_scanned_for_nouns(monkeypatch):
    """A dialogue that only narrates (mentions a 'lantern', a 'kettle') spawns
    NOTHING — objects become real only via an explicit spawn_object."""
    _install_rook_dialogue()
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"effects": [
            {"kind": "narrate", "text": "Rook nods toward a lantern and an old kettle."},
        ]}),
    )
    before = len(objects.contents("r-forge", "thing"))
    await verbs.execute_command("t-wren", "talk", dobj_id="t-rook", args="hello")
    assert len(objects.contents("r-forge", "thing")) == before  # no nouns promoted


# ---- lazy-cache examine ------------------------------------------------


@pytest.mark.asyncio
async def test_examine_generates_once_then_serves_cache(monkeypatch):
    # A spawned generative object with no seed and no cached examine text.
    objects.spawn(
        "w-bunny", "thing", "a sheaf of papers", "r-forge",
        prototype_id=objects.PROTO_READABLE,
        properties={"seed": "", "generated_by": "talk:t-rook"},
        object_id="o-papers",
    )
    spy = AsyncMock(return_value={"text": "Loose pages, covered edge to edge in careful little sketches of birds."})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)

    # First examine: one LLM call, text persisted.
    await verbs.execute_command("t-wren", "examine", dobj_id="o-papers")
    assert spy.call_count == 1
    assert "careful little sketches" in _last_narrate()
    assert objects.get_property("o-papers", "examined_text")  # persisted

    # Second examine: cache hit, ZERO further LLM calls.
    await verbs.execute_command("t-wren", "examine", dobj_id="o-papers")
    assert spy.call_count == 1  # unchanged
    assert "careful little sketches" in _last_narrate()


@pytest.mark.asyncio
async def test_examine_seeded_object_never_calls_llm(monkeypatch):
    # The lantern HAS a seed -> deterministic examine, no generation.
    objects.move("t-wren", "r-meadow")
    spy = AsyncMock(return_value={"text": "should not be used"})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    await verbs.execute_command("t-wren", "examine", dobj_id="i-lantern")
    assert spy.call_count == 0
    assert "hairline crack" in _last_narrate()


@pytest.mark.asyncio
async def test_examine_generation_outage_is_graceful(monkeypatch):
    from daydream.llm import client
    objects.spawn(
        "w-bunny", "thing", "a curious knot", "r-forge",
        prototype_id=objects.PROTO_THING, properties={"seed": ""},
        object_id="o-knot",
    )
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=client.LLMUnavailable("vllm down")),
    )
    await verbs.execute_command("t-wren", "examine", dobj_id="o-knot")
    # No crash, no cached text, a gentle foggy line.
    assert "foggy" in _last_narrate().lower()
    assert objects.get_property("o-knot", "examined_text") is None
