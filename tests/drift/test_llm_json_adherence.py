"""LLM JSON-adherence drift probes.

For each prompt in tests/drift/prompts/, call acompletion_json through
the real vLLM path (the client acquires the arbiter internally), assert
the declared expected_schema_keys are all present, measure latency, and
compare against the committed baseline.

The strict-JSON system prompt is the tripwire the fp8-KV regression
tripped on (see docs/gpu-and-models.md): 7B models with fp8_e4m3 KV
cache on drop out of JSON mode mid-generation and emit garbage tokens.
A divergence on any of the expected keys here is the same signal as
that known regression.

Requires vLLM reachable at config.llm_base_url(). Drift probes run in
the long tier — `bin/game test long`."""

from __future__ import annotations

import time

import pytest

from daydream.llm import client as llm_client

from .conftest import assert_within, load_prompt_corpus, write_latest

pytestmark = [
    pytest.mark.tier_long,
    pytest.mark.requires_vllm,
]


_corpus = load_prompt_corpus()


@pytest.mark.parametrize("probe_id,probe", _corpus, ids=[pid for pid, _ in _corpus])
async def test_llm_json_probe(probe_id: str, probe: dict):
    """Run one JSON-adherence probe end-to-end, compare latency + shape
    to baseline. Shape mismatches or missing baseline fail the test with
    a clear 'ratify me' message; a latency window of 0.5x-2.5x catches
    large regressions without alarming on every jitter."""
    t0 = time.monotonic()
    try:
        result = await llm_client.acompletion_json(
            system=probe["system"],
            user=probe["user"],
            max_tokens=probe["max_tokens"],
        )
    except llm_client.LLMUnavailable as e:
        # Record latest on failure so operator can see what came back
        # even when the call didn't produce a dict.
        write_latest(f"llm_{probe_id}", {"error": f"LLMUnavailable: {e}"})
        pytest.fail(f"LLM call failed for {probe_id!r}: {e}")
    dt_ms = (time.monotonic() - t0) * 1000

    missing = [k for k in probe["expected_schema_keys"] if k not in result]
    if missing:
        write_latest(
            f"llm_{probe_id}",
            {"missing_keys": missing, "observed_keys": list(result.keys()), "latency_ms": dt_ms},
        )
        pytest.fail(
            f"JSON schema drift for {probe_id!r}: missing keys {missing!r}. "
            f"Observed keys: {list(result.keys())!r}. "
            "This is the fp8-KV / format-adherence tripwire; see docs/gpu-and-models.md."
        )

    observed = {
        "latency_ms": dt_ms,
        "observed_keys": sorted(result.keys()),
        "model": llm_client.config.llm_model(),
    }
    assert_within(
        f"llm_{probe_id}",
        observed,
        within={"latency_ms": (0.5, 2.5)},
    )
