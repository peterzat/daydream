"""Parser grounding drift probe (real GPU).

Grounds real Qwen output to in-scope object IDS across a small command corpus:
for each phrasing, the model must return strict JSON selecting the right verb
from the closed set AND the right direct-object id from the enumerated scope.
This is the runtime half of the SPEC 2026-06-30 parser contract — the same
strict-JSON tripwire as the JSON-adherence probe (a model dropping out of JSON
mode, or grounding to the wrong id, fails here).

The probe builds the parser's actual SYSTEM + user prompt with a synthetic
scope (no DB), so it isolates the model's grounding behavior. Requires vLLM;
runs in the long tier — `bin/game test long`."""

from __future__ import annotations

import time

import pytest

from daydream import parser, verbs
from daydream.llm import client as llm_client

from .conftest import write_latest

pytestmark = [
    pytest.mark.tier_long,
    pytest.mark.requires_vllm,
]


# A fixed in-scope set the model grounds against (mirrors the canonical world:
# Rook the forge-keeper + a lantern on the ground + a carried dreamseed).
_SCOPE = [
    {"id": "t-rook", "name": "Rook", "kind": "toon",
     "verbs": ["examine", "talk"], "aliases": []},
    {"id": "i-lantern", "name": "lantern", "kind": "thing",
     "verbs": ["examine", "take", "drop"], "aliases": ["lamp"]},
    {"id": "o-dreamseed", "name": "dreamseed", "kind": "thing",
     "verbs": ["examine", "take", "drop", "give", "plant"],
     "aliases": ["seed"]},
]
_VOCAB = [{"name": v.name, "description": v.description} for v in verbs.VERBS.values()]

# (input, expected verb, expected dobj id). The talk variants are the headline
# pain point: "say hi to rook" must become talk(t-rook), not say.
_CASES = [
    ("say hi to rook", "talk", "t-rook"),
    ("talk to rook", "talk", "t-rook"),
    ("greet rook", "talk", "t-rook"),
    ("take the lantern", "take", "i-lantern"),
    ("pick up the lamp", "take", "i-lantern"),
    ("look closely at the lantern", "examine", "i-lantern"),
    # The typed plant path (SPEC 2026-07-02): free_text defers to the LLM,
    # which must ground the seed id and keep plant (not say/use/drop).
    ("plant the dreamseed to a moonlit orchard", "plant", "o-dreamseed"),
]


@pytest.mark.parametrize("text,want_verb,want_dobj", _CASES, ids=[c[0] for c in _CASES])
async def test_parser_grounds_to_ids(text: str, want_verb: str, want_dobj: str):
    t0 = time.monotonic()
    try:
        result = await llm_client.acompletion_json(
            system=parser.SYSTEM,
            user=parser._user_prompt(text, _VOCAB, _SCOPE),
            max_tokens=128,
        )
    except llm_client.LLMUnavailable as e:
        write_latest("parser_" + text.replace(" ", "_"), {"error": str(e)})
        pytest.fail(f"LLM call failed for {text!r}: {e}")
    dt_ms = (time.monotonic() - t0) * 1000

    got_verb = str(result.get("verb", "")).strip().lower()
    got_dobj = result.get("dobj_id")
    write_latest(
        "parser_" + text.replace(" ", "_"),
        {"verb": got_verb, "dobj_id": got_dobj, "latency_ms": dt_ms},
    )
    assert got_verb == want_verb, (
        f"grounding drift: {text!r} -> verb {got_verb!r}, expected {want_verb!r}. "
        "The parser model selected the wrong closed verb."
    )
    assert got_dobj == want_dobj, (
        f"grounding drift: {text!r} -> dobj {got_dobj!r}, expected {want_dobj!r}. "
        "The parser model grounded to the wrong / no in-scope id."
    )


# ---- the wide-command-surface corpus (SPEC 2026-07-02 criterion 9) ----------
#
# Natural phrasings a player actually types, grounded against a scope and
# verb vocabulary drawn from the Zork-scale world (world-declared verbs join
# the grounding prompt exactly as at runtime). The fast-path covers the
# canonical walkthrough without the LLM; THIS corpus records how well the
# local model backstops everything else. (The criterion's named phrase
# 'douse the lamp' is alias-covered and locked deterministically in
# tests/test_parser_zork.py; the LLM corpus tests phrasings the
# fast-path does NOT cover.)

import json  # noqa: E402
from pathlib import Path  # noqa: E402

_ZORK_ENV = json.loads(
    (Path(__file__).resolve().parent.parent.parent / "worlds/zork1.json").read_text()
)
_ZORK_VOCAB = _VOCAB + [
    {"name": name, "description": d.get("description", "")}
    for name, d in _ZORK_ENV.get("verbs", {}).items()
]

_ZORK_SCOPE = [
    {"id": "t-troll", "name": "troll", "kind": "toon",
     "verbs": ["examine", "attack"], "aliases": ["nasty troll"]},
    {"id": "t-thief", "name": "thief", "kind": "toon",
     "verbs": ["examine", "attack", "give"], "aliases": ["robber"]},
    {"id": "o-lamp", "name": "brass lantern", "kind": "thing",
     "verbs": ["examine", "take", "drop", "light", "extinguish"],
     "aliases": ["lamp", "lantern"]},
    {"id": "o-sword", "name": "elvish sword", "kind": "thing",
     "verbs": ["examine", "take", "drop"], "aliases": ["sword", "blade"]},
    {"id": "o-bar", "name": "platinum bar", "kind": "thing",
     "verbs": ["examine", "take", "drop"], "aliases": ["bar"]},
    {"id": "o-trap-door", "name": "trap door", "kind": "thing",
     "verbs": ["examine", "open", "close"], "aliases": ["trapdoor", "door"]},
    {"id": "o-candles", "name": "pair of candles", "kind": "thing",
     "verbs": ["examine", "take", "light", "extinguish"],
     "aliases": ["candles"]},
    {"id": "o-bell", "name": "brass bell", "kind": "thing",
     "verbs": ["examine", "take", "ring"], "aliases": ["bell"]},
    {"id": "o-rug", "name": "oriental rug", "kind": "thing",
     "verbs": ["examine", "move"], "aliases": ["rug", "carpet"]},
    {"id": "o-boat", "name": "magic boat", "kind": "thing",
     "verbs": ["examine", "board", "inflate"], "aliases": ["boat", "raft"]},
    {"id": "o-egg", "name": "jewel-encrusted egg", "kind": "thing",
     "verbs": ["examine", "take", "drop", "give", "open"], "aliases": ["egg"]},
]

_ZORK_CASES = [
    ("extinguish the lantern", "extinguish", "o-lamp"),
    ("smash the troll with my sword", "attack", "t-troll"),
    ("get the lantern", "take", "o-lamp"),
    ("pick up the platinum bar", "take", "o-bar"),
    ("shut the trap door", "close", "o-trap-door"),
    ("kindle the candles", "light", "o-candles"),
    ("strike the bell", "ring", "o-bell"),
    ("shove the rug aside", "move", "o-rug"),
    ("climb into the boat", "board", "o-boat"),
    ("hand the egg to the thief", "give", "o-egg"),
]


@pytest.mark.parametrize(
    "text,want_verb,want_dobj", _ZORK_CASES, ids=[c[0] for c in _ZORK_CASES]
)
async def test_wide_surface_grounding(text: str, want_verb: str, want_dobj: str):
    t0 = time.monotonic()
    try:
        result = await llm_client.acompletion_json(
            system=parser.SYSTEM,
            user=parser._user_prompt(text, _ZORK_VOCAB, _ZORK_SCOPE),
            max_tokens=128,
        )
    except llm_client.LLMUnavailable as e:
        write_latest("parser_wide_" + text.replace(" ", "_"), {"error": str(e)})
        pytest.fail(f"LLM call failed for {text!r}: {e}")
    dt_ms = (time.monotonic() - t0) * 1000

    got_verb = str(result.get("verb", "")).strip().lower()
    got_dobj = result.get("dobj_id")
    write_latest(
        "parser_wide_" + text.replace(" ", "_"),
        {"verb": got_verb, "dobj_id": got_dobj, "latency_ms": dt_ms},
    )
    assert got_verb == want_verb, (
        f"grounding drift: {text!r} -> verb {got_verb!r}, expected {want_verb!r}."
    )
    assert got_dobj == want_dobj, (
        f"grounding drift: {text!r} -> dobj {got_dobj!r}, expected {want_dobj!r}."
    )
