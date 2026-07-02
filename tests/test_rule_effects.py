"""Unit tests for the rule-only effect vocabulary (Zork turn, SPEC 2026-07-02
criterion 3's allowlist arm + criterion 2's engine-generic contract) and the
actor-private narrate routing (migration 014). Every new kind: happy path,
validation rejection (event=None, no mutation), and the restriction that no
LLM-facing path (allowed=None -> DEFAULT_KINDS) can emit it."""

from pathlib import Path

import pytest

from daydream import config, db, events, objects, worldstate
from daydream.skills import effects

pytestmark = pytest.mark.tier_short

WORLD = "w-bunny"
CTX = {"actor_id": "t-wren", "room_id": "r-meadow", "world_id": WORLD}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def dispatch(effs, allowed=effects.RULE_KINDS):
    return effects.dispatch_effects(effs, allowed=allowed, **CTX)


# ---- allowlist partition -------------------------------------------------


def test_rule_only_kinds_are_allowed_but_not_default():
    for kind in effects.RULE_ONLY_KINDS:
        assert kind in effects.ALLOWED_KINDS
        assert kind not in effects.DEFAULT_KINDS
        assert kind in effects.RULE_KINDS


def test_rule_kinds_exclude_world_shaping_and_aliases():
    assert not (effects.RULE_KINDS & effects.WORLD_SHAPING_KINDS)
    assert "rename_object" not in effects.RULE_KINDS
    assert "add_item" not in effects.RULE_KINDS
    assert "set_mood" not in effects.RULE_KINDS


def test_llm_facing_default_rejects_rule_only_kind():
    # allowed=None (the data-skill / LLM-facing default) must reject the rule
    # vocabulary exactly like an unknown kind: fallback narrate, no mutation.
    applied = effects.dispatch_effects(
        [{"kind": "adjust_score", "delta": 100}], allowed=None, **CTX
    )
    assert applied[0].event is not None and applied[0].event.kind == "narrate"
    assert worldstate.score(WORLD) == 0


# ---- narrate routing (to / room) ------------------------------------------


def test_narrate_to_actor_sets_recipient():
    applied = dispatch([{"kind": "narrate", "text": "hi", "to": "@actor"}])
    assert applied[0].event.recipient_id == "t-wren"


def test_narrate_to_explicit_toon_id():
    applied = dispatch([{"kind": "narrate", "text": "psst", "to": "t-rook"}])
    assert applied[0].event.recipient_id == "t-rook"


def test_narrate_default_is_broadcast():
    applied = dispatch([{"kind": "narrate", "text": "hello all"}])
    assert applied[0].event.recipient_id is None


def test_narrate_room_override_routes_to_other_room():
    applied = dispatch([{"kind": "narrate", "text": "far away", "room": "r-forge"}])
    assert applied[0].event.room_id == "r-forge"


# ---- set_flag / adjust_counter / adjust_score ------------------------------


def test_set_flag_sets_and_emits():
    applied = dispatch([{"kind": "set_flag", "name": "GATES-OPEN"}])
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is True
    assert applied[0].event.kind == "flag_set"
    dispatch([{"kind": "set_flag", "name": "GATES-OPEN", "value": False}])
    assert worldstate.get_flag(WORLD, "GATES-OPEN") is False


def test_set_flag_requires_name():
    applied = dispatch([{"kind": "set_flag"}])
    assert applied[0].event is None


def test_adjust_counter_and_validation():
    applied = dispatch([{"kind": "adjust_counter", "name": "digs", "delta": 1}])
    assert worldstate.counter(WORLD, "digs") == 1
    assert applied[0].event.payload["value"] == 1
    bad = dispatch([{"kind": "adjust_counter", "name": "digs", "delta": "x"}])
    assert bad[0].event is None and worldstate.counter(WORLD, "digs") == 1


def test_adjust_score_and_negative():
    dispatch([{"kind": "adjust_score", "delta": 10}])
    applied = dispatch([{"kind": "adjust_score", "delta": -4}])
    assert worldstate.score(WORLD) == 6
    assert applied[0].event.kind == "score_changed"
    assert applied[0].event.payload == {"delta": -4, "score": 6}


def test_adjust_score_once_fires_exactly_once():
    dispatch([{"kind": "adjust_score", "delta": 5, "once": "take:egg"}])
    second = dispatch([{"kind": "adjust_score", "delta": 5, "once": "take:egg"}])
    assert worldstate.score(WORLD) == 5
    assert second[0].event is None  # no event, no mutation on the re-fire


# ---- destroy_object --------------------------------------------------------


def test_destroy_object_drops_contents_to_its_location():
    box = objects.spawn(WORLD, "thing", "box", "r-meadow")
    coin = objects.spawn(WORLD, "thing", "coin", box.id)
    applied = dispatch([{"kind": "destroy_object", "object_id": box.id}])
    assert objects.get(box.id) is None
    assert objects.get(coin.id).location_id == "r-meadow"
    assert applied[0].event.kind == "object_destroyed"


def test_destroy_object_refuses_rooms_and_players():
    # Mark Wren as a claimed player (the seed ships is_human_controlled=0
    # until the slot picker claims it).
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1 WHERE id = 't-wren'"
    )
    for target in ("r-meadow", "t-wren"):
        applied = dispatch([{"kind": "destroy_object", "object_id": target}])
        assert applied[0].event is None
        assert objects.get(target) is not None


def test_destroy_object_allows_npc():
    # t-rook is an NPC (is_human_controlled=0): a combat death can unmake it.
    carried = objects.spawn(WORLD, "thing", "stiletto", "t-rook")
    dispatch([{"kind": "destroy_object", "object_id": "t-rook"}])
    assert objects.get("t-rook") is None
    assert objects.get(carried.id).location_id == "r-forge"  # rook's room


# ---- teleport_actor --------------------------------------------------------


def test_teleport_actor_moves_and_emits_move():
    applied = dispatch([{"kind": "teleport_actor", "room_id": "r-forge"}])
    assert objects.get("t-wren").location_id == "r-forge"
    ev = applied[0].event
    assert ev.kind == "move" and ev.actor_id == "t-wren"
    assert ev.payload["to_room"] == "r-forge" and ev.payload["teleport"] is True
    assert ev.room_id == "r-meadow"  # departure room, per broadcast contract


def test_teleport_actor_rejects_bad_room():
    applied = dispatch([{"kind": "teleport_actor", "room_id": "r-nowhere"}])
    assert applied[0].event is None
    assert objects.get("t-wren").location_id == "r-meadow"


# ---- fuses + daemons -------------------------------------------------------


def test_start_fuse_with_explicit_turns_captures_context():
    applied = dispatch([{"kind": "start_fuse", "name": "bell", "turns": 6}])
    state = worldstate.get(WORLD, "fuse:bell")
    assert state["remaining"] == 6
    assert state["context"] == {"actor_id": "t-wren", "room_id": "r-meadow"}
    assert applied[0].event.kind == "fuse_started"


def test_start_fuse_reads_authored_default_turns():
    worldstate.set(WORLD, "def:fuses", {"lamp": {"turns": 100}})
    dispatch([{"kind": "start_fuse", "name": "lamp"}])
    assert worldstate.get(WORLD, "fuse:lamp")["remaining"] == 100


def test_start_fuse_without_turns_anywhere_rejects():
    applied = dispatch([{"kind": "start_fuse", "name": "mystery"}])
    assert applied[0].event is None
    assert worldstate.get(WORLD, "fuse:mystery") is None


def test_stop_fuse_disarms_and_inactive_stop_is_quiet():
    dispatch([{"kind": "start_fuse", "name": "bell", "turns": 6}])
    applied = dispatch([{"kind": "stop_fuse", "name": "bell"}])
    assert worldstate.get(WORLD, "fuse:bell") is None
    assert applied[0].event.kind == "fuse_stopped"
    again = dispatch([{"kind": "stop_fuse", "name": "bell"}])
    assert again[0].event is None


def test_daemon_start_stop_preserves_state():
    dispatch([{"kind": "start_daemon", "name": "river"}])
    assert worldstate.get(WORLD, "daemon:river")["active"] is True
    # Simulate accumulated runtime state, then stop: state survives.
    st = worldstate.get(WORLD, "daemon:river")
    st["cell"] = 3
    worldstate.set(WORLD, "daemon:river", st)
    dispatch([{"kind": "stop_daemon", "name": "river"}])
    st = worldstate.get(WORLD, "daemon:river")
    assert st["active"] is False and st["cell"] == 3
    # Restart keeps position.
    dispatch([{"kind": "start_daemon", "name": "river"}])
    assert worldstate.get(WORLD, "daemon:river")["cell"] == 3


def test_stop_daemon_inactive_is_quiet():
    applied = dispatch([{"kind": "stop_daemon", "name": "never-started"}])
    assert applied[0].event is None


# ---- win -------------------------------------------------------------------


def test_win_records_once():
    applied = dispatch([{"kind": "win", "text": "The map is yours."}])
    ev = applied[0].event
    assert ev.kind == "game_won" and ev.payload["text"] == "The map is yours."
    assert worldstate.get(WORLD, "won")["actor_id"] == "t-wren"
    again = dispatch([{"kind": "win"}])
    assert again[0].event is None
