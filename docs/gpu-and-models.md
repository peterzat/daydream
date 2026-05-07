# GPU and models

The durable home for *why* daydream uses the GPU the way it does, *what* we picked, *what we tried and rejected*, and *what we should consider trying later*. Read this before bumping a model, swapping an engine, or adding a tuning flag.

If you only read one section, read [The fp8-KV story](#the-fp8-kv-story) and [Things we have not tried yet](#things-we-have-not-tried-yet).

## The box

- **GPU:** NVIDIA RTX 4000 SFF Ada Generation. Compute capability 8.9 (Ada Lovelace, sm_89). 20 GB ECC GDDR6. 70 W TDP — inference and experimentation, not heavy training. Per-channel FP8 (E4M3 and E5M2), FlashAttention-2 / 3, Marlin INT4 kernels, BF16, TF32 are all hardware-supported.
- **CPU/RAM:** Intel i5-13500 (14 cores, 20 threads), 64 GB DDR4. Plenty for inference servers' Python sides.
- **OS:** Ubuntu 22.04, CUDA driver 13.x, Python 3.10. ComfyUI venv carries torch 2.11+cu130; vLLM venv carries whatever vllm 0.19.1 pins.
- **Singleness:** This box is assumed dedicated to daydream. The only prior GPU consumer (`~/src/qwen-2.5-localreview`'s warm server) is off in its `.env` and stays off; see [CLAUDE.md "GPU posture"](../CLAUDE.md). Every tuning decision below assumes no external contention for VRAM.
- **Network exposure:** vLLM and ComfyUI bind `127.0.0.1` by default — daydream is their only consumer, so they don't need to be on the tailnet. The user-visible game port (`54321` by default) is filtered by the `AccessMiddleware` per `DAYDREAM_ACCESS=tailscale|public`. See [CLAUDE.md "Network access"](../CLAUDE.md#network-access).

## The VRAM budget

20 GB is tight when both inference engines stay resident. Rough math:

| | Resident | Peak during inference |
|---|---:|---:|
| vLLM (Qwen 2.5 7B Instruct AWQ) | ~5 GB weights | ~7 GB (weights + KV cache + activations on short prompts) |
| ComfyUI (SDXL base + watercolor LoRA, smart-managed) | ~6 GB when warm; drops idle | ~10-12 GB during a 1024×384 generation |
| **Sum (both resident, one inferencing)** | ~11 GB idle | ~17 GB peak (whichever side is in flight) |

The arbiter (`daydream/gpu/arbiter.py`) makes "both resident, one inferencing" the worst case by serializing inference requests. Without it, two simultaneous inferences would peak around 19-22 GB and OOM stochastically.

The `--gpu-memory-utilization 0.45` we pass to `vllm serve` (~9 GB ceiling for vLLM on 20 GB) is set so vLLM's KV cache reservation doesn't crowd ComfyUI out. With more margin we'd see better LLM throughput at long contexts; with less we'd see more headroom for ComfyUI to load larger SDXL variants.

## The arbiter, explained simply

`daydream/gpu/arbiter.py` is an `asyncio.Lock` wrapped in an async context manager. Both inference call sites (the LLM client and the image-gen client) acquire it before talking to their respective daemons. That's it.

We considered (and the localreview pattern uses) a flock-based mutex for cross-process coordination. We don't need it: daydream is a single Python process, so an in-process `asyncio.Lock` does the job. The flock pattern is documented in CLAUDE.md as the upgrade path if a second process ever needs to contend.

There are two arbiter contracts in the code, intentionally different:

- **`llm/client.acompletion_json`** — acquires the arbiter *internally*. Callers just `await acompletion_json(...)`.
- **`images/client.generate_room_background`** — expects the caller to acquire externally (`async with arbiter.acquire(): await generate_room_background(...)`). This is what `api/ws.py:_generate_and_emit` does.

The asymmetry is so neither function tries to re-acquire (asyncio.Lock is not reentrant; double-acquire would deadlock). If you add a third call site, follow whichever pattern matches: callers wrap if the function is meant to be composable; the function wraps if it's the obvious top-level entry.

## LLM stack

### What we picked: Qwen 2.5 7B Instruct AWQ, served by vLLM

Selection criteria:

1. **Fits the VRAM budget alongside SDXL.** AWQ INT4 weights weigh ~5 GB. Larger models (Qwen 2.5 14B AWQ ~9 GB, full 7B FP16 ~15 GB) crowd ComfyUI out unless we add a swap mechanism.
2. **vLLM-compatible.** vLLM's AWQ + Marlin INT4 kernels are mature and fast on Ada (Marlin is `sm_80+`).
3. **OpenAI-compatible HTTP API.** Lets daydream use `litellm.acompletion` against a local endpoint with the exact same call site that targets Cloudflare Workers AI / OpenAI / Anthropic later — the abstraction we set up in v0 keeps paying off.
4. **Instruct tune is good enough for both interpreter routing (small, structured outputs) and v1+ NPC dialogue.** It is not specifically tuned for cozy / atmospheric narration; see [Things we have not tried yet](#things-we-have-not-tried-yet) for the storytelling-finetune option.

Other 7B/8B-class models we considered and did not test (research-only, no live A/B):

- **Gemma 2 9B Instruct.** ~7-8 GB at Q4. Reportedly stronger creative writing than Qwen 7B in community benchmarks, but the extra ~2-3 GB matters when SDXL is also resident. Worth A/B-ing if we ever drop to 0.40 `gpu-memory-utilization`.
- **Llama 3.x 8B Instruct.** ~5 GB AWQ. No standout reason to prefer over Qwen 2.5; comparable quality at the 7B class.
- **Mistral 7B Instruct.** Older base than Qwen 2.5; likely worse on instruction-following.
- **Phi-3.5 / Phi-4 mini.** Microsoft's small-model line. Strong at structured tasks; less explored for narrative.

### Inference server: vLLM (over alternatives)

vLLM was picked over llama.cpp, TGI, SGLang, LM Studio's server, and Aphrodite. The reasons in priority order:

1. **OpenAI-compatible HTTP server** out of the box (`vllm serve`).
2. **PagedAttention** keeps KV cache fragmentation low, important when memory headroom is thin.
3. **Active mainline.** AWQ, FP8, GPTQ, Marlin, FlashInfer are all first-class.
4. **The localreview project** had already validated vLLM on this exact card. Adopting the same engine meant inheriting their tuning experiments (see below) for free.

llama.cpp would be a fair second choice if we ever want a much smaller dependency footprint, but its OpenAI-compatible server is less mature than vLLM's.

### Tunings inherited from `~/src/qwen-2.5-localreview`

That project ran careful experiments on the *same* RTX 4000 SFF Ada and committed the deltas to git history. Treat their findings as load-bearing prior art.

| Flag | Decision | Reason |
|---|---|---|
| `--enforce-eager` | **Keep** | Disables CUDA-graph capture. Avoids a graph-induced OOM localreview hit on this card (their commit `8321af1`). Tiny perf cost; real stability win for serial-inference. |
| `vllm==0.19.1` (pinned) | **Keep** | The version localreview validated against. `bin/vllm-bootstrap` reinstalls if drifted. Bumping is allowed, but pair with a re-run of `tools/arbiter-smoke.py`. |
| `VLLM_LOGGING_LEVEL=ERROR` | **Keep** | Ergonomics. Override with `VLLM_LOG_LEVEL=INFO bin/game vllm-up` when debugging. |
| `--kv-cache-dtype fp8_e4m3` | **Reject (with escape clause)** | See [The fp8-KV story](#the-fp8-kv-story). |

## The fp8-KV story

This is the single most important finding in this document.

Localreview measured **+58% decode TPS, +36% prefill TPS, ~0.9 GB freed VRAM** by adding `--kv-cache-dtype fp8_e4m3` on their **14B Coder** model. Ada has FP8 hardware; the win is real and big. We tried it on **Qwen 2.5 7B Instruct AWQ** (our model) on this same card.

It deterministically broke tight-format adherence. The `tools/arbiter-smoke.py` LLM probe asks for `{"n": <integer>}` echo. With fp8_e4m3 KV cache enabled, the model produced `{"number":": 1}<tool_call> !***oriously !***ographically !***ursively !***ompressing !***he !***idea ...` — sensible-ish opening, then a hard derail into looping garbage tokens. Same prompt, two runs back to back: identical output, so it was not a sampling fluke.

The plausible explanation: each decoded token's attention computation accumulates a small precision error from fp8 KV. The 14B has the parameter capacity to absorb the drift; the 7B does not, and once it crosses some boundary the autoregressive sampling locks into a degenerate token distribution.

**Do not re-enable `--kv-cache-dtype fp8_e4m3` without one of:**

1. **Moving to a >=14B model** that fits the VRAM budget (would require swapping SDXL out during LLM inference; significantly more arbiter complexity than we have today).
2. **Calibrated per-channel FP8 KV scales.** vLLM supports loading them; the calibration is a one-time pass over a representative dataset that produces per-channel scaling factors that recover most of the precision lost to E4M3's 4-bit mantissa. Real engineering work but documented as the path.
3. **A new 7B/8B variant that tolerates fp8_e4m3 KV.** Verified by re-running `tools/arbiter-smoke.py` and getting clean JSON across all five turns.

The smoke harness's strict-JSON probe was specifically chosen because it surfaces this regression on the first run. If you ever bump models, re-run the smoke; if it passes the JSON gate, you can trust the fp8-KV story scales similarly to your new model.

## Image gen stack

### What we picked: SDXL base 1.0 + `ostris/watercolor_style_lora_sdxl`, served by ComfyUI

- **SDXL base** instead of SDXL Turbo. Turbo's distillation actively *resists* soft watercolor wash because its 1-4 step sampler can't gently accumulate value. Documented at length in `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md` (Risk #1) and the original WHIMSY pivot.
- **`ostris/watercolor_style_lora_sdxl`** (`watercolor_v1_sdxl.safetensors`, 12 MB). Picked from a small set of HF candidates after the user picked Spiritfarer / A Short Hike as the aesthetic anchor. Produces visibly painterly, not crunchy, output (see `docs/pretty/meadow-at-dusk.png` for the v1 first-output proof).
- **22 steps, dpmpp_2m + karras, cfg 5.5** in `daydream/images/workflows/painterly_room.json`. Standard SDXL settings; nothing exotic.
- **1024×384** output to match the SPA's room-background slot. Wider than tall; framed as a landscape vignette behind the chat log.
- **ComfyUI** as the inference server (over A1111, raw `diffusers`, etc.). Node-based JSON workflows let the same file drive both the room-bg path (`images/client.py`) and the test harness (`images/cli.py`). Programmatic, reproducible, swappable.

### Latency on this box

5.7-6 seconds per 1024×384 at 22 steps, models warm. First-call cold start is +3-5 s for VAE/CLIP/sampler initialization. Well under the 30 s budget the SPEC criterion sets. Not a current bottleneck.

### Image-gen alternatives we considered and did not test

- **`ntc-ai/SDXL-LoRA-slider.watercolor`** — slider-style LoRA; lets you dial intensity. Worth A/B testing once we have an audit trail.
- **`lora-library/B-LoRA-watercolor`** — newer "B-LoRA" technique that decouples style and content. Different VAE; would need a workflow JSON variant.
- **`kchoi/lora-sdxl-watercolor`** — alternative ostris-tier candidate.
- **SD 1.5 + watercolor LoRA** — documented fallback if SDXL latency ever becomes a bottleneck (per the original plan: lower VRAM, often more Spiritfarer-y, but visibly older base). Cost: separate workflow JSON.
- **Pixel-art LoRAs** — explicitly rejected at the WHIMSY anchor stage. Do not revisit.

### Per-character / per-item sprite consistency

Not in scope for v1. The plan's recommendation when it lands is **IP-Adapter Face + reference image + seed discipline** (cheaper than per-character LoRAs). Documented in BACKLOG as part of the eventual item-sprites work.

## How to swap any of this

Swapping is config, not code, by design. The places it touches:

| Swap | Where to change |
|---|---|
| LLM model name | `DAYDREAM_VLLM_MODEL` env var (sets bootstrap default) AND `DAYDREAM_LLM_MODEL` env var (sets daydream's litellm call). Defaults match in `daydream/config.py:llm_model()` and `bin/vllm-bootstrap`. |
| LLM endpoint (e.g. swap to OpenAI / Cloudflare) | `DAYDREAM_LLM_BASE_URL` + `DAYDREAM_LLM_MODEL` env vars. litellm picks the right backend from the model prefix (`openai/`, `anthropic/`, `cloudflare/`, `hosted_vllm/`). |
| Image-gen LoRA | Edit `lora_name` in `daydream/images/workflows/painterly_room.json`. Both `bin/game image-test` and the room-bg generator pick it up. Drop the new LoRA file into `external/ComfyUI/models/loras/`. |
| Image-gen base model | Edit `ckpt_name` in the same workflow JSON. Drop the safetensors into `external/ComfyUI/models/checkpoints/`. |
| vLLM tuning flag | `bin/game cmd_vllm_up` in `bin/game`. Re-run `tools/arbiter-smoke.py` to validate. |
| Inference engine entirely (e.g., swap vLLM for SGLang or TGI) | New `bin/<engine>-bootstrap` + `bin/game <engine>-up/down` per the [External engines pattern](../CLAUDE.md#external-engines). |

## Quality guardrails (what we have, what we don't)

### What we have

- **`tools/arbiter-smoke.py`** — runs 5 alternating LLM + image requests through the real call paths. Verifies arbiter serialization (no OOM), latency budget, AND output format (the LLM probe demands strict JSON; this is what caught the fp8-KV regression).
- **`tests/`** — 128 pytest tests covering DB, events, skills, LLM client (mocked), image client (mocked), image cache, WS protocol, frontend SPA assets. All GPU-free; run on every change.
- **WHIMSY.md** — the durable tone bible. Tested via `tests/test_whimsy.py` for presence of the named sections.

### What we don't have

- **No LLM voice / narration quality benchmark.** The smoke catches "model returned garbage." It does not catch "model returned valid JSON but the narration tone shifted toward generic AI-speak after a version bump." Today the only check on this is human eyes-on of `bin/game image-test` and the SPA when a real player connects.
- **No image-gen aesthetic benchmark.** Same shape: we look at the output and judge. There's no fixture set of anchor prompts that gets regenerated on a model/LoRA bump for side-by-side.
- **No drift alarm.** If we bump vLLM or swap LoRA and the smoke passes, we won't know if the *quality* changed unless someone happens to look.

The `voice-and-aesthetic-audit-trail` BACKLOG entry is the proposed cheap fix — a `tools/voice-bench.py` (and image counterpart) that renders a small fixture of anchor prompts to dated directories under `docs/pretty/voice-samples/<date>.md` and `docs/pretty/aesthetic-samples/<date>/`. Not a pass/fail check; just a chronology you can scroll back through to see when the vibe shifted.

## Things we have not tried yet

Captured as BACKLOG entries (`BACKLOG.md`) so they survive turn-close. Listed here in rough ROI order:

1. **`watercolor-lora-ab`** — try `ntc-ai/SDXL-LoRA-slider.watercolor` and `lora-library/B-LoRA-watercolor` against the current ostris pick. 12 MB each.
2. **`calibrated-fp8-kv-scales`** — recover localreview's 58% decode TPS win on our 7B by running vLLM's calibration pass and shipping per-channel scales. Real engineering work; only worth it if we ever bottleneck on LLM throughput.
3. **`creative-finetune-json-fluent-base`** — re-attempt the voice-quality A/B with a creative-writing finetune of a JSON-fluent base (Qwen 2.5, Llama 3.x). The Mistral Nemo attempts in 2026-05-06/05-07 (both finetune and controlled-base) failed the data-skill pipeline, so we know the next attempt needs a base that preserves structured-output capability. Blocked on a published finetune existing.
4. **`free-form-prose-pipeline`** — daydream pipeline change so `daydream/skills/data.py` accepts free-form prose from the LLM and post-parses, instead of requiring strict-JSON `response_format`. Would enable prose-continuation finetunes (RP-Ink and similar) that don't fit the current pipeline. Architectural change; defer until a specific finetune is worth the work.
5. **`mistral-7b-instruct-fp16-ab`** — Mistral 7B Instruct A/B at fp16 against Qwen 2.5 7B Instruct AWQ. Smaller (less Q4-sensitive), fits BF16 in our budget without GGUF. Would separate the quantization axis from the architecture axis after the 12B Q4 Nemo experiments came up inconclusive.

We are also watching for:

- Qwen 3 series releases. Already in vLLM recipes per recent search (Qwen 3.5/3.6 docs). Refresh the model pick every ~6 months.
- New SDXL-class base models (SD3, etc.) once their licensing and tooling stabilize. SDXL is a known quantity; don't churn without reason.

## Things we tried and rejected

### Mistral Nemo 12B at Q4_K_M GGUF for creative-writing voice (2026-05-06 / 2026-05-07)

Three turns of voice-bench work tested whether a creative-writing-tuned 12B model would produce more interesting Rook narration than our default Qwen 2.5 7B Instruct AWQ. Two legs across two spec turns:

- **`bartowski/MN-12b-RP-Ink-GGUF`** (Q4_K_M, ~7 GB resident) — the RP-Ink creative-writing finetune. Captured at `docs/pretty/voice-samples/2026-05-06-mn-12b-rp-ink-q4_k_m.md`. Returns deterministic content-empty `{"effects":[{}]}` under our strict-JSON `response_format`; verbose free-form roleplay continuation without it. Trained for prose continuation; structured-output capability degraded relative to the Mistral Nemo Instruct base.
- **`bartowski/Mistral-Nemo-Instruct-2407-GGUF`** (Q4_K_M, ~7 GB resident) — the controlled-base leg, no creative-writing finetune. Captured at `docs/pretty/voice-samples/2026-05-07-mistral-nemo-instruct-2407.md`. ALSO fails the data-skill pipeline under daydream's harness prompt: 3/5 non-JSON output (88, 74 tokens, plus 1 timeout), 2/5 emit `{"refused":true}` with no reason field that the safety layer resolves to its default refusal text. A direct vLLM probe with a simpler system prompt confirmed MN-Instruct ALSO returns `{"effects":[{}]}` — the harness's longer prompt template fragments behavior across inputs.

**Conclusion: pipeline incompatibility is base-architecture + Q4-quantization + prompt-shape, NOT RP-Ink-specific.** The controlled-base leg confirms it: even without a creative-writing finetune, Mistral Nemo at Q4 fails the data-skill pipeline at our actual prompt template. The voice-quality A/B question (does a creative-writing finetune flex on Rook's voice?) remains open with shrunken forward paths captured as the BACKLOG entries above (`creative-finetune-json-fluent-base`, `free-form-prose-pipeline`, `mistral-7b-instruct-fp16-ab`).

vLLM flag deviation captured for the GGUF legs: `--max-model-len 4096` (down from 8192). At `--gpu-memory-utilization 0.45` the 12B Q4 weights leave only ~1.11 GiB for KV cache, vLLM reports 8192 needs 1.25 GiB and the actual ceiling is 7248. 4096 is well within budget and far above this corpus's actual ~1100-token-per-call usage.

Relevant commits: `4084bab` (RP-Ink leg), `55fffd0` (Instruct controlled-base leg).

### gguf packaging-metadata bug in transformers (worked around in `bin/vllm-bootstrap`)

Loading any GGUF in vLLM 0.19.1 originally crashed during config-load because `transformers.is_gguf_available()` reads gguf's version via `importlib.metadata.packages_distributions()` and falls back to `getattr(gguf, '__version__', 'N/A')`. Every gguf release in vLLM's supported `>=0.17.0` range (0.17.0, 0.17.1, 0.18.0, 0.19.0) fails to register the gguf import name in `packages_distributions()` AND exposes no `__version__` attr. Result: `version.parse('N/A')` raises `InvalidVersion: Invalid version: 'N/A'`.

Workaround landed in `bin/vllm-bootstrap` (commit `210bb51`): after `pip install vllm`, the bootstrap appends `__version__ = "<installed-version>"` to the installed `gguf/__init__.py`. Idempotent (re-bootstrap detects the prior patch via `grep -q "^__version__"` and skips). Generalizes — verified across two GGUF model loads (RP-Ink and Instruct) with no patch modification.

**Remove the patch block whenever upstream gguf fixes its packaging metadata.** Track via `pip show gguf` after a vLLM version bump: if a future gguf release registers the import name correctly in `packages_distributions()`, the patch is no longer needed and `bin/vllm-bootstrap`'s post-install step can be deleted.

## References

- `~/src/qwen-2.5-localreview/` — the prior-art project. `setup.sh`, `warm.py`, `review.py` are the most informative files. Their `gpu_lock.py` is the flock pattern we ported as documentation. Their commit history shows the experimental progression for the tunings we inherited.
- [vLLM quantized KV cache docs](https://docs.vllm.ai/en/latest/features/quantization/quantized_kvcache/)
- [vLLM serve CLI reference](https://docs.vllm.ai/en/stable/cli/serve/)
- [Qwen vLLM deployment guide](https://qwen.readthedocs.io/en/stable/deployment/vllm.html)
- `~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md` — the original v0 architectural plan, including the AI-stack research that informed our initial picks (Top risks section especially).
