"""Tests for the drift voice-bench harness (`daydream/drift_samples.py`).

The harness drives the LLM-driven drift narrate path against the live
vLLM end-to-end; tier_short tests here exercise the pure-Python
plumbing (corpus loader, prompt-build, markdown composer) and a
mocked-LLM end-to-end smoke. No real vLLM is touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import drift_samples
from daydream.llm import client as llm_client


@pytest.mark.tier_short
def test_load_corpus_finds_at_least_5_prompts():
    """The shipped corpus has 5 prompts mirroring the spec's 5 anchors."""
    prompts = drift_samples._load_corpus()
    assert len(prompts) >= 5
    names = {p["name"] for p in prompts}
    assert len(names) == len(prompts), "duplicate prompt names in corpus"


@pytest.mark.tier_short
def test_load_corpus_validates_required_fields(tmp_path, monkeypatch):
    """Corpus loader rejects files missing required keys."""
    bad_dir = tmp_path / "corpus"
    bad_dir.mkdir()
    (bad_dir / "incomplete.json").write_text(
        json.dumps({"name": "x", "npc_id": "t-x"})
    )
    monkeypatch.setattr(drift_samples, "DRIFT_VOICE_CORPUS_DIR", bad_dir)
    with pytest.raises(ValueError, match="missing required fields"):
        drift_samples._load_corpus()


@pytest.mark.tier_short
def test_load_corpus_validates_memories_is_list(tmp_path, monkeypatch):
    """`memories` must be a list of strings."""
    bad_dir = tmp_path / "corpus"
    bad_dir.mkdir()
    (bad_dir / "wrong_memories.json").write_text(
        json.dumps({
            "name": "x", "npc_id": "t-x", "npc_name": "X", "npc_seed": "s",
            "mood": "content", "memories": "not-a-list",
        })
    )
    monkeypatch.setattr(drift_samples, "DRIFT_VOICE_CORPUS_DIR", bad_dir)
    with pytest.raises(ValueError, match="memories must be a list"):
        drift_samples._load_corpus()


@pytest.mark.tier_short
def test_build_npc_passes_through_corpus_fields():
    """`_build_npc` produces a dict with the keys `_render_drift_prompt`
    and `_llm_narrate` need."""
    prompt = {
        "npc_id": "t-rook",
        "npc_name": "Rook",
        "npc_seed": "the forge-keeper",
        "mood": "content",
        "memories": [],
    }
    npc = drift_samples._build_npc(prompt)
    assert npc["id"] == "t-rook"
    assert npc["name"] == "Rook"
    assert npc["seed"] == "the forge-keeper"
    assert npc["mood"] == "content"
    assert "world_id" in npc


@pytest.mark.tier_short
def test_slug_strips_org_and_lowercases():
    """Filesystem-safe slug matches the voice_samples convention."""
    assert drift_samples._slug("Qwen/Qwen2.5-7B-Instruct-AWQ") == "qwen2.5-7b-instruct-awq"
    assert drift_samples._slug("foo-bar") == "foo-bar"


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_run_prompt_emit_path(monkeypatch):
    """`_run_prompt` with a clean LLM response produces a result with
    narrate set, no fallback_reason, and metrics fields."""
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"narrate": "Rook hums softly to himself."}),
    )
    prompt = {
        "name": "test_emit",
        "npc_id": "t-rook",
        "npc_name": "Rook",
        "npc_seed": "the forge-keeper",
        "mood": "content",
        "memories": ["the visitor said: hello"],
    }
    result = await drift_samples._run_prompt(prompt)
    assert result["narrate"] == "Rook hums softly to himself."
    assert result["fallback_reason"] is None
    assert result["wall_seconds"] >= 0
    assert "rendered_prompt" in result
    assert "<memory>the visitor said: hello</memory>" in result["rendered_prompt"]


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_run_prompt_fallback_on_llm_unavailable(monkeypatch):
    """`_run_prompt` captures fallback_reason on LLMUnavailable."""
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=llm_client.LLMUnavailable("vllm down")),
    )
    prompt = {
        "name": "test_fallback",
        "npc_id": "t-rook",
        "npc_name": "Rook",
        "npc_seed": "the forge-keeper",
        "mood": "content",
        "memories": [],
    }
    result = await drift_samples._run_prompt(prompt)
    assert result["narrate"] is None
    assert "LLMUnavailable" in result["fallback_reason"]


@pytest.mark.tier_short
@pytest.mark.asyncio
async def test_run_prompt_fallback_on_banlist_hit(monkeypatch):
    """A narrate that trips the WHIMSY banlist is captured as fallback."""
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(return_value={"narrate": "the dream feels uncannily pixel-art tonight"}),
    )
    prompt = {
        "name": "test_banlist",
        "npc_id": "t-rook",
        "npc_name": "Rook",
        "npc_seed": "the forge-keeper",
        "mood": "content",
        "memories": [],
    }
    result = await drift_samples._run_prompt(prompt)
    assert result["narrate"] is None
    assert "banlist" in result["fallback_reason"]


@pytest.mark.tier_short
def test_compose_markdown_includes_metrics_and_samples():
    """The composed markdown includes the metrics table, the samples
    section, and one entry per result."""
    snapshot = {
        "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
        "base_url": "http://localhost:8000/v1",
        "gpu_memory_utilization": "0.45",
        "max_model_len": "8192",
        "enforce_eager": "true",
        "kv_cache_dtype": "fp16",
    }
    results = [
        {
            "name": "anchor1",
            "npc_id": "t-rook",
            "npc_name": "Rook",
            "mood": "content",
            "memories": ["m1", "m2"],
            "rendered_prompt": "...",
            "narrate": "Rook hums softly.",
            "fallback_reason": None,
            "wall_seconds": 0.5,
            "prompt_tokens": 100,
            "completion_tokens": 20,
        },
        {
            "name": "anchor2",
            "npc_id": "t-iris",
            "npc_name": "Iris",
            "mood": "thoughtful",
            "memories": [],
            "rendered_prompt": "...",
            "narrate": None,
            "fallback_reason": "banlist hit: category=pixel-art",
            "wall_seconds": 0.4,
            "prompt_tokens": 80,
            "completion_tokens": 5,
        },
    ]
    md = drift_samples._compose_markdown(snapshot, results)
    assert "qwen2.5-7b-instruct-awq" in md.lower() or "Qwen/Qwen2.5-7B-Instruct-AWQ" in md
    assert "## Metrics" in md
    assert "## Samples" in md
    assert "anchor1" in md
    assert "anchor2" in md
    assert "Rook hums softly." in md
    assert "FALLBACK" in md
    assert "banlist hit" in md
    # Memories section appears only for non-empty memories.
    assert "**Memories injected:**" in md  # for anchor1
    assert "_(empty)_" in md  # for anchor2


@pytest.mark.tier_short
def test_compose_markdown_emit_only_no_fallback():
    """When all results emit cleanly, the markdown has no FALLBACK
    sections."""
    snapshot = {
        "model": "test/model",
        "base_url": "x",
        "gpu_memory_utilization": "0.5",
        "max_model_len": "8192",
        "enforce_eager": "true",
        "kv_cache_dtype": "fp16",
    }
    results = [
        {
            "name": "ok",
            "npc_id": "t-rook",
            "npc_name": "Rook",
            "mood": "content",
            "memories": [],
            "rendered_prompt": "...",
            "narrate": "Rook listens to the wind.",
            "fallback_reason": None,
            "wall_seconds": 0.3,
            "prompt_tokens": 50,
            "completion_tokens": 12,
        },
    ]
    md = drift_samples._compose_markdown(snapshot, results)
    assert "FALLBACK" not in md
    assert "Rook listens to the wind." in md
