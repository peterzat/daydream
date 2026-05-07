# Daydream

![A quiet meadow at dusk, watercolor — generated locally via SDXL + watercolor LoRA on the v1 image-gen pipeline](meadow-at-dusk.png)

A small atmospheric multiplayer web game running on a single dev box. Players enter a procedurally-generated daydream world that all players share and persistently mutate over time. Cozy goals (Animal Crossing-like self-driven storytelling) with MUD-style gameplay (Zork-like text, free-form input, contextual UI buttons).

The image above is the image-gen pipeline's first real output: prompt seeded from the meadow room, SDXL base + a watercolor LoRA via local ComfyUI, gated by the GPU arbiter, ~6 s of render on the dev box's RTX 4000 SFF Ada. It lives at the project root as a historical artifact — the cache layout has since changed (the file is no longer regenerable bit-for-bit by the current code path), but the rendering it captures is the moment v1 first proved itself. The aesthetic anchor is in [`WHIMSY.md`](WHIMSY.md): Spiritfarer / A Short Hike, soft and painterly.

## Status

Latest stable cut: **v0.2.0**. Runs on a single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later. Test gates: 320 fast tests (`bin/game test short`, ~3 s) and 469 integration tests (`bin/game test medium`, ~5 s); both 100% green. Real-GPU drift probes run on-demand under `bin/game test long`.

What works today:

- Multi-room world (5 rooms, bidirectional exits) with two hand-authored NPCs (Rook the forge-keeper at `r-forge`; Iris the attic archivist at `r-attic`) you can talk to via the data-skill pipeline.
- NPC drift loop emits per-NPC narrate ticks while the player is elsewhere (every 5 min idle, 30 min when humans are connected). Drift composes each tick via the LLM from the NPC's recent memories + mood, falling back to a mood-bucketed canned pool when vLLM is down or the response trips the WHIMSY banlist. Suppressed in any room a human is currently in (so it never feels intrusive in-frame); each tick has a small chance to nudge the NPC's mood to a different bucket so the world drifts over hours of play.
- NPC dialogue memory: each Rook / Iris exchange is captured to a per-world `memories` table with a 384-dim CPU embedding (BGE-small via `sentence-transformers`), and the next turn pulls top-K by `cosine_similarity * exp(-age/24h)` and weaves them into the prompt as context. Fail-closed (capture/retrieve return `None` / `[]` if the embedder isn't installed) so the dialogue path stays warm even before `bin/memory-bootstrap` runs. CPU-only by construction; no GPU arbiter contention.
- Watercolor SDXL backgrounds for any room, generated locally via ComfyUI behind the GPU arbiter. vLLM (Qwen 2.5 7B Instruct AWQ) serves narration. Both engines optional; the game runs at all engine combinations.
- Voice-bench audit-trail harness (`bin/game voice-samples`) captures dated narrate samples for any model swap; four baselines in tree under `docs/pretty/voice-samples/` (pre-fix and post-fix AWQ plus two Mistral-Nemo Q4 failure modes — see Release notes).
- World admin: `bin/game world list / archive / restore / verify / delete` covers per-world archival, full-bundle ship-to-friend, integrity checks, cascade delete.
- Friend-scope auth (shared password, single port). `DAYDREAM_ACCESS=tailscale` (default) or `public`.

Pointers: full release narrative in [`## Release notes`](#release-notes) below; the GPU/model decision narrative (VRAM math, picks, what we tried and rejected) lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md); deferred items in [`BACKLOG.md`](BACKLOG.md); the active spec (if any) in [`SPEC.md`](SPEC.md).

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

The voice-bench A/B harness `bin/game voice-samples` renders the 5-prompt corpus at `tests/drift/voice/*.json` against the current `DAYDREAM_LLM_MODEL` (vLLM must be up) and writes a dated, model-slugged markdown file under `docs/pretty/voice-samples/`. Same idea as the image A/B but for narration: each capture documents the vLLM flag set, per-prompt latency + token counts, and the rendered narrate verbatim, so a future bump can be eyeball-diffed against the prior baseline. Four baselines ship in tree: the pre-fix and post-fix Qwen-AWQ captures (showing the prompt-template tic before and after the variety pass) plus two Mistral-Nemo Q4 failure modes from the 2026-05-06/05-07 experiments.

For the live LLM ↔ image-gen serialization smoke (boots both engines, runs 5 alternating requests, asserts no OOM and clean output):

```sh
.venv/bin/python tools/arbiter-smoke.py
```

## NPC memory (optional)

NPC dialogue retrieval needs a CPU embedder (`sentence-transformers` BGE-small, ~100 MB). One-time install:

```sh
bin/memory-bootstrap     # ~200 MB CPU torch wheels + the BGE-small model
```

The script installs `sentence-transformers` against the PyTorch CPU wheel index (avoids the ~1.5 GB CUDA libs we never use; embedding runs on CPU by construction so the GPU stays free for vLLM + ComfyUI under the arbiter). Re-runs are no-ops. Skip it and the dialogue path still works — capture / retrieve fail closed and NPCs just have no memory until the bootstrap lands. Toggle the whole subsystem with `DAYDREAM_MEMORY_ENABLED` (default `1` in production, `0` in `tests/conftest.py`).

## Tests

```sh
bin/game test short     # unit / fast (~3s)      — pre-commit gate (320 tests)
bin/game test medium    # integration (~5s)      — pre-push gate (469 tests)
bin/game test long      # real-GPU drift (~15min) — on-demand / pre-release
bin/game test human     # aesthetic rubric via qpeek — async human review
```

One entry point; four tiers; durations scale with what the tier verifies. Bare `.venv/bin/pytest` still runs every test (backward compat). The drift probes under `tests/drift/` exercise the real LLM + image-gen paths and compare to git-committed baselines under `tests/baselines/*.golden.json` — a divergence fails the test with a diff and the operator ratifies a new baseline with `mv .latest .golden` + commit. The tic-detection probe at `tests/test_voice_baseline.py` parses captured voice-bench markdown and asserts pairwise-distinct body-language openers across the 5 corpus prompts; a parametrized regression-detection demo proves the probe catches the 04-24 prompt-template tic that motivated it. The durable philosophy and extension guide live in [`TESTING.md`](TESTING.md); read it before adding a test or bumping a model / LoRA / workflow.

## Release notes

### v0 — *the smallest dream* (10/10)

The first dream that runs. Single hardcoded toon (Wren) in a single hardcoded meadow at dusk; Python 3.10 + FastAPI + websockets in a single process tree; SQLite-per-world with an append-only events log as the spine; friend-scope shared-password auth; vanilla HTML / CSS / JS frontend. No LLM and no image gen yet. The point was proving the architectural spine: one process, events table is the source of truth, snapshot reconstruction from events, and a clean "join → see room → leave a footprint → reconnect → see your footprint" loop on a single dev box.

### v1 — image-gen pipeline (8/8)

SDXL base 1.0 + `ostris/watercolor_style_lora_sdxl` served by ComfyUI for room backgrounds; vLLM 0.19.1 serving Qwen 2.5 7B Instruct AWQ for free-form narration; both gated by an in-process GPU arbiter (`asyncio.Lock` at `daydream/gpu/arbiter.py`) that serializes inference on the 20 GB RTX 4000 SFF Ada so the engines never OOM each other. `tools/arbiter-smoke.py` runs 5 alternating LLM + image-gen requests and asserts no OOM in ~9 s wall-clock on this hardware; that's the live-stack canary to run after any engine bump. The arbiter lock is asyncio-only (single process); cross-process concurrency would need a flock and isn't on the table at v1's CCU. The hero `meadow-at-dusk.png` at the project root is this pipeline's first real output.

### v0.2.0 — second inhabited dream

v0.2.0 keeps v0.1.0's foundation (multi-room world, two NPCs, dialogue memory, image gen) and layers reactive depth on top. Drift narrates now compose from the LLM with each NPC's recent memories + mood (mood-bucketed canned pool retained as offline fallback), drift is suppressed in any room a human currently occupies, and each tick has a small probability of nudging the NPC's mood to a different bucket so the world drifts over hours of play. A drift voice-bench harness mirrors the dialogue voice-bench so tone drift in LLM-composed drift output is eyeball-diffable across model swaps. Tier gates green throughout: 320 fast tests (`tier_short`) and 451 integration tests (`tier_medium`), each 100% passing.

**What's new since v0.1.0:**

- *LLM-driven drift narrates.* `daydream/drift.py:_tick` runs a two-path tick when `DAYDREAM_DRIFT_LLM_ENABLED=1`: pulls up to K memories via `memories.retrieve(query=npc.seed)`, renders a tight Jinja prompt (npc_name + seed + mood + `<memory>`-wrapped recents), calls `acompletion_json` (which holds the GPU arbiter), runs `safety.first_banned` on the parsed `narrate`, emits. On any failure (`LLMUnavailable`, banlist hit, empty/missing narrate) it falls through to the canned pool. The canned pool is now mood-bucketed (`dict[str, dict[str, list[str]]]`) — Rook's existing 4 lines carry into the `content` bucket, Iris's into `thoughtful`, plus 4 new lines per NPC across the other buckets so the offline path stays varied.

- *Drift polish.* Per-NPC selection weights (`_NPC_DRIFT_WEIGHT` defaults equal; weight 0 excludes); room-occupancy suppression (`_occupied_room_ids` filter, default-on via `DAYDREAM_DRIFT_SUPPRESS_OCCUPIED`); probabilistic mood transitions (`_maybe_transition_mood` with `DAYDREAM_DRIFT_MOOD_DRIFT_PROB` default 0.2 + new `daydream/toons.py:set_mood` parameterized helper). The three compose: filter occupied rooms → weighted-pick from survivors → emit narrate → maybe-transition mood.

- *Drift instrumentation.* `bin/game drift-samples` writes dated markdown under `docs/pretty/drift-voice-samples/` from a 5-prompt corpus at `tests/drift/drift-voice/*.json` (covers Rook/Iris × content/thoughtful × empty/with-memories + a non-bucketed `weary` mood). Hermetic by construction — no DB, synthetic memories from the corpus. Plus `_TICK_COUNTS` outcome counters (`llm_emit` / `canned_fallback` / `noop`) surfaced via the `/status/drift` plain-text endpoint and a one-liner in `bin/game status` when any counter is non-zero.

- *Tooling.* `bin/install-hooks` (idempotent pre-commit + pre-push installer; marker-aware so user-written hooks aren't clobbered, refuses to overwrite hand-written hooks). Memory salience drift probe at `tests/drift/test_memory_ranking.py` pinning the `cosine_similarity * exp(-age/24h)` formula against `tests/baselines/memory_ranking.golden.json`.

**What's next:** capture the first drift voice-bench baseline (operator session: bring vLLM up, run `bin/game drift-samples`, commit the markdown); LanceDB-backed memory retrieval once memory counts cross ~10K per NPC (v0 is SQLite-only); drift voice-bench corpus expansion once the first baseline reveals what patterns are worth probing. Then anything else operator-driven.

### v0.1.0 — first inhabited dream

v0.1.0 takes the v1 image-gen pipeline as a substrate and builds a multi-room world with two hand-authored NPCs, a data-skill safety baseline, an asyncio drift loop emitting per-NPC narrate ticks while the player is elsewhere, NPC dialogue memory so Rook and Iris remember past exchanges, and a voice-bench audit-trail harness that captures dated narrate samples for any model swap. Tier gates green throughout: 290 fast tests (`tier_short`) and 401 integration tests (`tier_medium`), each 100% passing. Bare-mocked-LLM tests cover the data-skill safety pipeline + WS dispatch end-to-end; real-GPU drift probes run on-demand under `bin/game test long` against committed golden baselines.

**What works:**

- *World.* Five rooms (`r-meadow` spawn, `r-forge`, `r-bridge`, `r-attic`, `r-hollow`) connected by bidirectional `exits_json`; a player can `go north`, `go up`, etc., and the SPA renders the snapshot's exits as clickable buttons.
- *NPCs.* Rook (forge-keeper, slot 100, at `r-forge`) and Iris (attic archivist, slot 101, at `r-attic`). Each has a `presence_text` line that fires when the player enters the room, plus a `skills/<npc>.json` data-skill that handles dialogue (`rook hello` at `r-forge` dispatches Rook's voice via the LLM; the same `iris hello` at `r-meadow` falls through to the chat fallback because the `context_predicate` scopes to `room_slug=attic`).
- *Drift loop.* `daydream/drift.py` runs as an asyncio.Task in the FastAPI lifespan, sleeps `DAYDREAM_DRIFT_IDLE_SECONDS` (300 s) when no WS subscribers are connected and `DAYDREAM_DRIFT_BUSY_SECONDS` (1800 s) when ≥1 is. Each tick picks a random NPC, draws a line from a per-NPC pre-canned pool of 4 lines, emits a `narrate` event to the NPC's room. v0 is pre-canned — no LLM call, no GPU arbiter contention by design — so the BACKLOG entry's "yield arbiter on player input" requirement is vacuously satisfied until v1 introduces LLM-driven drift.
- *NPC dialogue memory.* Each Rook / Iris exchange is captured to a per-world `memories` table (migration 009) with a 384-dim CPU embedding via `sentence-transformers` BGE-small; the next turn pulls top-K by `cosine_similarity * exp(-age/24h)` and weaves them into the prompt as `<memory>...</memory>`-wrapped context. Capture short-circuits on the input banlist before INSERT (defense-in-depth against stored prompt-injection); retrieval is per-(npc, world) scoped. Fail-closed everywhere — capture/retrieve return `None` / `[]` if `bin/memory-bootstrap` hasn't run, so the dialogue path stays warm without the embedder. CPU-only by construction; the GPU stays free for vLLM + ComfyUI under the arbiter.
- *Safety baseline.* `daydream/llm/safety.py` plus the data-skill effect-allowlist in `daydream/skills/effects.py` give us: input-banlist short-circuit (banned mood / pixel-art / urgency triggers a soft-narrate fallback before the LLM is called), Jinja `SandboxedEnvironment` template render with `<player_input>` and `<memory>` role-separator tags, JSON `response_format` constraint at the LLM call site, refusal schema with default-reason fallback, and an output-banlist check on the parsed effects payload before any state mutation.
- *Voice-bench audit trail.* `bin/game voice-samples` writes `docs/pretty/voice-samples/<today>-<model_slug>.md`. Four durable baselines in tree: `2026-04-24-qwen2.5-7b-instruct-awq.md` (the pre-fix substrate, frozen as the regression-detection before-shot), `2026-05-06-qwen2.5-7b-instruct-awq.md` (the post-fix substrate after the prompt-template variety pass), `2026-05-06-mn-12b-rp-ink-q4_k_m.md` (RP-Ink failure mode), `2026-05-07-mistral-nemo-instruct-2407.md` (Instruct controlled-base failure mode). Plus a regression-detection probe at `tests/test_voice_baseline.py` that parametrizes over the pre-fix and post-fix AWQ baselines.
- *World admin.* `bin/game world list / archive / restore / verify / delete` covers per-world archival, full-bundle ship-to-friend, on-disk integrity checks, and cascade deletion (memory rows included). State lives under `~/data/daydream/`, never the project tree; archive bundles include a `MANIFEST.json` recording schema_version + asset counts.

**Engines and operational notes:**

- *vLLM.* 0.19.1 pinned, serving Qwen 2.5 7B Instruct AWQ on the RTX 4000 SFF Ada (compute capability 8.9). Tunings: `--enforce-eager` (avoids a CUDA-graph OOM hit on this card), `--gpu-memory-utilization 0.45` (~9 GB ceiling so SDXL fits alongside), `--max-model-len 8192`, `VLLM_LOGGING_LEVEL=ERROR`. **No `--kv-cache-dtype fp8_e4m3`**: deterministically broke tight-format JSON adherence on Qwen 2.5 7B AWQ during the `tools/arbiter-smoke.py` strict-JSON probe (model looped `!***` garbage tokens after one clean turn). Re-enabling the flag is gated on a calibration pass per the BACKLOG `calibrated-fp8-kv-scales` entry.
- *gguf packaging-bug workaround.* `bin/vllm-bootstrap` includes an idempotent post-install patch that injects `__version__` into the installed `gguf/__init__.py`. transformers 5.6's `is_gguf_available()` reads the version via `importlib.metadata.packages_distributions()` and falls back to `getattr(gguf, '__version__', 'N/A')`; every gguf release in vLLM's supported range (0.17.0 through 0.19.0) fails to register the import name and exposes no `__version__`, so the fallback returns "N/A" and `version.parse` rejects it, crashing vLLM startup any time it tries to load a GGUF model. Patch is applied unmodified across two GGUF model loads (RP-Ink + Instruct, both Mistral-arch) so it generalizes; remove the patch block when upstream gguf fixes its packaging metadata. See [`docs/gpu-and-models.md`](docs/gpu-and-models.md) "Things we tried and rejected" for the full diagnosis chain.
- *Image gen.* SDXL base 1.0 + `ostris/watercolor_style_lora_sdxl` via ComfyUI. ~6 GB resident, ~10-12 GB peak during inference. Coexists with vLLM behind the in-process arbiter (`asyncio.Lock`) at `daydream/gpu/arbiter.py`.

**What we learned (and what didn't work):**

- *Prompt-template variety.* The first AWQ baseline showed 4 of 5 narrate responses opening with the same 14-word phrase ("Rook pauses the steady rhythm of the bellows, wiping hands on the apron, and says,") — a template-induced tic from a flat list of candidate sensory beats. Eight prompt-template iterations later, the working configuration is: kind-specific input-anchor mapping (5 input kinds map to 5 distinct opener anchors), 3 illustrative exemplars showing varied openers + concrete spoken lines, explicit ban on the originating tic phrase by name. PREFER lists trigger direct phrase copying; AVOID lists prime the topics they ban; over-constrained prompts cause truncation. Iris was authored with these lessons baked in from version 1, no iteration needed.
- *Greedy decoding tax.* vLLM's `acompletion_json` defaults to `temperature=0.0`, which makes capture deterministic but funnels the model into ONE preferred response shape regardless of input. Variety has to come from the prompt's input-differentiating signals, not from sampling.
- *Mistral Nemo Q4 + data-skill pipeline = no.* Both `bartowski/MN-12b-RP-Ink-GGUF/MN-12b-RP-Ink-Q4_K_M.gguf` (creative-writing finetune) and `bartowski/Mistral-Nemo-Instruct-2407-GGUF/Mistral-Nemo-Instruct-2407-Q4_K_M.gguf` (controlled-base) fail the data-skill pipeline at our prompt template. RP-Ink returns `{"effects":[{}]}` (content-empty) deterministically; MN-Instruct fragments behavior across inputs (some non-JSON output, some `{"refused":true}` minimal refusals, some timeouts), and a direct probe with a simpler system prompt confirms it ALSO returns `{"effects":[{}]}` like RP-Ink. The pipeline incompatibility is base-architecture + Q4-quantization + prompt-shape, not RP-Ink-specific. The original "does a creative-writing finetune flex on Rook's voice?" question is parked under three forward-path BACKLOG entries (`creative-finetune-json-fluent-base`, `free-form-prose-pipeline`, `mistral-7b-instruct-fp16-ab`).

## Tech sketch

| Layer | Choice |
|---|---|
| Backend | Python 3.10 + FastAPI + websockets, single process tree |
| Persistence | SQLite per world (WAL), append-only event log as the spine; world archive/restore via tarball bundling DB + per-world cache + manifest (`bin/game world archive/restore`) |
| LLM (optional) | vLLM 0.19.1 serving Qwen 2.5 7B Instruct AWQ, called via `litellm` so the same code path works against vLLM today and Cloudflare / OpenAI / Anthropic later. GGUF support in vLLM is patched-in via `bin/vllm-bootstrap`'s post-install workaround for the upstream gguf packaging-metadata bug — see Release notes above |
| Image gen (optional) | SDXL base + `ostris/watercolor_style_lora_sdxl` via ComfyUI, GPU arbiter shared with vLLM |
| GPU arbiter | `daydream/gpu/arbiter.py` (`asyncio.Lock`); serializes LLM and image-gen on the 20 GB card |
| World content | Five rooms; two NPCs (Rook at `r-forge`, Iris at `r-attic`) authored as data-skills under `skills/<name>.json` with `context_predicate` room-scoping; `daydream/drift.py` emits per-NPC narrate ticks on the gentle-drift cadence (5 min idle / 30 min when humans are connected) |
| NPC memory (optional) | Per-world `memories` table at `daydream/memories.py`; sentence-transformers BGE-small on CPU lazy-loaded on first call; embeddings stored as float32 BLOBs; retrieval ranks by `cosine_similarity * exp(-age_hours/24)`; `bin/memory-bootstrap` is the one-time CPU-torch + model install. v0 is SQLite-only; LanceDB is the v1 path once memory counts cross ~10K per NPC |
| Frontend | Vanilla HTML / CSS / JS under `web/`, plain `<img>` tags (no Vite yet; Svelte polish is a backlog item) |
| Auth | Friend-scope: shared password from `.env` on a single port |
| Network access | `DAYDREAM_ACCESS` toggle in `.env`: `tailscale` (default) or `public` |
| Target hardware | Single Linux dev box (RTX 4000 SFF Ada, 20 GB VRAM); designed to port to Cloudflare and containers later |

The full GPU/ML narrative — VRAM math, model selection rationale, what we tried and rejected (the fp8-KV-cache story especially), what to try later — lives in [`docs/gpu-and-models.md`](docs/gpu-and-models.md). [`CLAUDE.md`](CLAUDE.md) is the operator/agent reference for project conventions, lifecycle, the External engines pattern, and the `pretty <filename>` shorthand for promoting image outputs.
