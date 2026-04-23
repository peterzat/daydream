# Daydream

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally-generated daydream world that all players share and persistently mutate over time. Cozy goals (Animal Crossing-like self-driven storytelling) with MUD-style gameplay (Zork-like text, free-form input, contextual UI buttons).

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
bin/game up        # start the FastAPI server on 0.0.0.0:8080 (override with DAYDREAM_PORT)
bin/game status    # what is running, port reachability, where state lives
bin/game logs      # tail recent FastAPI output
bin/game down      # stop
```

Then visit `http://0.0.0.0:8080` (from the box) or `http://<host>:8080` (from another tailnet device) and enter your password. Re-running `up` while already up, or `down` while already down, is a no-op.

`DAYDREAM_PASSWORD` is the only required setting. If `.env` is missing or that variable is unset, the auth endpoint refuses every login (503) — there is no published default. `~/.config/daydream/secrets.env` (per-host, gitignored) overrides anything set in project `.env`.

## LLM (optional in v0)

The three baked-in skills (`look`, `say`, `examine`) work without GPU. Free-form text that does not match a baked-in skill is routed through an LLM interpreter; with no vLLM running, those inputs gracefully narrate "the dream is foggy" instead of crashing. To enable LLM routing, run a vLLM warm process serving an OpenAI-compatible endpoint at `http://localhost:8000/v1` (default; override with `DAYDREAM_LLM_BASE_URL` / `DAYDREAM_LLM_MODEL`).

## Tests

```sh
.venv/bin/pytest
```

Tests do not require GPU or a running vLLM (the LLM client is mocked). 67 passing as of this commit.

## Tech sketch

- Backend: Python 3.10 + FastAPI + websockets, single process tree
- Persistence: SQLite per world (WAL), append-only event log as the spine; snapshots via file copy land in v1
- LLM (optional v0; required v1+): vLLM serving Qwen 2.5 7B Instruct (Q4_K_M), called via `litellm` as a Python library
- Image gen (v1): SDXL base + watercolor LoRA via ComfyUI, GPU arbiter shared with vLLM
- Frontend: vanilla HTML / CSS / JS under `web/`, plain `<img>` tags for sprites and backgrounds (no Vite yet; Svelte polish is a v1 backlog item)
- Friend-scope auth: shared password from `.env` on a single port behind `bin/game up`/`down`
- Target hardware: single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later
