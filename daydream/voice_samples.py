"""Voice-samples harness: render anchor prompts through the rook data
skill against the live vLLM, write a dated model-slugged markdown
file for eyeball review and A/B comparison.

Invoked via `bin/game voice-samples` (thin shell wrapper in bin/game
that just shells to `python -m daydream.voice_samples`).

Dispatch path: for each corpus file, the harness installs
skills/rook.json into a tmp DB (hermetic — the capture reflects the
CHECKED-IN author file, not whatever the operator has installed),
then calls `daydream.skills.data.execute_by_name` with the prompt's
`player_input` as args. The same data-skill pipeline the game runs
in production is exercised end-to-end: safety banlist on input,
Jinja SandboxedEnvironment render with `<player_input>` wrap, LLM
call (arbiter-held), refusal parse, output banlist, effect dispatch.
The narrate events emitted during each dispatch are captured and
written verbatim to the output.

Per-prompt metrics come from a side channel on the LLM client
(`daydream.llm.client.get_last_usage`) — we read prompt_tokens and
completion_tokens after each dispatch to build a metrics table.
Wall-time is measured around the dispatch itself.

Output: `docs/pretty/voice-samples/YYYY-MM-DD-<model_slug>.md`. Same
model on the same day overwrites (date granularity is the chronology
unit); different models on the same day land in distinct files so
`git diff` between them is the A/B comparison. See SPEC 2026-04-24
"voice-bench + Qwen RP-Ink A/B" for the decisional framing and
docs/gpu-and-models.md for the vLLM flag discipline this tool
expects (same-config across A/B legs; no --kv-cache-dtype fp8_e4m3
on 7B models)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import httpx

from daydream import admin, config, db, events
from daydream.llm import client as llm_client
from daydream.skills import data as data_skills

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VOICE_CORPUS_DIR = PROJECT_ROOT / "tests" / "drift" / "voice"
ROOK_JSON = PROJECT_ROOT / "skills" / "rook.json"
OUTPUT_DIR_DEFAULT = PROJECT_ROOT / "docs" / "pretty" / "voice-samples"

HUMAN_TOON_ID = "t-wren"
ROOK_ROOM_ID = "r-forge"

VLLM_PROBE_TIMEOUT_SECONDS = 2.0


def _slug(model_name: str) -> str:
    """Filesystem-safe slug of a HuggingFace model id. Strips the
    leading org prefix for readability, lowercases, and collapses any
    non-[a-z0-9._-] character run into a single hyphen.

    Example: `Qwen/Qwen2.5-7B-Instruct-AWQ` -> `qwen2.5-7b-instruct-awq`.
    """
    tail = model_name.rsplit("/", 1)[-1]
    s = tail.lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown-model"


def _probe_vllm_reachable(base_url: str) -> bool:
    """Quick HTTP probe on the vLLM /models endpoint. Same 2s-timeout
    pattern the test suite uses for requires_vllm gating."""
    url = base_url.rstrip("/") + "/models"
    try:
        r = httpx.get(url, timeout=VLLM_PROBE_TIMEOUT_SECONDS)
        return r.status_code < 500
    except httpx.HTTPError:
        return False


def _load_corpus() -> list[dict]:
    """Load and validate every .json file in tests/drift/voice/. Sorted
    by filename for deterministic output ordering. Each file must
    declare name, skill, and player_input; _doc is optional."""
    files = sorted(VOICE_CORPUS_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no corpus files in {VOICE_CORPUS_DIR}")
    prompts: list[dict] = []
    required = {"name", "skill", "player_input"}
    for f in files:
        d = json.loads(f.read_text())
        missing = required - set(d.keys())
        if missing:
            raise ValueError(f"{f.name}: missing required fields {sorted(missing)}")
        if not isinstance(d.get("player_input"), str):
            raise ValueError(f"{f.name}: player_input must be a string")
        prompts.append(d)
    return prompts


async def _run_prompt(prompt: dict) -> dict:
    """Dispatch one prompt through the data-skill pipeline; return a
    dict with name, player_input, captured narrate, wall_seconds, and
    optional prompt_tokens / completion_tokens (None if the LLM call
    never happened, e.g. banlist short-circuit)."""
    llm_client.reset_last_usage()
    before_seq = events.max_seq()
    start = time.monotonic()
    await data_skills.execute_by_name(
        prompt["skill"], HUMAN_TOON_ID, ROOK_ROOM_ID, prompt["player_input"],
    )
    elapsed = time.monotonic() - start

    new_events = events.fetch_since(before_seq)
    narrate_texts = [
        e.payload.get("text", "")
        for e in new_events
        if e.kind == "narrate"
    ]
    narrate = "\n".join(narrate_texts) if narrate_texts else "(no narrate emitted)"

    usage = llm_client.get_last_usage() or {}
    return {
        "name": prompt["name"],
        "player_input": prompt["player_input"],
        "narrate": narrate,
        "wall_seconds": round(elapsed, 3),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }


async def _dispatch_all(prompts: list[dict]) -> list[dict]:
    results: list[dict] = []
    for p in prompts:
        r = await _run_prompt(p)
        # Per-prompt progress on stderr while the harness runs against
        # the live LLM (each dispatch takes several seconds).
        p_in = r["prompt_tokens"] if r["prompt_tokens"] is not None else "—"
        p_out = r["completion_tokens"] if r["completion_tokens"] is not None else "—"
        sys.stderr.write(
            f"[voice-samples] {r['name']}: {r['wall_seconds']}s"
            f" ({p_in} in / {p_out} out)\n"
        )
        sys.stderr.flush()
        results.append(r)
    return results


def _vllm_config_snapshot() -> dict:
    """The vLLM-side config the captured markdown describes. Values
    pulled from the same env vars bin/game vllm-up honors, with
    defaults documented in docs/gpu-and-models.md. The snapshot
    reflects what the operator intends to have set; a live probe of
    the running vLLM would be more accurate but adds complexity for
    no real win (mismatches are an operator bug, not a common case)."""
    return {
        "model": config.llm_model(),
        "base_url": config.llm_base_url(),
        "gpu_memory_utilization": os.environ.get("DAYDREAM_VLLM_GMU", "0.45"),
        "max_model_len": os.environ.get("DAYDREAM_VLLM_MAX_MODEL_LEN", "8192"),
        "enforce_eager": "true",
        "kv_cache_dtype": "fp16 (auto; see docs/gpu-and-models.md)",
    }


def _compose_markdown(config_snapshot: dict, results: list[dict]) -> str:
    """Build the dated markdown: header, config block, metrics table,
    one H3 per prompt with player_input + captured narrate."""
    today = date.today().isoformat()
    model = config_snapshot["model"]
    lines: list[str] = []
    lines.append(f"# Voice samples — {today} — `{model}`")
    lines.append("")
    lines.append(
        "Rendered via `bin/game voice-samples`. Corpus: "
        "`tests/drift/voice/*.json`. Pipeline: `daydream.skills.data.execute_by_name` "
        "against `skills/rook.json` in a tmp DB (hermetic)."
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
    lines.append("| prompt | tokens in | tokens out | wall seconds |")
    lines.append("|---|---:|---:|---:|")
    for r in results:
        p_in = r["prompt_tokens"] if r["prompt_tokens"] is not None else "—"
        p_out = r["completion_tokens"] if r["completion_tokens"] is not None else "—"
        lines.append(
            f"| `{r['name']}` | {p_in} | {p_out} | {r['wall_seconds']} |"
        )
    lines.append("")

    lines.append("## Samples")
    lines.append("")
    for r in results:
        lines.append(f"### {r['name']}")
        lines.append("")
        lines.append("**Player input:**")
        lines.append("")
        lines.append(f"> {r['player_input']}")
        lines.append("")
        lines.append("**Narrate:**")
        lines.append("")
        for line in r["narrate"].splitlines() or [""]:
            lines.append(f"> {line}")
        lines.append("")
    return "\n".join(lines)


async def _main_async(out_dir: Path) -> int:
    base = config.llm_base_url()
    if not _probe_vllm_reachable(base):
        print(
            f"[voice-samples] vLLM unreachable at {base};"
            " start it via `bin/game vllm-up`",
            file=sys.stderr,
        )
        return 2

    try:
        prompts = _load_corpus()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"[voice-samples] corpus error: {e}", file=sys.stderr)
        return 3

    # Hermetic tmp DB: the capture reflects the CHECKED-IN rook.json,
    # not whatever happens to be installed on the operator's live DB.
    # We also stash DAYDREAM_DATA_DIR so admin.cmd_skill_add's
    # _require_live_db sees the tmp live.db path.
    saved_data_dir = os.environ.get("DAYDREAM_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="voice-samples-") as tmp:
        tmp_path = Path(tmp)
        os.environ["DAYDREAM_DATA_DIR"] = str(tmp_path)
        (tmp_path / f"worlds-{config.env()}").mkdir(parents=True, exist_ok=True)
        try:
            db.close_db()
            events.reset_subscribers()
            db.init_live(
                path=tmp_path / f"worlds-{config.env()}" / "live.db",
                migrations_dir=config.MIGRATIONS_DIR,
            )
            rc = admin.cmd_skill_add(ROOK_JSON)
            if rc != 0:
                print(
                    f"[voice-samples] failed to install {ROOK_JSON};"
                    " run `bin/game world skill add` manually to see the diagnostic",
                    file=sys.stderr,
                )
                return 3
            results = await _dispatch_all(prompts)
        finally:
            db.close_db()
            events.reset_subscribers()
            if saved_data_dir is None:
                os.environ.pop("DAYDREAM_DATA_DIR", None)
            else:
                os.environ["DAYDREAM_DATA_DIR"] = saved_data_dir

    snapshot = _vllm_config_snapshot()
    markdown = _compose_markdown(snapshot, results)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-{_slug(snapshot['model'])}.md"
    out_path.write_text(markdown)
    print(f"[voice-samples] wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daydream.voice_samples")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUTPUT_DIR_DEFAULT,
        help="output directory for dated markdown files "
        "(default: docs/pretty/voice-samples/)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_main_async(args.out_dir))


if __name__ == "__main__":
    sys.exit(main())
