# Backlog

Durable register of considered proposals that were deferred, scoped out, or
rejected. Read before drafting a new SPEC.md; swept at turn close. Long-form
context for every entry below lives in `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md`.

## v1: cozy single-player loop

### drift-pools-for-loft-npcs
- **One-line description:** `daydream/drift.py`'s hand-authored canned pools (`_DRIFT_POOLS`) and selection weights (`_NPC_DRIFT_WEIGHT`) are still keyed to the retired bunny-world NPCs (`t-rook`/`t-iris`); the live Clockmaker's Loft NPCs (Tace/Bell/Mott) fall through to the shared generic pool on the offline path, so canned drift is voice-neutral in the canonical world. Author per-NPC pools for the loft, or better, let the world envelope carry pools so `world load` installs them for any future world.
- **Why deferred:** The LLM drift path (the normal case, vLLM up) already composes per-NPC from seed + mood + memories; only the offline fallback is generic. Surfaced during the 2026-07-02 doc/state audit.
- **Revisit criteria:** vLLM-down play feels voice-flat, or the next world-authoring pass touches drift anyway (envelope-carried pools would close this for every world at once).
- **Origin:** state audit 2026-07-02 (first Fable session sweep).

### drift-variety-richer-beats
- **One-line description:** Reduce NPC drift repetition beyond the v0 mitigation (laconic prompt + a "vary the beat" nudge in `_DRIFT_SYSTEM_PROMPT` + a consecutive-near-duplicate suppressor in `daydream/drift.py:_tick`). Options: per-NPC canned-pool rotation tracking recently-used beats, a "recently noticed" exclusion passed into the drift prompt, or richer hand-authored pools so Qwen 7B isn't leaned on for variety. The 7B reliably fixates on a seed's most salient image (Rook -> "hums softly, moving the bellows") regardless of mood/memory.
- **Why deferred:** v0's de-dup suppresses the *visible* consecutive repeats (the player won't see them stacked), so this is variety polish, not a correctness fix. Wants the drift-samples golden + a "distinctness over N ticks" metric before tuning.
- **Revisit criteria:** Playtesters report a room's NPC feeling samey across a session even with de-dup, or when adding NPCs whose seeds are similarly single-image.
- **Origin:** playtest follow-up (plan note-that-when-the-snuggly-music), drift-voice-samples 2026-06-30

### dialogue-refusal-fallback-on-benign-input
- **One-line description:** Occasionally an in-character dialogue turn degrades to the "the dream won't hold that thought" fallback on a benign input (observed once on "hello" in `voice-samples`): the model's spoken line trips the output banlist / refusal path (`daydream/llm/safety.py`, `daydream/skills/data.py` `_BANNED_FALLBACK_TEXT`) or the narrate truncates. Investigate whether it's flaky (sampling) or systematic (a banlist false-positive / max-tokens), then tighten the trigger or raise the cap.
- **Why deferred:** Intermittent (1 of 5 samples) and the fallback is graceful, not a crash. Needs a repeatability pass (re-run `voice-samples` N times, log which layer fired) before touching the safety pipeline.
- **Revisit criteria:** Players hit the fallback on ordinary inputs often enough to feel broken, or a repeatability run shows a systematic banlist false-positive.
- **Origin:** playtest follow-up (plan note-that-when-the-snuggly-music), voice-samples 2026-06-30

## v2: shared world + skill authoring

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
- **2026-06-30 reframe (objects + verbs spec):** verbs now largely replace skills as the interaction surface, and the same allowlist + role-separation + refusal/banlist pipeline now guards LLM-driven **world-mutation** effects (`narrate`/`set_property`/`spawn_object`/`move_object`), not just dialogue. This entry narrows to the web authoring UI + the deeper pipeline (jsonschema, content-safety classifier, audit/undo); the effect-allowlist substrate it depended on is in tree and generalized.
- **One-line description:** Web UI at `daydream/api/` for admin to edit `prompt_template`, dry-run against a sandbox, and publish; full six-layer security pipeline (Jinja2 SandboxedEnvironment, role separation with `<player_input>` tags, jsonschema validation, effect allowlist enforced in `daydream/skills/effects.py`, content-safety classifier in `daydream/llm/safety.py`, `audit` table + `bin/game world undo --invocation N`).
- **Why deferred:** v1 ships data-skills-cli (admin authors via JSON files); the web UI + full security pipeline land in v2 once a real authoring rhythm exists and the threat model is exercised.
- **Revisit criteria:** Admin uses JSON-CLI authoring frequently enough that a UI pays off; or first time a data skill produces an unwanted effect that needs to be rolled back.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### litellm-proxy-fallbacks
- **One-line description:** Stand up the LiteLLM proxy as a separate process; configure Qwen → Claude fallback chain on local outage; add cost tracking and per-model rate limits in proxy config rather than game code.
- **Why deferred:** v0/v1 use `litellm` as a Python library only — no extra process, no extra port. The proxy adds operational overhead that pays for itself only once a third backend or an automatic-fallback need exists.
- **Revisit criteria:** Want to add Cloudflare Workers AI as a third backend, OR want automatic fallback when local vLLM is unreachable, OR multiple environments need shared rate-limiting.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

## v2: objects + verbs (deferred depth, captured 2026-06-30)

Deferred depth from the objects + local-LLMs spec (plan `the-output-of-this-greedy-hedgehog`). The object/property/verb core, command bus, grounded parser, clickable UI, and the explicit-spawn + lazy-cache generative slice shipped; these are the prepared-for next increments.

### player-touch-object-promotion
- **One-line description:** The "later" half of generative objects: a noun mentioned in narration but never `spawn_object`'d gets promoted to a real object when a player tries to interact with it (e.g. examines/takes a thing the narration named). Today promotion is explicit-only (a verb's LLM output must emit `spawn_object`); narration is deliberately never auto-scanned.
- **Why deferred:** Fully spec'd as the documented next increment in the 2026-06-30 plan; the explicit-spawn path landed first as the irreducible, safe foundation. Player-touch promotion needs a resolution story for "which mentioned noun did they mean" that the grounded parser's in-scope-id model does not yet cover (the noun isn't an object yet, so it has no id).
- **Revisit criteria:** The explicit-spawn slice feels good in play AND players visibly reach for nouns the dialogue named but didn't spawn.
- **Origin:** plan the-output-of-this-greedy-hedgehog (§6, the hybrid's later half).

### object-lifecycle-clutter-gc
- **One-line description:** Salience / TTL / `last_accessed_at` pruning of generated objects so a long-played world doesn't accumulate clutter. The flags are already in place (`properties.generated_by`, an `ephemeral` flag, `last_accessed_at`) so the first GC pass needs no migration (mirrors `generated_assets.pinned`).
- **Why deferred:** No clutter exists yet; the generative slice just landed. GC is premature until a world accrues enough spawned objects to feel noisy.
- **Revisit criteria:** A played world accumulates enough ephemeral spawned things that rooms feel cluttered, OR a spawned-object count crosses a threshold worth measuring.
- **Origin:** plan the-output-of-this-greedy-hedgehog (§6, provenance + minimal lifecycle).

### deep-prototype-inheritance-and-per-object-verbs
- **Per-object-verbs slice: SHIPPED (2026-07-01).** The playable-quest-loop turn added a `fixture` prototype (immovable: examine only) and lets authored objects declare per-object `verbs` in the world envelope (a case is `open`-able, a given key is `use`-able) and a spawn declare its own verbs (`spawn_object` verbs passthrough → the given case-key becomes use-able). The `properties.verbs` union with prototype defaults (`objects.verbs_for`) is now load-bearing, exercised by the Clockmaker's Loft quest. What REMAINS deferred is the multi-level part below.
- **One-line description (remaining):** Multi-level prototype chains (today inheritance is one level, shallow) + per-object *behavior overrides* beyond adding verbs (an object that overrides a verb's default HANDLER, not just its verb list). The MOO "generic object" pattern taken further.
- **Why deferred:** v1 has one handler per verb and one prototype level; the resolution ORDER (player→room→dobj→iobj) is already implemented so overrides slot in without re-architecting. Depth is only worth it once authored content wants a prototype that extends another prototype or an object that replaces a verb's behavior.
- **Revisit criteria:** Authored content needs an object that OVERRIDES a verb's default behavior (not just adds a verb), or a prototype that extends another prototype.
- **Origin:** plan the-output-of-this-greedy-hedgehog (§2); per-object-verbs slice shipped by plan this-plan-will-be-peppy-kay.

### user-authored-llm-driven-world-building-verbs
- **2026-07-02 narrowing (Dreamseeds spec):** the effect-vocabulary half is being built. The Dreamseeds increment implements `spawn_room` + `link_exit` behind an ENGINE-authored verb (`plant`), gated by a quest-earned seed item whose Opus-authored `growth` boundaries constrain one local-LLM room composition. What remains in this entry is the player/admin-AUTHORED verb surface: a player authoring a verb whose LLM output builds rooms/objects, plus `destroy_object` and the authoring UI + safety story.
- **One-line description (remaining):** A player/admin authors a verb whose LLM output BUILDS new rooms and objects (MOO-style). `destroy_object` stays documented-not-built.
- **Why deferred:** The authoring surface + the safety story for player-authored world-mutation are the work. Couples to `skills-authoring-and-security` and `player-authored-skills`.
- **Revisit criteria:** Dreamseeds ships and feels good in play (the effect vocabulary + boundary model exercised on an authored verb first); appetite to hand authoring to players.
- **Origin:** plan the-output-of-this-greedy-hedgehog (the explicit future direction; §5 future-prepared vocabulary); narrowed by the Dreamseeds spec 2026-07-02.

### per-npc-event-log-visibility-filtering
- **One-line description:** Filter which events an NPC "sees" so dialogue stays consistent (an NPC shouldn't reference an event that happened in another room or that it couldn't have witnessed). A research-suggested consistency guard for the LLM dialogue path.
- **Why deferred:** Single-player, two-NPC scale; the room-filtered broadcast already keeps cross-room events off a player's stream. NPC-side visibility matters once dialogue starts citing world events.
- **Revisit criteria:** Dialogue or memory starts surfacing events the NPC couldn't plausibly know about.
- **Origin:** plan the-output-of-this-greedy-hedgehog (out-of-scope list).

### parser-latency-and-throughput-tuning
- **One-line description:** Every free-text input is now one ~256-token parse call serialized behind the GPU arbiter with image-gen. Tune throughput (batching, a smaller/faster parse model, or speculative fast-paths) if it gates UX. The click-bypass + deterministic fast-path keep this off the hot path today.
- **Why deferred:** Single-stream decode is sub-second warm; clicks and exact words make no LLM call. No user-visible pressure yet. Ties to `calibrated-fp8-kv-scales` (a 7B fp8-KV recovery would help here too).
- **Revisit criteria:** Natural-language input feels laggy in play (e.g. multiple humans, or NPC dialogue chains), OR `calibrated-fp8-kv-scales` lands and frees decode headroom.
- **Origin:** plan the-output-of-this-greedy-hedgehog (parser latency/arbiter contention note).

## Quality and tooling (GPU/ML follow-ups)

Captured from the comprehensive GPU/ML doc pass; full rationale per item lives in `docs/gpu-and-models.md` "Things we have not tried yet".

### watercolor-lora-ab
- **One-line description:** Try `ntc-ai/SDXL-LoRA-slider.watercolor` (slider-style; lets you dial intensity) and `lora-library/B-LoRA-watercolor` (decoupled style/content via B-LoRA technique) against the current `ostris/watercolor_style_lora_sdxl`. 12 MB each. Use `bin/game image-test "<prompt>" --lora <new>.safetensors` for the A/B.
- **Why deferred:** Current pick (`ostris`) produces visibly painterly output matching the WHIMSY anchor; no concrete complaint to fix. Surfaced as a revisit candidate in 6 prior proposals (2026-04 through 2026-05) without ever being selected — the audit-trail-substrate-landed gate alone has consistently failed to motivate the work, so the criterion is tightened to require an actual aesthetic complaint before resurfacing.
- **Revisit criteria:** A specific aesthetic complaint about current renders (e.g., "trees too sharp", "skies look uniform", "watercolor edges feel inconsistent across rooms") that we want to address by trying a different LoRA. The audit-trail substrate is in tree (`bin/game test human` qpeek output to `docs/pretty/aesthetic-samples/`) and ready to capture before/after comparisons whenever this entry activates.
- **Revisit criteria (now MET, 2026-07-01):** `forge-render-legibility` below is a concrete complaint (the forge doesn't read as a forge; hard objects don't render under `ostris`), which is exactly the trigger this entry was waiting for. A LoRA A/B is one candidate fix for that item.
- **Origin:** docs/gpu-and-models.md (Image-gen alternatives we considered and did not test); revisit-criteria refresh 2026-05-07 (was double-gated; tightened to single complaint-driven gate after 6 declines).

### forge-render-legibility
- **One-line description:** "The Quiet Forge" doesn't render as a blacksmith's forge. Across five seed variants (2026-07-01, via `bin/game image-test` + agent review), SDXL + the `ostris` watercolor LoRA turned "iron anvil / leather bellows / forge" into soft vessels, kilns, pots, and cottages in warm tones — cozy and on-palette, but never a legible anvil or forge. The loose watercolor style actively fights the crisp silhouette a recognizable hard object needs. This is the general "hard objects don't render legibly under a loose style LoRA" limit, surfaced on the forge.
- **Why deferred:** Out of scope for the verification-infrastructure turn (which was about tests, not fixing one room's image). Candidate fixes, none free: (a) reframe the room to what renders well (a warm rustic workshop / hearth-nook — cheapest, drops the blacksmith concept); (b) pre-bake a picked forge image as a pinned `r-forge` asset (keeps the concept, no global change); (c) lower the LoRA strength or A/B a different LoRA per `watercolor-lora-ab` (most likely to yield a real anvil, but a GLOBAL workflow change that re-baselines every room). Which one is a product/aesthetic call for the operator.
- **Revisit criteria:** The operator picks a direction (reframe / pre-bake / LoRA A/B), OR a second authored room needs a hard object (tool, machine, sign) and hits the same wall — at which point the general fix is worth more than the per-room workaround.
- **Coordinate with:** `watercolor-lora-ab` (a LoRA swap is fix option c); the `image_forge.golden.json` perceptual baseline (re-ratify after any fix).
- **Origin:** 2026-07-01 forge-render agent-review loop (this turn), flagged per the CLAUDE.md "flag local limits at design time" process rule.

### calibrated-fp8-kv-scales
- **One-line description:** Run vLLM's FP8 calibration pass over a representative dataset to produce per-channel FP8 KV scales for `Qwen/Qwen2.5-7B-Instruct-AWQ`, then re-enable `--kv-cache-dtype fp8_e4m3` in `bin/game cmd_vllm_up`. Recovers localreview's documented +58% decode TPS / ~0.9 GB freed VRAM win that was lost when we rejected naive fp8_e4m3 on the 7B (model looped garbage tokens).
- **Why deferred:** Real engineering work (calibration dataset, vLLM scale-export pipeline, validation run). Only worth it if LLM throughput becomes a bottleneck. Today single-stream decode latency is sub-second warm; no user-visible pressure.
- **Revisit criteria:** LLM round-trip latency starts gating UX (e.g., NPC dialogue chains feel laggy with multiple humans connected); OR vLLM ships an official calibration recipe for Qwen 2.5 family that drops the engineering cost meaningfully.
- **Origin:** docs/gpu-and-models.md (The fp8-KV story, condition #2)

## Test architecture follow-ups

Captured from the test-architecture landing (2026-04-23); scaffolding for these is in place, the work itself is deferred until the triggering signal arrives. See `TESTING.md` for the full architecture and philosophy.

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

## UI & presentation (captured 2026-07-01 Reading Room turn)

### snapshot-enrichments-for-reading-room
- **One-line description:** Three small server-side snapshot enrichments the client-only Reading Room turn deliberately skipped: item description/provenance in the snapshot's `_object_card` so keepsake specimen cards read richer than name + generic tag; exit destination TITLES so the compass can say "up — the Clockmaker's Loft" without leaking room ids; a server-derived objective string for the "a small errand" marginalia group.
- **Why deferred:** The Reading Room spec was explicitly client-only (no server/world change, no WORLD_VERSION bump); each of these is a deliberate server change weighed against that stance.
- **Revisit criteria:** The next server-touching increment lands (cheap to ride along), or playtest feedback that the compass/keepsakes feel thin.
- **Origin:** SPEC proposal block 2026-07-01 (Reading Room turn), preserved here when the Dreamseeds spec replaced that block.

## Closed

Resolved and rejected entries, compressed to a line each; full narratives live in git history (this file, pre-2026-07-02) and the linked plans.

- **two-object-verbs — done 2026-07-01.** `give`/`use` (+ state-gated `open`, `read`) shipped as the playable-quest-loop turn; exercised by the Clockmaker's Loft quest, guarded by `tests/test_quest_playthrough.py`.
- **claude-vision-quality-gate — done, reframed 2026-07-01.** The aesthetic critic is the Claude Code agent Reading renders against `WHIMSY.md` in-session; the env-gated litellm vision gate was removed for needing an API key (generation policy). Human escalation: `qpeek` or in-game.
- **toon-delete-drops-items — done 2026-06-30.** `toons.delete_slot` reparents carried things to the toon's room before deletion; belongings persist in the world.
- **forge-render-drift-anchor — done 2026-06-30, golden pending re-ratification.** The forge dHash anchor + golden shipped; NOTE (2026-07-01): the render was later judged NOT to read as a forge (see `forge-render-legibility`, still open), so the golden gets re-ratified after that fix.
- **present-player-drift-cadence-guard — rejected 2026-06-30.** Redundant: the busy-cadence magnitude is already pinned in tier_short (`test_compute_next_interval_busy_default`). Kept so a future design pass does not re-propose it.
- **voice-baseline-add-model-helper — done 2026-06-30.** `tests/test_voice_baseline.py` derives its parametrization from a glob + `baseline-class` markers; new tracked baselines auto-extend the regression with no code edit.
