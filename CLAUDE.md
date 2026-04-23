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

Single shared password (default `REDACTED`) sourced from `~/.config/daydream/secrets.env` (gitignored). No per-user identity. Cookie-based session, no expiry in v0. The session-cookie signing secret comes from `DAYDREAM_SESSION_SECRET`; if unset, a per-install random secret is generated on first boot and persisted at `~/.config/daydream/session_secret` (mode 0600, gitignored). The published source default is never used to sign real cookies. Friend-scope only; access to the box itself is the real gate (Tailscale, not Tailscale Funnel; not exposed to public DNS).

## GPU posture

20 GB VRAM ceiling on this box (RTX 4000 SFF Ada). Qwen 2.5 7B Q4 (~6-8 GB) is the v0 LLM. v0 only loads the LLM; SDXL and the GPU arbiter come in v1. Keep all LLM calls behind `daydream/llm/client.py` so the v1 arbiter can swap in without touching call sites. The flock pattern to copy lives at `~/src/qwen-2.5-localreview/gpu_lock.py`.

This project assumes Daydream is the only GPU consumer on this box. The `qwen-2.5-localreview` warm server is off (per its `.env`) and is assumed to stay off indefinitely; no external process competes for VRAM. The v1 arbiter therefore needs only in-process coordination (asyncio.Lock is sufficient; flock is still a fine code template).

## Aesthetic

Cozy, soft, painterly. Spiritfarer / A Short Hike. NOT pixel art, NOT crunchy 8-bit. Bake this into placeholder PNGs and any narration prompts. WHIMSY.md (the tone bible) drafts in v1 alongside the image-gen pipeline.

## Tests

`pytest` from the project root. Tests must not require GPU or a running vLLM; mock the LLM client. Slow/integration tests that boot the server with a stubbed LLM are fine if marked.

## Commits

Per global convention: attribute commits to `user.name` only, no Co-Authored-By trailers. Work in small committable increments; verify build + tests pass before adding new work. Push only when explicitly asked.

## Reference projects on this box

- `~/src/qpeek/`: FastAPI server skeleton, project layout, CLAUDE.md style.
- `~/src/qwen-2.5-localreview/`: vLLM warm-process lifecycle (`warm.py`), flock GPU mutex (`gpu_lock.py`), `gpu-release` handshake script. v1 arbiter ports from here.
