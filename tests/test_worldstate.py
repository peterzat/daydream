"""Unit tests for the per-world KV state layer (daydream/worldstate.py,
migration 013): generic get/set, the turn clock, flags, counters, score,
rank resolution, and the seeded-RNG determinism contract that every later
clock/daemon/combat test leans on."""

from pathlib import Path

import pytest

from daydream import config, db, events, worldstate

pytestmark = pytest.mark.tier_short

WORLD = "w-bunny"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


# ---- generic KV ---------------------------------------------------------


def test_get_missing_returns_default():
    assert worldstate.get(WORLD, "nope") is None
    assert worldstate.get(WORLD, "nope", 7) == 7


def test_set_get_roundtrip_json_values():
    for value in ("text", 42, True, None, {"a": [1, 2]}, ["x", {"y": 1}]):
        worldstate.set(WORLD, "k", value)
        assert worldstate.get(WORLD, "k") == value


def test_set_upserts():
    worldstate.set(WORLD, "k", 1)
    worldstate.set(WORLD, "k", 2)
    assert worldstate.get(WORLD, "k") == 2
    rows = db.get_conn().execute(
        "SELECT COUNT(*) FROM world_state WHERE world_id = ? AND key = 'k'", (WORLD,)
    ).fetchone()
    assert rows[0] == 1


def test_worlds_are_isolated():
    db.get_conn().execute(
        "INSERT INTO worlds (id, name, slug, aesthetic_seed) VALUES "
        "('w-other', 'Other', 'other', 'seed')"
    )
    worldstate.set(WORLD, "k", "bunny")
    worldstate.set("w-other", "k", "other")
    assert worldstate.get(WORLD, "k") == "bunny"
    assert worldstate.get("w-other", "k") == "other"


def test_delete_and_keys_prefix():
    worldstate.set(WORLD, "fuse:lamp", {"turns": 3})
    worldstate.set(WORLD, "fuse:bell", {"turns": 6})
    worldstate.set(WORLD, "daemon:thief", {"active": True})
    assert worldstate.keys(WORLD, "fuse:") == ["fuse:bell", "fuse:lamp"]
    worldstate.delete(WORLD, "fuse:bell")
    assert worldstate.keys(WORLD, "fuse:") == ["fuse:lamp"]


def test_delete_world_state_cascade():
    worldstate.set(WORLD, "a", 1)
    worldstate.set(WORLD, "b", 2)
    worldstate.delete_world_state(WORLD)
    assert worldstate.keys(WORLD) == []


# ---- turn clock ---------------------------------------------------------


def test_turn_defaults_zero_and_advances():
    assert worldstate.turn(WORLD) == 0
    assert worldstate.advance_turn(WORLD) == 1
    assert worldstate.advance_turn(WORLD) == 2
    assert worldstate.turn(WORLD) == 2


# ---- flags + counters + score -------------------------------------------


def test_flags_default_false_and_set():
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is False
    worldstate.set_flag(WORLD, "GATES-OPEN", True)
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is True
    worldstate.set_flag(WORLD, "GATES-OPEN", False)
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is False


def test_counters_default_zero_adjust_and_set():
    assert worldstate.counter(WORLD, "deaths") == 0
    assert worldstate.adjust_counter(WORLD, "deaths", 1) == 1
    assert worldstate.adjust_counter(WORLD, "deaths", 2) == 3
    worldstate.set_counter(WORLD, "deaths", 0)
    assert worldstate.counter(WORLD, "deaths") == 0


def test_score_adjusts_and_goes_negative():
    assert worldstate.score(WORLD) == 0
    assert worldstate.adjust_score(WORLD, 10) == 10
    assert worldstate.adjust_score(WORLD, -25) == -15


# ---- seeded RNG ---------------------------------------------------------


def test_rng_deterministic_per_seed_turn_purpose():
    worldstate.set(WORLD, "rng_seed", "pin")
    a = worldstate.rng(WORLD, "hazard").random()
    b = worldstate.rng(WORLD, "hazard").random()
    assert a == b  # same triple -> same stream


def test_rng_varies_by_purpose_and_turn():
    worldstate.set(WORLD, "rng_seed", "pin")
    hazard = worldstate.rng(WORLD, "hazard").random()
    combat = worldstate.rng(WORLD, "combat").random()
    assert hazard != combat
    worldstate.advance_turn(WORLD)
    assert worldstate.rng(WORLD, "hazard").random() != hazard


def test_rng_default_seed_is_stable():
    # No authored rng_seed: the constant default still yields determinism.
    assert worldstate.rng_seed(WORLD) == worldstate.DEFAULT_RNG_SEED
    assert (
        worldstate.rng(WORLD, "x").random() == worldstate.rng(WORLD, "x").random()
    )


# ---- rank + status block ------------------------------------------------

RANKS = {
    "ranks": [
        {"min": 0, "name": "Beginner"},
        {"min": 100, "name": "Junior Adventurer"},
        {"min": 350, "name": "Master Adventurer"},
    ]
}


def test_rank_for_resolves_ladder():
    worldstate.set(WORLD, "def:scoring", RANKS)
    assert worldstate.rank_for(WORLD, 0) == "Beginner"
    assert worldstate.rank_for(WORLD, 99) == "Beginner"
    assert worldstate.rank_for(WORLD, 100) == "Junior Adventurer"
    assert worldstate.rank_for(WORLD, 350) == "Master Adventurer"


def test_rank_for_none_without_scoring():
    assert worldstate.rank_for(WORLD, 10) is None


def test_status_block_shape_and_defaults():
    s = worldstate.status_block(WORLD)
    assert s == {"score": 0, "rank": None, "moves": 0, "deaths": 0, "lit": True}
    worldstate.set(WORLD, "def:scoring", RANKS)
    worldstate.adjust_score(WORLD, 100)
    worldstate.advance_turn(WORLD)
    worldstate.adjust_counter(WORLD, "deaths", 1)
    s = worldstate.status_block(WORLD)
    assert s["score"] == 100 and s["rank"] == "Junior Adventurer"
    assert s["moves"] == 1 and s["deaths"] == 1
