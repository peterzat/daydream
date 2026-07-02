# TESTING.md — daydream

## Test Strategy Review — 2026-04-23

**Summary:** Test architecture just shipped in commits C1-C5 (`4d606e6`..`844884e`). Three-tier dispatcher (`bin/game test short|medium|long|ci|human`) with 156/211/220 tests respectively; short in 2.06s, medium in 2.65s — well under budget. Drift loop is fully implemented with in-tree golden baselines, a perceptual-hash image corpus, a JSON-adherence LLM corpus, and an arbiter-held tripwire for real-GPU tests. The strategy is appropriate and proportionate for a single-contributor project at v1.

**Test infrastructure found:**
- Framework: pytest 8+ with pytest-asyncio (auto mode)
- Tier markers: `tier_short`, `tier_medium`, `tier_long` (budgets in pyproject.toml markers)
- Liveness gates: `requires_vllm`, `requires_comfyui` (session-cached 2s HTTP probes)
- Dispatcher: `daydream.testing.__main__` (`bin/game test <tier>`) with `--target=local|staging|prod_verify`
- Drift framework: `tests/drift/conftest.py` (dHash, baseline assert helpers, arbiter-held tripwire)
- Baselines: `tests/baselines/*.golden.json` (in-tree, PR-reviewable) + `*.latest.json` (gitignored)
- Corpora: 5 LLM prompts (`tests/drift/prompts/`) + 4 image aesthetics (`tests/drift/aesthetics/`; cozy_room / forest_path / meadow_dusk / forge)
- Fixtures: tmp_path DB isolation, HOME redirected to tmp, autouse arbiter/in-flight resets, TestClient-bypass of AccessMiddleware via `DAYDREAM_ACCESS=public`
- Human-eval: `daydream.testing.human_eval` → qpeek rubric loop (commit C4)
- Coverage tools: none configured (deliberate — TESTING.md explicitly rejects coverage-for-coverage)
- CI system: none configured; single-contributor project (deferred per `## Future refinements`)
- Pre-commit/pre-push hooks: none installed

### Findings

[NOTE] Automatic test execution — No pre-commit hook, no pre-push hook, no CI.
  Current state: `.git/hooks/` holds only the default `.sample` files. No `.github/workflows/`, no `.pre-commit-config.yaml`. Tests run only when an operator types `bin/game test <tier>`. TESTING.md documents this gap explicitly under `## Future refinements` ("CI pipeline when a second contributor lands") and calls short "pre-commit, every save" as intent, not as an enforced gate. Proportional for a single-contributor box where every change comes through Claude Code sessions that already run tests, but worth revisiting when a second contributor lands or before the first non-local target goes live.
  Recommendation: When adding a second contributor or wiring staging, install a pre-push hook invoking `bin/game test medium` at minimum. The test suite is fast enough (under 3s) that a pre-commit hook running `bin/game test short` is also viable and would catch the cheap class of breakage before it enters the working tree. Both can be added as one-line scripts under `.git/hooks/` and optionally shipped via a `bin/install-hooks` helper so fresh clones pick them up.

[NOTE] SPEC.md — 0/7 acceptance criteria have tests yet for the active spec (`multi-room navigation`, 2026-04-23).
  Current state: The current SPEC.md is open (criteria_met: 0). No `test_go_*` in `tests/test_skills.py`; no navigation flow test in `tests/test_ws.py`; no new assertion in `tests/test_db.py` for the pending `migrations/002_multi_room.sql`. This is the expected state immediately after `/spec consume` — the spec has been adopted but implementation plus paired tests haven't landed. Flagging so the next implementer knows the test obligations are already itemized in the spec's criterion 7 and should ship in the same increments as the code.
  Recommendation: No change to test infrastructure. When implementing, follow the zat.env coding rule: write tests in the same increment as the code they cover. The spec's criterion 7 enumerates exactly what's needed (`go` happy-path, unknown-direction rejection, case-insensitivity, WS navigation flow), all GPU/network-free via existing mocks. No new infrastructure required.

[NOTE] `tier_medium` suite at ~3s leaves substantial headroom against its 90s documented budget.
  Current state: `bin/game test medium` runs 211 tests in 2.65s — about 3% of the 90s target. The spare budget is healthy for the pending spec work (new WS integration test, new migration-effect assertions), and is deliberate: TESTING.md's tier contracts are "per-test budgets," not aggregate, and the aggregate has room to grow by 30x before hitting the pre-push pain threshold.
  Recommendation: None. Mentioned only so the reviewer doesn't miss that the current figure isn't an accident — it's room left for the next several quarters of feature work without needing to re-tier.

### Status of Prior Recommendations

No prior dated review entry existed. The existing durable-doc content of this file (the philosophy + tier contract, preserved below) was written by the test-architecture commit series (C1-C5) and is the authoritative reference this review validates against.

---
*Prior review (none): this is the first dated test-strategy review. The rest of this file is the durable test-architecture contract introduced by commits 4d606e6..844884e; treat it as the spec this review measured against.*

<!-- TESTING_META: {"date":"2026-04-23","commit":"844884e","block":0,"warn":0,"note":3} -->

---

# Durable test-architecture contract

Durable philosophy + concrete contract for the test architecture. Read this before adding a test, changing how tests are run, or bumping a model / LoRA / workflow. A fresh Claude session should be able to cold-open this file and execute the loop without reading anything else.

## Cold-open

Right now, before reading further, run:

```sh
bin/game test short
```

Expected: under 10 seconds, exits 0, several hundred tests pass (~454 in ~4 s at HEAD 8c755b0). The marker expression, not the exact count, is the contract — the count grows with features. If not, the venv is broken or the repo is in a weird state — fix that first. The rest of this document assumes you have a green `short` tier as a starting point.

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

| Dimension     | What it asserts                                                     | Examples                                                                  |
|---------------|---------------------------------------------------------------------|---------------------------------------------------------------------------|
| Correctness   | Pass/fail against concrete behavior.                                | Most current pytest tests.                                                |
| Drift         | Current measurement within tolerance of a committed baseline.       | `tests/drift/*.py` + `tests/baselines/`; `tests/test_voice_baseline.py`.  |
| Human eval    | Reviewer rates artifacts against a rubric; result is a durable log. | `bin/game test human` via qpeek; `bin/game voice-samples`.                |

Correctness is binary. Drift is statistical-ish (perceptual hash, JSON schema, latency window, pairwise-distinct openers across a corpus). Human-eval is subjective-but-logged. Each tier may run any combination of the three.

This project tilts deliberately toward **proxy** verification (a measurable number that stands in for the goal) over **critic** verification (a model reading the output). Proxies catch what the generator can't see — the voice-bench tic regression, the fp8-KV format-adherence breakage, the aesthetic dHash drift. The critics are supplements, not substitutes, and NONE of them use a cloud API: the design-time aesthetic critic is the Claude Code agent itself (after `bin/game review` renders the anchors, the agent Reads each PNG and grades it against `WHIMSY.md`, no key), and the human critic is `qpeek` (`bin/game test human`) or an in-game look. The batched-review harness `bin/game review` rolls the proxies' renders + the voice samples + the one browser-checklist glance into a single offline `index.html`, so a qualitative review is one glance instead of a live reset per check.

## Tier contracts in detail

### `short` — the pre-commit gate

- Marker expression: `tier_short`
- Test count: ~407 (grows with features; the marker expression, not the count, is the contract). Wall-clock: ~3 s.
- What's in it: every test that doesn't boot `daydream.server.app`, spawn a subprocess, or do heavy filesystem I/O. Includes the object/verb/parser/generative core (`tests/test_objects.py`, `test_verbs.py`, `test_parser.py`, `test_generative.py`, `test_effects.py` — all DB-on-tmp + mocked-LLM), plus the constants-drift probes under `tests/drift/test_drift_constants.py` (cheap; they just read files), the WHIMSY suffix probe, the voice-baseline tic-regression probe (`tests/test_voice_baseline.py`; parses captured markdown, asserts pairwise-distinct openers), and the memory-ranking drift probe (`tests/drift/test_memory_ranking.py`; tmp_path SQLite + mocked embeddings, fingerprints the salience formula's ordering and per-item scores). The 2026-06-30 playtest turn added two authored-prompt static scans here: the second-person player-narration scan (`tests/test_second_person.py`, SPEC C9 — asserts no third-person "the visitor" framing in the affordance prompts) and the per-NPC voice-constraint presence scan (`tests/test_npc_voice.py`, SPEC C11).
- What it catches: broken imports, wrong migration, object-access / verb-dispatch / parser-grounding regressions, effect-allowlist gaps, cache-key math bug, WHIMSY.md drift, vllm-version doc drift, prompt-template tic regressions on the captured voice corpus, salience-formula drift in NPC memory, third-person leakage into player-action prompts, missing per-NPC voice constraints.
- When to run: every commit, every save if you've got a file-watcher. `bin/install-hooks` wires this to `.git/hooks/pre-commit` so it fires automatically.

### `medium` — the pre-push gate

- Marker expression: `tier_short or tier_medium`
- Test count: ~648. Wall-clock: ~9 s.
- What's in it: everything from `short` plus tests that boot `TestClient` (auth, frontend, ws + the command-frame / scene-object snapshot tests, ws_images, ws_rook, ws_iris, ws_swap, the WS cross-origin CSRF guard `test_csrf_middleware.py`), spawn `bin/game` as a subprocess, round-trip archives, or exercise the per-world DB schema (memories included) and the keyless object-schema world authoring (`test_world_load.py`, including the committed `worlds/bunny.json` reset world end to end). The scripted end-to-end gameplay-scenario test (`tests/test_scenario.py`, SPEC 2026-06-30 C14) lives here: one story through connect → picker → claim → look → take → go-to-place → talk → spawn → examine → inventory, mocked-LLM. GPU calls are still mocked; the BGE-small embedder is mocked at `daydream.memories._embed`.
- What it catches: WebSocket protocol regressions (input + command frames), auth flow breaks, admin CLI breaks, bash dispatcher breaks, NPC dialogue path regressions, world-load / authoring regressions, memory capture/retrieve/scoping breaks, end-to-end playable-flow regressions (the picker-first entry + scene + inventory path the scenario test walks).
- When to run: before every push, after finishing a feature. `bin/install-hooks` wires this to `.git/hooks/pre-push` so it fires automatically.

### `long` — the drift + end-to-end gate

- Marker expression: `tier_short or tier_medium or tier_long`
- Test count: ~663 (~648 + the real-engine drift probes, including the 6-case parser-grounding probe). Wall-clock: ~30 s with vLLM + ComfyUI up.
- What's in it: everything from `medium` plus the `tests/drift/` probes. Real LLM calls through vLLM. Real image renders through ComfyUI. The arbiter smoke alternates the two under a 90-second budget. The parser-grounding probe (`tests/drift/test_parser_grounding.py`) grounds real Qwen output to in-scope ids across a command corpus.
- What it catches: fp8-KV-style format-adherence regressions, parser verb/dobj grounding drift, LoRA-swap aesthetic drift, image-gen latency regressions, arbiter serialization bugs.
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

The voice-bench audit-trail harness (`bin/game voice-samples`) is a sibling to `human`: same "render a corpus, eyeball-diff against the prior baseline" pattern but for narration prose. Output lands at `docs/pretty/voice-samples/<date>-<model_slug>.md`. Re-run after any vLLM model / flag swap; the tic-regression probe (`tests/test_voice_baseline.py`, `tier_short`) parses the committed markdown and asserts pairwise-distinct openers across the 5 corpus prompts so a future capture that regresses the 04-24 prompt-template tic fails the gate mechanically.

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
| `tests/drift/test_llm_json_adherence.py` | JSON schema keys + latency window per prompt.                             | `tests/drift/prompts/*.json` (5 probes)    |
| `tests/drift/test_parser_grounding.py`   | Real Qwen grounds free text to the right closed verb + in-scope dobj id.   | 6-case command corpus (in-file)            |
| `tests/drift/test_image_perceptual.py`   | dHash + resolution + (model, lora, workflow_hash). Hamming tolerance.     | `tests/drift/aesthetics/*.json` (4 probes; +`forge`) |
| `tests/drift/test_arbiter_smoke.py`      | 5 alternating LLM + image calls; per-call + aggregate budgets.            | reuses prompts/                            |
| `tests/drift/test_growth_compose.py`     | Shipped-seed growth composition against real vLLM: validity / refusal / phrase-woven / exemplar-distinctness / object count, + latency window. The mitigation-ladder gate — ratifying its golden records the rung decision (SPEC 2026-07-02). | 3-phrase vision corpus (in-file)           |
| `tests/drift/test_drift_constants.py` (`tier_short`) | WHIMSY_PROMPT_SUFFIX vs WHIMSY.md; vllm version; GPU fraction; model id. | CLAUDE.md + bin/ scripts        |
| `tests/test_voice_baseline.py` (`tier_short`) | Pairwise-distinct narrate openers; glob-derived params classified by a `baseline-class` marker (tracked / regression-demo / documented-failure). | `docs/pretty/voice-samples/*.md` |
| `tests/drift/test_memory_ranking.py` (`tier_short`) | Salience-formula ordering + per-item scores for a fixed (sim, age) corpus; pins `cosine * exp(-age/24h)` math + `DECAY_HOURS` constant. | 5-row in-memory corpus + mocked embeddings |

The dHash is a pure-Pillow difference hash — no numpy or scipy dep. For drift *detection* (not content ID) it is plenty sensitive: a material aesthetic shift moves many bits, not 1-2.

The voice-baseline probe is unusual: it runs as `tier_short` (no GPU, just markdown parsing), and the "baseline" it gates against is the committed voice-bench markdown itself rather than a separate `.golden.json`. The probe's parametrized fixture covers both the pre-fix (regression-detection demo) and post-fix substrate so the regression catch is provable, not just claimed.

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

The NPC memory subsystem (`daydream/memories.py`) deliberately does NOT take the arbiter — embedding runs on CPU via BGE-small and capture/retrieve must never serialize against in-flight LLM/image-gen. Tests opt into the memory path via `monkeypatch.setenv("DAYDREAM_MEMORY_ENABLED", "1")` and mock `daydream.memories._embed` to inject deterministic vectors; the conftest disables memory by default so the suite never loads the real embedder model.

## What NOT to test

Per zat.env: "prompts must earn their keep" and "false positives erode trust faster than false negatives." The same applies to tests.

- **Coverage-for-coverage.** If a test only exists to hit a line number, delete it.
- **Re-asserting the mock.** If a test only verifies that a mocked function was called, it's testing the mock, not the code.
- **Impl detail churn.** Pinning internal state (dict ordering, log wording, tuple shape) without a SPEC claim invites churn without signal.
- **Multi-provider fan-out for future flexibility.** daydream calls vLLM via litellm. We don't need tests against OpenAI / Anthropic providers until we actually run against them.
- **Baselines for noisy single-shot measurements.** One-shot latency is too jittery to lock into a golden. Record it, but don't gate on it until you have trend data.
- **Critic-only gates without a proxy.** A "does the LLM think this output is good" test is a critic; without a proxy alongside (latency, schema, opener-distinctness, dHash) the gate has shared blind spots with the generator and erodes signal over time.

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

So `bin/game test long` with both engines down still runs ~648 tests (short + medium) and skips the ~15 engine-gated probes with a clear "engine unreachable" reason.

## Glossary

- **Probe.** A test that measures something against a committed baseline, typically under `tests/drift/`. Distinct from a correctness test.
- **Anchor corpus.** The small set of inputs a drift probe runs against. Lives in `tests/drift/prompts/` (LLM), `tests/drift/aesthetics/` (image), and `tests/drift/voice/` (narration). Expanding the corpus is a positive act; the probes scale with it automatically.
- **Gold baseline / `.golden.json`.** The git-committed reference values for a probe. Updated only via explicit `mv .latest .golden` + commit.
- **Latest observation / `.latest.json`.** Gitignored; written on every probe run whether pass or fail. Visible in the working tree only.
- **Tier.** The duration-tier marker (`tier_short`, `tier_medium`, `tier_long`). Contract: individual tests stay within the tier's per-test budget.
- **Target.** The operational environment (`local`, `staging`, `prod_verify`). Today only `local` is wired; others skip cleanly.
- **Arbiter.** The in-process GPU lock at `daydream/gpu/arbiter.py`. Every real-GPU call holds it. CPU-only paths (memory embedding) do NOT take it.
- **Drift loop.** The cycle of: run probe → produce `.latest.json` → review → ratify via `mv .latest .golden` → commit. The commit is the ratification.
- **Voice-bench audit trail.** Dated markdown captures of the 5-prompt corpus rendered by the current `DAYDREAM_LLM_MODEL` (via `bin/game voice-samples`), committed under `docs/pretty/voice-samples/`. Read by `tests/test_voice_baseline.py` for tic-regression detection.
- **Proxy vs critic.** A proxy is a measurable number that stands in for the goal (latency window, perceptual-hash tolerance, JSON schema adherence, opener-distinctness). A critic is another LLM reading output. Proxies catch what the generator can't see; critics share the generator's blind spots. Daydream prefers proxies; critics are cost-gated supplements.

## Future refinements

Tracked in `BACKLOG.md`. Worth naming the shape:

- Per-call LLM latency windows tighten as we collect multi-run trends (`latency-regression-corpus`).
- Aesthetic critic: DONE, and agent-driven — the Claude Code agent Reads each render and grades it against `WHIMSY.md`, no API key. An earlier cost-gated litellm version was removed 2026-07-01 (`claude-vision-quality-gate`).
- Staging / prod_verify probes when those environments exist (`staging-probes`, `prod-verify-probes`).
- CI pipeline when a second contributor lands (`ci-pipeline`).
- mypy gate once the typing effort is worth it (`mypy-gate`).
- Drift alarms that auto-open a Claude Code session when a baseline diff lands on main (`drift-alarms`).
- Voice-baseline harness generalization so a new model adds to the regression-detection parametrization without code changes (`voice-baseline-add-model-helper`).
- A perceptual-hash drift anchor for the authored `r-forge` render so "the forge looks like a forge" (SPEC 2026-06-30 C12) becomes a ratify-once-then-mechanical proxy rather than an eyeball-only check (`forge-render-drift-anchor`).
- A tier_short guard pinning the present-player drift cadence to a minutes-scale value so it can't silently revert to the 30-min occupancy-hiding cadence the witnessed-drift criterion fixed (`present-player-drift-cadence-guard`).
