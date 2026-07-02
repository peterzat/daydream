"""Retell drift probe (real GPU; SPEC 2026-07-02 criterion 13).

Runs the SHIPPED retell layer — the Zork world's voice block, the real
system prompt, real vLLM — over a fixed corpus of eligible authored
narrations sampled deterministically from worlds/zork1.json, and
fingerprints the SECOND telling of each line (the scoped rung: first
tellings are always authored): how many retold (survived validation),
how many fell back, and the per-line valid/fallback split. Texts are
captured to the .latest file for the agent's in-session voice grading
(the ratification step: the agent reads the samples against the voice
register and records the shipped rung — ON / scoped / OFF — in the
ratification commit, per the flag-local-limits pact). The numbers catch
DRIFT; the initial ship/scope call is the agent's.

Temperature is pinned to 0 for the probe (production runs 0.8 for
variety), so the fingerprint is stable run to run on the same engine.

Requires vLLM; runs in the long tier — `bin/game test long`, server DOWN
per the GPU policy."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from daydream import db, retell, worldstate

from .conftest import assert_against_baseline

pytestmark = [
    pytest.mark.tier_long,
    pytest.mark.requires_vllm,
]

_REPO = Path(__file__).resolve().parent.parent.parent
_ENVELOPE = _REPO / "worlds" / "zork1.json"
_WORLD = "w-zork1-retell-probe"
_SAMPLES = 8


def _eligible_corpus() -> list[str]:
    """The first N eligible narrate texts from the envelope's rules, in
    stable author order (rooms, then things, then toons, then world) —
    growing the world grows the pool deterministically."""
    env = json.loads(_ENVELOPE.read_text())
    texts: list[str] = []
    seen: set[str] = set()

    def scan(rules) -> None:
        for rule in rules or []:
            for eff in rule.get("do", []):
                t = eff.get("text")
                if (
                    eff.get("kind") == "narrate" and isinstance(t, str)
                    and not eff.get("verbatim") and retell.eligible(t)
                    and t not in seen
                ):
                    seen.add(t)
                    texts.append(t)

    for section in ("rooms", "things", "toons"):
        for obj in env.get(section, []):
            scan(obj.get("rules"))
    scan(env.get("rules"))
    return texts[:_SAMPLES]


@pytest.fixture()
def probe_world(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_RETELL_ENABLED", "1")
    monkeypatch.setattr(retell, "RETELL_TEMPERATURE", 0.0)
    db.close_db()
    db.init_live(path=tmp_path / "retell-probe.db")
    db.get_conn().execute(
        "INSERT INTO worlds (id, name, slug, aesthetic_seed) VALUES "
        f"('{_WORLD}', 'Probe', 'probe', 'seed')"
    )
    voice = json.loads(_ENVELOPE.read_text())["voice"]
    worldstate.set(_WORLD, "voice", voice)
    yield
    db.close_db()


async def test_retell_layer_holds_register(probe_world):
    corpus = _eligible_corpus()
    assert len(corpus) == _SAMPLES, "corpus shrank; the sampler is deterministic"

    results = []
    retold_count = 0
    t0 = time.monotonic()
    for text in corpus:
        primed = await retell.maybe_retell(_WORLD, text, purpose="probe-prime")
        assert primed == text, "the scoped rung: first telling is authored"
        out = await retell.maybe_retell(_WORLD, text, purpose="probe")
        changed = out != text
        retold_count += changed
        results.append({
            "original": text,
            "retold": out if changed else None,
            "changed": changed,
        })
    total_ms = (time.monotonic() - t0) * 1000

    observed = {
        "samples": len(corpus),
        "retold": retold_count,
        "fallbacks": len(corpus) - retold_count,
        "results": results,
        "total_latency_ms": round(total_ms),
    }
    # The retell layer earns ON only if the majority of eligible lines
    # survive validation — below that the shipped rung question reopens.
    assert retold_count * 2 >= len(corpus), (
        f"only {retold_count}/{len(corpus)} lines survived validation; "
        "the retell rung decision needs revisiting (ON -> scoped -> OFF)")
    assert_against_baseline(
        "retell_probe_zork1", observed,
        compare_keys=["samples", "retold", "fallbacks"],
    )
