"""The Village of Lost Hours as data (SPEC 2026-09-26 criteria 1, 2).

Always on: the committed envelope byte-matches a re-assembly of its sources;
it validates fail-loud; the static analyzer proves every room reachable and
every arc solvable; every arc ending ships at least one walkthrough that
asserts it. Armed when the world stops declaring `under_construction`: the
scale thresholds (15 rooms, 8 residents, 10 arcs with 6 guest + the 3
keeper arcs + 1 cumulative multiplayer arc, 150 stray minutes)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from daydream import analyzer
from daydream.llm import format2

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())
WALKS = [json.loads(p.read_text())
         for p in sorted((ROOT / "worlds/lost-hours/walkthroughs").glob("*.json"))]
UNDER_CONSTRUCTION = bool((ENV.get("config") or {}).get("under_construction"))
KEEPERS = {"t-tace", "t-bell", "t-mott"}


def test_committed_envelope_matches_reassembly():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/assemble_world.py"),
         "--source", str(ROOT / "worlds/lost-hours"), "--check"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_envelope_validates():
    format2.validate_envelope2(json.loads(json.dumps(ENV)))


def test_analyzer_finds_the_world_sound():
    assert analyzer.analyze(ENV) == []


def _asserted_endings() -> set[tuple[str, str]]:
    out = set()

    def scan(node):
        if isinstance(node, dict):
            for arc, ending in (node.get("ending") or {}).items() \
                    if isinstance(node.get("ending"), dict) else []:
                out.add((arc, ending))
            for v in node.values():
                scan(v)
        elif isinstance(node, list):
            for v in node:
                scan(v)

    for w in WALKS:
        scan(w)
    return out


def test_every_arc_ending_ships_a_walkthrough():
    asserted = _asserted_endings()
    missing = [f"{a}/{e}" for a, arc in ENV["arcs"].items()
               for e in arc["endings"] if (a, e) not in asserted]
    assert not missing, f"endings with no walkthrough asserting them: {missing}"


def test_no_ending_is_a_fail_state():
    for aid, arc in ENV["arcs"].items():
        for eid, ending in arc["endings"].items():
            text = json.dumps(ending)
            for bad in ("kill_actor", "teleport_actor", "destroy_object"):
                assert bad not in text, f"{aid}/{eid} uses {bad}"


@pytest.mark.skipif(UNDER_CONSTRUCTION, reason="world under construction: the "
                    "scale thresholds arm when config.under_construction is removed")
def test_world_scale_meets_criterion_1():
    rooms = ENV["rooms"]
    guests = {a["guest"] for a in ENV["arcs"].values() if a.get("guest")}
    residents = [t for t in ENV["toons"] if t["id"] not in guests
                 and not t.get("is_human_controlled")]
    arcs = ENV["arcs"]
    kinds = [a["kind"] for a in arcs.values()]
    keeper_npcs = set()
    for a in arcs.values():
        if a["kind"] == "keeper":
            for b in a["beats"].values():
                if b.get("npc") in KEEPERS:
                    keeper_npcs.add(b["npc"])
    assert len(rooms) >= 15
    assert len(residents) >= 8
    assert len(arcs) >= 10
    assert kinds.count("guest") >= 6
    assert keeper_npcs == KEEPERS, keeper_npcs
    assert any(a.get("cumulative") for a in arcs.values()), \
        "no cumulative multiplayer arc (authored `cumulative: true`)"
    assert len(ENV.get("collectibles", [])) >= 150


# ---- invariants carried over from the retired loft world tests -------------


def test_quest_cross_references_resolve_by_name():
    toons = {t["id"]: t for t in ENV["toons"]}
    things = {t["id"]: t for t in ENV["things"]}
    tace = toons["t-tace"]["properties"]
    gear = things["o-escapement-gear"]
    assert tace["wants"] in [gear["name"], *gear.get("aliases", [])]
    case = things["o-clock-case"]["properties"]
    assert case["use"]["with"] == tace["gives"]["name"]
    assert "use" in tace["gives"]["verbs"]


def test_the_dreamseed_template_is_plantable_and_its_growth_validates():
    from daydream import growth
    from daydream.llm import bootstrap

    tpl = ENV["config"]["templates"]["dreamseed"]
    assert "plant" in tpl["verbs"]
    g = tpl["properties"]["growth"]
    bootstrap._validate_growth(g, "config.templates.dreamseed.properties.growth")
    assert growth._growth_shape_ok(g)
    assert g.get("first_planting_text") and g.get("propagation")


def test_every_resident_carries_a_voice_sheet_and_authored_drift():
    guests = {a["guest"] for a in ENV["arcs"].values() if a.get("guest")}
    for t in ENV["toons"]:
        if t["id"] in guests:
            continue
        props = t.get("properties") or {}
        assert isinstance(props.get("voice"), dict), t["id"]
        if t["id"] != "t-tock":
            assert props.get("topics"), f"{t['id']} has nothing to be asked about"
