# CLAUDE.md — daydream

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally generated world that all players share and persistently mutate. See `SPEC.md` for the current acceptance contract, `BACKLOG.md` for the deferred-ideas register, `README.md` for orientation, and [`docs/gpu-and-models.md`](docs/gpu-and-models.md) for the full GPU/ML decision narrative (model picks, what we tried and rejected, what to try later).

## Conventions

- Python venv at `.venv/`. Never `pip install` outside the venv (`PIP_REQUIRE_VIRTUALENV=true` is set globally).
- Python 3.10. Pin `requires-python = ">=3.10"` in `pyproject.toml`.
- User-visible services (the daydream FastAPI server) bind `0.0.0.0` so tailnet clients can reach them; default port `54321` (memorable, non-default — modest security-by-obscurity on a user-visible service). Override via `DAYDREAM_PORT`. Per-env ports land in v2.
- Internal services (vLLM, ComfyUI) bind `127.0.0.1` by default since daydream is their only consumer. Override with `DAYDREAM_VLLM_HOST` / `DAYDREAM_COMFYUI_HOST` to expose on the tailnet (e.g., for the ComfyUI web UI). For ComfyUI specifically, an SSH tunnel from your laptop is usually the right move: `ssh -L 8188:localhost:8188 <host>`.
- Persistent state lives under `~/data/daydream/`, never in the project tree. The active world is `worlds-dev/live.db`; per-env layout (`worlds-dev/`, `worlds-preview/`, `worlds-prod/`) lands in v2.
- HuggingFace cache is shared at `~/.cache/huggingface`. Never override `HF_HOME`.
- All `*.db`, `*.db-wal`, `*.db-shm` are gitignored. Live state never gets committed.

## Lifecycle

`bin/game up`, `bin/game down`, `bin/game status`, `bin/game logs` are the supported daydream-server entry points; `bin/game comfyui-up`/`down` and `bin/game vllm-up`/`down` manage the inference engines (see "External engines" below); `bin/game image-test "<prompt>"` is the aesthetic A/B harness for image gen. Each daemon command writes a PID file to `$XDG_RUNTIME_DIR/daydream-<env>/<process>.pid` and a log alongside; `bin/game status` reports liveness and reachability for all three processes plus the current `DAYDREAM_ACCESS` mode and a UFW-reminder warning when `public`.

## Auth

Single shared password sourced from the `DAYDREAM_PASSWORD` env var. `bin/game` loads `.env` at the project root (gitignored; see `.env.example`) and then `~/.config/daydream/secrets.env` (per-host overrides win). If neither sets `DAYDREAM_PASSWORD`, the auth endpoint refuses every login with a 503 — empty default never grants access. No per-user identity. Cookie-based session, no expiry in v0. The session-cookie signing secret comes from `DAYDREAM_SESSION_SECRET`; if unset, a per-install random secret is generated on first boot and persisted at `~/.config/daydream/session_secret` (mode 0600, gitignored).

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

`bin/game up` does NOT auto-start engines (they're heavy: ComfyUI loads SDXL into VRAM, vLLM loads Qwen). Operator brings them up explicitly when needed. Daydream's graceful-failure paths (`narrate "the dream is foggy"` for LLM down, "painting..." overlay for ComfyUI down) mean the game still runs without them.

`external/` is gitignored entirely. No submodules, no nested .git tracking — bootstrap re-creates the whole thing from a single command, so losing it is cheap.

### Pattern exception: HF cache

Engines that use HuggingFace's model hub (vLLM is the obvious case) put their model files in `~/.cache/huggingface/hub`, NOT under `external/<engine>/models/`. The shared HF cache is a zat.env convention (never override `HF_HOME`) and trumps the per-engine self-containment when the two collide. Bootstraps for HF-backed engines pre-cache via `huggingface_hub.snapshot_download` so first-launch is fast.

ComfyUI does NOT use the HF cache (its `models/` dir lives under `external/ComfyUI/`); vLLM does. Future engines decide case by case.

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
  archives/{world}-{ts}.tar.gz                        # bin/game world archive output
```

The cache key `combined_hash = sha256(seed_hash + workflow_hash)` so editing the seed OR the workflow JSON (sampler tweaks, LoRA strength, resolution) busts the cache and triggers regen. The recorded `workflow_hash` column lets you query "which assets came from which workflow version" later. The `target_kind` segment in the path prevents slug collision when NPC portraits land alongside room backgrounds.

**Schema (per-world):** `id, asset_kind, target_kind, target_id, target_seed, seed_hash, file_relpath, model, lora, prompt_text, generated_at, file_bytes, world_id, pinned, workflow_hash`. The `pinned` column is the future-GC escape hatch: a hero image that should never be auto-cleaned can be marked via `assets.pin_asset(id)`. Used by zero code today; in place so the first gardening pass needs no migration.

**Operator commands** (all under `bin/game world`, dispatch via `daydream/admin.py`):

```sh
bin/game world list                              # worlds + per-world asset count + cache footprint
bin/game world archive <world_id>                # checkpoint WAL, tar DB + cache + manifest → archives/
bin/game world restore <archive.tar.gz> --yes    # validate manifest, untar into data_dir (refuses if live DB exists)
bin/game world verify [world_id]                 # report orphan rows (file missing) + orphan files (no row)
bin/game world delete <world_id> --yes           # cascade DELETE rows (filtered by world_id) + rm -rf cache dir
```

`archive` runs `PRAGMA wal_checkpoint(TRUNCATE)` before the tar so a hot DB's most recent transactions are captured (without this, anything in `live.db-wal` would be missed). It writes a `MANIFEST.json` to the archive root recording `archive_format_version`, `schema_version`, `world_id`, `asset_count`, `asset_bytes`, `created_at`. `restore` validates the manifest before extracting; refuses archives produced by a newer schema than this code knows about, and refuses to overwrite an existing live DB.

`verify` is diagnostic only — it never deletes. Reports two kinds of inconsistencies: rows whose `file_relpath` no longer exists on disk, and PNG files in the cache dir that have no matching row. Both happen naturally: the legacy meadow PNG from before this turn's cache layout change is exactly an orphan-file. Future GC tooling will read these reports.

**Extending to other asset kinds.** The schema's `asset_kind` (`'image'` for now) and `target_kind` (`'room'`, `'toon'`, `'item'`) columns are the extensibility hooks. NPC portraits land as `target_kind='toon'` rows, no migration needed. Regenerated text outputs (e.g., room descriptions written back into `rooms.description_cached`) would be `asset_kind='text'` and need a small schema relaxation (`file_relpath` becomes nullable; an inline-text column joins it). That's the next migration whenever LLM-driven text caching becomes load-bearing.

**Distinct from `snapshot-restore-commands` (BACKLOG).** That entry plans hot-swap-grade DB-only snapshots for the `world-hot-swap` flow. `archive/restore` here is the heavyweight bundle — full DB + per-world cache + manifest, suitable for shipping a world to another box.

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
