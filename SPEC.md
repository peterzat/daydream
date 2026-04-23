## Spec — 2026-04-23 — v1: image-gen pipeline

**Goal:** Replace the v0 watercolor placeholder with real per-room AI-generated backgrounds using SDXL base + a watercolor LoRA via ComfyUI, gated by a flock-based GPU arbiter that serializes vLLM and image-gen on the single 20 GB GPU. Anchor the aesthetic with a committed `WHIMSY.md` tone bible and a `bin/game image-test` harness so swapping models or LoRAs stays a one-liner.

### Acceptance Criteria

- [ ] **WHIMSY.md drafted as the tone bible.** `WHIMSY.md` at the project root contains: aesthetic touchstones (Spiritfarer, A Short Hike), explicit warm-painterly palette guidance, 1-2 narration voice samples, banned moods (pixel-art, crunchy 8-bit, grimdark, sexual, violence-toward-toons), and a reusable "prompt suffix" string. A test verifies the file exists and contains each named section.
- [ ] **`bin/game image-test "<prompt>"` produces a painterly PNG.** The harness writes a PNG at a deterministic path under `~/data/daydream/images/`, at least 512x512 px, in under 30 s end-to-end on this box. Output is visibly painterly (soft, warm; not pixel-art, not crunchy 8-bit) per the WHIMSY anchor (human-verified). `--model X` and `--lora Y` flags swap pipeline pieces without code edits.
- [ ] **Flock-based GPU arbiter serializes vLLM and image-gen.** `daydream/gpu/arbiter.py` (ported from `~/src/qwen-2.5-localreview/gpu_lock.py`) provides an exclusive lock that both LLM and image-gen call sites acquire and release. A live-GPU smoke test (5 alternating requests: LLM, image, LLM, image, LLM) completes without OOM, without a stuck "permanently fogged" LLM state, and within 90 s wall-clock total on this box.
- [ ] **Room backgrounds generate and cache per `(world_id, room_id, seed_hash)`.** First entry to a room without a cached background enqueues an async generation job. The cached image lives at a deterministic path under `~/data/daydream/images/cache/{world}/{room}/{hash}.{png|webp}`. Subsequent visits with the same room seed serve the cached file without re-generating. Editing the room's seed changes the hash and re-triggers generation; the previously cached file remains on disk (no destructive deletes).
- [ ] **SPA shows a "painting..." state and swaps the background when the image is ready.** When a room has no cached image, the SPA renders an explicit placeholder (textual "painting..." or animated indicator) at the room background slot. When the server emits a new `room_image_ready` event, the SPA swaps the background `<img>` `src` to the generated file without a full page reload.
- [ ] **LLM continues to work after image-gen cycles.** Following any image-gen run, the next LLM-routed input (e.g., "look around") completes within 15 s cold-load latency on this box and routes correctly (returns a known skill or `none` as appropriate). No permanent "the dream is foggy" state from a stuck arbiter or perpetually unloaded model.
- [ ] **ComfyUI workflow JSON is committed and used by both call sites.** A workflow file under `daydream/images/workflows/` defines the SDXL base + watercolor LoRA pipeline. Both `bin/game image-test` and the room-background generator load the same workflow file (no inline duplication of the pipeline definition). Replacing the workflow file changes both call sites' output.
- [ ] **Test suite stays green without a GPU.** `pytest` passes with image-gen mocked at the client boundary. New coverage at minimum: cache-key hashing test, cache hit/miss path test, GPU arbiter contract test (acquire/release order, double-acquire blocks the second caller), and the `room_image_ready` event flow with a stub image client. No new test requires vLLM, ComfyUI, or the GPU.

### Context

**Adopted from BACKLOG entry** `image-gen-pipeline` (now annotated `(ACTIVE in spec 2026-04-23)` in BACKLOG.md). Long-form architectural detail lives in `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md` (Architecture / Top risks sections especially).

**Aesthetic compass (locked in v0; do not drift).** Spiritfarer / A Short Hike: cozy, warm, painterly, soft edges. WHIMSY.md is the durable home for this; every prompt template downstream references it. Explicitly NOT pixel-art, NOT crunchy 8-bit, NOT melancholic. Per the plan's risk #1, this rules out SDXL Turbo (its distillation fights soft-watercolor wash) and pixel-art LoRAs. Default to SDXL base + a watercolor / storybook LoRA at 20-25 steps; if the per-image latency is unworkable, the documented fallback is SD 1.5 + watercolor LoRA (lower VRAM, often more Spiritfarer-y).

**GPU posture.** 20 GB VRAM ceiling on this box. Daydream is assumed to be the only GPU consumer (qwen-2.5-localreview's warm server is off in its `.env` and stays that way; see CLAUDE.md). Daydream's own Qwen 2.5 7B Q4 (~6-8 GB) plus SDXL base during inference (~10-12 GB) sums to roughly 16-20 GB, tight enough that resident coexistence risks OOM under burst, so serialize via the arbiter is the safe default. If a careful VRAM budget later shows resident coexistence is reliable, that is an acceptable optimization, but ship serialize first. The arbiter scope is in-process only (no external process to coordinate with); the flock pattern at `~/src/qwen-2.5-localreview/gpu_lock.py` is still a clean code template, but `asyncio.Lock` would work equally well here. The `daydream/llm/client.py` call site already exists as a single chokepoint so the wrap-in is one diff.

**ComfyUI as a separate process.** ComfyUI runs in its own venv as a separate daemon (default port 8188), called via HTTP. Mirror the vLLM pattern in `bin/game`: detect ComfyUI presence in `status`, document the launch command, do not auto-start in `bin/game up` for v1 (separate sub-command or just a documented manual launch). Image-gen requests serialize through the GPU arbiter regardless of which process runs them.

**Where cached images live and how they are served.** `~/data/daydream/images/cache/{world}/{room}/{hash}.{png|webp}` (never in the project tree). FastAPI mounts a static route over the cache root so `<img src="/cache/{world}/{room}/{hash}.png">` works from the SPA. Path traversal protection is acceptable at "validate-world-and-room-IDs" level given friend-scope security; the v2 multi-user spec will tighten if needed.

**zat.env conventions to respect.** HF model cache shared at `~/.cache/huggingface`; never override `HF_HOME` (per `ml-gpu.md`). SDXL base + the chosen watercolor LoRA download into that cache and are reusable across projects. Bind `0.0.0.0`. Single shared password (`DAYDREAM_PASSWORD` from `.env`) still gates everything. No Co-Authored-By trailers in commits. Persistent state lives under `~/data/daydream/`, never in the project tree.

**Coding practices (zat.env carry-overs).** Work in small committable increments; verify build + tests pass before adding new work. When adding or changing functionality, write or update tests in the same increment. Do not push or modify remote state without explicit user instruction. The `bin/game image-test` harness exists specifically so aesthetic A/B swaps stay cheap (plan's risk #1 mitigation): use it before locking in any LoRA choice.

**Out of scope for this spec** (deferred; do not build):
- **Item sprites.** BACKLOG entry's description includes them, but the room-background path is the v1 demo. Item sprites can be a tiny follow-up backlog entry once the cache + workflow patterns are in place.
- **Multi-room navigation.** Separate backlog entry; without it, image-gen demos with one room only.
- **Bootstrap-via-Opus.** Separate backlog entry; this spec uses the existing hand-seeded bunny world.
- **Data skills, NPC drift, NPC memory, world snapshot, multi-env layout.** All separate backlog entries.
- **Painterly Svelte UI polish.** Vanilla TS SPA stays for v1; the "painting..." placeholder is a one-line CSS state, not a component refactor.
- **Per-character sprite consistency (IP-Adapter).** Plan calls this out but it is item-sprite territory; defer with item sprites.

**Critical files to create or modify:**

- `/home/peter/src/daydream/WHIMSY.md` (new)
- `/home/peter/src/daydream/daydream/gpu/__init__.py` (new)
- `/home/peter/src/daydream/daydream/gpu/arbiter.py` (new; port from `~/src/qwen-2.5-localreview/gpu_lock.py`)
- `/home/peter/src/daydream/daydream/images/__init__.py` (new)
- `/home/peter/src/daydream/daydream/images/client.py` (new; ComfyUI HTTP client)
- `/home/peter/src/daydream/daydream/images/cache.py` (new; cache key, paths, async enqueue)
- `/home/peter/src/daydream/daydream/images/workflows/painterly_room.json` (new; ComfyUI workflow)
- `/home/peter/src/daydream/daydream/llm/client.py` (modify; acquire/release the arbiter lock around `litellm.acompletion`)
- `/home/peter/src/daydream/daydream/api/ws.py` (modify; on `state_snapshot`, check cache; if miss, enqueue image-gen and emit `room_image_ready` when done)
- `/home/peter/src/daydream/daydream/server.py` (modify; mount `/cache` static route over `~/data/daydream/images/cache/`)
- `/home/peter/src/daydream/web/assets/main.js` (modify; render "painting..." when no cached image; swap `room-bg` `src` on `room_image_ready`)
- `/home/peter/src/daydream/bin/game` (modify; add `image-test` subcommand and ComfyUI presence detection in `status`)
- `/home/peter/src/daydream/tests/test_arbiter.py`, `tests/test_images.py`, `tests/test_whimsy.py` (new; all GPU/network-free via mocks and file checks)

---
*Prior spec (2026-04-22): v0 (the smallest dream) shipped 10/10 acceptance criteria — lifecycle, auth, DB, websocket, LLM-routed skills, persistence, watercolor placeholder, mocked-LLM tests.*

<!-- SPEC_META: {"date":"2026-04-23","title":"v1: image-gen pipeline","criteria_total":8,"criteria_met":0} -->
