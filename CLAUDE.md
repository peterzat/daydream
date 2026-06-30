# CLAUDE.md — daydream

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally generated world that all players share and persistently mutate. See `SPEC.md` for the current acceptance contract, `BACKLOG.md` for the deferred-ideas register, `README.md` for orientation, and [`docs/gpu-and-models.md`](docs/gpu-and-models.md) for the full GPU/ML decision narrative (model picks, what we tried and rejected, what to try later).

## Generation policy: local at runtime, Opus at design time

Foundational and load-bearing; it informs every design and build decision in this project. Daydream has two LLM tiers and they never blur. (The narrative version is README "Two dreamers".)

- **Runtime (the live game) uses ONLY local models on the RTX 4000.** Every generation the running game performs — room art (ComfyUI/SDXL), narration + NPC dialogue + drift (vLLM/Qwen), any future in-game text or gameplay generation — runs locally behind the GPU arbiter. The runtime makes NO calls to any cloud LLM. There is NO production `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, and we do not add one. A runtime feature that seems to need a cloud model is a signal to pre-bake or rethink, not to add a key.
- **Design-time heavy generation is done by Opus inside a Claude Code session** — the agent reading this file authors content and writes it into the DB / a seed, rather than the game shelling out to an API. World authoring, initial seeding, and the infrequent admin capability the local model can't do well are "cheats" we make happily *at design time, with a human in the loop*, because they run in Claude Code and never in the product.
- **Pre-bake, don't phone home.** The quality ceiling of the running game is (Opus-authored groundwork, baked in at design time) + (local-model polish at runtime). To get Opus-grade quality in-game, bake it into the world's seed/cache ahead of time and let the local models animate it live.
- **Flag local limits at design time (process rule).** When a target experience likely won't be compelling under the local-model budget, say so explicitly during design/dev — here, in the session — and reason through the fix together (pre-bake with Opus / cache harder / simplify / accept the edge) before building. Never quietly ship a flat experience because the small model couldn't reach.

**World authoring is keyless (`world load`).** `bin/game world load <envelope.json>` (`daydream/llm/bootstrap.py:load_world`) builds a world DB from an Opus-authored JSON envelope with no LLM call and no API key: author the world in a Claude Code session, write the envelope (the schema lives in `bootstrap.py`'s system prompt), then load it. This is the canonical path. The older `bin/game world bootstrap`, which called the Anthropic API via litellm (needs `ANTHROPIC_API_KEY`), is DEPRECATED under this policy: it still works but prints a deprecation notice, and shares the same validator + DB writer (`bootstrap_world` now calls `load_world` after its LLM call).

## Conventions

- Python venv at `.venv/`. Never `pip install` outside the venv (`PIP_REQUIRE_VIRTUALENV=true` is set globally).
- Python 3.10. Pin `requires-python = ">=3.10"` in `pyproject.toml`.
- User-visible services (the daydream FastAPI server) bind `0.0.0.0` so tailnet clients can reach them; default port `54321` (memorable, non-default — modest security-by-obscurity on a user-visible service). Override via `DAYDREAM_PORT`. Per-env ports land in v2.
- Internal services (vLLM, ComfyUI) bind `127.0.0.1` by default since daydream is their only consumer. Override with `DAYDREAM_VLLM_HOST` / `DAYDREAM_COMFYUI_HOST` to expose on the tailnet (e.g., for the ComfyUI web UI). For ComfyUI specifically, an SSH tunnel from your laptop is usually the right move: `ssh -L 8188:localhost:8188 <host>`.
- Persistent state lives under `~/data/daydream/`, never in the project tree. The active world is `worlds-dev/live.db`; per-env layout (`worlds-dev/`, `worlds-preview/`, `worlds-prod/`) lands in v2.
- HuggingFace cache is shared at `~/.cache/huggingface`. Never override `HF_HOME`.
- All `*.db`, `*.db-wal`, `*.db-shm` are gitignored. Live state never gets committed.

## Lifecycle

`bin/game up`, `bin/game down`, `bin/game status`, `bin/game logs` are the supported daydream-server entry points; `bin/game comfyui-up`/`down` and `bin/game vllm-up`/`down` manage the inference engines (see "External engines" below); `bin/game image-test "<prompt>"` is the aesthetic A/B harness for image gen. `bin/game up` is GPU-assuming by default: it runs a GPU preflight (free-VRAM check via `nvidia-smi`; floor `DAYDREAM_GPU_MIN_FREE_MIB`, default 9500 MiB) that exits with an actionable error if the GPU won't be available, then starts FastAPI synchronously and kicks off vLLM + ComfyUI in the background (engines warm over ~30-60 s; the game is reachable as soon as FastAPI's readiness poll completes). `bin/game up --no-gpu` brings up FastAPI only (CPU-only / docs / tests: no preflight, no engines). `bin/game up-all` is a back-compat alias for `bin/game up`. There is no symmetric `down-all`; `bin/game down` stops only FastAPI, so the engines need explicit `vllm-down` / `comfyui-down`. Each daemon command writes a PID file to `$XDG_RUNTIME_DIR/daydream-<env>/<process>.pid` and a log alongside; `bin/game status` reports liveness and reachability for all three processes plus the current `DAYDREAM_ACCESS` mode and a UFW-reminder warning when `public`.

Tests are tiered under a single entry point: `bin/game test {short,medium,long,ci,human}`. The durable contract (tier budgets, drift-loop semantics, adding a new test) lives in [`TESTING.md`](TESTING.md); read that before adding tests or bumping a model / LoRA / workflow. `bin/game test short` is the pre-commit gate (~10 s); `bin/game test long` runs the real-GPU drift probes under `tests/drift/` and compares against git-committed baselines at `tests/baselines/*.golden.json` (the baseline-update loop is the primary drift-detection mechanism, so a PR that changes a golden is a review event by design). The pytest-ified arbiter smoke replaces `tools/arbiter-smoke.py` as the authoritative source; the standalone script is still usable but reads the same probe corpus from `tests/drift/prompts/`.

### Coding turn vs. live server

Default: `bin/game down` before a coding turn. The server isn't required for any part of the dev loop — `bin/game test short/medium` boots its own TestClient against tmp state (`DAYDREAM_DATA_DIR` is overridden in `tests/conftest.py`), so nothing touches the live DB or the running server. Bring the game up only when you need to eyeball the SPA in a browser or demo something.

Safe to do with the game up:
- **Python edits.** uvicorn is NOT started with `--reload`; edits are inert until the next `bin/game up`. That's a feature: you can't accidentally half-apply a change.
- **Static asset edits** under `web/` (HTML, CSS, JS). FastAPI's StaticFiles re-reads from disk each request; a browser refresh picks up the change.
- **`bin/game test short` / `medium`.** Isolated via tmp data dir.
- **Commits, git work, file shuffling.**

Three reasons to bring it down first:
1. **`bin/game test long` while the game is up.** The GPU arbiter is an in-process lock — the server and the pytest process each have their own. Concurrent image-gen from both can OOM on the 20 GB card. Low-prob if the game is idle, but the arbiter exists specifically to prevent this class of bug.
2. **Migration work.** A new migration file is inert until `bin/game up` runs `init_live`. Control when it fires against `~/data/daydream/worlds-dev/live.db` by keeping the server down while iterating on the SQL. A wrong migration against live state means recovering from `~/data/daydream/archives/` or wiping and re-seeding.
3. **Schema / data-model refactors.** A connected WS session holds stale dataclasses (`Room`, `Toon`) in memory even after the DB has been migrated; the client sees pre-refactor shapes until restart. Confusing to debug.

**Agent automation policy for `bin/game up` / `down`.** An agent working on this project (Claude Code or otherwise) treats these as shared-state actions in the same category as `git push`: observable, disruptive to anyone with a browser session open. Auto-execute in only two cases: (a) about to run `bin/game test long` with the server up — auto `down` with a one-sentence note, since the GPU-OOM risk is real; (b) the user has explicitly asked to eyeball / verify / test in a browser — auto `up` if it's down, since intent is clear. Every other lifecycle change asks first. Never auto-cycle mid-turn when the server is running without checking (`bin/game status` shows it), because the cycle kills any open browser session — Safari in particular shows a disconnect banner and replays chat history on reconnect, which is visible and annoying. When in doubt, ask — same default as `git push`.

## Auth

Single shared password sourced from the `DAYDREAM_PASSWORD` env var. `bin/game` loads `.env` at the project root (gitignored; see `.env.example`) and then `~/.config/daydream/secrets.env` (per-host overrides win). If neither sets `DAYDREAM_PASSWORD`, the auth endpoint refuses every login with a 503 — empty default never grants access. No per-user identity. Cookie-based session, no expiry in v0. The session-cookie signing secret comes from `DAYDREAM_SESSION_SECRET`; if unset, a per-install random secret is generated on first boot and persisted at `~/.config/daydream/session_secret` (mode 0600, gitignored).

## Session & presence

A few WS / slot-picker behaviors (`daydream/api/ws.py`, `daydream/api/slots.py`, `web/assets/main.js`) worth knowing before touching them:

- **Room descriptions on entry.** Every `state_snapshot` carries `room.description`; the SPA renders it. Per-connection visit memory makes it the FULL stored `rooms.description_cached` on the first entry to a room this session and a short "you return to ..." line on re-entry (sticky for the visit so effect re-snapshots don't shrink it). Pre-baked stored text, never a live LLM call.
- **Fresh sessions.** A fresh page load opens `/ws` (no query) and gets an empty event log; a reconnect opens `/ws?since=<lastSeq>` and the server replays the room's missed events. Move/effect re-snapshots still carry the recent slice.
- **Leave the dream.** `POST /api/session/leave` rests this session's toon (`toons.release_session_toon`) and marks the session `left`; a `left` session with no claimed toon gets a `{kind: "needs_toon"}` frame on WS connect (instead of the legacy `t-wren` fallback) and the SPA shows the picker. Create / claim clear `left`.
- **Toon delete.** `POST /api/slots/{slot}/delete` (`toons.delete_slot`) removes a toon and frees the slot — distinct from kick (rest). It clears the toon's carried items (FK) + memories; its events stay as append-only history.

## Objects, verbs, and the command bus

The MOO-style object/verb core (SPEC 2026-06-30). Foundational; read before touching `daydream/objects.py`, `verbs.py`, `parser.py`, `skills/effects.py`, or the WS input path.

- **One object store.** Migration 011 unified `rooms`/`toons`/`items` into a single `objects` table (`kind` in `room`/`toon`/`thing`/`prototype`). Containment is a self-referential `location_id` (a toon's location is its room; a thing's is the room or the carrying toon; a room is top-level). Inheritance is `prototype_id` → a `kind='prototype'` row whose `properties.verbs` are the default verb set. Promoted columns are only the toon auth/slot fields (`slot`, `controller_session`, `is_human_controlled`, `kicked_at`) + a partial unique index `(world_id, slot) WHERE kind='toon'`; everything kind-specific (seed, title, exits, appearance, mood, examined_text, ...) lives in `properties_json`. `daydream/objects.py` is the single read/write surface (`get`/`contents`/`in_scope`/`move`/`get+set_property`/`spawn`/`verbs_for`); `rooms.py`/`toons.py`/`items.py` are thin typed views over it, preserving their old APIs. No other module issues raw `objects` SQL.

- **Closed verbs + MOO dispatch.** `daydream/verbs.py` is a closed, engine-implemented verb set (`look`, `examine`, `take`, `drop`, `talk`, `say`, `go`), each with an arg-spec (needs a dobj? valid target kinds? per-verb effect allowlist? on the UI verb bar?). `execute_command(actor, verb, dobj_id?, iobj_id?, args?)` is the single executor: it validates the dobj is in scope and the verb applies (`verb in objects.verbs_for(dobj)` — this rejects "take a toon" / "talk to a rock"), then dispatches by MOO priority (player → room → dobj → iobj). The one object-bound handler in v1 is an NPC's `talk` dialogue on the dobj, which beats the generic stub. Deterministic verbs make NO LLM call; only `talk` (dialogue) and a lazy-cache `examine` (below) do.

- **Two producers, one executor.** UI clicks send a `{kind:"command", verb, dobj_id?, …}` WS frame straight to `execute_command` (no parser, no LLM). Free text goes through the grounded parser (below) → `execute_command`. `take`/`drop`/`spawn` emit `object_moved`/`object_spawned`, which the broadcast loop treats as snapshot-refresh triggers so the scene/inventory panels update live.

- **Grounded local-LLM parser.** `daydream/parser.py` maps free text to one grounded command. A deterministic fast-path (exit directions, bare verbs, "verb \<in-scope-name>", legacy `rook hi`/`forge a ring` data-skill names) makes zero LLM calls. Otherwise one JSON-constrained Qwen call picks a closed verb + grounds the target to an in-scope **id** ("say hi to rook" / "talk to rook" / "greet rook" → `talk(t-rook, "hi")`; bare "say hi" → `say`). Unknown verb or out-of-scope/ambiguous target → verb `none` → a gentle "don't understand", no mutation. `say`/`talk` carry a `free_text` flag so the fast-path defers their args to the LLM (say-vs-talk).

- **LLM is a hard runtime dependency.** "The dream is foggy" is an OUTAGE message, not a play mode. When vLLM is down, natural-language free text degrades to foggy, while deterministic click/exit verbs (examine-of-cached, take, drop, go) still work. The `bin/game up` GPU preflight is the startup guard. (Consistent with the generation policy: still local-only, no cloud key.)

- **World-mutation effect API.** `daydream/skills/effects.py` is the allowlisted vocabulary ALL runtime mutation flows through: `narrate`, `set_property`, `spawn_object`, `move_object` (with `add_item`/`set_mood` retained as aliases for existing data-skill author files). `dispatch_effects(..., allowed=<subset>)` enforces a per-verb allowlist — a kind outside it is rejected like an unknown kind (no mutation). Future `spawn_room`/`link_exit`/`destroy_object` are documented, not built: the hook for user-authored, LLM-driven world-building.

- **Generative objects.** Promotion is by EXPLICIT declaration only — narration is never auto-scanned for nouns. An object becomes real when a verb's LLM output emits a `spawn_object` effect (Rook's "sheaf of papers"); generative spawns dedup on name+location+provenance so re-running the verb never duplicates. `examine` is lazy-cache: a spawned object with no seed and no cached text gets ONE LLM call, persisted as `properties.examined_text`, then served from cache (zero LLM) thereafter; seeded objects stay deterministic. Provenance (`generated_by`) + an `ephemeral` flag are in place for the future clutter-GC pass (no GC today).

- **NPC dialogue binding.** `talk`'s dialogue is resolved by `verbs._bound_dialogue_skill`: the NPC's `properties.dialogue` (a data-skill name) first, else the legacy `t-<name>` convention (seeded Rook/Iris). `load_world` installs per-NPC dialogue from the envelope's `toons[].dialogue` as a hidden data skill (a sentinel `context_predicate` keeps it out of room-affordance lists; `talk` reaches it directly) and sets `properties.dialogue`. The canonical reset world is authored at `worlds/bunny.json`.

## Network access

`DAYDREAM_ACCESS` in `.env` (default `tailscale`) controls the `AccessMiddleware` in `daydream/api/access.py`:

- **`tailscale`**: middleware rejects any HTTP/WS client whose source IP is not in Tailscale's CGNAT range (`100.64.0.0/10`) or loopback. 403 on HTTP, WebSocket close 1008 on WS. This is the safe default and is enforced at the app layer regardless of UFW state.
- **`public`**: middleware lets all clients through. This is an "agree to be public" flag — flipping it does NOT also open UFW. For traffic to actually arrive you must also `sudo ufw allow ${DAYDREAM_PORT}/tcp` and have public DNS pointing at the box. Without UFW open, public clients still can't reach the bind, so the toggle is harmless if mis-flipped.

The middleware sits at the outer edge of the FastAPI middleware stack (added LAST so it runs FIRST per request) — non-tailnet clients get rejected before any session cookie or password gate machinery runs. Tests opt into pass-through by default via `tests/conftest.py` (sets `DAYDREAM_ACCESS=public` for `TestClient`); the middleware contract itself is exercised in `tests/test_access_middleware.py` with mocked ASGI scopes.

The 100.64.0.0/10 hardcoding is correct because Tailscale's CGNAT range is fixed by their design. A self-hosted Headscale with a custom range would need that constant updated.

## GPU posture

20 GB VRAM ceiling on this box (RTX 4000 SFF Ada, compute capability 8.9). vLLM (Qwen 2.5 7B Instruct AWQ, ~5 GB resident) and ComfyUI (SDXL base + watercolor LoRA, ~6 GB resident, ~10-12 GB peak during inference) coexist behind a flock-free in-process arbiter at `daydream/gpu/arbiter.py` (`asyncio.Lock`) that serializes inference requests. All LLM calls flow through `daydream/llm/client.py` and all image-gen through `daydream/images/client.py` so the arbiter has exactly two call sites.

This project assumes Daydream is the only GPU consumer on this box. The `qwen-2.5-localreview` warm server is off (per its `.env`) and is assumed to stay off indefinitely; no external process competes for VRAM. The arbiter therefore needs only in-process coordination (asyncio.Lock is sufficient; flock is still a fine code template at `~/src/qwen-2.5-localreview/gpu_lock.py`).

**Full narrative — VRAM math, model selection rationale, things we tried and rejected (the fp8-KV story especially), things to try later — lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md).** Read that before bumping a model, swapping an engine, or adding a tuning flag.

## External engines

External engines that daydream calls over HTTP but does not vendor as code (ComfyUI, vLLM, future image-gen / LLM backends) follow one pattern so the project tree stays self-contained on disk while staying git-light:

```
external/<engine>/         # upstream repo, gitignored; cloned by bootstrap
external/<engine>/.venv/   # the engine's own python venv (separate from daydream's .venv)
external/<engine>/models/  # large model files where the engine expects them
```

Each engine gets:
- `bin/<engine>-bootstrap` — idempotent: clone if missing, venv if missing, pip install requirements, download model files. Re-runs are no-ops on every step. Safe to invoke whenever you're not sure if it's installed.
- `bin/game <engine>-up` / `<engine>-down` — daemon lifecycle, mirroring `bin/game up` / `down` for FastAPI. PID file under `$XDG_RUNTIME_DIR/daydream-<env>/<engine>.pid`, log alongside.
- `bin/game status` — shows the daydream-managed PID when up; falls back to a reachability probe so externally-launched instances are still detected.
- A config function in `daydream/config.py` (e.g. `comfyui_base_url()`) that returns the endpoint, overridable via env var, so daydream Python code never hardcodes `localhost:<port>`.

`bin/game up` does NOT auto-start engines (they're heavy: ComfyUI loads SDXL into VRAM, vLLM loads Qwen). Operator brings them up explicitly when needed, or uses `bin/game up-all` for the bundled boot (FastAPI synchronously + vLLM/ComfyUI lazy-launched in the background). Daydream's graceful-failure paths (`narrate "the dream is foggy"` for LLM down, "painting..." overlay for ComfyUI down) mean the game still runs at every engine combination.

`external/` is gitignored entirely. No submodules, no nested .git tracking — bootstrap re-creates the whole thing from a single command, so losing it is cheap.

### Pattern exception: HF cache

Engines that use HuggingFace's model hub (vLLM is the obvious case) put their model files in `~/.cache/huggingface/hub`, NOT under `external/<engine>/models/`. The shared HF cache is a zat.env convention (never override `HF_HOME`) and trumps the per-engine self-containment when the two collide. Bootstraps for HF-backed engines pre-cache via `huggingface_hub.snapshot_download` so first-launch is fast.

ComfyUI does NOT use the HF cache (its `models/` dir lives under `external/ComfyUI/`); vLLM does. Future engines decide case by case.

### Pattern exception: foreground engines (qpeek)

Not every external engine is a daemon. `qpeek` (the human-aesthetic-eval engine used by `bin/game test human`) is a **foreground** process: `bin/qpeek-bootstrap` clones and installs like every other engine, but there is no `bin/game qpeek-up/down` and no PID file — `bin/game test human` invokes qpeek directly as a blocking subprocess and parses the JSON rating array from its stdout. Design reason: qpeek is transient by nature (human-interactive, one-shot per review). Forcing it through a daemon lifecycle would add complexity the use case doesn't need.

## ComfyUI (v1 image gen)

The first engine on the pattern. Binds `127.0.0.1:8188` by default since daydream is the only consumer; override `DAYDREAM_COMFYUI_HOST=0.0.0.0` to expose on the tailnet (e.g., for the ComfyUI web UI from another machine), or SSH-tunnel: `ssh -L 8188:localhost:8188 <host>`. Override the URL daydream calls with `DAYDREAM_COMFYUI_BASE_URL` or the port via `DAYDREAM_COMFYUI_PORT`.

One-time install:

```sh
bin/comfyui-bootstrap        # clones, venv, pip install, downloads SDXL + LoRA (~10 min, ~13 GB)
```

Daily lifecycle:

```sh
bin/game comfyui-up          # start daemon (PID owned by daydream)
bin/game comfyui-down        # stop daemon
bin/game status              # shows pid + reachability when running
```

The shared workflow JSON at `daydream/images/workflows/painterly_room.json` is read by both `daydream/images/client.py` (room backgrounds) and `daydream/images/cli.py` (`bin/game image-test`). The current pick is SDXL base 1.0 + `ostris/watercolor_style_lora_sdxl` (`watercolor_v1_sdxl.safetensors`); to swap, edit `lora_name` in the workflow and both call sites pick it up. Use `bin/game image-test "<prompt>" --lora <new>.safetensors` for cheap A/B before committing the swap.

## vLLM (v1 LLM)

The second engine on the pattern. Different from ComfyUI in that vLLM is a pip package (no upstream clone), and its model weights live in the shared HF cache (per the exception above). Binds `127.0.0.1:8000` by default since daydream is the only consumer; override `DAYDREAM_VLLM_HOST=0.0.0.0` to expose on the tailnet. Override the URL daydream calls with `DAYDREAM_LLM_BASE_URL` or the port via `DAYDREAM_VLLM_PORT`. Default model is Qwen 2.5 7B Instruct AWQ (`DAYDREAM_VLLM_MODEL` to override).

One-time install:

```sh
bin/vllm-bootstrap           # venv, pip install vllm, pre-cache Qwen 2.5 7B AWQ (~5 GB)
```

Daily lifecycle:

```sh
bin/game vllm-up             # start daemon (PID owned by daydream)
bin/game vllm-down           # stop daemon
```

`bin/game vllm-up` launches with `--gpu-memory-utilization 0.45` (~9 GB on the 20 GB card) leaving headroom for SDXL during inference. Both daemons can stay resident under the arbiter; the arbiter's lock means only one inference runs at a time, so the peak is bounded by whichever inference is in flight, not the sum. `--max-model-len 8192` is the default context window; increase if v2 long-context needs warrant it (raises KV cache memory).

daydream calls vLLM through `daydream/llm/client.py` via `litellm.acompletion` against the OpenAI-compatible endpoint, all wrapped in `daydream.gpu.arbiter.acquire()` so it serializes with image-gen on the same GPU.

### vLLM tunings on Ada

These flags ride on every `bin/game vllm-up`. Most are inherited from `~/src/qwen-2.5-localreview`, which did careful experiments on this same RTX 4000 SFF Ada (compute capability 8.9). Treat them as load-bearing: don't drop one without re-running `tools/arbiter-smoke.py` and confirming both decode latency AND output quality (the smoke prompts a tight-format JSON echo specifically to catch quality regressions). Full rationale per flag, plus the alternatives we considered, lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md).

| Flag | Why |
|---|---|
| `--enforce-eager` | Disables CUDA-graph capture. Avoids a graph-induced OOM localreview hit on this card (their commit 8321af1). Trades a small bit of perf for stability; keep until proven unnecessary. |
| `VLLM_LOGGING_LEVEL=ERROR` | Suppresses vLLM's verbose startup banner. Override with `VLLM_LOG_LEVEL=INFO bin/game vllm-up` when debugging. |
| `vllm==0.19.1` (pinned in bootstrap) | The version localreview validated against. Bumping is allowed but should be paired with a re-run of the arbiter smoke. |

**Model choice (Qwen 2.5 7B Instruct AWQ).** AWQ INT4 weights are the right pick on this VRAM budget: ~5 GB resident leaves room for SDXL's 7-10 GB during image-gen inference. Switching to FP8 weights (Ada-supported) would push past 7 GB resident with marginal gain over AWQ + Marlin kernels at single-stream decode latency.

### `--kv-cache-dtype fp8_e4m3` deliberately NOT enabled

Localreview gets a documented **+58% decode TPS / ~0.9 GB freed VRAM** from FP8 KV cache on their 14B Coder. We tried it on Qwen 2.5 7B Instruct AWQ and it deterministically broke tight-format JSON adherence — the model started fine then looped `!***` garbage tokens. The 14B has the parameter capacity to absorb FP8 KV's precision loss; the 7B does not.

Re-enable FP8 KV cache only after one of:
1. Moving to a >=14B model that fits our VRAM budget (would require swapping SDXL out during LLM inference; significantly more arbiter complexity).
2. Shipping calibrated per-channel FP8 KV scales (vLLM supports loading them; needs a one-time calibration pass over a representative dataset).
3. Confirming a future Qwen / Llama 7B variant tolerates fp8_e4m3 KV by re-running `tools/arbiter-smoke.py` and getting clean JSON across all five turns.

The smoke harness's choice of a strict-JSON LLM probe is intentional precisely so this regression surfaces immediately when someone tries to re-add the flag.

## NPC memory

Per-world NPC dialogue memory at `daydream/memories.py`. `capture(npc_id, world_id, text, source_event_seq=None)` and `retrieve(npc_id, world_id, query, k=3)` are sync, fail-closed (None / [] + log on any failure), and CPU-only — they never take the GPU arbiter. Embeddings via `sentence-transformers` BGE-small (`BAAI/bge-small-en-v1.5`, 384-dim) on CPU, lazy-loaded on first call, stored as raw float32 BLOBs in the per-world `memories` table (migration 009). Retrieval ranks by `cosine_similarity * exp(-age_hours / 24)`; the constant lives in `DAYDREAM_MEMORY_DECAY_HOURS`. v0 deliberately keeps it SQLite-only; LanceDB is the v1 path once memory counts cross ~10K per NPC.

The data-skill pipeline (`daydream/skills/data.py`) calls `retrieve` before Jinja render (the `memories` template variable is always present, possibly `[]`) and `capture` after a successful narrate-effect dispatch. Skill-name → NPC-id mapping is `f"t-{skill_name}"`; skills with no matching NPC row (e.g., `forge`) skip both phases.

One-time setup: `bin/memory-bootstrap` installs `sentence-transformers` against the PyTorch CPU wheel index (~200 MB vs ~2 GB for default CUDA wheels) and pre-caches BGE-small in the shared HF cache. Idempotent; skip-if-present. Bootstrap is optional — the dialogue path keeps working without it (capture/retrieve fail closed and NPCs just have no memory). Toggle via `DAYDREAM_MEMORY_ENABLED` (default `1` in production; `0` in `tests/conftest.py`); tests that exercise memory monkeypatch `daydream.memories._embed` to inject deterministic vectors so the suite never loads the real model.

## Image generation API

Single entry point: `daydream.images.client.generate_image(target, *, model=None, lora=None, seed=None, base_url=None) -> Path`. The target is a discriminated union — `PersistentTarget` or `EphemeralTarget` — and the persistent vs ephemeral distinction lives there as a first-class concept rather than as two parallel functions.

**`PersistentTarget(world_id, target_kind, target_id, seed, prompt_suffix="")`** is bound to an in-world entity (a room, in v1; toons / items later via `target_kind`). Output lands at `images/cache/{world}/{kind}/{id}/{combined_hash}.png` where the combined hash folds in seed text + canonical workflow JSON. On cache miss: render, write, record to `generated_assets`. On cache hit: return immediately, no re-record. Recording is REQUIRED here — if the DB isn't initialized, the call raises (production WS path always has DB initialized; this catches programming bugs).

**`EphemeralTarget(name, prompt, with_whimsy_suffix=True, out_path=None)`** is for one-off output: aesthetic A/B, debugging, scratch. Output lands at `images/ephemeral/{safe_name}-{prompt_hash}.png` (deterministic per prompt so re-runs overwrite, which is what A/B work wants). Never recorded. Works with no DB initialized — the `bin/game image-test` CLI takes this path.

Both paths share the same workflow build, the same ComfyUI HTTP layer (`_execute_workflow` is the single mock point), and the same arbiter contract: callers MUST hold `daydream.gpu.arbiter.acquire()` for the duration of any `generate_image` call. The two callers in production (WS layer, image-test CLI) do this; `tools/arbiter-smoke.py` does it; tests bypass via `@pytest.mark.real_image_gen` and mock `_execute_workflow`.

## Generated assets

Every persistent generation lands a row in the per-world `generated_assets` table. The table is the durable provenance index over the cache layout — given a world, you can answer "what was generated, with which model + LoRA + workflow, from which prompt, how big on disk, when?" without scanning the filesystem.

**File layout:**
```
~/data/daydream/
  worlds-{env}/live.db                                # per-env DB; holds generated_assets
  images/cache/{world}/{kind}/{id}/{combined_hash}.png   # persistent output
  images/ephemeral/{safe_name}-{prompt_hash}.png      # ephemeral output (no row)
  archives/{world}-{ts}.tar.gz                        # bin/game world archive output (full bundle)
  snapshots/{world}-{ts}.db                           # bin/game world snapshot output (DB-only)
```

The cache key `combined_hash = sha256(seed_hash + workflow_hash)` so editing the seed OR the workflow JSON (sampler tweaks, LoRA strength, resolution) busts the cache and triggers regen. The recorded `workflow_hash` column lets you query "which assets came from which workflow version" later. The `target_kind` segment in the path prevents slug collision when NPC portraits land alongside room backgrounds.

**Schema (per-world):** `id, asset_kind, target_kind, target_id, target_seed, seed_hash, file_relpath, model, lora, prompt_text, generated_at, file_bytes, world_id, pinned, workflow_hash`. The `pinned` column is the future-GC escape hatch: a hero image that should never be auto-cleaned can be marked via `assets.pin_asset(id)`. Used by zero code today; in place so the first gardening pass needs no migration.

**Operator commands** (all under `bin/game world`, dispatch via `daydream/admin.py`):

```sh
bin/game world list                              # worlds + per-world asset count + cache footprint
bin/game world archive <world_id>                # checkpoint WAL, tar DB + cache + manifest → archives/
bin/game world restore <archive.tar.gz> --yes    # validate manifest, untar into data_dir (refuses if live DB exists)
bin/game world snapshot <world_id>               # checkpoint WAL, copy live DB → snapshots/{world}-{ts}.db (DB-only, no cache/manifest)
bin/game world snapshot-restore <snap.db> --yes  # install a snapshot as the live DB (refuses to overwrite; refuses newer schema)
bin/game world swap <target.db>                  # LIVE hot-swap the running server's world to target.db (no restart; clients re-snapshot)
bin/game world verify [world_id]                 # report orphan rows (file missing) + orphan files (no row)
bin/game world delete <world_id> --yes           # cascade DELETE rows (filtered by world_id) + rm -rf cache dir
bin/game world load <envelope.json>              # KEYLESS: build a world DB from an Opus-authored JSON envelope (no API key)
```

`archive` runs `PRAGMA wal_checkpoint(TRUNCATE)` before the tar so a hot DB's most recent transactions are captured (without this, anything in `live.db-wal` would be missed). It writes a `MANIFEST.json` to the archive root recording `archive_format_version`, `schema_version`, `world_id`, `asset_count`, `asset_bytes`, `created_at`. `restore` validates the manifest before extracting; refuses archives produced by a newer schema than this code knows about, and refuses to overwrite an existing live DB.

`verify` is diagnostic only — it never deletes. Reports two kinds of inconsistencies: rows whose `file_relpath` no longer exists on disk, and PNG files in the cache dir that have no matching row. Both happen naturally: the legacy meadow PNG from before this turn's cache layout change is exactly an orphan-file. Future GC tooling will read these reports.

**Extending to other asset kinds.** The schema's `asset_kind` (`'image'` for now) and `target_kind` (`'room'`, `'toon'`, `'item'`) columns are the extensibility hooks. NPC portraits land as `target_kind='toon'` rows, no migration needed. Regenerated text outputs (e.g., room descriptions written back into `rooms.description_cached`) would be `asset_kind='text'` and need a small schema relaxation (`file_relpath` becomes nullable; an inline-text column joins it). That's the next migration whenever LLM-driven text caching becomes load-bearing.

**`snapshot`/`snapshot-restore` vs `swap` vs `archive`/`restore`.** `snapshot` (above) is the fast, DB-only point-in-time copy: it WAL-checkpoints the live DB and copies just the `.db` file to `snapshots/{world}-{ts}.db` — no per-world cache, no `MANIFEST.json`, no tarball. `snapshot-restore` installs such a file as the live DB OFFLINE: it refuses to overwrite an existing live DB and so requires the server down. `swap` is the ONLINE counterpart: it talks to the running server's `POST /api/world/swap` (the offline CLI cannot reach the in-process live connection / drift task), which stops drift, performs a synchronous-and-therefore-atomic close+install+reopen of the live connection onto the target (`daydream/db.py:swap_live_db`, failure-safe: a failed swap restores the original world), restarts drift, and broadcasts a `WORLD_CHANGED` control signal (`daydream/events.py`) so each connected WS client re-snapshots against the new world. Both restore paths read the target's own `_migrations` table and refuse a newer-than-known schema. `archive`/`restore` is the heavyweight bundle — full DB + per-world cache + manifest, suitable for shipping a world to another box. (The graceful SPA transition for `swap` — a "the dream shifts" overlay and re-picking a toon absent from the new world — is the named follow-up; today the client receives a fresh `state_snapshot`.)

## Aesthetic

Cozy, soft, painterly. Spiritfarer / A Short Hike. NOT pixel art, NOT crunchy 8-bit. Bake this into placeholder PNGs and any narration prompts. The durable tone bible is [`WHIMSY.md`](WHIMSY.md) at the project root — read it before drafting any narration prompt template, image-gen prompt suffix, or asset choice. The image-gen prompt suffix lives both in `WHIMSY.md` (`## Prompt suffix`) and as `WHIMSY_PROMPT_SUFFIX` in `daydream/images/client.py`; `tests/test_whimsy_prompt_suffix.py` catches drift between the two.

## Tests

`pytest` from the project root. Tests must not require GPU or a running vLLM; mock the LLM client. Slow/integration tests that boot the server with a stubbed LLM are fine if marked. Tests that need the real arbiter path opt in via `@pytest.mark.real_image_gen` (see `tests/conftest.py`).

For live-stack verification (vLLM and ComfyUI both up), `tools/arbiter-smoke.py` runs 5 alternating LLM + image requests through the real call paths, asserts no OOM under a 90 s wall-clock budget, AND probes LLM output quality with a strict-JSON echo. The JSON probe is what caught the fp8-KV regression on 7B models documented in [`docs/gpu-and-models.md`](docs/gpu-and-models.md). Re-run the smoke after any vLLM version bump, model swap, or tuning-flag change.

## Commits

Per global convention: attribute commits to `user.name` only, no Co-Authored-By trailers. Work in small committable increments; verify build + tests pass before adding new work. Push only when explicitly asked.

## Keeper images (`docs/pretty/`)

`docs/pretty/` is the durable, git-tracked home for image outputs worth keeping (README hero shots, future docs illustrations). Day-to-day output of `bin/game image-test` and the room-background cache live under `~/data/daydream/images/` and are ephemeral.

**Convention:** when the user says **`pretty <filename-or-fragment>`** in conversation, that means: find the file (typically under `~/data/daydream/images/test/<name>` or `~/data/daydream/images/cache/...`, glob-match the fragment if needed), copy it to `docs/pretty/` with a clean human-readable name, and commit. If the user does not specify where it should be referenced, ask once before adding it to README.md or other docs.

## Reference projects on this box

- `~/src/qpeek/`: FastAPI server skeleton, project layout, CLAUDE.md style.
- `~/src/qwen-2.5-localreview/`: vLLM warm-process lifecycle (`warm.py`), flock GPU mutex (`gpu_lock.py`), `gpu-release` handshake script. The arbiter pattern was inspired here; their commit history is the prior art for our Ada tunings (their `setup.sh` pins `vllm==0.19.0`, the `LLM(...)` call site in `review.py` documents their `kv_cache_dtype="fp8_e4m3"` + `enforce_eager=True` choices and the experiment commits that justify them).
