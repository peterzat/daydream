# Daydream

![A quiet meadow at dusk, watercolor — generated locally via SDXL + watercolor LoRA on the v1 image-gen pipeline](docs/pretty/meadow-at-dusk.png)

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally-generated daydream world that all players share and persistently mutate over time. Cozy goals (Animal Crossing-like self-driven storytelling) with MUD-style gameplay (Zork-like text, free-form input, contextual UI buttons).

The image above is the v1 pipeline's first real output: prompt seeded from the meadow room, SDXL base + a watercolor LoRA via local ComfyUI, gated by the GPU arbiter. ~6 s of render on the dev box's RTX 4000 SFF Ada. The aesthetic anchor is in [WHIMSY.md](WHIMSY.md): Spiritfarer / A Short Hike, soft and painterly.

## Status

**v0 (the smallest dream) is shipped and playable.** One human authenticates with a shared password, sees the meadow with a watercolor placeholder background, types free-form text routed through a small skill registry, and has changes persist across restart. v1 (the image-gen pipeline: SDXL base + watercolor LoRA via ComfyUI behind a GPU arbiter) is the active spec — see [SPEC.md](SPEC.md). Roadmap and deferred entries live in [BACKLOG.md](BACKLOG.md). The long-form architectural plan is local-only at `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md`.

## Aesthetic

Cozy, soft, painterly. Reference touchstones: Spiritfarer and A Short Hike. NOT pixel-art, NOT crunchy 8-bit, NOT melancholic. `WHIMSY.md` (the tone bible) lands with v1.

## Run

First time:

```sh
cd ~/src/daydream
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
$EDITOR .env   # set DAYDREAM_PASSWORD to whatever shared word you like
```

Daily:

```sh
bin/game up        # start the FastAPI server on 0.0.0.0:54321 (override with DAYDREAM_PORT)
bin/game status    # what is running, port reachability, access mode, where state lives
bin/game logs      # tail recent FastAPI output
bin/game down      # stop
```

Then visit `http://<host>:54321` from another tailnet device (or `http://localhost:54321` from the box) and enter your password. Re-running `up` while already up, or `down` while already down, is a no-op.

`DAYDREAM_PASSWORD` is the only required setting. If `.env` is missing or that variable is unset, the auth endpoint refuses every login (503) — there is no published default. `~/.config/daydream/secrets.env` (per-host, gitignored) overrides anything set in project `.env`.

### Network access

`DAYDREAM_ACCESS` in `.env` controls who the FastAPI server will talk to:

- **`tailscale`** (default): the `AccessMiddleware` rejects any HTTP/WS client whose source IP is not in Tailscale's CGNAT range (`100.64.0.0/10`) or loopback. Tailnet members reach the game; the wider internet sees a 403 (or a WebSocket close 1008) even if the port is somehow exposed.
- **`public`**: middleware lets all clients through.

`DAYDREAM_ACCESS=public` is an "agree to be public" flag at the app layer — flipping it does NOT also open UFW. For traffic to actually arrive from the internet you also need to `sudo ufw allow 54321/tcp` and (probably) point public DNS at the box.

Internal services (vLLM, ComfyUI) bind `127.0.0.1` by default — daydream is their only consumer. To reach ComfyUI's web UI from another machine, SSH-tunnel: `ssh -L 8188:localhost:8188 <host>`. Override with `DAYDREAM_COMFYUI_HOST=0.0.0.0` if you want it on the tailnet directly.

## LLM (optional)

The three baked-in skills (`look`, `say`, `examine`) work without GPU. Free-form text that does not match a baked-in skill is routed through an LLM interpreter; with no vLLM running, those inputs gracefully narrate "the dream is foggy" instead of crashing.

vLLM follows the same `external/` engine pattern as ComfyUI:

```sh
bin/vllm-bootstrap           # one-time install: venv, pip install vllm, Qwen 2.5 7B AWQ (~5 GB)
bin/game vllm-up             # start the daemon (~10 s warmup)
bin/game vllm-down           # stop
```

Override the endpoint or model with `DAYDREAM_LLM_BASE_URL` / `DAYDREAM_VLLM_MODEL`. Operator notes in [CLAUDE.md](CLAUDE.md) under "vLLM".

## Image gen (v1, optional)

When a room has no cached background, the SPA shows a "painting..." overlay and the server enqueues an image-gen job. With no ComfyUI running the overlay disappears after the failed call and the placeholder stays; the rest of the game keeps working.

ComfyUI lives inside the project tree at `external/ComfyUI/` (gitignored, ~13 GB once installed). Two commands:

```sh
bin/comfyui-bootstrap        # one-time install: clone, venv, requirements, SDXL + watercolor LoRA (~10 min)
bin/game comfyui-up          # start the daemon; bin/game comfyui-down to stop
```

`bin/game status` shows the ComfyUI pid + reachability. The aesthetic A/B harness is `bin/game image-test "<prompt>" [--model X --lora Y]`; use it before locking in any LoRA choice. The engine pattern (and how vLLM will follow it) is documented in [CLAUDE.md](CLAUDE.md) under "External engines".

## Tests

```sh
.venv/bin/pytest
```

Tests do not require GPU or a running vLLM (the LLM client is mocked). 67 passing as of this commit.

## Tech sketch

- Backend: Python 3.10 + FastAPI + websockets, single process tree
- Persistence: SQLite per world (WAL), append-only event log as the spine; snapshots via file copy land in v1
- LLM (optional in v0): vLLM 0.19.1 serving Qwen 2.5 7B Instruct AWQ, called via `litellm` so the same code path works against vLLM today and Cloudflare / OpenAI / Anthropic later
- Image gen (v1): SDXL base + `ostris/watercolor_style_lora_sdxl` via ComfyUI, GPU arbiter shared with vLLM
- Frontend: vanilla HTML / CSS / JS under `web/`, plain `<img>` tags for sprites and backgrounds (no Vite yet; Svelte polish is a v1 backlog item)
- Friend-scope auth: shared password from `.env` on a single port behind `bin/game up`/`down`
- Target hardware: single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later

The full GPU/ML narrative — VRAM math, model selection rationale, what we tried and rejected (the fp8-KV-cache story especially), what to try later — lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md).
