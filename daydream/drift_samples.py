"""Drift voice-bench harness: render the LLM-driven drift narrate
prompt against the live vLLM for a small corpus of (npc, mood, memories)
combinations, write a dated model-slugged markdown file for eyeball
review and A/B comparison.

Invoked via `bin/game drift-samples` (thin shell wrapper that shells to
`python -m daydream.drift_samples`).

Dispatch path: for each corpus file, build a synthetic NPC dict and a
list of objects with a `.text` attribute (the drift prompt template only
reads `m.text` from each memory), call `daydream.drift._render_drift_prompt`
to build the user prompt, then `daydream.llm.client.acompletion_json` to
hit vLLM. Parse `narrate` from the JSON response, run `safety.first_banned`
on it, and capture either the narrate or the fallback reason. Per-prompt
metrics (wall-time + prompt/completion tokens via `llm_client.get_last_usage`)
land in the output's metrics table.

Output: `docs/pretty/drift-voice-samples/YYYY-MM-DD-<model_slug>.md`.
Same model on the same day overwrites; different models on the same day
land in distinct files (slug-disambiguated) for git-diff A/B.

Hermetic by construction: no DB, no `memories.retrieve`, no `arbiter`
(it's already inside `acompletion_json`). The corpus drives every input
the production drift code would have built; the captured output is what
the LLM saw and produced for that input. Mirrors `daydream/voice_samples.py`
end-to-end, swapping the dialogue pipeline for the drift prompt pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from daydream import config, drift
from daydream.llm import client as llm_client
from daydream.llm import safety

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRIFT_VOICE_CORPUS_DIR = PROJECT_ROOT / "tests" / "drift" / "drift-voice"
OUTPUT_DIR_DEFAULT = PROJECT_ROOT / "docs" / "pretty" / "drift-voice-samples"

VLLM_PROBE_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class _SyntheticMemory:
    """Minimal memory-shape: only `text` is read by the drift prompt
    template. Frozen so a corpus list is hashable / safe to pass around."""

    text: str


def _slug(model_name: str) -> str:
    """Filesystem-safe slug. Mirrors voice_samples._slug exactly so the
    two output dirs land at the same model-slug shape."""
    tail = model_name.rsplit("/", 1)[-1]
    s = tail.lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown-model"


def _probe_vllm_reachable(base_url: str) -> bool:
    """Quick HTTP probe on the vLLM /models endpoint."""
    url = base_url.rstrip("/") + "/models"
    try:
        r = httpx.get(url, timeout=VLLM_PROBE_TIMEOUT_SECONDS)
        return r.status_code < 500
    except httpx.HTTPError:
        return False


def _load_corpus() -> list[dict]:
    """Load and validate every .json file in tests/drift/drift-voice/.
    Sorted by filename for deterministic output ordering. Each file
    must declare name, npc_id, npc_name, npc_seed, mood, memories."""
    files = sorted(DRIFT_VOICE_CORPUS_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no corpus files in {DRIFT_VOICE_CORPUS_DIR}")
    prompts: list[dict] = []
    required = {"name", "npc_id", "npc_name", "npc_seed", "mood", "memories"}
    for f in files:
        d = json.loads(f.read_text())
        missing = required - set(d.keys())
        if missing:
            raise ValueError(f"{f.name}: missing required fields {sorted(missing)}")
        if not isinstance(d.get("memories"), list):
            raise ValueError(f"{f.name}: memories must be a list of strings")
        for i, m in enumerate(d["memories"]):
            if not isinstance(m, str):
                raise ValueError(f"{f.name}: memories[{i}] must be a string")
        prompts.append(d)
    return prompts


def _build_npc(prompt: dict) -> dict:
    """Build the synthetic NPC dict the drift prompt template expects."""
    return {
        "id": prompt["npc_id"],
        "name": prompt["npc_name"],
        "seed": prompt["npc_seed"],
        "mood": prompt["mood"],
        "world_id": "w-bunny",  # arbitrary; not used by the prompt
        "current_room_id": None,
    }


async def _run_prompt(prompt: dict) -> dict:
    """Render one drift prompt and dispatch it through `acompletion_json`.
    Returns a dict with name, npc_id, mood, memories, rendered_prompt,
    narrate-or-fallback-reason, wall_seconds, prompt_tokens,
    completion_tokens."""
    npc = _build_npc(prompt)
    mems = [_SyntheticMemory(text=t) for t in prompt["memories"]]
    rendered = drift._render_drift_prompt(npc, mems)

    llm_client.reset_last_usage()
    start = time.monotonic()
    narrate: str | None = None
    fallback_reason: str | None = None
    try:
        response = await llm_client.acompletion_json(
            system=drift._DRIFT_SYSTEM_PROMPT, user=rendered
        )
    except llm_client.LLMUnavailable as e:
        fallback_reason = f"LLMUnavailable: {e}"
        response = None
    elapsed = time.monotonic() - start

    if response is not None:
        text = response.get("narrate") if isinstance(response, dict) else None
        if not isinstance(text, str) or not text.strip():
            fallback_reason = f"empty/missing narrate (response={response!r})"
        elif (hit := safety.first_banned(text)) is not None:
            fallback_reason = f"banlist hit: category={hit}, text={text!r}"
        else:
            narrate = text.strip()

    usage = llm_client.get_last_usage() or {}
    return {
        "name": prompt["name"],
        "npc_id": prompt["npc_id"],
        "npc_name": prompt["npc_name"],
        "mood": prompt["mood"],
        "memories": list(prompt["memories"]),
        "rendered_prompt": rendered,
        "narrate": narrate,
        "fallback_reason": fallback_reason,
        "wall_seconds": round(elapsed, 3),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }


async def _dispatch_all(prompts: list[dict]) -> list[dict]:
    results: list[dict] = []
    for p in prompts:
        r = await _run_prompt(p)
        verdict = "emit" if r["narrate"] is not None else "fallback"
        p_in = r["prompt_tokens"] if r["prompt_tokens"] is not None else "—"
        p_out = r["completion_tokens"] if r["completion_tokens"] is not None else "—"
        sys.stderr.write(
            f"[drift-samples] {r['name']}: {verdict} ({r['wall_seconds']}s,"
            f" {p_in} in / {p_out} out)\n"
        )
        sys.stderr.flush()
        results.append(r)
    return results


def _vllm_config_snapshot() -> dict:
    """Same shape as voice_samples._vllm_config_snapshot for visual
    parity in the captured markdown."""
    return {
        "model": config.llm_model(),
        "base_url": config.llm_base_url(),
        "gpu_memory_utilization": os.environ.get("DAYDREAM_VLLM_GMU", "0.45"),
        "max_model_len": os.environ.get("DAYDREAM_VLLM_MAX_LEN", "8192"),
        "enforce_eager": "true",
        "kv_cache_dtype": "fp16 (auto; see docs/gpu-and-models.md)",
    }


def _compose_markdown(config_snapshot: dict, results: list[dict]) -> str:
    """Build the dated markdown: header, config block, metrics table,
    one H3 per prompt with corpus metadata + rendered prompt + narrate
    or fallback reason."""
    today = date.today().isoformat()
    model = config_snapshot["model"]
    lines: list[str] = []
    lines.append(f"# Drift voice samples — {today} — `{model}`")
    lines.append("")
    lines.append(
        "Rendered via `bin/game drift-samples`. Corpus: "
        "`tests/drift/drift-voice/*.json`. Pipeline: "
        "`daydream.drift._render_drift_prompt` then "
        "`daydream.llm.client.acompletion_json` (hermetic — no DB, "
        "no memory store, synthetic memories from each corpus file)."
    )
    lines.append("")

    lines.append("## Config")
    lines.append("")
    lines.append("| setting | value |")
    lines.append("|---|---|")
    for k in sorted(config_snapshot.keys()):
        v = config_snapshot[k]
        lines.append(f"| `{k}` | `{v}` |")
    lines.append("")

    lines.append("## Metrics")
    lines.append("")
    lines.append("| prompt | npc | mood | mems | verdict | tokens in | tokens out | wall s |")
    lines.append("|---|---|---|---:|---|---:|---:|---:|")
    for r in results:
        p_in = r["prompt_tokens"] if r["prompt_tokens"] is not None else "—"
        p_out = r["completion_tokens"] if r["completion_tokens"] is not None else "—"
        verdict = "emit" if r["narrate"] is not None else "fallback"
        lines.append(
            f"| `{r['name']}` | {r['npc_name']} | {r['mood']} | {len(r['memories'])} |"
            f" {verdict} | {p_in} | {p_out} | {r['wall_seconds']} |"
        )
    lines.append("")

    lines.append("## Samples")
    lines.append("")
    for r in results:
        lines.append(f"### {r['name']}")
        lines.append("")
        lines.append(f"**NPC:** {r['npc_name']} ({r['npc_id']}) — mood: `{r['mood']}`")
        lines.append("")
        if r["memories"]:
            lines.append("**Memories injected:**")
            lines.append("")
            for m in r["memories"]:
                lines.append(f"- `{m}`")
            lines.append("")
        else:
            lines.append("**Memories:** _(empty)_")
            lines.append("")
        if r["narrate"] is not None:
            lines.append("**Narrate:**")
            lines.append("")
            for line in r["narrate"].splitlines() or [""]:
                lines.append(f"> {line}")
        else:
            lines.append(f"**FALLBACK:** {r['fallback_reason']}")
        lines.append("")
    return "\n".join(lines)


async def _main_async(out_dir: Path) -> int:
    base = config.llm_base_url()
    if not _probe_vllm_reachable(base):
        print(
            f"[drift-samples] vLLM unreachable at {base};"
            " start it via `bin/game vllm-up`",
            file=sys.stderr,
        )
        return 2

    try:
        prompts = _load_corpus()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"[drift-samples] corpus error: {e}", file=sys.stderr)
        return 3

    results = await _dispatch_all(prompts)

    snapshot = _vllm_config_snapshot()
    markdown = _compose_markdown(snapshot, results)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-{_slug(snapshot['model'])}.md"
    out_path.write_text(markdown)
    print(f"[drift-samples] wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daydream.drift_samples")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUTPUT_DIR_DEFAULT,
        help="output directory for dated markdown files "
        "(default: docs/pretty/drift-voice-samples/)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_main_async(args.out_dir))


if __name__ == "__main__":
    sys.exit(main())
