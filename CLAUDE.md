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

## ComfyUI (v1 image gen)

ComfyUI runs as a separate process at `http://localhost:8188` (override with `DAYDREAM_COMFYUI_BASE_URL`). `bin/game status` reports its presence; `bin/game up` does not auto-start it.

Operator install (one-time):

```sh
# Choose a directory outside this repo, e.g. ~/src/ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI ~/src/ComfyUI
cd ~/src/ComfyUI
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# SDXL base (~7 GB) -> models/checkpoints/sd_xl_base_1.0.safetensors
# Pick a watercolor / storybook LoRA from HF and drop in models/loras/
# Then update lora_name in daydream/images/workflows/painterly_room.json
.venv/bin/python main.py --listen 0.0.0.0 --port 8188
```

Operator launch (every session): the same `.venv/bin/python main.py --listen 0.0.0.0 --port 8188`. Daydream connects on demand and serializes via the arbiter so a player input is never racing an image-gen request for the same VRAM.

The shared workflow JSON at `daydream/images/workflows/painterly_room.json` is read by both `daydream/images/client.py` (room backgrounds) and `daydream/images/cli.py` (`bin/game image-test`). Update the LoRA name there once and both call sites pick it up.

## Aesthetic

Cozy, soft, painterly. Spiritfarer / A Short Hike. NOT pixel art, NOT crunchy 8-bit. Bake this into placeholder PNGs and any narration prompts. WHIMSY.md (the tone bible) drafts in v1 alongside the image-gen pipeline.

## Tests

`pytest` from the project root. Tests must not require GPU or a running vLLM; mock the LLM client. Slow/integration tests that boot the server with a stubbed LLM are fine if marked.

## Commits

Per global convention: attribute commits to `user.name` only, no Co-Authored-By trailers. Work in small committable increments; verify build + tests pass before adding new work. Push only when explicitly asked.

## Reference projects on this box

- `~/src/qpeek/`: FastAPI server skeleton, project layout, CLAUDE.md style.
- `~/src/qwen-2.5-localreview/`: vLLM warm-process lifecycle (`warm.py`), flock GPU mutex (`gpu_lock.py`), `gpu-release` handshake script. v1 arbiter ports from here.
