"""Tests for daydream/drift.py.

Covers the canned-pool path (the v0 contract) and the LLM-driven path
landed in SPEC 2026-05-07 "LLM-driven drift narrates with mood-aware
canned fallback". Pure-function tests run as `tier_short`; tick tests
that need the seed migration chain run as `tier_medium`.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import db, drift, events
from daydream.llm import client as llm_client


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


# ---- cadence rule (pure function, tier_short) --------------------------


@pytest.mark.tier_short
def test_compute_next_interval_idle_default():
    """Zero subscribers => idle default (300 s)."""
    assert drift._compute_next_interval(0) == 300.0


@pytest.mark.tier_short
def test_compute_next_interval_busy_default():
    """One or more subscribers => busy default (1800 s)."""
    assert drift._compute_next_interval(1) == 1800.0
    assert drift._compute_next_interval(7) == 1800.0


@pytest.mark.tier_short
def test_compute_next_interval_env_overrides(monkeypatch):
    """DAYDREAM_DRIFT_IDLE_SECONDS / BUSY_SECONDS take effect on
    subsequent calls."""
    monkeypatch.setenv("DAYDREAM_DRIFT_IDLE_SECONDS", "60")
    monkeypatch.setenv("DAYDREAM_DRIFT_BUSY_SECONDS", "240")
    assert drift._compute_next_interval(0) == 60.0
    assert drift._compute_next_interval(1) == 240.0


# ---- pool quality (pure check, tier_short) -----------------------------


@pytest.mark.tier_short
def test_drift_pools_have_mood_buckets_and_min_lines():
    """Per the SPEC contract: each NPC's pool is a dict-of-dicts with
    >=3 mood buckets including `default`, and >=6 distinct non-empty
    lines across all buckets per NPC."""
    assert drift._DRIFT_POOLS, "no drift pools defined"
    for npc_id, buckets in drift._DRIFT_POOLS.items():
        assert isinstance(buckets, dict), f"{npc_id}: pool is not a dict"
        assert "default" in buckets, f"{npc_id}: missing `default` mood bucket"
        assert len(buckets) >= 3, f"{npc_id}: only {len(buckets)} mood buckets"
        all_lines: list[str] = []
        for mood, lines in buckets.items():
            assert isinstance(lines, list), f"{npc_id}/{mood}: not a list"
            for line in lines:
                assert isinstance(line, str), f"{npc_id}/{mood}: non-string {line!r}"
                assert line.strip(), f"{npc_id}/{mood}: empty/whitespace-only line"
            all_lines.extend(lines)
        assert len(all_lines) >= 6, f"{npc_id}: only {len(all_lines)} total lines"
        assert len(set(all_lines)) == len(all_lines), f"{npc_id}: duplicates in pool"


@pytest.mark.tier_short
def test_pick_canned_line_uses_matching_mood_bucket():
    """`_pick_canned_line` returns a line from the bucket matching the
    given mood when present."""
    rng = random.Random(0)
    line = drift._pick_canned_line("t-rook", "thoughtful", rng=rng)
    assert line is not None
    assert line in drift._DRIFT_POOLS["t-rook"]["thoughtful"], (
        f"line {line!r} not from rook/thoughtful bucket"
    )


@pytest.mark.tier_short
def test_pick_canned_line_falls_back_to_default_for_unknown_mood():
    """Unknown moods fall back to the `default` bucket."""
    rng = random.Random(0)
    line = drift._pick_canned_line("t-rook", "weary", rng=rng)
    assert line is not None
    assert line in drift._DRIFT_POOLS["t-rook"]["default"]


@pytest.mark.tier_short
def test_pick_canned_line_returns_none_for_unknown_npc():
    """An NPC id with no pool entry returns None (caller treats as no-op)."""
    line = drift._pick_canned_line("t-nonexistent", "content")
    assert line is None


# ---- tick: canned path (tier_medium, DB needed) ------------------------


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_emits_one_narrate_in_chosen_npc_room(monkeypatch):
    """One tick with two NPCs (Rook at r-forge, Iris at r-attic)
    produces exactly one new narrate event addressed to the chosen
    NPC's room, with text from one of the NPC's pool buckets. LLM
    branch is off (conftest default)."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    before_seq = events.max_seq()

    rng = random.Random(0)
    emitted = await drift._tick(rng=rng)
    assert emitted is True

    new_events = events.fetch_since(before_seq)
    assert len(new_events) == 1
    e = new_events[0]
    assert e.kind == "narrate"
    assert e.actor_type == "system"
    assert e.actor_id is None

    payload_text = e.payload["text"]
    chosen_room = e.room_id
    chosen_npc_id = None
    for npc_id, buckets in drift._DRIFT_POOLS.items():
        for lines in buckets.values():
            if payload_text in lines:
                chosen_npc_id = npc_id
                break
        if chosen_npc_id is not None:
            break
    assert chosen_npc_id is not None, f"text {payload_text!r} not found in any pool"
    from daydream import toons
    npc = toons.get_toon(chosen_npc_id)
    assert npc is not None
    assert chosen_room == npc.current_room_id


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_no_op_when_no_npcs():
    """If no NPCs exist (after explicit deletion), tick is a no-op
    and emits no events."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute("DELETE FROM toons WHERE is_human_controlled = 0")
    before_seq = events.max_seq()
    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is False
    assert events.fetch_since(before_seq) == []


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_canned_uses_npc_mood_bucket(monkeypatch):
    """With LLM disabled and an NPC mood explicitly set, the canned
    line picked must come from the matching bucket. Sets Rook's mood
    to `thoughtful` directly via DB then deletes Iris so the choice
    is deterministic."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    conn = db.get_conn()
    conn.execute("UPDATE toons SET mood = 'thoughtful' WHERE id = 't-rook'")
    conn.execute("DELETE FROM toons WHERE id = 't-iris'")
    before_seq = events.max_seq()

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    e = events.fetch_since(before_seq)[0]
    assert e.payload["text"] in drift._DRIFT_POOLS["t-rook"]["thoughtful"]


# ---- tick: LLM path (tier_medium) --------------------------------------


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_llm_happy_path_emits_llm_text(monkeypatch):
    """With LLM enabled and `acompletion_json` mocked, the tick emits
    the LLM's `narrate` text verbatim, in the chosen NPC's room."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    # Delete Iris so choice is deterministic on Rook.
    db.get_conn().execute("DELETE FROM toons WHERE id = 't-iris'")
    llm_text = "Rook tilts the lamp's wick a quarter-turn brighter and watches the shadows soften."
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"narrate": llm_text}),
    )
    before_seq = events.max_seq()

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    e = events.fetch_since(before_seq)[0]
    assert e.payload["text"] == llm_text
    from daydream import toons
    rook = toons.get_toon("t-rook")
    assert e.room_id == rook.current_room_id


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_llm_falls_back_to_canned_on_unavailable(monkeypatch):
    """LLMUnavailable from `acompletion_json` triggers canned fallback;
    a narrate is still emitted."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    db.get_conn().execute("DELETE FROM toons WHERE id = 't-iris'")
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=llm_client.LLMUnavailable("vllm down")),
    )
    before_seq = events.max_seq()

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    e = events.fetch_since(before_seq)[0]
    rook_lines: list[str] = []
    for lines in drift._DRIFT_POOLS["t-rook"].values():
        rook_lines.extend(lines)
    assert e.payload["text"] in rook_lines


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_llm_narrate_returns_none_on_banlist_hit(monkeypatch):
    """`_llm_narrate` returns None when the parsed narrate trips the
    banlist; caller falls through to canned. Pure-ish unit test of the
    LLM branch — uses an in-memory NPC dict to avoid DB init."""
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"narrate": "the dream feels uncannily pixel-art tonight"}),
    )
    monkeypatch.setattr(
        "daydream.memories.retrieve", lambda *a, **kw: []
    )
    npc = {
        "id": "t-rook",
        "current_room_id": "r-forge",
        "world_id": "w-bunny",
        "mood": "content",
        "name": "Rook",
        "seed": "the forge-keeper",
    }
    result = await drift._llm_narrate(npc)
    assert result is None


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_llm_narrate_returns_none_on_empty_text(monkeypatch):
    """Whitespace-only narrate from the LLM falls back."""
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"narrate": "   "}),
    )
    monkeypatch.setattr(
        "daydream.memories.retrieve", lambda *a, **kw: []
    )
    npc = {
        "id": "t-rook",
        "current_room_id": "r-forge",
        "world_id": "w-bunny",
        "mood": "content",
        "name": "Rook",
        "seed": "the forge-keeper",
    }
    result = await drift._llm_narrate(npc)
    assert result is None


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_llm_narrate_returns_none_on_missing_key(monkeypatch):
    """LLM response without a `narrate` key falls back to canned."""
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"text": "wrong key"}),
    )
    monkeypatch.setattr(
        "daydream.memories.retrieve", lambda *a, **kw: []
    )
    npc = {
        "id": "t-rook",
        "current_room_id": "r-forge",
        "world_id": "w-bunny",
        "mood": "content",
        "name": "Rook",
        "seed": "the forge-keeper",
    }
    result = await drift._llm_narrate(npc)
    assert result is None


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_llm_disabled_never_calls_acompletion(monkeypatch):
    """With `DAYDREAM_DRIFT_LLM_ENABLED=0`, `acompletion_json` is never
    called. Tier_medium because the canned path still requires DB init."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "0")
    mock_llm = AsyncMock(side_effect=AssertionError("LLM should not be called"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", mock_llm)
    db.get_conn().execute("DELETE FROM toons WHERE id = 't-iris'")

    before_seq = events.max_seq()
    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    assert mock_llm.await_count == 0
    e = events.fetch_since(before_seq)[0]
    rook_lines: list[str] = []
    for lines in drift._DRIFT_POOLS["t-rook"].values():
        rook_lines.extend(lines)
    assert e.payload["text"] in rook_lines


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_llm_runs_with_empty_memories(monkeypatch):
    """Fresh world (no memories captured) — the LLM path still runs
    with `memories=[]` and emits the LLM's narrate. Verifies the empty
    branch of the prompt template."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    db.get_conn().execute("DELETE FROM toons WHERE id = 't-iris'")
    captured_user_prompt = {}

    async def fake(system: str, user: str, **kwargs):
        captured_user_prompt["system"] = system
        captured_user_prompt["user"] = user
        return {"narrate": "Rook listens to the wind for a moment."}

    monkeypatch.setattr("daydream.llm.client.acompletion_json", fake)
    before_seq = events.max_seq()

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    assert "<memory>" not in captured_user_prompt["user"], (
        "empty-memories branch should not render <memory> tags"
    )
    e = events.fetch_since(before_seq)[0]
    assert e.payload["text"] == "Rook listens to the wind for a moment."


# ---- cancellation cleanup (tier_short, no DB) --------------------------


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_drift_loop_cancels_cleanly(monkeypatch):
    """start_drift_loop returns a Task that cancellation can stop
    cleanly within ~1 s. Exercises the asyncio.CancelledError path
    without waiting for any tick to fire."""
    monkeypatch.setenv("DAYDREAM_DRIFT_ENABLED", "1")
    handle = drift.start_drift_loop()
    assert handle is not None
    await asyncio.sleep(0.01)
    await drift.stop_drift_loop(handle)
    assert handle.done()
    assert handle.cancelled() or handle.exception() is None


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_start_drift_loop_returns_none_when_disabled(monkeypatch):
    """When DAYDREAM_DRIFT_ENABLED=0, start_drift_loop returns None
    without creating a task. stop_drift_loop(None) is a no-op."""
    monkeypatch.setenv("DAYDREAM_DRIFT_ENABLED", "0")
    handle = drift.start_drift_loop()
    assert handle is None
    await drift.stop_drift_loop(handle)
