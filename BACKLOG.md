# Backlog

Durable register of considered proposals that were deferred, scoped out, or
rejected. Read before drafting a new SPEC.md; swept at turn close. Long-form
context for every entry below lives in `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md`.

## v1: cozy single-player loop

### multi-room-navigation (ACTIVE in spec 2026-04-23)
- **One-line description:** Add `go <direction>` core skill in `daydream/skills/core.py`, populate `rooms.exits_json`, render exits in the SPA, and migrate to a 5-room hand-seeded world for the v1 demo.
- **Why deferred:** v0 is hardcoded one-room; navigation has no value until persistence and the skill spine work.
- **Revisit criteria:** v0 done; ready to seed a second room in `migrations/`.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### toon-slot-management
- **One-line description:** Add the 5-slot toon picker UI, slot CRUD endpoints in `daydream/api/`, and `kicked_at` promotion that turns a kicked toon into an NPC carrying its inventory and history.
- **Why deferred:** v0 has one hardcoded toon; slot management only matters once a second human (or NPC) wants to occupy the world.
- **Revisit criteria:** v0 persistence verified; second human player wants in, or first NPC needs to be authored.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### npc-drift-loop
- **One-line description:** Add APScheduler-driven background ticks in `daydream/drift.py` (weather, NPC mood, in-world calendar) on the "gentle drift" cadence (every ~5 min when empty, ~30 min when humans present); drift loop must yield the GPU lock immediately on player input.
- **Why deferred:** v0 has no NPCs to drift; cadence design needs the GPU arbiter from image-gen-pipeline to be in place.
- **Revisit criteria:** image-gen-pipeline landed (arbiter exists); at least 2 NPCs in the world.
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

### data-skills-cli
- **One-line description:** Add `bin/game world skill add path/to/skill.json` plus hot-reload in `daydream/skills/registry.py`; data skills carry `context_predicate_json`, `prompt_template` (Jinja sandboxed), `effects_schema_json`, `ui_hint`. The `forge` skill is the v1 showcase. Pairs with `safety-baseline-v1` (must land together).
- **Why deferred:** v0 ships only baked-in core skills (look/say/examine). Data skills are the v1 unlock for content variety, but need the safety baseline alongside before player exposure.
- **Revisit criteria:** Core skills + LLM interpreter stable in v0; first non-trivial data skill (forge) authored by hand.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### safety-baseline-v1
- **One-line description:** Add the v1 safety floor in `daydream/llm/safety.py`: banned-words filter (regex banlist informed by WHIMSY.md), refusal-schema enforcement (`refused: true` in skill output propagates as a `narrate` event instead of effects), and prompt-injection containment via `<player_input>...</player_input>` tag wrapping in skill prompt templates. Distinct from the v2 full pipeline (Jinja sandbox, content classifier, audit/undo) which lives in `skills-authoring-and-security`.
- **Why deferred:** v0 has no LLM-driven state mutation (only LLM-driven free-text routing with a `narrate` chat fallback). Safety becomes load-bearing the moment `data-skills-cli` ships, because data skills can propose effects.
- **Revisit criteria:** Ship in the same change as `data-skills-cli`; first authored data skill (forge) is the smoke test.
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

### voice-and-aesthetic-audit-trail
- **One-line description:** Add `tools/voice-bench.py` (and image counterpart) that renders 3-5 anchor LLM prompts to `docs/pretty/voice-samples/<date>.md` and 3-5 anchor image prompts to `docs/pretty/aesthetic-samples/<date>/`. Not pass/fail; a dated chronology you can scroll back through to see when the vibe shifted, and a side-by-side substrate when swapping models or LoRAs.
- **Why deferred:** v1 closed without it. Today the only quality check is human eyes-on; the smoke catches output-format regressions but not voice/aesthetic drift. Cheap to build (under an hour) but the absence is currently "before our second user" risk, not "right now" risk.
- **Revisit criteria:** First time someone asks "did the new model get worse?" and we have no answer; OR first vLLM/LoRA bump where we want a side-by-side; OR first non-author player joins and we want a baseline to compare against.
- **Origin:** docs/gpu-and-models.md (Quality guardrails)

### qwen-2.5-7b-rp-ink-trial
- **One-line description:** A/B `Qwen/Qwen2.5-7B-RP-Ink` (or successor creative-writing finetune) against the current `Qwen/Qwen2.5-7B-Instruct-AWQ` for narration voice. Drop-in `DAYDREAM_VLLM_MODEL` swap; same compute, same VRAM. The original Plan-agent research called it out for cozy/atmospheric narration specifically.
- **Why deferred:** v1 has no NPC dialogue yet (data-skills + drift land in later turns). Without representative narration, the A/B has nothing meaningful to compare. Also blocked on `voice-and-aesthetic-audit-trail` for clean side-by-side capture.
- **Revisit criteria:** `npc-drift-loop` or `data-skills-cli` lands and produces real NPC narration; voice-bench fixture exists.
- **Origin:** docs/gpu-and-models.md (Things we have not tried yet)

### watercolor-lora-ab
- **One-line description:** Try `ntc-ai/SDXL-LoRA-slider.watercolor` (slider-style; lets you dial intensity) and `lora-library/B-LoRA-watercolor` (decoupled style/content via B-LoRA technique) against the current `ostris/watercolor_style_lora_sdxl`. 12 MB each. Use `bin/game image-test "<prompt>" --lora <new>.safetensors` for the A/B.
- **Why deferred:** Current pick (`ostris`) produces visibly painterly output that matches the WHIMSY anchor; no concrete complaint to fix. Worth doing once when there's an audit-trail fixture so the comparison is durable.
- **Revisit criteria:** `voice-and-aesthetic-audit-trail` lands; OR a specific aesthetic complaint ("the trees are too sharp", "skies look uniform") that we want a different LoRA to address.
- **Origin:** docs/gpu-and-models.md (Image-gen alternatives we considered and did not test)

### calibrated-fp8-kv-scales
- **One-line description:** Run vLLM's FP8 calibration pass over a representative dataset to produce per-channel FP8 KV scales for `Qwen/Qwen2.5-7B-Instruct-AWQ`, then re-enable `--kv-cache-dtype fp8_e4m3` in `bin/game cmd_vllm_up`. Recovers localreview's documented +58% decode TPS / ~0.9 GB freed VRAM win that was lost when we rejected naive fp8_e4m3 on the 7B (model looped garbage tokens).
- **Why deferred:** Real engineering work (calibration dataset, vLLM scale-export pipeline, validation run). Only worth it if LLM throughput becomes a bottleneck. Today single-stream decode latency is sub-second warm; no user-visible pressure.
- **Revisit criteria:** LLM round-trip latency starts gating UX (e.g., NPC dialogue chains feel laggy with multiple humans connected); OR vLLM ships an official calibration recipe for Qwen 2.5 family that drops the engineering cost meaningfully.
- **Origin:** docs/gpu-and-models.md (The fp8-KV story, condition #2)

## Open questions

### player-authored-skills
- **One-line description:** Open data-skill authoring to non-admin players (currently admin-only via CLI in v1, admin-only via web UI in v2). Plan explicitly defers the question of review workflow gating: dry-run sandbox + admin approval queue, vs. trusted-friend flag, vs. full auto-publish with audit/undo as the safety net.
- **Why deferred:** Plan punts to v2 because the security surface is too large to design without first learning what skills feel good when admin-authored. Friend-scope security stops being load-bearing the moment a player can author LLM prompts that any other player triggers.
- **Revisit criteria:** skills-authoring-and-security shipped (admin web UI + six-layer pipeline both done); clear desire to expand authoring beyond admin (a player asks "can I make a skill?").
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal
