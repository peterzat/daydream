"""Human-aesthetic-eval loop: render the anchor corpus, launch qpeek for
rating, write a dated review.md into docs/pretty/aesthetic-samples/.

Run via `bin/game test human`. Requires:
  - ComfyUI reachable (images are rendered through the real pipeline).
  - qpeek bootstrapped at external/qpeek/ (run `bin/qpeek-bootstrap`).

Design trades:
- Uses EphemeralTarget (not PersistentTarget) for rendering: we want
  one-off review artifacts that don't pile into the operator's
  generated_assets cache or create noise in drift probes.
- Renders under `~/data/daydream/images/test/human-review/<date>/` so
  review PNGs live alongside other test artifacts outside the project
  tree. The dated folder lets you compare today's review to last
  week's side-by-side on disk.
- The review.md summary IS git-tracked under `docs/pretty/aesthetic-
  samples/<date>/` — that's the backlog item `voice-and-aesthetic-
  audit-trail` realized by construction. The PNGs themselves are NOT
  committed (they're under ~/data/daydream/, outside the tree); if a
  reviewer wants to keep one, the `pretty <filename-fragment>`
  convention in CLAUDE.md covers it.

Rubric: v0 is minimal on purpose — one choice per image ('on-aesthetic
/ off-aesthetic / banned-mood') captured via qpeek's --choices. Richer
per-image ratings (a 1-5 scale, banned-mood-list, notes) are a future
refinement; qpeek supports multi-field rubrics by invoking it multiple
times per image, but that interaction cost isn't earned until someone
needs the finer signal."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from daydream import config
from daydream.gpu import arbiter
from daydream.images import cache as image_cache
from daydream.images import client as image_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AESTHETICS_DIR = PROJECT_ROOT / "tests" / "drift" / "aesthetics"
QPEEK_DIR = PROJECT_ROOT / "external" / "qpeek"
QPEEK_BIN = QPEEK_DIR / ".venv" / "bin" / "qpeek"


async def _render_corpus(out_dir: Path) -> list[Path]:
    """Render each tests/drift/aesthetics/*.json prompt to a deterministic
    path under out_dir. Holds the GPU arbiter for each render (contract
    shared with every other real-GPU path in the codebase)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for probe_file in sorted(AESTHETICS_DIR.glob("*.json")):
        probe = json.loads(probe_file.read_text())
        out_path = out_dir / f"{probe['name']}.png"
        target = image_client.EphemeralTarget(
            name=probe["name"],
            prompt=probe["prompt"],
            with_whimsy_suffix=True,
            out_path=out_path,
        )
        print(f"  rendering {probe['name']}...", file=sys.stderr, flush=True)
        async with arbiter.acquire():
            path = await image_client.generate_image(target)
        paths.append(path)
    return paths


def _run_qpeek(image_paths: list[Path]) -> list[dict]:
    """Launch qpeek in batch mode, block until the reviewer submits,
    parse the JSON array from stdout. Non-zero exit codes propagate
    (1 = abandoned, 3 = timeout, per qpeek's contract)."""
    if not QPEEK_BIN.exists():
        print(
            f"qpeek not installed at {QPEEK_BIN}.\n"
            "run: bin/qpeek-bootstrap",
            file=sys.stderr,
        )
        raise SystemExit(2)
    cmd = [
        str(QPEEK_BIN),
        "--batch",
        "--ask",
        "Aesthetic review: cozy, painterly, Spiritfarer-adjacent. Any banned moods (pixel-art, grimdark, modern-tech, urgency)?",
        "--choices",
        "on-aesthetic,off-aesthetic,banned-mood",
        *[str(p) for p in image_paths],
    ]
    print(
        f"launching qpeek on {len(image_paths)} image(s); open the URL it "
        "prints, submit, then this will continue.",
        file=sys.stderr,
        flush=True,
    )
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode == 1:
        print("qpeek: review abandoned", file=sys.stderr)
        raise SystemExit(1)
    if result.returncode == 3:
        print("qpeek: review timed out", file=sys.stderr)
        raise SystemExit(3)
    if result.returncode != 0:
        print(
            f"qpeek exited {result.returncode}\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}",
            file=sys.stderr,
        )
        raise SystemExit(result.returncode)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(
            f"qpeek output was not JSON ({e}):\n{result.stdout[:500]}",
            file=sys.stderr,
        )
        raise SystemExit(2) from e


def _write_report(
    ratings: list[dict], out_dir: Path, report_dir: Path
) -> Path:
    """Append a dated Markdown summary under docs/pretty/aesthetic-
    samples/<date>/review.md. If a review already exists for today,
    append a new run rather than overwriting (so repeated runs in the
    same day don't erase each other)."""
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "review.md"

    wf = image_client.load_workflow()
    model = wf.get(image_client.CHECKPOINT_NODE, {}).get("inputs", {}).get("ckpt_name")
    lora = wf.get(image_client.LORA_NODE, {}).get("inputs", {}).get("lora_name")
    wfh = image_cache.workflow_hash(wf)

    header_new = not report_path.exists()
    with report_path.open("a", encoding="utf-8") as f:
        if header_new:
            f.write(f"# Aesthetic review — {date.today().isoformat()}\n\n")
        f.write(f"## Run @ {_wallclock_now()}\n\n")
        f.write(f"Reviewed {len(ratings)} anchor image(s).\n\n")
        f.write(f"- model: `{model}`\n")
        f.write(f"- lora: `{lora}`\n")
        f.write(f"- workflow_hash: `{wfh}`\n")
        f.write(f"- render dir: `{out_dir}`\n\n")
        f.write("| image | choice |\n")
        f.write("|---|---|\n")
        for r in ratings:
            name = Path(r.get("file", "?")).name
            choice = r.get("choice", r.get("response", "?"))
            f.write(f"| {name} | {choice} |\n")
        f.write("\n")
    return report_path


def _wallclock_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


async def _run() -> int:
    today = date.today().isoformat()
    render_root = config.data_dir() / "images" / "test" / "human-review" / today
    report_root = PROJECT_ROOT / "docs" / "pretty" / "aesthetic-samples" / today

    print(f"human-eval: rendering anchor corpus to {render_root}", file=sys.stderr)
    image_paths = await _render_corpus(render_root)

    ratings = _run_qpeek(image_paths)
    report_path = _write_report(ratings, render_root, report_root)
    print(f"wrote review: {report_path}", flush=True)
    # Summary line so the operator sees the aggregate at a glance.
    counts: dict[str, int] = {}
    for r in ratings:
        key = r.get("choice", r.get("response", "?"))
        counts[key] = counts.get(key, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"aggregate: {summary}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point invoked by daydream.testing.__main__ when tier='human'.
    argv is accepted for interface parity but not currently consumed."""
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
