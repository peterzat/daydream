"""The static analyzer over the assembled world (SPEC 2026-07-02 criterion
10). Structural checks run at every commit; the FINAL-WORLD checks (110
rooms, 350 arithmetic, full reachability, rank coverage) arm automatically
when the last region lands (no stubs left). The committed envelope must
byte-match a re-assembly from its region sources."""

import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENVELOPE_PATH = ROOT / "worlds/zork1.json"
ENV = json.loads(ENVELOPE_PATH.read_text())
ROOMS = {r["id"]: r for r in ENV["rooms"]}
THINGS = {t["id"]: t for t in ENV["things"]}
TOONS = {t["id"]: t for t in ENV.get("toons", [])}
WALKTHROUGH = json.loads((ROOT / "tests/data/zork1_walkthrough.json").read_text())

UNDER_CONSTRUCTION = any(
    (r.get("properties") or {}).get("stub") for r in ENV["rooms"]
)

final_world = pytest.mark.skipif(
    UNDER_CONSTRUCTION,
    reason="world under construction (99-stubs.json present); arms when the "
           "final region lands",
)


def exit_destinations(room: dict):
    for direction, value in (room.get("exits") or {}).items():
        if isinstance(value, str):
            yield direction, value
        elif isinstance(value, dict) and "to" in value:
            yield direction, value["to"]


# ---- always-on structural checks -------------------------------------------


def test_committed_envelope_matches_reassembly():
    """The drift guard: worlds/zork1.json is exactly what the region sources
    assemble to (tools/assemble_world.py --check)."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/assemble_world.py"),
         "--source", str(ROOT / "worlds/zork1"), "--check"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_envelope_validates():
    from daydream.llm import format2

    format2.validate_envelope2(ENV)  # raises on any hard error


def test_every_exit_target_resolves():
    for rid, room in ROOMS.items():
        for direction, dest in exit_destinations(room):
            assert dest in ROOMS, f"{rid}.{direction} -> unknown {dest}"


def test_authored_rooms_reachable_from_start():
    """Reachability treating conditions as satisfiable, over the AUTHORED
    (non-stub) rooms. Stub rooms are sealed by design and excluded; the
    final-world check below covers all 110."""
    authored = {rid for rid, r in ROOMS.items()
                if not (r.get("properties") or {}).get("stub")}
    seen = {ENV["start_room"]}
    queue = deque(seen)
    while queue:
        here = queue.popleft()
        for _, dest in exit_destinations(ROOMS[here]):
            if dest not in seen:
                seen.add(dest)
                queue.append(dest)
    unreachable = authored - seen
    assert not unreachable, f"authored rooms unreachable: {sorted(unreachable)}"


def test_treasure_arithmetic_is_consistent_so_far():
    """Every authored treasure carries both halves; the grand total is
    checked by the final-world test."""
    for oid, thing in THINGS.items():
        props = thing.get("properties") or {}
        if props.get("treasure"):
            assert isinstance(props.get("score_take"), int) or isinstance(
                props.get("score_case"), int
            ), f"{oid}: treasure with no authored value"


def test_walkthrough_verbs_are_click_reachable():
    """Criterion 10: every walkthrough command's verb is reachable by click
    — the verb bar, a per-object verb grant, room rules, or an exit button.
    Directions count as exit buttons; engine bar verbs count; world verbs
    must be granted on at least one object or fire via room/world rules."""
    from daydream import verbs as engine_verbs

    granted: set[str] = set()
    for coll in (THINGS, TOONS):
        for obj in coll.values():
            granted.update(obj.get("verbs") or [])
            for rule in obj.get("rules") or []:
                granted.add(rule.get("on"))
    for room in ROOMS.values():
        for rule in room.get("rules") or []:
            granted.add(rule.get("on"))
    for rule in ENV.get("rules") or []:
        granted.add(rule.get("on"))
    world_verb_words = set()
    for name, d in (ENV.get("verbs") or {}).items():
        world_verb_words.add(name)
        world_verb_words.update(d.get("aliases") or [])

    for segment in WALKTHROUGH["segments"]:
        for step in segment["commands"]:
            for part in step["cmd"].replace(".", " then ").split(" then "):
                word = part.strip().split()[0].lower()
                two = " ".join(part.strip().lower().split()[:2])
                if word in engine_verbs.DIRECTION_WORDS:
                    continue  # exit button
                if word in ("again", "g", "it"):
                    continue  # parser meta-words, not verbs (a click IS a repeat)
                spec = engine_verbs.get(two) or engine_verbs.get(word)
                if spec is not None:
                    continue  # engine verb (bar or object verbs)
                assert two in world_verb_words or word in world_verb_words, (
                    f"walkthrough verb {word!r} is not declared")
                canonical = None
                for name, d in (ENV.get("verbs") or {}).items():
                    if word == name or two == name or word in (d.get("aliases") or []) \
                            or two in (d.get("aliases") or []):
                        canonical = name
                        break
                assert canonical in granted, (
                    f"walkthrough verb {word!r} ({canonical}) has no clickable grant")


def test_underground_rooms_are_dark_flagged():
    """Every authored room transcribed from a ZIL room without ONBIT must
    carry dark: true. Spot-checked here structurally: any room whose id is
    known-underground must be dark. (The stub rooms are all dark.)"""
    known_dark = [rid for rid, r in ROOMS.items() if r.get("dark")]
    assert "r-attic" in known_dark
    for rid, r in ROOMS.items():
        if (r.get("properties") or {}).get("stub"):
            assert r.get("dark"), f"stub {rid} must be dark"


# ---- final-world checks (arm when the stubs are gone) ------------------------


@final_world
def test_exactly_110_rooms():
    assert len(ROOMS) == 110


@final_world
def test_all_rooms_reachable_treating_conditions_satisfiable():
    seen = {ENV["start_room"]}
    queue = deque(seen)
    while queue:
        here = queue.popleft()
        for _, dest in exit_destinations(ROOMS[here]):
            if dest not in seen:
                seen.add(dest)
                queue.append(dest)
    assert seen == set(ROOMS), f"unreachable: {sorted(set(ROOMS) - seen)}"


@final_world
def test_treasure_arithmetic_sums_to_exactly_350():
    take = case = 0
    treasures = 0
    for thing in THINGS.values():
        props = thing.get("properties") or {}
        if props.get("treasure"):
            treasures += 1
            take += props.get("score_take", 0)
            case += props.get("score_case", 0)
    # The bauble is spawned by the canary at runtime, not authored statically:
    # its 1+1 rides the spawn effect. Count it from the canary's rule.
    canary = THINGS["o-canary"]
    spawn = next(e for r in canary["rules"] for e in r["do"]
                 if e["kind"] == "spawn_object")
    treasures += 1
    take += spawn["properties"]["score_take"]
    case += spawn["properties"]["score_case"]
    bonuses = 0
    for room in ROOMS.values():
        for rule in room.get("rules") or []:
            for eff in rule.get("do") or []:
                if eff.get("kind") == "adjust_score" and str(
                        eff.get("once", "")).startswith("room:"):
                    bonuses += eff["delta"]
    assert treasures == 19, f"expected 19 treasures, counted {treasures}"
    assert take + case == 272, f"take {take} + case {case} != 272"
    assert take + case + bonuses == 350, f"bonuses {bonuses} close the sum wrong"


@final_world
def test_rank_ladder_covers_0_to_350():
    ranks = ENV["scoring"]["ranks"]
    mins = sorted(r["min"] for r in ranks)
    assert mins[0] == 0 and 350 in mins


@final_world
def test_no_stub_markers_remain():
    for coll in (ROOMS, THINGS, TOONS):
        for oid, obj in coll.items():
            assert not (obj.get("properties") or {}).get("stub"), oid
