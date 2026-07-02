"""Growth-composition drift probe (real GPU; SPEC 2026-07-02 criterion 7).

Renders the SHIPPED dreamseed's growth block (worlds/clockmakers-loft.json)
through the real growth prompt against real vLLM for a fixed corpus of vision
phrases, and fingerprints per phrase: schema validity, refusal, whether the
player's phrase was woven into the composition, distinctness from the seed's
authored exemplars, and object count — plus a latency window.

This probe IS the local-limits gate for the mitigation ladder (rung a: free
composition / rung b: skeleton select-and-fill / rung c: deterministic fill).
Ratifying the first golden REQUIRES the agent reading the captured prose in
`tests/baselines/growth_compose_*.latest.json` against WHIMSY.md and recording
the rung decision in the ratification commit message — the numbers here catch
DRIFT; the initial "is the prose good enough to ship" call is the agent's
(per the CLAUDE.md "flag local limits at design time" pact).

Requires vLLM; runs in the long tier — `bin/game test long`, server DOWN per
the GPU policy."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from daydream import growth, rooms
from daydream.llm import client as llm_client
from daydream.llm import safety

from .conftest import assert_against_baseline, load_golden, write_latest

pytestmark = [
    pytest.mark.tier_long,
    pytest.mark.requires_vllm,
]

_REPO = Path(__file__).resolve().parent.parent.parent
_WORLD = _REPO / "worlds" / "clockmakers-loft.json"

# The fixed vision corpus (>=3 phrases, in-tone, varied register). Expanding
# it is a positive act; the probe scales automatically.
_CORPUS: list[tuple[str, str]] = [
    ("mossy_stair", "a mossy stair down to a slow river"),
    ("moth_attic", "an attic where the moths keep the hours"),
    ("cedar_kitchen", "a warm kitchen that smells of cedar and rain"),
]

_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "to", "and", "that", "where", "down", "into",
     "with", "keep", "keeps"}
)


def _shipped_growth_and_room() -> tuple[dict, "rooms.Room"]:
    """The SHIPPED seed's growth block + the clocktower it is found in, read
    straight from the canonical envelope (no DB, no loader)."""
    env = json.loads(_WORLD.read_text())
    case = next(it for it in env["items"] if it["name"] == "clock case")
    seed = next(e for e in case["properties"]["contains"]
                if e["name"] == "dreamseed")
    g = seed["properties"]["growth"]
    tower = next(r for r in env["rooms"] if r["slug"] == "clocktower")
    room = rooms.Room(
        id="r-clocktower", world_id="w-bunny", slug="clocktower",
        title=tower["title"], seed=tower["seed"],
        description_cached=None, exits={}, parent_id=None,
    )
    return g, room


def _phrase_words(phrase: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", phrase.lower())
            if len(w) >= 4 and w not in _STOPWORDS]


def _word_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def _distinct_from_exemplars(comp: dict, g: dict) -> bool:
    """Distinctness proxy: the title is not an exemplar title, and the
    description's word overlap with every exemplar description stays under
    60% — copies and near-copies read as not-distinct."""
    for ex in g["exemplars"]:
        if comp["title"].strip().lower() == ex["title"].strip().lower():
            return False
    comp_words = _word_set(comp["description"])
    if not comp_words:
        return False
    for ex in g["exemplars"]:
        overlap = len(comp_words & _word_set(ex["description"])) / len(comp_words)
        if overlap >= 0.6:
            return False
    return True


@pytest.mark.parametrize("probe_id,phrase", _CORPUS, ids=[p for p, _ in _CORPUS])
async def test_growth_compose_probe(probe_id: str, phrase: str):
    g, room = _shipped_growth_and_room()
    t0 = time.monotonic()
    try:
        result = await llm_client.acompletion_json(
            system=growth.GROWTH_SYSTEM,
            user=growth._user_prompt(g, room, phrase),
            max_tokens=450,
            timeout=30.0,
        )
    except llm_client.LLMUnavailable as e:
        write_latest(f"growth_compose_{probe_id}", {"error": str(e)})
        pytest.fail(f"growth LLM call failed for {probe_id!r}: {e}")
    dt_ms = (time.monotonic() - t0) * 1000

    refused = safety.parse_refusal(result) is not None
    composition = None if refused else growth.validate_growth_output(result, g)
    valid = composition is not None

    if valid:
        woven_text = " ".join(
            [composition["title"], composition["room_seed"],
             composition["description"]]
        ).lower()
        observed = {
            "valid": True,
            "refused": False,
            "phrase_woven": any(w in woven_text for w in _phrase_words(phrase)),
            "distinct_from_exemplars": _distinct_from_exemplars(composition, g),
            "object_count": len(composition["objects"]),
            "latency_ms": dt_ms,
            # The captured prose the agent reads for the rung ratification —
            # metadata, never compared.
            "phrase": phrase,
            "title": composition["title"],
            "room_seed": composition["room_seed"],
            "description": composition["description"],
            "objects": composition["objects"],
            "model": llm_client.config.llm_model(),
        }
    else:
        observed = {
            "valid": False,
            "refused": refused,
            "phrase_woven": False,
            "distinct_from_exemplars": False,
            "object_count": 0,
            "latency_ms": dt_ms,
            "phrase": phrase,
            "raw_result": result if isinstance(result, dict) else str(result),
            "model": llm_client.config.llm_model(),
        }

    assert_against_baseline(
        f"growth_compose_{probe_id}",
        observed,
        compare_keys=["valid", "refused", "phrase_woven",
                      "distinct_from_exemplars", "object_count"],
    )
    # Latency window rides separately (the flags above are exact-compare):
    # 0.5x-2.5x of the ratified golden, matching the JSON-adherence probe.
    golden = load_golden(f"growth_compose_{probe_id}")
    assert golden is not None  # assert_against_baseline failed otherwise
    lo, hi = golden["latency_ms"] * 0.5, golden["latency_ms"] * 2.5
    assert lo <= dt_ms <= hi, (
        f"growth compose latency drift for {probe_id!r}: {dt_ms:.0f}ms outside "
        f"[{lo:.0f}, {hi:.0f}]ms (golden {golden['latency_ms']:.0f}ms)"
    )
