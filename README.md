# Daydream

![A quiet meadow at dusk, watercolor — generated locally via SDXL + watercolor LoRA on the v1 image-gen pipeline](meadow-at-dusk.png)

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally-generated daydream world that all players share and persistently mutate over time. Cozy goals (Animal Crossing-like self-driven storytelling) with MUD-style gameplay (Zork-like text, free-form input, contextual UI buttons).

The image above is the image-gen pipeline's first real output: prompt seeded from the meadow room, SDXL base + a watercolor LoRA via local ComfyUI, gated by the GPU arbiter, ~6 s of render on the dev box's RTX 4000 SFF Ada. It lives at the project root as a historical artifact — the cache layout has since changed (the file is no longer regenerable bit-for-bit by the current code path), but the rendering it captures is the moment v1 first proved itself. The aesthetic anchor is in [`WHIMSY.md`](WHIMSY.md): Spiritfarer / A Short Hike, soft and painterly.

## Status

v0 (*the smallest dream*) shipped 10/10. v1 (*image-gen pipeline*: SDXL base + watercolor LoRA via ComfyUI behind a GPU arbiter, vLLM serving Qwen 2.5 7B Instruct AWQ) shipped 8/8 with `tools/arbiter-smoke.py` validating live LLM ↔ image-gen serialization in 9 s on this hardware. Currently between spec turns; the v1 close-out proposal in [`SPEC.md`](SPEC.md) names three candidate next slices (`multi-room-navigation`, `data-skills-cli` + `safety-baseline-v1`, or `npc-drift-loop`). Roadmap and deferred entries live in [`BACKLOG.md`](BACKLOG.md).

## Aesthetic

Cozy, soft, painterly. Reference touchstones: Spiritfarer and A Short Hike. NOT pixel-art, NOT crunchy 8-bit, NOT melancholic. The durable tone bible is [`WHIMSY.md`](WHIMSY.md).

## Run

First time:

```sh
cd ~/src/daydream
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
$EDITOR .env   # set DAYDREAM_PASSWORD; review DAYDREAM_ACCESS
```

Daily:

```sh
bin/game up        # start the FastAPI server on 0.0.0.0:54321 (override with DAYDREAM_PORT)
bin/game status    # process state, port reachability, access mode, where state lives
bin/game logs      # tail recent FastAPI output
bin/game down      # stop
bin/game world     # list / archive / delete worlds + their generated assets
```

Visit `http://<host>:54321` from another tailnet device (or `http://localhost:54321` from the box) and enter your password. Re-running `up` while up, or `down` while down, is a no-op.

`DAYDREAM_PASSWORD` is the only required setting. If `.env` is missing or that variable is unset, the auth endpoint refuses every login (503) — there is no published default. `~/.config/daydream/secrets.env` (per-host, gitignored) overrides anything in project `.env`.

### Network access

`DAYDREAM_ACCESS` in `.env` controls who the FastAPI server will talk to:

- **`tailscale`** (default): the `AccessMiddleware` in `daydream/api/access.py` rejects any HTTP/WS client whose source IP is not in Tailscale's CGNAT range (`100.64.0.0/10`) or loopback. Tailnet members reach the game; the wider internet sees a 403 (or a WebSocket close 1008) even if the port is somehow exposed.
- **`public`**: middleware lets all clients through.

`DAYDREAM_ACCESS=public` is an "agree to be public" flag at the app layer — flipping it does NOT also open UFW. For traffic to actually arrive from the internet you also need `sudo ufw allow 54321/tcp` and (probably) public DNS pointing at the box. `bin/game status` prints a UFW-reminder warning when `public`.

Internal services (vLLM on 8000, ComfyUI on 8188) bind `127.0.0.1` by default — daydream is their only consumer. To reach ComfyUI's web UI from another machine, SSH-tunnel: `ssh -L 8188:localhost:8188 <host>`. Or override `DAYDREAM_COMFYUI_HOST=0.0.0.0` to expose on the tailnet.

## Optional engines: LLM and image gen

The three baked-in skills (`look`, `say`, `examine`) work without GPU or any external engine. Free-form text that does not match a baked-in skill is routed through an LLM interpreter; with no vLLM running, those inputs gracefully narrate "the dream is foggy" instead of crashing. When a room has no cached background, the SPA shows a "painting..." overlay and queues an image-gen job; with no ComfyUI running the overlay disappears after the failed call and the placeholder stays. **The game runs at all engine combinations: neither, just LLM, just image-gen, or both.**

To enable, follow the same `external/<engine>/` pattern (full rationale in [CLAUDE.md "External engines"](CLAUDE.md#external-engines)):

```sh
# ComfyUI: ~13 GB on disk (SDXL base + watercolor LoRA), ~10 min one-time
bin/comfyui-bootstrap
bin/game comfyui-up         # bin/game comfyui-down to stop

# vLLM: ~5 GB model cache + ~3 GB pip deps, ~10 min one-time
bin/vllm-bootstrap
bin/game vllm-up            # bin/game vllm-down to stop
```

The aesthetic A/B harness `bin/game image-test "<prompt>" [--model X --lora Y]` produces a one-shot PNG via the same workflow JSON the room-bg generator uses. Use it before locking in any LoRA choice. Output lands at `~/data/daydream/images/test/`; promote keepers to `docs/pretty/` (see [CLAUDE.md "Keeper images"](CLAUDE.md#keeper-images-docspretty)).

For the live LLM ↔ image-gen serialization smoke (boots both engines, runs 5 alternating requests, asserts no OOM and clean output):

```sh
.venv/bin/python tools/arbiter-smoke.py
```

## Tests

```sh
.venv/bin/pytest
```

Tests do not require GPU, vLLM, or ComfyUI — the LLM client is mocked, the image client is mocked, and `tests/conftest.py` opts the test runner into `DAYDREAM_ACCESS=public` so TestClient passes through the access middleware. **153 passing** as of this commit, including the access-middleware contract (`tests/test_access_middleware.py`), the WHIMSY drift catcher (`tests/test_whimsy_prompt_suffix.py`), and the workflow-LoRA real-name check (`tests/test_workflow_real_lora.py`).

## Tech sketch

| Layer | Choice |
|---|---|
| Backend | Python 3.10 + FastAPI + websockets, single process tree |
| Persistence | SQLite per world (WAL), append-only event log as the spine; snapshots via file copy land in v1+ |
| LLM (optional) | vLLM 0.19.1 serving Qwen 2.5 7B Instruct AWQ, called via `litellm` so the same code path works against vLLM today and Cloudflare / OpenAI / Anthropic later |
| Image gen (optional) | SDXL base + `ostris/watercolor_style_lora_sdxl` via ComfyUI, GPU arbiter shared with vLLM |
| GPU arbiter | `daydream/gpu/arbiter.py` (`asyncio.Lock`); serializes LLM and image-gen on the 20 GB card |
| Frontend | Vanilla HTML / CSS / JS under `web/`, plain `<img>` tags (no Vite yet; Svelte polish is a backlog item) |
| Auth | Friend-scope: shared password from `.env` on a single port |
| Network access | `DAYDREAM_ACCESS` toggle in `.env`: `tailscale` (default) or `public` |
| Target hardware | Single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later |

The full GPU/ML narrative — VRAM math, model selection rationale, what we tried and rejected (the fp8-KV-cache story especially), what to try later — lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md). [`CLAUDE.md`](CLAUDE.md) is the operator/agent reference for project conventions, lifecycle, the External engines pattern, and the `pretty <filename>` shorthand for promoting image outputs.
