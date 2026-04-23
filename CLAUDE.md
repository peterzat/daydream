# CLAUDE.md — daydream

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally generated world that all players share and persistently mutate. See `SPEC.md` for the current v0 acceptance contract, `BACKLOG.md` for v1/v2, `README.md` for orientation.

## Conventions

- Python venv at `.venv/`. Never `pip install` outside the venv (`PIP_REQUIRE_VIRTUALENV=true` is set globally).
- Python 3.10. Pin `requires-python = ">=3.10"` in `pyproject.toml`.
- Bind services to `0.0.0.0` so Tailscale clients can reach them. Default port 8080. Per-env ports land in v2.
- Persistent state lives under `~/data/daydream/`, never in the project tree. Per-env layout (`worlds-dev/`, `worlds-preview/`, `worlds-prod/`) lands in v2; v0 just uses `worlds-dev/live.db`.
- HuggingFace cache is shared at `~/.cache/huggingface`. Never override `HF_HOME`.
- All `*.db`, `*.db-wal`, `*.db-shm` are gitignored. Live state never gets committed.

## Lifecycle

`bin/game up`, `bin/game down`, `bin/game status` are the only supported entry points. They drive a tmux- or systemd-user-unit-backed process group containing the FastAPI server and a vLLM warm process. Lands in increment 8 of v0.

## Auth

Single shared password sourced from the `DAYDREAM_PASSWORD` env var. `bin/game` loads `.env` at the project root (gitignored; see `.env.example`) and then `~/.config/daydream/secrets.env` (per-host overrides win). If neither sets `DAYDREAM_PASSWORD`, the auth endpoint refuses every login with a 503 — empty default never grants access. No per-user identity. Cookie-based session, no expiry in v0. The session-cookie signing secret comes from `DAYDREAM_SESSION_SECRET`; if unset, a per-install random secret is generated on first boot and persisted at `~/.config/daydream/session_secret` (mode 0600, gitignored). Friend-scope only; access to the box itself is the real gate (Tailscale, not Tailscale Funnel; not exposed to public DNS).

## GPU posture

20 GB VRAM ceiling on this box (RTX 4000 SFF Ada). Qwen 2.5 7B Q4 (~6-8 GB) is the v0 LLM. v1 adds SDXL base + a watercolor LoRA via ComfyUI behind a flock-free in-process arbiter at `daydream/gpu/arbiter.py` that serializes vLLM and image-gen calls. Keep all LLM calls behind `daydream/llm/client.py` and all image-gen behind `daydream/images/client.py` so the arbiter has exactly two call sites.

This project assumes Daydream is the only GPU consumer on this box. The `qwen-2.5-localreview` warm server is off (per its `.env`) and is assumed to stay off indefinitely; no external process competes for VRAM. The arbiter therefore needs only in-process coordination (asyncio.Lock is sufficient; flock is still a fine code template at `~/src/qwen-2.5-localreview/gpu_lock.py`).

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

## ComfyUI (v1 image gen)

ComfyUI is the first engine on the pattern above. Default endpoint `http://localhost:8188`; override with `DAYDREAM_COMFYUI_BASE_URL` or `DAYDREAM_COMFYUI_PORT`.

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

## Aesthetic

Cozy, soft, painterly. Spiritfarer / A Short Hike. NOT pixel art, NOT crunchy 8-bit. Bake this into placeholder PNGs and any narration prompts. WHIMSY.md (the tone bible) drafts in v1 alongside the image-gen pipeline.

## Tests

`pytest` from the project root. Tests must not require GPU or a running vLLM; mock the LLM client. Slow/integration tests that boot the server with a stubbed LLM are fine if marked.

## Commits

Per global convention: attribute commits to `user.name` only, no Co-Authored-By trailers. Work in small committable increments; verify build + tests pass before adding new work. Push only when explicitly asked.

## Keeper images (`docs/pretty/`)

`docs/pretty/` is the durable, git-tracked home for image outputs worth keeping (README hero shots, future docs illustrations). Day-to-day output of `bin/game image-test` and the room-background cache live under `~/data/daydream/images/` and are ephemeral.

**Convention:** when the user says **`pretty <filename-or-fragment>`** in conversation, that means: find the file (typically under `~/data/daydream/images/test/<name>` or `~/data/daydream/images/cache/...`, glob-match the fragment if needed), copy it to `docs/pretty/` with a clean human-readable name, and commit. If the user does not specify where it should be referenced, ask once before adding it to README.md or other docs.

## Reference projects on this box

- `~/src/qpeek/`: FastAPI server skeleton, project layout, CLAUDE.md style.
- `~/src/qwen-2.5-localreview/`: vLLM warm-process lifecycle (`warm.py`), flock GPU mutex (`gpu_lock.py`), `gpu-release` handshake script. v1 arbiter ports from here.
