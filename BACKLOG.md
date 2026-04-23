# Backlog

Durable register of considered proposals that were deferred, scoped out, or
rejected. Read before drafting a new SPEC.md; swept at turn close. Long-form
context for every entry below lives in `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md`.

## v1: cozy single-player loop

### image-gen-pipeline (ACTIVE in spec 2026-04-23)
- **One-line description:** Draft `WHIMSY.md` first (Spiritfarer / A Short Hike tone bible: aesthetic refs, voice samples, banned moods) to anchor every prompt. Then add SDXL base + watercolor LoRA via ComfyUI for room backgrounds and item sprites under `daydream/images/`; integrate flock-based GPU arbiter at `daydream/gpu/arbiter.py` (port from `~/src/qwen-2.5-localreview/gpu_lock.py`) so vLLM and image-gen serialize cleanly on the 20 GB GPU. Includes the `bin/game image-test "prompt" --model X --lora Y` aesthetic A/B harness for swapping LoRAs cheaply.
- **Why deferred:** Out of scope for v0 (ships one committed placeholder PNG only). The spine (lifecycle, auth, DB, websocket, LLM routing) must prove out before adding GPU contention. WHIMSY.md folds in here because every image and narration prompt template will reference it.
- **Revisit criteria:** All v0 acceptance criteria met; one-room demo loop runs end to end and survives restart.
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal

### multi-room-navigation
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
- **One-line description:** Add `bin/game world snapshot NAME` (cp live db to `~/data/daydream/snapshots/{world}-{ts}.db`) and `bin/game world restore` matching it; `bin/game world list` enumerates known worlds.
- **Why deferred:** v0 has no irreplaceable state; first interesting bootstrap is the moment a snapshot becomes worth taking.
- **Revisit criteria:** First Opus-bootstrapped world worth preserving.
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

## Open questions

### player-authored-skills
- **One-line description:** Open data-skill authoring to non-admin players (currently admin-only via CLI in v1, admin-only via web UI in v2). Plan explicitly defers the question of review workflow gating: dry-run sandbox + admin approval queue, vs. trusted-friend flag, vs. full auto-publish with audit/undo as the safety net.
- **Why deferred:** Plan punts to v2 because the security surface is too large to design without first learning what skills feel good when admin-authored. Friend-scope security stops being load-bearing the moment a player can author LLM prompts that any other player triggers.
- **Revisit criteria:** skills-authoring-and-security shipped (admin web UI + six-layer pipeline both done); clear desire to expand authoring beyond admin (a player asks "can I make a skill?").
- **Origin:** plan let-s-design-a-fairly-giggly-narwhal
