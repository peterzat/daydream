# Daydream

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally-generated daydream world that all players share and persistently mutate over time. Cozy goals (Animal Crossing-like self-driven storytelling) with MUD-style gameplay (Zork-like text, free-form input, contextual UI buttons).

## Status

Pre-implementation. The v0 acceptance contract lives in [SPEC.md](SPEC.md). The deferred roadmap (v1, v2, and the open question on player-authored skills) lives in [BACKLOG.md](BACKLOG.md). The long-form architectural plan is local at `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md` and not committed.

## Aesthetic

Cozy, soft, painterly. Reference touchstones: Spiritfarer and A Short Hike. NOT pixel-art, NOT crunchy 8-bit, NOT melancholic. WHIMSY.md (the tone bible) lands with the v1 image-gen pipeline.

## Tech sketch (planned)

- Backend: Python 3.11 + FastAPI + websockets, single process tree
- Persistence: SQLite per world (WAL), snapshot via file copy, append-only event log as the spine
- LLM: vLLM serving Qwen 2.5 7B Instruct (Q4_K_M), called via `litellm` as a Python library
- Image gen (v1): SDXL base + watercolor LoRA via ComfyUI, GPU arbiter shared with vLLM
- Frontend: Vite + Svelte SPA, plain `<img>` tags for sprites and backgrounds
- Friend-scope auth: shared password on a single port behind `bin/game up`/`down`
- Target hardware: single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later

## Run

Not yet runnable. v0 implementation will add `bin/game up/down/status`, the FastAPI server, and a hardcoded one-room SQLite migration.
