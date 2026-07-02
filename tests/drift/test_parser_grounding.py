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
