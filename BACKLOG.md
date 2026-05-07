# Backlog

Durable register of considered proposals that were deferred, scoped out, or
rejected. Read before drafting a new SPEC.md; swept at turn close. Long-form
context for every entry below lives in `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md`.

## v1: cozy single-player loop

### toon-slot-management
- **One-line description:** Add the 5-slot toon picker UI, slot CRUD endpoints in `daydream/api/`, and `kicked_at` promotion that turns a kicked toon into an NPC carrying its inventory and history.
- **Why deferred:** v0 has one hardcoded toon; slot management only matters once a second human (or NPC) wants to occupy the world.
- **Revisit criteria:** v0 persistence verified; second human player wants in, or first NPC needs to be authored.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### npc-memory-retrieval
- **One-line description:** Add `memories` SQLite table + LanceDB vector store at `daydream/memories.py`; embed events near NPCs with sentence-transformers BGE-small on CPU; NPC dialogue retrieves top-K by salience+recency before generating.
- **Why deferred:** Requires multiple NPCs and a stable LLM dialogue path; v1 milestone after drift lands.
- **Revisit criteria:** npc-drift-loop landed; first NPC dialogue path works without memory and feels too goldfish.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### world-bootstrap-opus
- **One-line description:** Add `bin/game world bootstrap NAME --aesthetic "..."` that calls Anthropic Opus 4.7 via `litellm.acompletion(model="anthropic/claude-opus-4-7", ...)` from `daydream/llm/bootstrap.py` to author 5 rooms + 4 toons + initial seeds + 2 starter data skills into a fresh `.db` under `~/data/daydream/worlds-dev/`.
- **Why deferred:** v0 ships hardcoded one-room migration. Bootstrap is the v1 way to author varied worlds quickly without writing SQL by hand.
- **Revisit criteria:** multi-room-navigation and toon-slot-management landed; ready to populate a real "bunny world."
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### snapshot-restore-commands
- **One-line description:** Add `bin/game world snapshot NAME` (cp live db to `~/data/daydream/snapshots/{world}-{ts}.db`) — fast DB-only point-in-time snapshots for hot-swap, distinct from the existing `bin/game world archive/restore` which bundles DB + per-world cache dir into a full tarball. The snapshot flow is what `world-hot-swap` (below) needs: atomic rename of live → snapshot, reopen pool, broadcast `world_changed`. Archive/restore is for shelving a world off the box entirely.
- **Why deferred:** v0 has no irreplaceable state; first interesting bootstrap is the moment a snapshot becomes worth taking. `archive/restore` is already sufficient for the "ship a world to a friend" use case.
- **Revisit criteria:** First Opus-bootstrapped world worth preserving via fast hot-swap (as opposed to a full archive).
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

## v2: shared world + skill authoring

### world-hot-swap
- **One-line description:** `bin/game world swap NAME` performs the SHELVE broadcast → drain (~200 ms) → `PRAGMA wal_checkpoint(TRUNCATE)` → close pool → atomic `rename` of `~/data/daydream/worlds-{env}/live` symlink → reopen pool → broadcast `world_changed`. Clients show "the dream shifts..." and reconnect within ~1 s.
- **Why deferred:** v0 has no symlink and only one db. Hot-swap is meaningful once snapshot-restore-commands and world-bootstrap-opus produce multiple shelved worlds.
- **Revisit criteria:** Two or more bootstrapped worlds exist and admin wants to switch live without restart.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### multi-env-layout
- **One-line description:** Add `--env dev|preview|prod` flag in `bin/game` that pins separate ports (8080/8081/8082) and separate `~/data/daydream/worlds-{env}/` dirs; vLLM and ComfyUI shared across envs (one warm process serves all three FastAPI processes).
- **Why deferred:** v0 only has dev. Multi-env needs world-hot-swap + snapshot to be useful (otherwise three identical envs is just three ports).
- **Revisit criteria:** At least one stable "preview" config worth running alongside dev for stakeholder review.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### multi-user-shared-world
- **One-line description:** Single asyncio task drains event log to disk per world (single-writer pattern); websocket fanout to all sockets in a room from `daydream/api/ws.py`; per-toon human-NPC handoff with grace period and reconnect tokens; load-test harness (10 bots, 10 min) with smoke metrics in `bin/game status`; nightly snapshot cron retaining 14 days under `~/data/daydream/snapshots/`.
- **Why deferred:** v0 is single-user. Concurrency design needs careful write-contention testing and benchmarks before claiming readiness.
- **Revisit criteria:** Two or more humans want to share a session, or before claiming the v2 "shared dream" milestone done.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### skills-authoring-and-security
- **One-line description:** Web UI at `daydream/api/` for admin to edit `prompt_template`, dry-run against a sandbox, and publish; full six-layer security pipeline (Jinja2 SandboxedEnvironment, role separation with `<player_input>` tags, jsonschema validation, effect allowlist enforced in `daydream/skills/effects.py`, content-safety classifier in `daydream/llm/safety.py`, `audit` table + `bin/game world undo --invocation N`).
- **Why deferred:** v1 ships data-skills-cli (admin authors via JSON files); the web UI + full security pipeline land in v2 once a real authoring rhythm exists and the threat model is exercised.
- **Revisit criteria:** Admin uses JSON-CLI authoring frequently enough that a UI pays off; or first time a data skill produces an unwanted effect that needs to be rolled back.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### litellm-proxy-fallbacks
- **One-line description:** Stand up the LiteLLM proxy as a separate process; configure Qwen → Claude fallback chain on local outage; add cost tracking and per-model rate limits in proxy config rather than game code.
- **Why deferred:** v0/v1 use `litellm` as a Python library only — no extra process, no extra port. The proxy adds operational overhead that pays for itself only once a third backend or an automatic-fallback need exists.
- **Revisit criteria:** Want to add Cloudflare Workers AI as a third backend, OR want automatic fallback when local vLLM is unreachable, OR multiple environments need shared rate-limiting.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

## Quality and tooling (GPU/ML follow-ups)

Captured from the comprehensive GPU/ML doc pass; full rationale per item lives in `docs/gpu-and-models.md` "Things we have not tried yet".

### watercolor-lora-ab
- **One-line description:** Try `ntc-ai/SDXL-LoRA-slider.watercolor` (slider-style; lets you dial intensity) and `lora-library/B-LoRA-watercolor` (decoupled style/content via B-LoRA technique) against the current `ostris/watercolor_style_lora_sdxl`. 12 MB each. Use `bin/game image-test "<prompt>" --lora <new>.safetensors` for the A/B.
- **Why deferred:** Current pick (`ostris`) produces visibly painterly output matching the WHIMSY anchor; no concrete complaint to fix. Surfaced as a revisit candidate in 6 prior proposals (2026-04 through 2026-05) without ever being selected — the audit-trail-substrate-landed gate alone has consistently failed to motivate the work, so the criterion is tightened to require an actual aesthetic complaint before resurfacing.
- **Revisit criteria:** A specific aesthetic complaint about current renders (e.g., "trees too sharp", "skies look uniform", "watercolor edges feel inconsistent across rooms") that we want to address by trying a different LoRA. The audit-trail substrate is in tree (`bin/game test human` qpeek output to `docs/pretty/aesthetic-samples/`) and ready to capture before/after comparisons whenever this entry activates.
- **Origin:** docs/gpu-and-models.md (Image-gen alternatives we considered and did not test); revisit-criteria refresh 2026-05-07 (was double-gated; tightened to single complaint-driven gate after 6 declines).

### calibrated-fp8-kv-scales
- **One-line description:** Run vLLM's FP8 calibration pass over a representative dataset to produce per-channel FP8 KV scales for `Qwen/Qwen2.5-7B-Instruct-AWQ`, then re-enable `--kv-cache-dtype fp8_e4m3` in `bin/game cmd_vllm_up`. Recovers localreview's documented +58% decode TPS / ~0.9 GB freed VRAM win that was lost when we rejected naive fp8_e4m3 on the 7B (model looped garbage tokens).
- **Why deferred:** Real engineering work (calibration dataset, vLLM scale-export pipeline, validation run). Only worth it if LLM throughput becomes a bottleneck. Today single-stream decode latency is sub-second warm; no user-visible pressure.
- **Revisit criteria:** LLM round-trip latency starts gating UX (e.g., NPC dialogue chains feel laggy with multiple humans connected); OR vLLM ships an official calibration recipe for Qwen 2.5 family that drops the engineering cost meaningfully.
- **Origin:** docs/gpu-and-models.md (The fp8-KV story, condition #2)

## Test architecture follow-ups

Captured from the test-architecture landing (2026-04-23); scaffolding for these is in place, the work itself is deferred until the triggering signal arrives. See `TESTING.md` for the full architecture and philosophy.

### claude-vision-quality-gate
- **One-line description:** Add a `tier_long` probe under `tests/drift/` that submits each rendered anchor image to Claude Opus 4.7 vision with the WHIMSY rubric, asserts a minimum rating. Cost-gated behind an env flag (e.g. `DAYDREAM_CLAUDE_VISION_GATE=1`) so routine runs don't burn tokens.
- **Why deferred:** Human qpeek review (commit 2026-04-23) is the v0 human-in-the-loop. A Claude-vision gate is complementary but costs API tokens per run; only earns its keep when human bandwidth is the bottleneck (multiple daily workflow tweaks, or a second contributor).
- **Revisit criteria:** We start doing ≥3 LoRA/workflow/sampler A/Bs per week and qpeek interactive review becomes the rate limit; OR a second contributor needs machine-verifiable aesthetic gating without interactive review.
- **Origin:** test architecture plan (2026-04-23)

### archive-restore-roundtrip-test
- **One-line description:** Add a `tier_long` test that archives a world via `bin/game world archive`, deletes it, restores from the archive, then diffs the restored DB + cache against the pre-archive state. Goes deeper than the current `test_admin.py` unit coverage (belt-and-suspenders on the E2E flow).
- **Why deferred:** `test_admin.py` already covers archive + restore individually with the round-trip construct in `test_restore_round_trip`; a dedicated drift-tier end-to-end would be redundant until we have multi-world state + a non-trivial cache to diff.
- **Revisit criteria:** First Opus-bootstrapped world worth keeping; OR first operator incident where archive/restore loses state and the existing unit coverage didn't catch it.
- **Origin:** test architecture plan (2026-04-23)

### security-tests-tier
- **One-line description:** Dedicated `tests/security/` directory covering banned-word filter regression, session-cookie tamper detection, AccessMiddleware fuzz (invalid CGNAT edge cases), `daydream/admin.py` path-traversal edge cases beyond the current CVE-2007-4559 coverage. Marker mix: some `tier_short`, some `tier_medium`.
- **Why deferred:** Couples to `safety-baseline-v1` (no LLM-driven state mutation in v0 means no banned-word surface to regress against). AccessMiddleware fuzz is lower-priority since the middleware is heavily tested already.
- **Revisit criteria:** `data-skills-cli` + `safety-baseline-v1` land; OR a security-review pass surfaces a class of risk not covered today.
- **Origin:** test architecture plan (2026-04-23)

### load-test-harness
- **One-line description:** Add a `tier_long` capacity test: 10 simulated bots holding WS connections for 10 minutes, sending a modest input cadence, assert no OOM / no arbiter deadlock / bounded room-image queue depth. Under `tests/load/` to keep it distinct from drift.
- **Why deferred:** v0 has 1 user per world; capacity is a v2 concern. Arbiter smoke already exercises serialization; this is the multi-user extension.
- **Revisit criteria:** `multi-user-shared-world` lands; OR oncall starts seeing WS queue backpressure in real usage.
- **Origin:** test architecture plan (2026-04-23)

### ci-pipeline
- **One-line description:** Add `.github/workflows/test.yml` that runs `bin/game test ci` on push / PR. Skips `tier_long` unless the runner has a GPU (AWS EC2 G-family or a self-hosted runner).
- **Why deferred:** Single-dev box today; `bin/game test ci` is run locally. CI earns its keep when a second contributor lands or when we need to enforce green-on-push across branches.
- **Revisit criteria:** Second contributor joins; OR cross-branch churn makes local-only verification feel unsafe.
- **Origin:** test architecture plan (2026-04-23)

### mypy-gate
- **One-line description:** Add `[tool.mypy]` to `pyproject.toml` with `strict = true` and include a mypy pass in `tier_short`. Probably needs typing backfill across `daydream/` first.
- **Why deferred:** The typing work itself is weeks. Ruff B + UP already catches ~80% of what mypy would on this codebase today. Low marginal signal per hour invested.
- **Revisit criteria:** A typing-related bug slips past ruff and causes real damage; OR a contributor with typing momentum lands.
- **Origin:** test architecture plan (2026-04-23)

### staging-probes
- **One-line description:** Implement the `DAYDREAM_TARGET=staging` tier_medium probes. Today the knob is scaffolded (`config.target()` + `_resolve_target` fixture in `tests/conftest.py`) but all tier_medium tests skip with "staging not yet wired" under that target. The real probes would hit `/healthz`, login flow, WS handshake against a deployed staging URL — read-safe, no DB mutation.
- **Why deferred:** No staging environment yet.
- **Revisit criteria:** Staging env exists; `multi-env-layout` lands.
- **Origin:** test architecture plan (2026-04-23)

### prod-verify-probes
- **One-line description:** Implement the `DAYDREAM_TARGET=prod_verify` tier_long probes. Read-only; hits health, auth form, public asset endpoints to confirm a deploy is live after a push. Never writes DB state.
- **Why deferred:** Prod is one box today; there is no "deploy" to verify beyond a local restart.
- **Revisit criteria:** Multi-box prod deploy lands (whether as Cloudflare Workers per the tech-sketch plan or a second physical box).
- **Origin:** test architecture plan (2026-04-23)

### drift-alarms
- **One-line description:** When a baseline diff lands on main, auto-open a Claude Code session (via the `schedule` skill or a push-notification hook) with the diff as context. Keeps the "baseline changed — why?" review loop warm without relying on a human noticing the commit.
- **Why deferred:** Today there's one contributor; every baseline update passes through that person's eyes by construction. The alarm becomes valuable when ratified drift happens on branches that the author doesn't review.
- **Revisit criteria:** Second contributor joins AND starts ratifying baselines independently.
- **Origin:** test architecture plan (2026-04-23)

### gameplay-scenario-tests
- **One-line description:** Upgrade `test_ws.py` with scripted multi-step scenarios: a toon enters meadow → goes north → narrates the new room → leaves an item → reconnects, snapshot reflects the state. Tests the narration + cache + persistence spine as one story rather than three unit assertions.
- **Why deferred:** `multi-room-navigation` just landed; scenarios want to stabilize before being canonicalized as tests. And individual correctness is already covered by the existing WS tests.
- **Revisit criteria:** `multi-room-navigation` feels stable for a few turns; first regression in the flow that single-step tests didn't catch.
- **Origin:** test architecture plan (2026-04-23)

### latency-regression-corpus
- **One-line description:** Tighten the per-call latency windows in `tests/drift/*.py` as multi-run trend data accumulates. Today wall-clock fields are recorded to `.latest.json` but not gated (too noisy on a single sample). Once we have ~10 same-config runs, derive p50 + p95 from the trend and set windows at (p50 / 2, p95 * 2).
- **Why deferred:** Need samples. Until then, recorded values are the substrate, not the contract.
- **Revisit criteria:** 10+ `bin/game test long` runs in `.latest.json` history (moved to a branch-local scratch dir since `.latest.json` is gitignored — maybe add a `tests/baselines/history/` append-only log as part of this work); OR a regression in wall-clock that eyeballs caught but no probe alarmed on.
- **Origin:** test architecture plan (2026-04-23)

## Open questions

### player-authored-skills
- **One-line description:** Open data-skill authoring to non-admin players (currently admin-only via CLI in v1, admin-only via web UI in v2). Plan explicitly defers the question of review workflow gating: dry-run sandbox + admin approval queue, vs. trusted-friend flag, vs. full auto-publish with audit/undo as the safety net.
- **Why deferred:** Plan punts to v2 because the security surface is too large to design without first learning what skills feel good when admin-authored. Friend-scope security stops being load-bearing the moment a player can author LLM prompts that any other player triggers.
- **Revisit criteria:** skills-authoring-and-security shipped (admin web UI + six-layer pipeline both done); clear desire to expand authoring beyond admin (a player asks "can I make a skill?").
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### creative-finetune-json-fluent-base
- **One-line description:** Re-attempt the voice-quality A/B with a creative-writing finetune of a JSON-fluent base (e.g., Qwen 2.5 7B/14B AWQ, Llama 3.x AWQ). Drop-in `DAYDREAM_LLM_MODEL` / `DAYDREAM_VLLM_MODEL` swap; same harness path (`bin/game voice-samples`); compare against `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md`.
- **Why deferred:** As of 2026-05-07 no published creative-writing finetune of a JSON-fluent base is known to fit our 20 GB VRAM budget. Mistral Nemo 12B Q4 was the closest viable candidate and failed the data-skill pipeline (base-arch + Q4 + prompt-shape interaction; see `docs/gpu-and-models.md` "Things we tried and rejected"). A Qwen-family or Llama-family creative-writing finetune at AWQ or fp16 (where it fits) would close the original 2026-04-24 question.
- **Revisit criteria:** A creative-writing finetune of a JSON-fluent base (Qwen 2.5 7B/14B, Llama 3.x 7B/8B, or comparable) publishes on HF AND fits under `--gpu-memory-utilization 0.45-0.7` at AWQ or fp16; OR voice quality becomes a UX-gating concern that justifies the search effort.
- **Origin:** spec 2026-05-07

### free-form-prose-pipeline
- **One-line description:** Daydream pipeline change in `daydream/skills/data.py` to accept free-form prose responses from the LLM and post-parse for `narrate` effects, instead of requiring strict-JSON `response_format`. Would enable prose-continuation finetunes (RP-Ink and similar) that don't fit the current pipeline. Touches `acompletion_json` call site, safety layers (`safety.parse_refusal`, `safety.first_banned`, `_emit_narrate` fallbacks), and the effect-allowlist contract.
- **Why deferred:** The Mistral Nemo experiments (2026-05-06/05-07) showed strict-JSON breaks prose-continuation finetunes, but the current pipeline depends on `json.loads` validation + the effect-allowlist for safety. A pipeline change is architectural and touches multiple components; defer until a specific finetune is worth the cost. The change would also need a new safety story for free-form text (no banned-word output filter today operates on raw LLM text before structured parsing).
- **Revisit criteria:** A specific creative-writing finetune emerges that's worth using AND only works with free-form prose output (not JSON); OR the v2 `skills-authoring-and-security` work picks up this question as part of a broader pipeline refactor.
- **Origin:** spec 2026-05-07

### mistral-7b-instruct-fp16-ab
- **One-line description:** A/B Mistral 7B Instruct at fp16 against the current Qwen 2.5 7B Instruct AWQ for narration voice. Mistral 7B fp16 is ~14 GB resident (fits at `--gpu-memory-utilization 0.7` with ComfyUI down); separates the quantization axis from the architecture axis after the 12B Q4 Nemo experiments came up inconclusive. Same harness path (`bin/game voice-samples`); compare against `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md`.
- **Why deferred:** Diminishing returns after 3 turns of voice-bench work. The Nemo Q4 result already shrunk the answer space; a 7B Instruct A/B would close a specific axis question (is the failure quant or arch?) rather than answer the original "does a creative-writing finetune flex?" question. Worth doing only if a future decision needs that closure.
- **Revisit criteria:** Operator wants definitive closure on Mistral arch suitability before authoring a different LLM-pipeline change; OR a Mistral 7B creative-writing finetune publishes on HF (which would make the Mistral-vs-Qwen axis question load-bearing).
- **Origin:** spec 2026-05-07

