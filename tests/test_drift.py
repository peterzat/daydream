"""Tests for daydream/drift.py.

Covers the canned-pool path (the v0 contract) and the LLM-driven path
landed in SPEC 2026-05-07 "LLM-driven drift narrates with mood-aware
canned fallback". Pure-function tests run as `tier_short`; tick tests
that need the seed migration chain run as `tier_medium`.
"""

from __future__ import annotations

import asyncio
import json
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
    """One or more subscribers => the minutes-scale witnessed-drift cadence
    (240 s), retuned down from the old 30-min busy cadence (SPEC 2026-06-30)."""
    assert drift._compute_next_interval(1) == 240.0
    assert drift._compute_next_interval(7) == 240.0


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
def test_pick_canned_line_falls_through_to_generic_for_unknown_npc():
    """An NPC id with no per-NPC pool entry falls through to
    `_GENERIC_DRIFT_POOL` (was: returned None). With no `name` passed,
    the `{name}` token is left literal. Replaces the old
    returns-None-for-unknown-npc test, since the contract is now
    generic-pool fall-through, not None."""
    line = drift._pick_canned_line("t-nonexistent", "content")
    assert line is not None
    assert line in drift._GENERIC_DRIFT_POOL["content"], (
        f"line {line!r} not from generic/content bucket"
    )
    assert "{name}" in line, "name=None should leave the {name} token untouched"


@pytest.mark.tier_short
def test_pick_canned_line_substitutes_name_in_generic_pool():
    """`_pick_canned_line(unknown_id, mood, name=...)` returns a line
    from the generic pool's matching mood bucket with `{name}`
    substituted by the toon name via str.replace."""
    rng = random.Random(0)
    line = drift._pick_canned_line("t-foo", "curious", rng=rng, name="Foo")
    assert line is not None
    expected = {
        l.replace("{name}", "Foo") for l in drift._GENERIC_DRIFT_POOL["curious"]
    }
    assert line in expected, f"line {line!r} not a name-substituted curious line"
    assert "{name}" not in line, "the {name} token should be fully substituted"
    assert "Foo" in line


@pytest.mark.tier_short
def test_pick_canned_line_curly_brace_name_does_not_crash():
    """A generated name containing `{`/`}` (which would crash
    str.format) substitutes cleanly via str.replace and appears
    verbatim in the result."""
    rng = random.Random(0)
    line = drift._pick_canned_line("t-foo", "content", rng=rng, name="Q{x}Q")
    assert line is not None
    assert "Q{x}Q" in line, f"curly-brace name not preserved in {line!r}"


@pytest.mark.tier_short
def test_generic_drift_pool_shape():
    """`_GENERIC_DRIFT_POOL` ships the SPEC-required buckets
    (content / thoughtful / curious / default), each with >=3 distinct
    non-empty lines, >=12 total, and every line carries the literal
    `{name}` token."""
    pool = drift._GENERIC_DRIFT_POOL
    for bucket in ("content", "thoughtful", "curious", "default"):
        assert bucket in pool, f"generic pool missing `{bucket}` bucket"
        lines = pool[bucket]
        assert isinstance(lines, list), f"generic/{bucket}: not a list"
        assert len(lines) >= 3, f"generic/{bucket}: only {len(lines)} lines"
        for line in lines:
            assert isinstance(line, str) and line.strip(), (
                f"generic/{bucket}: empty/non-string line {line!r}"
            )
            assert "{name}" in line, (
                f"generic/{bucket}: line missing {{name}} token: {line!r}"
            )
    all_lines = [l for lines in pool.values() for l in lines]
    assert len(all_lines) >= 12, f"generic pool has only {len(all_lines)} lines"
    assert len(set(all_lines)) == len(all_lines), "duplicates in generic pool"


# ---- tick: canned path (tier_medium, DB needed) ------------------------


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_emits_one_narrate_in_chosen_npc_room(monkeypatch):
    """One tick with two NPCs (Rook at r-forge, Iris at r-attic)
    produces exactly one new narrate event addressed to the chosen
    NPC's room, with text from one of the NPC's pool buckets. LLM
    branch is off (conftest default). Drops the seeded slot-1 Wren so
    only the two hand-authored, `_DRIFT_POOLS`-backed NPCs are eligible
    (Wren now drifts via the generic pool, which this test's
    `_DRIFT_POOLS`-only identification step does not cover)."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id = 't-wren'")
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
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND is_human_controlled = 0")
    before_seq = events.max_seq()
    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is False
    assert events.fetch_since(before_seq) == []


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_canned_uses_npc_mood_bucket(monkeypatch):
    """With LLM disabled and an NPC mood explicitly set, the canned
    line picked must come from the matching bucket. Sets Rook's mood
    to `thoughtful` directly via DB then deletes Iris and Wren so the
    choice is deterministic on Rook."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    conn = db.get_conn()
    conn.execute("UPDATE objects SET properties_json = json_set(properties_json, '$.mood', 'thoughtful') WHERE id = 't-rook'")
    # Drop Iris and the seeded Wren so the choice is deterministic on Rook
    # (Wren is drift-eligible now that eligibility no longer needs a pool).
    conn.execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")
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
    # Delete Iris and the now-eligible Wren so choice is deterministic on Rook.
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")
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
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")
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
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")

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
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")
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


# ---- tick: bootstrapped NPC (no per-NPC pool) (tier_medium, DB) --------


def _seed_bootstrapped_npc(
    npc_id: str = "t-test-abc123",
    name: str = "Bramble",
    room_id: str = "r-meadow",
    mood: str = "curious",
    slot: int = 100,
) -> None:
    """Insert a bootstrapped-style NPC (id shaped `t-<slug>-<uuid>`, no
    `_DRIFT_POOLS` entry, is_human_controlled=0) into the seeded world.
    Mirrors the column set of `_seed_human_in_room` but NPC-controlled,
    so the drift loop treats it like a `bin/game world bootstrap` toon.
    Caller is expected to have cleared the hand-authored NPCs first so
    this one is selected deterministically."""
    db.get_conn().execute(
        "INSERT INTO objects (id, world_id, kind, name, location_id, "
        "prototype_id, properties_json, slot, is_human_controlled) VALUES "
        "(?, 'w-bunny', 'toon', ?, ?, 'proto-npc', ?, ?, 0)",
        (npc_id, name, room_id,
         json.dumps({"seed": "a wandering tinker", "appearance_seed": "",
                     "mood": mood, "presence_text": None}), slot),
    )


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_bootstrapped_npc_emits_generic_canned_when_llm_none(monkeypatch):
    """A bootstrapped NPC (id t-test-abc123, no per-NPC pool) is now
    eligible and selected by _tick; when _llm_narrate yields None it
    emits a generic-pool line with `{name}` replaced by the toon name.
    Exercises eligibility-opening + generic-fall-through end to end."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    # Drop the hand-authored NPCs so the bootstrapped one is the only
    # eligible toon and selection is deterministic.
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND is_human_controlled = 0")
    _seed_bootstrapped_npc(name="Bramble", room_id="r-meadow", mood="curious")
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    monkeypatch.setattr(drift, "_llm_narrate", AsyncMock(return_value=None))
    before_seq = events.max_seq()

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    e = events.fetch_since(before_seq)[0]
    assert e.kind == "narrate"
    assert e.room_id == "r-meadow"
    expected = {
        line.replace("{name}", "Bramble")
        for line in drift._GENERIC_DRIFT_POOL["curious"]
    }
    assert e.payload["text"] in expected, (
        f"emitted {e.payload['text']!r} not a name-substituted generic curious line"
    )
    assert "{name}" not in e.payload["text"]
    assert drift.tick_counts() == {"llm_emit": 0, "canned_fallback": 1, "noop": 0}


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_bootstrapped_npc_emits_llm_text_when_present(monkeypatch):
    """The same bootstrapped NPC emits the LLM text verbatim when
    _llm_narrate returns a string, recording an llm_emit (not a
    canned_fallback)."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND is_human_controlled = 0")
    _seed_bootstrapped_npc(name="Bramble", room_id="r-meadow", mood="curious")
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    llm_text = "Bramble watches the meadow grass lean and settle in the late light."
    monkeypatch.setattr(drift, "_llm_narrate", AsyncMock(return_value=llm_text))
    before_seq = events.max_seq()

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    e = events.fetch_since(before_seq)[0]
    assert e.payload["text"] == llm_text
    assert e.room_id == "r-meadow"
    assert drift.tick_counts() == {"llm_emit": 1, "canned_fallback": 0, "noop": 0}


# ---- per-NPC drift selection weights (tier_short, pure) ----------------


@pytest.mark.tier_short
def test_pick_npc_weight_zero_excludes_npc(monkeypatch):
    """An NPC with weight 0.0 is never picked over many trials."""
    monkeypatch.setattr(
        drift, "_NPC_DRIFT_WEIGHT", {"t-rook": 1.0, "t-iris": 0.0}
    )
    eligible = [
        {"id": "t-rook", "current_room_id": "r-forge"},
        {"id": "t-iris", "current_room_id": "r-attic"},
    ]
    rng = random.Random(0)
    picks = [drift._pick_npc(eligible, rng=rng)["id"] for _ in range(200)]
    assert all(p == "t-rook" for p in picks), "weight 0 NPC should never be picked"


@pytest.mark.tier_short
def test_pick_npc_weight_3_to_1_distributes_roughly(monkeypatch):
    """Weight 3 vs 1 produces a ~75/25 distribution under a seeded RNG
    over enough trials to be stable. Tolerance is loose (10 percentage
    points) so a slow PRNG drift doesn't flake."""
    monkeypatch.setattr(
        drift, "_NPC_DRIFT_WEIGHT", {"t-rook": 3.0, "t-iris": 1.0}
    )
    eligible = [
        {"id": "t-rook", "current_room_id": "r-forge"},
        {"id": "t-iris", "current_room_id": "r-attic"},
    ]
    rng = random.Random(42)
    picks = [drift._pick_npc(eligible, rng=rng)["id"] for _ in range(1000)]
    rook_share = sum(1 for p in picks if p == "t-rook") / len(picks)
    assert 0.65 <= rook_share <= 0.85, f"expected ~0.75, got {rook_share:.3f}"


@pytest.mark.tier_short
def test_pick_npc_missing_from_dict_defaults_to_one(monkeypatch):
    """An eligible NPC missing from `_NPC_DRIFT_WEIGHT` defaults to
    weight 1.0 and gets picked normally."""
    monkeypatch.setattr(drift, "_NPC_DRIFT_WEIGHT", {"t-rook": 1.0})
    eligible = [{"id": "t-newbie", "current_room_id": "r-meadow"}]
    rng = random.Random(0)
    chosen = drift._pick_npc(eligible, rng=rng)
    assert chosen is not None
    assert chosen["id"] == "t-newbie"


@pytest.mark.tier_short
def test_pick_npc_all_zero_weights_returns_none(monkeypatch):
    """When all eligible NPCs have weight 0.0 (or sum to 0), return
    None — caller treats as a no-op tick rather than crashing."""
    monkeypatch.setattr(
        drift, "_NPC_DRIFT_WEIGHT", {"t-rook": 0.0, "t-iris": 0.0}
    )
    eligible = [
        {"id": "t-rook", "current_room_id": "r-forge"},
        {"id": "t-iris", "current_room_id": "r-attic"},
    ]
    chosen = drift._pick_npc(eligible, rng=random.Random(0))
    assert chosen is None


@pytest.mark.tier_short
def test_pick_npc_empty_eligible_returns_none():
    """Empty eligible list returns None."""
    assert drift._pick_npc([], rng=random.Random(0)) is None


# ---- witnessed drift in occupied rooms (tier_medium, DB needed) --------


def _seed_human_in_room(room_id: str, slot: int = 2) -> None:
    """Insert a human-controlled toon into the named room, mimicking
    what the WS join path does. Keeps the test self-contained without
    pulling in the full TestClient stack. Slot defaults to 2 because
    slot 1 is occupied by Wren (the seeded slot-1 NPC from migration 001)."""
    db.get_conn().execute(
        "INSERT INTO objects (id, world_id, kind, name, location_id, "
        "prototype_id, properties_json, slot, is_human_controlled) VALUES "
        "(?, 'w-bunny', 'toon', ?, ?, 'proto-npc', ?, ?, 1)",
        (f"t-h{slot}", f"Human{slot}", room_id,
         json.dumps({"seed": "", "appearance_seed": "", "mood": "curious",
                     "presence_text": None}), slot),
    )


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_witnessed_in_occupied_room():
    """Witnessed drift (SPEC 2026-06-30): a co-located NPC's beat fires in a
    room a human occupies -- inverting the old occupancy suppression. With a
    human in Rook's room, at least one narrate across several ticks lands in
    r-forge, where the present player would see it."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    _seed_human_in_room("r-forge")  # a human co-located with Rook
    before_seq = events.max_seq()
    for seed in range(20):
        await drift._tick(rng=random.Random(seed))
    rooms_hit = {e.room_id for e in events.fetch_since(before_seq)}
    assert "r-forge" in rooms_hit, "witnessed drift never fired in the occupied room"


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_emits_even_when_all_rooms_occupied():
    """Witnessed drift (SPEC 2026-06-30): even with a human in every NPC room,
    a tick still emits a narrate -- occupancy no longer suppresses (the old
    'all rooms occupied -> no-op' behavior is inverted)."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    _seed_human_in_room("r-forge", slot=2)
    _seed_human_in_room("r-attic", slot=3)
    _seed_human_in_room("r-meadow", slot=4)
    before_seq = events.max_seq()

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    assert len(events.fetch_since(before_seq)) == 1


# ---- mood-affecting drift (tier_short pure + tier_medium DB) -----------


@pytest.mark.tier_short
def test_maybe_transition_mood_disabled_returns_none(monkeypatch):
    """With `DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED=0`, never transitions
    regardless of the RNG."""
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "0")
    npc = {"id": "t-rook", "mood": "content"}
    rng = random.Random(0)
    assert drift._maybe_transition_mood(npc, rng=rng) is None


@pytest.mark.tier_short
def test_maybe_transition_mood_roll_above_threshold_returns_none(monkeypatch):
    """RNG roll >= probability threshold → no transition."""
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_PROB", "0.2")
    # An RNG that returns 0.9 on the first .random() call → above 0.2
    # threshold, no transition.
    class FakeRng:
        def random(self):
            return 0.9

        def choice(self, seq):
            return seq[0]

    assert drift._maybe_transition_mood({"id": "t-rook", "mood": "content"}, rng=FakeRng()) is None


@pytest.mark.tier_short
def test_maybe_transition_mood_only_default_bucket_returns_none(monkeypatch):
    """An NPC whose pool has only `default` plus its current mood has
    no transition target — returns None."""
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_PROB", "1.0")
    monkeypatch.setattr(
        drift, "_DRIFT_POOLS", {
            "t-rook": {"content": ["one line"], "default": ["another"]},
        },
    )
    npc = {"id": "t-rook", "mood": "content"}
    # Probability 1.0 → would transition if a target existed.
    assert drift._maybe_transition_mood(npc, rng=random.Random(0)) is None


@pytest.mark.tier_short
def test_maybe_transition_mood_uses_generic_pool_for_bootstrapped_npc(monkeypatch):
    """A bootstrapped NPC (no `_DRIFT_POOLS` entry) draws its mood
    transition target from `_GENERIC_DRIFT_POOL.keys()` minus `default`
    minus the current mood. Probability forced to 1.0 so the roll
    always lands; `set_mood` is stubbed so the test stays tier_short
    (no DB) — the generic-key selection is the behavior under test."""
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_PROB", "1.0")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "daydream.toons.set_mood", lambda tid, mood: calls.append((tid, mood))
    )
    npc = {"id": "t-test-abc123", "mood": "curious"}
    expected = set(drift._GENERIC_DRIFT_POOL) - {"default", "curious"}
    new_mood = drift._maybe_transition_mood(npc, rng=random.Random(0))
    assert new_mood in expected, f"{new_mood!r} not in generic targets {expected}"
    assert calls == [("t-test-abc123", new_mood)]


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_maybe_transition_mood_persists_to_db(monkeypatch):
    """When mood-drift is enabled and the roll lands AND a target
    bucket exists, the new mood is persisted via `toons.set_mood`."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_PROB", "1.0")

    # RNG that always rolls 0.0 (below threshold) and picks index 0
    # from any sequence — deterministic transition target.
    class FakeRng:
        def random(self):
            return 0.0

        def choice(self, seq):
            return seq[0]

    npc = {"id": "t-rook", "mood": "content"}
    new_mood = drift._maybe_transition_mood(npc, rng=FakeRng())
    assert new_mood is not None
    assert new_mood != "content"
    assert new_mood != "default"

    from daydream import toons as toons_mod
    rook = toons_mod.get_toon("t-rook")
    assert rook is not None
    assert rook.mood == new_mood


# ---- composed path: weighted + mood-drift + LLM ------------------------


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_composed_iris_only_with_mood_drift(monkeypatch):
    """Compose: the LLM-driven path + mood-drift on, isolated to a single NPC
    (Iris) by removing the others (occupancy no longer suppresses). Multiple
    ticks: every narrate lands on Iris; Iris's mood eventually transitions
    away from `thoughtful`."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_DRIFT_MOOD_DRIFT_PROB", "1.0")
    # Isolate on Iris: remove the other drift-eligible NPCs.
    db.get_conn().execute(
        "DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-rook', 't-wren')"
    )
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"narrate": "Iris hums quietly to herself in the slanting light."}),
    )
    before_seq = events.max_seq()

    # Run a handful of ticks; each must land on Iris's room.
    for seed in range(5):
        await drift._tick(rng=random.Random(seed))

    new_events = events.fetch_since(before_seq)
    assert len(new_events) == 5
    from daydream import toons as toons_mod
    iris_initial = toons_mod.get_toon("t-iris")
    assert iris_initial is not None
    for e in new_events:
        assert e.room_id == iris_initial.current_room_id

    # With prob 1.0 and at least one transition target, Iris's mood
    # should have moved off `thoughtful` after the ticks.
    iris_final = toons_mod.get_toon("t-iris")
    assert iris_final is not None
    assert iris_final.mood != "thoughtful"


# ---- drift outcome counters (tier_short pure + tier_medium DB) ---------


@pytest.fixture(autouse=True)
def reset_drift_counters():
    """Drift outcome counters are module-level; reset before/after each
    test so cross-test bleed never produces phantom increments."""
    drift.reset_tick_counts()
    yield
    drift.reset_tick_counts()


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_counter_canned_fallback_increments_on_canned_path(monkeypatch):
    """LLM disabled (conftest default) → canned path → counter
    `canned_fallback` increments exactly 1; others stay 0."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    counts = drift.tick_counts()
    assert counts == {"llm_emit": 0, "canned_fallback": 1, "noop": 0}


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_counter_llm_emit_increments_on_llm_path(monkeypatch):
    """LLM enabled and returning a clean narrate → counter `llm_emit`
    increments exactly 1; others stay 0."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"narrate": "Rook hums softly to himself."}),
    )

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    counts = drift.tick_counts()
    assert counts == {"llm_emit": 1, "canned_fallback": 0, "noop": 0}


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_counter_canned_fallback_increments_when_llm_fails(monkeypatch):
    """LLM enabled but raising LLMUnavailable → canned path emits →
    counter `canned_fallback` increments exactly 1; `llm_emit` stays 0."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setenv("DAYDREAM_DRIFT_LLM_ENABLED", "1")
    db.get_conn().execute("DELETE FROM objects WHERE kind = 'toon' AND id IN ('t-iris', 't-wren')")
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=llm_client.LLMUnavailable("vllm down")),
    )

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is True
    counts = drift.tick_counts()
    assert counts == {"llm_emit": 0, "canned_fallback": 1, "noop": 0}


@pytest.mark.tier_medium
@pytest.mark.asyncio
async def test_tick_counter_noop_increments_when_no_npcs():
    """No NPCs at all → counter `noop` increments; others stay 0. Occupancy no
    longer suppresses (witnessed drift, SPEC 2026-06-30), so an empty NPC
    roster is how a tick legitimately no-ops."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute(
        "DELETE FROM objects WHERE kind = 'toon' AND is_human_controlled = 0"
    )

    emitted = await drift._tick(rng=random.Random(0))
    assert emitted is False
    counts = drift.tick_counts()
    assert counts == {"llm_emit": 0, "canned_fallback": 0, "noop": 1}


@pytest.mark.tier_short
def test_tick_counts_returns_copy_not_reference():
    """`tick_counts()` returns a copy so callers can't mutate the
    module-level dict accidentally."""
    snapshot = drift.tick_counts()
    snapshot["llm_emit"] = 999
    assert drift.tick_counts()["llm_emit"] == 0


@pytest.mark.tier_short
def test_reset_tick_counts_zeros_all_keys():
    """`reset_tick_counts()` zeros every key in `_TICK_COUNTS`."""
    drift._TICK_COUNTS["llm_emit"] = 5
    drift._TICK_COUNTS["canned_fallback"] = 2
    drift._TICK_COUNTS["noop"] = 1
    drift.reset_tick_counts()
    assert drift.tick_counts() == {"llm_emit": 0, "canned_fallback": 0, "noop": 0}


# ---- _render_drift_prompt (tier_short pure) ----------------------------


@pytest.mark.tier_short
def test_render_drift_prompt_with_memories():
    """Rendered prompt includes npc_name, mood, and each memory wrapped
    in <memory>...</memory> tags."""
    from types import SimpleNamespace
    npc = {
        "name": "Rook",
        "seed": "the forge-keeper",
        "mood": "content",
    }
    mems = [SimpleNamespace(text="the visitor said: hello"),
            SimpleNamespace(text="Rook said: come warm your hands")]
    prompt = drift._render_drift_prompt(npc, mems)
    assert "Rook" in prompt
    assert "content" in prompt
    assert "<memory>the visitor said: hello</memory>" in prompt
    assert "<memory>Rook said: come warm your hands</memory>" in prompt


@pytest.mark.tier_short
def test_render_drift_prompt_empty_memories_skips_block():
    """Empty memory list omits the <memory> block entirely."""
    npc = {
        "name": "Iris",
        "seed": "the attic archivist",
        "mood": "thoughtful",
    }
    prompt = drift._render_drift_prompt(npc, [])
    assert "Iris" in prompt
    assert "thoughtful" in prompt
    assert "<memory>" not in prompt


@pytest.mark.tier_short
def test_render_drift_prompt_falsy_mood_uses_calm_default():
    """When mood is None or empty, prompt uses 'calm' as default."""
    npc = {
        "name": "Rook",
        "seed": "the forge-keeper",
        "mood": None,
    }
    prompt = drift._render_drift_prompt(npc, [])
    assert "calm" in prompt


# ---- /status/drift endpoint (tier_medium) ------------------------------


@pytest.mark.tier_medium
def test_status_drift_returns_empty_when_no_ticks():
    """`/status/drift` returns 200 with empty body when drift hasn't
    ticked yet (zero-state silent surface)."""
    from fastapi.testclient import TestClient
    from daydream.server import app

    drift.reset_tick_counts()
    with TestClient(app) as client:
        r = client.get("/status/drift")
        assert r.status_code == 200
        assert r.text == ""


@pytest.mark.tier_medium
def test_status_drift_returns_summary_when_counters_nonzero():
    """`/status/drift` returns a one-line summary in plain text when
    any counter is non-zero."""
    from fastapi.testclient import TestClient
    from daydream.server import app

    drift._TICK_COUNTS["llm_emit"] = 12
    drift._TICK_COUNTS["canned_fallback"] = 3
    drift._TICK_COUNTS["noop"] = 1
    try:
        with TestClient(app) as client:
            r = client.get("/status/drift")
            assert r.status_code == 200
            assert "12 emits" in r.text
            assert "3 fallback" in r.text
            assert "1 noop" in r.text
            assert "since boot" in r.text
    finally:
        drift.reset_tick_counts()


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
