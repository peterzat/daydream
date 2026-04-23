# TESTING.md — daydream

Durable philosophy + concrete contract for the test architecture. Read this before adding a test, changing how tests are run, or bumping a model / LoRA / workflow. A fresh Claude session should be able to cold-open this file and execute the loop without reading anything else.

## Cold-open

Right now, before reading further, run:

```sh
bin/game test short
```

Expected: under 10 seconds, exits 0, ~156 tests pass. If not, the venv is broken or the repo is in a weird state — fix that first. The rest of this document assumes you have a green `short` tier as a starting point.

## The single entry point

```
bin/game test <tier> [--target=local|staging|prod_verify] [pytest flags...]

  short   unit / fast              ~<10s     pre-commit, every save
  medium  integration              ~<90s     pre-push, after a feature
  long    real-GPU drift + E2E     ~<15min   on demand, pre-release
  ci      semantic alias for long; one command "run all machine-verifiable"
  human   aesthetic rubric via qpeek; produces a dated chronology
```

`bin/game test` is a thin wrapper over `python -m daydream.testing` (mirrors `bin/game world` → `daydream.admin`). Unknown pytest flags after the tier name pass through, so `bin/game test short -q -k cache` becomes `pytest -m tier_short -q -k cache`.

Bare `pytest` also still runs everything — backward compat is preserved.

## Three axes

The architecture cuts the test problem along three orthogonal axes. Every test sits somewhere on each.

### 1. Duration tier (pytest markers)

| Marker         | Budget (per test) | What earns the marker                                                        |
|----------------|-------------------|------------------------------------------------------------------------------|
| `tier_short`   | ≤ 2 s             | Unit; no app boot, no subprocess, no GPU, no network. Mocked everything.    |
| `tier_medium`  | ≤ 10 s            | Integration; TestClient boot, subprocess, or heavy filesystem I/O. GPU mocked. |
| `tier_long`    | ≤ 120 s           | Real engines (vLLM / ComfyUI). Drift probes. End-to-end through the pipeline. |

The **tier budget is the contract**, not a suggestion: if a `tier_short` test regularly exceeds 2 s, demote it to `tier_medium` or split it. The cheap pre-commit tier has to stay cheap or developers bypass it.

### 2. Operational target (env var)

| `DAYDREAM_TARGET`  | What it means                                                      | Wired?          |
|--------------------|--------------------------------------------------------------------|-----------------|
| `local` (default)  | Full test behavior against a tmp data dir + real DB/stubbed GPU.   | yes             |
| `staging`          | Probes against a deployed staging env; read/write is write-safe.   | scaffolded only |
| `prod_verify`      | Read-only probes against production.                               | scaffolded only |

When `DAYDREAM_TARGET != local`, `tier_medium` and `tier_long` tests **skip cleanly** with a clear "not yet wired" reason. `tier_short` is target-agnostic. The knob is in place so v0 can establish the shape; real staging / prod probes arrive when those environments do.

### 3. Quality dimension (test style)

| Dimension     | What it asserts                                                     | Examples                                  |
|---------------|---------------------------------------------------------------------|-------------------------------------------|
| Correctness   | Pass/fail against concrete behavior.                                | All current pytest tests.                 |
| Drift         | Current measurement within tolerance of a committed baseline.       | `tests/drift/*.py` + `tests/baselines/`.  |
| Human eval    | Reviewer rates artifacts against a rubric; result is a durable log. | `bin/game test human` via qpeek.          |

Correctness is binary. Drift is statistical-ish. Human-eval is subjective-but-logged. Each tier may run any combination of the three.

## Tier contracts in detail

### `short` — the pre-commit gate

- Marker expression: `tier_short`
- Test count today: ~156. Duration: ~2 s.
- What's in it: every test that doesn't boot `daydream.server.app`, spawn a subprocess, or do heavy filesystem I/O. Also the constants-drift probes under `tests/drift/test_drift_constants.py` (cheap; they just read files).
- What it catches: broken imports, wrong migration, skill-interpreter regression, cache-key math bug, WHIMSY.md drift, vllm-version doc drift.
- When to run: every commit, every save if you've got a file-watcher.

### `medium` — the pre-push gate

- Marker expression: `tier_short or tier_medium`
- Test count today: ~211. Duration: ~3 s.
- What's in it: everything from `short` plus tests that boot `TestClient` (auth, frontend, ws, ws_images), spawn `bin/game` as a subprocess, or round-trip archives. GPU calls are still mocked.
- What it catches: WebSocket protocol regressions, auth flow breaks, admin CLI breaks, bash dispatcher breaks.
- When to run: before every push, after finishing a feature.

### `long` — the drift + end-to-end gate

- Marker expression: `tier_short or tier_medium or tier_long`
- Test count today: ~220 (211 + 9 drift probes). Duration: ~30 s with vLLM + ComfyUI up.
- What's in it: everything from `medium` plus the `tests/drift/` probes. Real LLM calls through vLLM. Real image renders through ComfyUI. The arbiter smoke alternates the two under a 90-second budget.
- What it catches: fp8-KV-style format-adherence regressions, LoRA-swap aesthetic drift, image-gen latency regressions, arbiter serialization bugs.
- When to run: before a release, after swapping a model / LoRA / workflow, after any arbiter change.
- Requires: `bin/game vllm-up && bin/game comfyui-up`. Engine-gated tests (`requires_vllm`, `requires_comfyui` markers) skip cleanly if engines are down — the rest of the tier still runs.

### `ci` — the "run it all" alias

Semantic equivalent of `long` today. Kept distinct so CI invocations are a stable name if long's default output format ever diverges (structured exit codes, compact tracebacks, etc.).

### `human` — the aesthetic rubric loop

- Dispatches to `daydream.testing.human_eval.main()`, not pytest.
- What it does: renders `tests/drift/aesthetics/*.json` prompts via `EphemeralTarget` under `arbiter.acquire()`, launches qpeek in batch mode, captures the per-image choice (`on-aesthetic | off-aesthetic | banned-mood`), appends a dated Markdown summary to `docs/pretty/aesthetic-samples/<date>/review.md`.
- Requires: ComfyUI up, qpeek bootstrapped (`bin/qpeek-bootstrap`).
- When to run: after a LoRA / checkpoint / workflow swap, monthly-ish as a vibe-check even without a change, whenever you feel the output has subtly drifted.
- Blocks on human interaction. Don't run this in CI.

## The drift loop

A drift probe runs the real code path, measures something, and compares to a **git-committed `tests/baselines/<probe_id>.golden.json`**. A divergence fails the test with a diff-friendly message; the captured observation lands at `tests/baselines/<probe_id>.latest.json` (gitignored) for review.

### State transitions

1. **No baseline.** First run of a new probe. Test fails with "baseline missing for probe X. captured at tests/baselines/X.latest.json. Ratify with `cp ... .golden.json`." Operator reviews the observed values, decides they're good, moves `.latest` → `.golden`, commits.
2. **Baseline matches.** Test passes. `.latest.json` is refreshed (so trend is visible over time).
3. **Baseline diverges.** Test fails with a diff listing each mismatched field. Operator either:
   - Fixes the regression (revert the offending commit, etc.), or
   - Decides the new values are the new truth (LoRA swap, model bump) and ratifies by moving `.latest` → `.golden` + commits.

**The commit IS the ratification event.** Every baseline update is a PR-reviewable diff. That's the whole point — drift updates don't happen silently on one developer's box.

### Drift probes today

| Probe file                               | What it fingerprints                                                      | Corpus                                     |
|------------------------------------------|---------------------------------------------------------------------------|--------------------------------------------|
| `test_llm_json_adherence.py`             | JSON schema keys + latency window per prompt.                             | `tests/drift/prompts/*.json` (5 probes)    |
| `test_image_perceptual.py`               | dHash + resolution + (model, lora, workflow_hash). Hamming tolerance.     | `tests/drift/aesthetics/*.json` (3 probes) |
| `test_arbiter_smoke.py`                  | 5 alternating LLM + image calls; per-call + aggregate budgets.            | reuses prompts/                            |
| `test_drift_constants.py` (`tier_short`) | WHIMSY_PROMPT_SUFFIX vs WHIMSY.md; vllm version; GPU fraction; model id.  | CLAUDE.md + bin/ scripts                   |

The dHash is a pure-Pillow difference hash — no numpy or scipy dep. For drift *detection* (not content ID) it is plenty sensitive: a material aesthetic shift moves many bits, not 1-2.

### Why baselines live in-tree

- In-tree `.golden.json` makes the drift diff a reviewable commit. Out-of-tree would let drift accumulate silently on one box.
- `.latest.json` is gitignored so repeated runs don't spam the working tree.
- pHash + metadata is tiny JSON; PNG bytes stay under `~/data/daydream/` (not in git). If a reference PNG is worth keeping, use the `pretty <filename-fragment>` convention from CLAUDE.md and it lands in `docs/pretty/`.

## Adding a new test

### Decision tree

Walk the tree top-to-bottom; first match wins.

1. **Does this test need a running vLLM or ComfyUI?**
   - Yes → `tier_long` + `requires_vllm` and/or `requires_comfyui`. Consider: is this a drift probe? If yes, put it under `tests/drift/` and write a baseline.
2. **Does this test boot `daydream.server.app` (TestClient / AsyncClient), spawn a subprocess, or do heavy filesystem I/O (tarfile, archive round-trip)?**
   - Yes → `tier_medium`.
3. **Otherwise** → `tier_short`.

### Does it need a baseline?

- "Did this value regress vs the last good run?" questions want a drift probe with a baseline (`tests/drift/`).
- "Is this behavior correct per the SPEC?" questions want a regular assert (no baseline).
- Don't make it a drift probe just because it's expensive. A slow assertion is still a correctness test if it has a deterministic pass/fail.

### Pattern

```python
# tests/test_something.py
import pytest

from daydream.something import thing

pytestmark = pytest.mark.tier_short   # or tier_medium / tier_long


def test_thing_returns_the_right_value():
    assert thing() == "expected"
```

Module-level `pytestmark` tags every test in the file. Per-test markers (via `@pytest.mark.X`) compose fine.

## GPU hygiene

Every test that fires a real LLM or image-gen call **must hold the arbiter lock** for the duration of that call. LLM is automatic — `daydream.llm.client.acompletion_json` acquires internally. Image-gen is **caller-held**: wrap it in `async with arbiter.acquire():`.

```python
from daydream.gpu import arbiter
from daydream.images import client as image_client

async with arbiter.acquire():
    path = await image_client.generate_image(target)
```

For `tier_long` tests, the `enforce_arbiter_held` fixture in `tests/drift/conftest.py` is armed: any real-GPU call without the arbiter held fails the test immediately with a clear reason. Turns the policy into a mechanical tripwire.

Why this matters: the 20 GB VRAM ceiling. vLLM and SDXL can coexist resident, but can't infer simultaneously. The arbiter is the only thing keeping us out of OOM-land.

## What NOT to test

Per zat.env: "prompts must earn their keep" and "false positives erode trust faster than false negatives." The same applies to tests.

- **Coverage-for-coverage.** If a test only exists to hit a line number, delete it.
- **Re-asserting the mock.** If a test only verifies that a mocked function was called, it's testing the mock, not the code.
- **Impl detail churn.** Pinning internal state (dict ordering, log wording, tuple shape) without a SPEC claim invites churn without signal.
- **Multi-provider fan-out for future flexibility.** daydream calls vLLM via litellm. We don't need tests against OpenAI / Anthropic providers until we actually run against them.
- **Baselines for noisy single-shot measurements.** One-shot latency is too jittery to lock into a golden. Record it, but don't gate on it until you have trend data.

## Operational posture

`DAYDREAM_TARGET` controls which tests apply at which layer:

|                | `target=local` | `target=staging`     | `target=prod_verify` |
|----------------|----------------|----------------------|----------------------|
| `tier_short`   | runs           | runs                 | runs                 |
| `tier_medium`  | runs           | skip (not yet wired) | skip (not yet wired) |
| `tier_long`    | runs           | skip (not yet wired) | skip (not yet wired) |

Liveness gates are orthogonal:

- `requires_vllm` marker: test skips if `{DAYDREAM_LLM_BASE_URL}/models` is unreachable (2 s timeout, one probe per session).
- `requires_comfyui` marker: test skips if `{DAYDREAM_COMFYUI_BASE_URL}/system_stats` is unreachable.

So `bin/game test long` with both engines down still runs ~211 tests (short + medium) and skips the 9 drift probes with a clear "engine unreachable" reason.

## Glossary

- **Probe.** A test that measures something against a committed baseline, typically under `tests/drift/`. Distinct from a correctness test.
- **Anchor corpus.** The small set of inputs a drift probe runs against. Lives in `tests/drift/prompts/` (LLM) and `tests/drift/aesthetics/` (image). Expanding the corpus is a positive act; the probes scale with it automatically.
- **Gold baseline / `.golden.json`.** The git-committed reference values for a probe. Updated only via explicit `mv .latest .golden` + commit.
- **Latest observation / `.latest.json`.** Gitignored; written on every probe run whether pass or fail. Visible in the working tree only.
- **Tier.** The duration-tier marker (`tier_short`, `tier_medium`, `tier_long`). Contract: individual tests stay within the tier's per-test budget.
- **Target.** The operational environment (`local`, `staging`, `prod_verify`). Today only `local` is wired; others skip cleanly.
- **Arbiter.** The in-process GPU lock at `daydream/gpu/arbiter.py`. Every real-GPU call holds it.
- **Drift loop.** The cycle of: run probe → produce `.latest.json` → review → ratify via `mv .latest .golden` → commit. The commit is the ratification.

## Future refinements

Tracked in `BACKLOG.md` under the `test-architecture-*` family. Worth naming the shape:

- Per-call LLM latency windows tighten as we collect multi-run trends.
- Claude-vision aesthetic gate (Opus 4.7 vision rates each rendered image; asserts score ≥ threshold).
- Staging / prod_verify probes when those environments exist.
- CI pipeline when a second contributor lands.
- mypy gate once the typing effort is worth it.
- Drift alarms that auto-open a Claude Code session when a baseline diff lands on main.
