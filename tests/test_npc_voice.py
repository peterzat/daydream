"""Per-NPC voice constraints + forge-as-forge seed in the authored world
(SPEC 2026-06-30 C11, C12).

These pin the testable PRESENCE of the voice constraints (Rook laconic, Iris
bookish, Bram gentle; all terse and non-florid) and the working-forge imagery
in the r-forge seed. The in-character feel of the dialogue and the rendered
forge image itself are the flagged one-time qpeek / browser eyeball, per the
generation policy (these are prompt/seed authoring within the local 7B budget,
not a model swap)."""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

BUNNY = Path(__file__).resolve().parent.parent / "worlds" / "bunny.json"


def _toon_prompt(env: dict, name: str) -> str:
    for t in env["toons"]:
        if t.get("name") == name:
            return ((t.get("dialogue") or {}).get("prompt_template") or "").lower()
    return ""


def _room_seed(env: dict, slug: str) -> str:
    for r in env["rooms"]:
        if r.get("slug") == slug:
            return (r.get("seed") or "").lower()
    return ""


def test_npc_prompts_encode_per_voice_descriptor():
    env = json.loads(BUNNY.read_text())
    assert "laconic" in _toon_prompt(env, "Rook")
    assert "bookish" in _toon_prompt(env, "Iris")
    assert "gentle" in _toon_prompt(env, "Bram")


def test_npc_prompts_constrain_terseness_and_florid():
    """Each dialogue prompt holds a terseness cap and a no-florid guard, so the
    local 7B stays in-voice rather than over-writing."""
    env = json.loads(BUNNY.read_text())
    for name in ("Rook", "Iris", "Bram"):
        p = _toon_prompt(env, name)
        assert "short sentence" in p, f"{name} prompt lacks a terseness cap"
        assert "florid" in p, f"{name} prompt lacks a no-florid guard"


def test_forge_seed_reads_as_working_forge():
    """The forge image prompt seed foregrounds a working forge (anvil +
    bellows), not a domestic hearth."""
    seed = _room_seed(json.loads(BUNNY.read_text()), "forge")
    assert "anvil" in seed
    assert "bellows" in seed
