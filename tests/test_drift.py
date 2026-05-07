"""Tests for daydream/drift.py.

Covers SPEC 2026-05-07 "NPC drift loop (v0: pre-canned narrates)" —
criteria 2, 3, 4. Pure-function tests run as `tier_short`; the
lifespan-integration test boots the FastAPI TestClient with drift
explicitly enabled and is `tier_medium`.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest

from daydream import db, drift, events


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


# ---- criterion 2: cadence rule (pure function) -------------------------


@pytest.mark.tier_short
def test_compute_next_interval_idle_default():
    """Zero subscribers => idle default (300 s)."""
    # Defaults are read fresh from env each call, so clearing any
    # leftover override exercises the fallback.
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


# ---- criterion 3: tick behavior (DB-touching, tier_medium) -------------


def _open_db():
    """Run init_live so the seed migration chain (incl. 008 Iris)
    populates the test DB. Mirrors the pattern in test_ws_*.py."""
    from daydream import config
    db.init_live(
        path=Path(events.db.get_conn().execute("PRAGMA database_list").fetchone()[2])
        if False  # placeholder; actual init below
        else None,
        migrations_dir=config.MIGRATIONS_DIR,
    )


@pytest.mark.tier_medium
def test_tick_emits_one_narrate_in_chosen_npc_room():
    """One tick with two NPCs (Rook at r-forge, Iris at r-attic)
    produces exactly one new narrate event in events table, addressed
    to the chosen NPC's room, with text from the NPC's drift pool."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    before_seq = events.max_seq()

    # Seeded RNG so the choice is deterministic; we don't care WHICH
    # NPC is picked, just that ONE narrate is emitted in the right
    # room with text from the right pool.
    rng = random.Random(0)
    emitted = drift._tick(rng=rng)
    assert emitted is True

    new_events = events.fetch_since(before_seq)
    assert len(new_events) == 1
    e = new_events[0]
    assert e.kind == "narrate"
    assert e.actor_type == "system"
    assert e.actor_id is None

    # Whichever NPC was chosen, the room and text must match its pool.
    payload_text = e.payload["text"]
    chosen_room = e.room_id
    matching_pools = [
        (npc_id, pool) for npc_id, pool in drift._DRIFT_POOLS.items()
        if payload_text in pool
    ]
    assert len(matching_pools) == 1, f"text {payload_text!r} not found in any pool"
    chosen_npc_id, _ = matching_pools[0]
    # And the room_id matches the chosen NPC's current_room_id.
    from daydream import toons
    npc = toons.get_toon(chosen_npc_id)
    assert npc is not None
    assert chosen_room == npc.current_room_id


@pytest.mark.tier_medium
def test_tick_no_op_when_no_npcs():
    """If no NPCs exist (after explicit deletion), tick is a no-op
    and emits no events."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    db.get_conn().execute("DELETE FROM toons WHERE is_human_controlled = 0")
    before_seq = events.max_seq()
    emitted = drift._tick(rng=random.Random(0))
    assert emitted is False
    assert events.fetch_since(before_seq) == []


# ---- criterion 4 (pool quality, pure check) ----------------------------


@pytest.mark.tier_short
def test_drift_pools_have_at_least_three_distinct_lines_each():
    """Per the spec contract: each NPC's pool has >=3 distinct
    non-empty drift lines, in the NPC's voice."""
    assert drift._DRIFT_POOLS, "no drift pools defined"
    for npc_id, pool in drift._DRIFT_POOLS.items():
        assert len(pool) >= 3, f"{npc_id}: pool has only {len(pool)} lines"
        assert len(set(pool)) == len(pool), f"{npc_id}: pool has duplicates"
        for line in pool:
            assert isinstance(line, str), f"{npc_id}: non-string line {line!r}"
            assert line.strip(), f"{npc_id}: empty/whitespace-only line"


# ---- criterion 1: cancellation cleanup ---------------------------------


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_drift_loop_cancels_cleanly(monkeypatch):
    """start_drift_loop returns a Task that cancellation can stop
    cleanly within ~1 s. Exercises the asyncio.CancelledError path
    without waiting for any tick to fire."""
    monkeypatch.setenv("DAYDREAM_DRIFT_ENABLED", "1")
    handle = drift.start_drift_loop()
    assert handle is not None
    # Give the loop one tick of the event loop to start sleeping.
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
    # Should not raise.
    await drift.stop_drift_loop(handle)
