## Spec — 2026-04-22 — v0: the smallest dream

**Goal:** Stand up the smallest playable Daydream slice. One human in a browser authenticates with the password `REDACTED`, sees one room with a committed watercolor placeholder background, types free-form text that an LLM routes through a tiny skill registry, and has the resulting events persist across `bin/game down && bin/game up`. This proves the spine (lifecycle, auth, DB, websocket, LLM routing, persistence) end to end before adding image generation, multi-room navigation, NPC memory, or any other v1/v2 feature.

### Acceptance Criteria

- [x] **Lifecycle commands work and are idempotent.** `bin/game up` starts the vLLM warm process and the FastAPI server. `bin/game status` reports both as running and the configured port (default 8080) as reachable. `bin/game down` stops both cleanly. Re-running `up` while up, or `down` while down, is a no-op.
- [x] **Password gate enforces `REDACTED`.** Unauthenticated requests to the SPA root are redirected to a login page. POSTing the password `REDACTED` to the auth endpoint sets a session cookie and grants subsequent access; any other password is rejected without setting a cookie.
- [x] **Database initializes from a checked-in migration.** On first start, `~/data/daydream/worlds-dev/live.db` is created from `migrations/001_initial.sql` containing one world row, one room, one toon, and at least one examinable item (e.g., a lantern with a non-empty seed). On subsequent starts the migration does not re-apply; existing rows are untouched.
- [x] **Websocket protocol carries `state_snapshot`, `input`, and `event`.** On connect after auth, the client receives one `state_snapshot` describing the current room and inventory. Sending `{kind: "input", text: "..."}` results in one or more `event` messages broadcast back. Reconnecting receives a current `state_snapshot` reflecting any persisted state.
- [x] **Three core skills work without invoking the LLM.** `look` returns the room's stored description. `examine the lantern` returns deterministic text that incorporates the lantern's stored seed (verifiable by setting a sentinel string in the seed and asserting it appears in the output). `say hello` produces a `say` event with the player text visible in the chat log. None of these three exercise the LLM client; the GPU and vLLM can be down and they still pass.
- [x] **LLM-driven free-form interpreter routes phrases.** A phrase that maps to a known skill (e.g., "look around") is routed to `look` and produces the same `event` sequence as typing `look`. A phrase with no matching skill (e.g., "sing a song") causes the interpreter to return `none`, and the server broadcasts a `narrate` event with non-empty fallback text rather than dispatching a wrong skill or returning an error. The LLM call goes through `litellm.acompletion` against the local vLLM endpoint.
- [x] **LLM-backend failure is graceful.** When vLLM is not running or returns an error, free-form inputs that require LLM routing produce a `narrate` event with a recognizable in-game error message ("the dream is foggy" or similar) rather than crashing the websocket or returning an HTTP 500. Core skills (criterion 5) continue to work in this state.
- [x] **State persists across restart.** After typing `say hello`, then `bin/game down && bin/game up`, then reloading the SPA, the chat log shows the prior `say hello` event sourced from the persisted event log. The `events` table is the canonical persistence target; clients hydrate from it on reconnect.
- [x] **Watercolor placeholder background renders in the room view.** A committed PNG asset in the repo (not generated at runtime, no image gen subsystem in v0) is displayed at the top of the room view in the SPA. The image's aesthetic matches WHIMSY (Spiritfarer / A Short Hike: cozy, soft, painterly; not pixel art, not crunchy 8-bit).
- [x] **Test suite exists and passes without GPU.** `pytest` runs to green with the LLM client stubbed/mocked. Coverage at minimum: migration + DB schema test, event-log append/fetch test, core-skills test, skill-interpreter test (with a mocked LLM returning canned JSON), and a graceful-failure test for the unreachable-LLM path. Tests do not require vLLM or the GPU.

### Context

**Adopted from plan** `let-s-design-a-fairly-giggly-narwhal` (in `~/.claude/plans/`). Read that plan for v1/v2 milestones, the GPU arbiter design, the skill-system data model, the v2 skills-as-data security boundary, the NPC drift/memory model, and the bootstrap-via-Opus flow. v0 deliberately omits all of these.

**Aesthetic compass.** Spiritfarer / A Short Hike: cozy, warm, painterly, soft edges. NOT pixel art, NOT crunchy 8-bit, NOT melancholic. Even the placeholder PNG and any narration copy in v0 must reflect this so the tone does not have to be retroactively reset in v1.

**Operational shape.** Single Python process tree (FastAPI + uvicorn + websockets) plus a vLLM warm process running Qwen 2.5 7B Instruct (Q4_K_M), gated by a `bin/game` shell dispatcher. Bind `0.0.0.0`, default port 8080, accessible only on the dev box (no Tailscale Funnel, no public DNS, single shared password). LiteLLM is imported as a Python library (not run as a proxy) so the same call site works against vLLM today and Cloudflare Workers AI / OpenAI / Anthropic later. SQLite at `~/data/daydream/worlds-dev/live.db` in WAL mode with `synchronous=NORMAL`; v0 has no world swap, no symlink dance, no multi-env layout (those land in v1/v2).

**GPU posture.** v0 only ever loads the LLM. SDXL and the full GPU arbiter come in v1. The LLM client must be structured so the v1 arbiter slots in without changing call sites: route every LLM call through one async client module that can later acquire and release a flock-based GPU lock (the pattern lives in `/home/peter/src/qwen-2.5-localreview/gpu_lock.py`).

**zat.env conventions to respect.** Bind `0.0.0.0` (per `~/src/zat.env/claude/references/networking.md`). HF model cache shared at `~/.cache/huggingface`; never override `HF_HOME` (per `ml-gpu.md`). Python venv at `.venv/`, never `pip install` outside it (`PIP_REQUIRE_VIRTUALENV=true` is set globally). All commits must use the configured `user.name` only; never add Co-Authored-By trailers (per `~/.claude/CLAUDE.md`). Persistent state goes under `~/data/daydream/`, never inside the project tree. Mirror project skeleton from `~/src/qpeek/` (FastAPI, layout, CLAUDE.md style) and `~/src/qwen-2.5-localreview/` (`warm.py` lifecycle pattern, ready to lift in v1).

**Coding practices (zat.env carry-overs).** Work in small committable increments; verify build + tests pass before adding new work. When adding or changing functionality, write or update tests in the same increment. After each functional change, run the relevant test subset. Do not push or modify remote state without explicit user instruction. Spec is code: every acceptance criterion above is testable, and `/codereview` will check the implementation against this spec before any push.

**Out of scope for v0** (deferred; do not build):
- Image generation (SDXL, ComfyUI, watercolor LoRA, GPU arbiter sharing). v1.
- Multiple rooms; navigation between rooms. v1.
- Toon slot management (5 slots, kick to NPC promotion). v1.
- NPC drift, NPC memory, embeddings, LanceDB. v1.
- World snapshot, world swap, world bootstrap, hot reload of skills. v1/v2.
- Multi-environment layout (dev/preview/prod ports + worlds dirs). v2.
- Skill authoring UI, six-layer security pipeline (Jinja sandbox, content filter, audit/undo). v2.
- Painterly Svelte UI polish (v0 ships plain HTML: chat log, input, placeholder PNG). v1.
- Per-user identity beyond the shared password. Out of scope for the foreseeable future.

**Critical files to create in v0:**

- `/home/peter/src/daydream/bin/game` (and `bin/game-up`, `bin/game-down`, `bin/game-status`)
- `/home/peter/src/daydream/daydream/server.py` (FastAPI app, lifespan, websocket endpoint)
- `/home/peter/src/daydream/daydream/db.py` (SQLite pool, WAL, migration runner)
- `/home/peter/src/daydream/daydream/events.py` (append-only log, fetch_since, broadcast)
- `/home/peter/src/daydream/daydream/skills/{core,registry,interpreter}.py`
- `/home/peter/src/daydream/daydream/llm/client.py` (litellm wrapper; designed for v1 arbiter swap-in)
- `/home/peter/src/daydream/daydream/api/{ws,auth}.py`
- `/home/peter/src/daydream/web/` (Vite + minimal HTML/JS; no Svelte yet)
- `/home/peter/src/daydream/migrations/001_initial.sql`
- `/home/peter/src/daydream/tests/`
- `/home/peter/src/daydream/CLAUDE.md`, `pyproject.toml`, `.gitignore`, `README.md`, placeholder watercolor PNG asset

---

### Proposal (2026-04-22)

**What happened.** v0 (the smallest dream) shipped 10/10 in one turn across 8 increments. Each commit was test-green: project skeleton (84fc373), DB + migration with sentinel-bearing seed (fce8772), append-only event log (d24b5d1), look/say/examine core skills (a9c4480), litellm wrapper + LLM-driven interpreter with mocked tests (ba09985), FastAPI app with REDACTED password gate and the state_snapshot/input/event websocket protocol (3a208c7), vanilla TS SPA with a 118 KB hand-generated watercolor PNG (9771ec1), bin/game lifecycle dispatcher (007ead6). 66 pytest tests pass with no GPU or network. Live integration check confirmed bin/game up launches uvicorn, REDACTED sets a signed session cookie, GET / serves the SPA, /assets/ serves the PNG, idempotent up/down works, and live.db persists across restart.

**Questions and directions.** v1 is genuinely unblocked. Three natural next slices, each a different tradeoff:
- **Most cinematic:** `image-gen-pipeline` (SDXL + watercolor LoRA + ComfyUI + GPU arbiter). Highest operational impact, biggest "feels real" payoff.
- **Most game-feeling:** `data-skills-cli` + `safety-baseline-v1` + `world-bootstrap-opus`, in that order. Unlocks content variety; brings Opus into world authoring; defers GPU work.
- **Smallest committable:** `multi-room-navigation` (add `go` skill, a second room). Quick win, no LLM/GPU contract changes.

A natural sequence: multi-room first (proves navigation in a day), then image-gen (the GPU arbiter is the biggest unknown), then data-skills + safety-baseline + bootstrap (content unlock that benefits from the arbiter being stable).

**Revisit candidates** (criteria now plausibly hold):
- `image-gen-pipeline` — v0 demo loop works end to end and survives restart.
- `multi-room-navigation` — v0 done; ready to seed a second room.
- `data-skills-cli` — core skills + LLM interpreter stable; forge not yet authored (partial).

<!-- SPEC_META: {"date":"2026-04-22","title":"v0: the smallest dream","criteria_total":10,"criteria_met":10} -->
