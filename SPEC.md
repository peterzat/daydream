## Spec — 2026-04-24 — voice-bench + Qwen RP-Ink A/B

**Goal:** build a voice-sample harness and use it to run a same-config A/B between the current default model (`Qwen/Qwen2.5-7B-Instruct-AWQ`) and the creative-writing finetune `Qwen/Qwen2.5-7B-RP-Ink` across Rook's dialogue prompts. Produces two dated, same-day sample files that git-diff side by side plus a captured metrics table, so the operator can judge whether RP-Ink lands better for Rook's voice on evidence rather than vibe. Bundles the voice-samples-capture infrastructure since the A/B has no meaning without it.

### Acceptance Criteria

- [x] **Anchor corpus lands at `tests/drift/voice/*.json`.** Five hand-authored prompts, each `{"_doc": "...", "name": "<slug>", "skill": "rook", "player_input": "..."}`. Files exercise Rook's voice across conversational variety: a greeting, a factual question about the forge, a question about Rook's inner life, small talk, and an open-ended invitation. `_doc` explains the voice signal each prompt probes. `skill` defaults to `"rook"` (forward-compat for multi-NPC corpora). The prompts are chosen to expose voice differences a creative-writing finetune should plausibly flex on (unhurried sensory detail, quiet one-liners) rather than probes that only check JSON shape.

- [x] **`bin/game voice-samples` dispatches the corpus and writes a dated model-slugged markdown file with captured metrics.** Invoked from the project root. For each corpus file: install `skills/rook.json` into a tmp DB (hermetic — does not depend on operator live-DB state), dispatch the named data skill with `player_input` as args via the real `daydream.skills.data.execute_by_name` path, capture the emitted narrate text plus per-prompt metrics (wall-time in seconds; `prompt_tokens` and `completion_tokens` from the LiteLLM response). Write `docs/pretty/voice-samples/YYYY-MM-DD-<model_slug>.md` where `<model_slug>` is a filesystem-safe slug of `config.llm_model()` (e.g. `qwen2.5-7b-instruct-awq`, `qwen2.5-7b-rp-ink`). Markdown includes: date header, full model name, vLLM config summary (max_model_len, gpu_memory_utilization, kv_cache_dtype, enforce_eager — pulled from env/config so the snapshot is self-describing), a metrics table (one row per prompt: prompt name, tokens-in, tokens-out, wall-time), and one H3 per prompt with `player_input` + captured narrate text verbatim. Same-date + same-model re-runs overwrite; different model = distinct file.

- [x] **The harness fails clean when vLLM is unreachable.** A one-line stderr diagnostic naming the unreachable base_url plus suggested fix (`bin/game vllm-up`) and a non-zero exit. No traceback. Mirrors the skip pattern used by `requires_vllm` in the test tier.

- [ ] **Two dated captures commit in-tree, rendered under identical vLLM flags.** The spec delivery includes both `docs/pretty/voice-samples/<today>-qwen2.5-7b-instruct-awq.md` (baseline) and `docs/pretty/voice-samples/<today>-qwen2.5-7b-rp-ink.md` (A/B). Same-flag contract: BOTH vLLM invocations use `--enforce-eager`, `--gpu-memory-utilization 0.45`, `--max-model-len 8192`, `VLLM_LOGGING_LEVEL=ERROR`, and explicitly do NOT set `--kv-cache-dtype fp8_e4m3` (the 7B fp8-KV regression is documented in daydream/docs/gpu-and-models.md and applies to both models). The only variable across the two captures is `DAYDREAM_VLLM_MODEL`. The captured vLLM config block in each markdown file makes this auditable at a glance — a reader can verify both files declare matching config. If RP-Ink cannot load under these identical flags (see Context: VRAM/quantization risk), the spec is blocked on quant selection; the implementer surfaces the blocker and the turn does not ship until resolved.

- [x] **Tests cover the harness without GPU or live LLM, and existing tests stay green.** A new `tests/test_voice_samples.py` (`tier_short`) mocks `daydream.llm.client.acompletion_json` (including the LiteLLM response shape so `prompt_tokens` / `completion_tokens` flow into the metrics table), mocks `config.llm_model()`, and runs the harness against a `tmp_path` output dir; asserts corpus loading, dispatch-to-markdown composition, metrics table population (per-prompt row present with tokens + wall-time), filename model-slug derivation, same-file overwrite on re-run, and the clean-skip path on `LLMUnavailable`. `bin/game test short` + `bin/game test medium` remain green before and after. No new tier_medium or tier_long cost from this feature.

### Context

**Adopted from BACKLOG entry** `qwen-2.5-7b-rp-ink-trial` via explicit `/spec qwen-2.5-7b-rp-ink-trial`. The RP-Ink A/B's own revisit criteria name "voice-bench fixture exists" as a prerequisite, so this spec subsumes `voice-samples-capture` (the harness + corpus + baseline capture) into its scope. Both BACKLOG entries are natural delete candidates at turn close.

**Prior art: `~/src/qwen-2.5-localreview` bench / eval harness.** Daydream's GPU/ML lineage is inherited from that project via `docs/gpu-and-models.md`. Localreview's methodology is load-bearing for this spec — read it before implementing:

- **`tests/bench.py` + `tests/eval.py`** in localreview run a fixed corpus against named configs (`baseline`, `stage1-fp8kv`), measure prefill TPS, decode TPS, aggregate wall-time, and post-load VRAM, and commit the results table under `tests/results/<config>.md`. The committed markdown IS the regression detection mechanism — a future PR that bumps vLLM or swaps the KV dtype re-runs and diffs. Voice-bench's `docs/pretty/voice-samples/<date>-<model>.md` is the same pattern for text output (narrate prose + token-count metrics), minus the TPS precision; voice quality is eyeball-reviewed, not numerically scored.
- **Same-flag A/B discipline.** Localreview's +58% decode / +36% prefill claim is believable precisely because every non-KV-dtype flag was identical across baseline and stage1-fp8kv. Daydream's A/B follows the same rule: only `DAYDREAM_VLLM_MODEL` varies; every other flag matches. This is criterion 4's same-flag contract.
- **Weight-bandwidth lesson from localreview Stage 4.** Localreview measured FP8-dynamic 14B weights (instead of INT4 AWQ) and got +19% prefill but **−58% decode**. Why: on a 20 GB Ada card, autoregressive decode is memory-bandwidth-bound, and doubling weight bytes doubles the bytes that must cross the memory bus on every decode step. Generalized: *doubling weight VRAM is strictly worse than halving KV cache bytes on this hardware.* Direct implication for this spec: if `Qwen/Qwen2.5-7B-RP-Ink` is only available as fp16/bf16 weights (~14 GB), the A/B is comparing an INT4-AWQ (~5 GB) baseline against a fp16 (~14 GB) challenger and the RP-Ink leg will likely be ~2x slower at decode time as a direct consequence of quantization, independent of voice quality. The operator should find an AWQ or GGUF quantization of RP-Ink on HuggingFace and prefer it; if none exists, the A/B's verdict must explicitly attribute latency differences to the quantization asymmetry rather than the finetune.

**fp8_e4m3 KV cache is not enabled on either leg (load-bearing).** Daydream's `tools/arbiter-smoke.py` has already demonstrated that `--kv-cache-dtype fp8_e4m3` deterministically breaks tight-format JSON adherence on Qwen 2.5 7B AWQ (the model produced `!***` garbage-token loops after one clean turn). The `docs/gpu-and-models.md` "The fp8-KV story" section documents the three conditions under which re-enabling would be safe (a ≥14B model, calibrated per-channel scales, or a new 7B variant that passes the arbiter-smoke strict-JSON probe). None of those are met by this turn. Both A/B legs therefore run with FP16 KV cache. If a future turn wants to re-evaluate FP8 KV against RP-Ink specifically, that's a separate spec that starts with the arbiter-smoke check.

**VRAM budget sanity.** Current vLLM serves Qwen 2.5 7B Instruct AWQ at `--gpu-memory-utilization 0.45` (~9 GB ceiling on 20 GB card) to coexist with ComfyUI's SDXL. AWQ INT4 weights are ~5 GB resident. The RP-Ink finetune published as AWQ would slot in at similar residency; fp16/bf16 weights (~14 GB) would not fit under 0.45. Options if no AWQ exists: (a) find a GGUF/AWQ re-quantization by a third party on HF, (b) temporarily `bin/game comfyui-down` during the RP-Ink capture to free VRAM and raise `--gpu-memory-utilization` (commit note documents the deviation), (c) surface the blocker and defer this spec's A/B leg until a fit-budget quant exists. Pick the cheapest path that preserves criterion 4's same-flag contract.

**Hermeticity choice.** The harness installs `skills/rook.json` into a tmp DB rather than the operator's live DB (`~/data/daydream/worlds-dev/live.db`). The capture reflects the CHECKED-IN `rook.json` prompt template, not whatever version is installed on the operator's machine. Makes re-runs deterministic against the source file and lets CI (if ever) run the harness without touching persistent state.

**Model slug derivation.** A safe slug of `config.llm_model()`: lowercase, replace `/` with `-`, strip trailing whitespace. Example: `Qwen/Qwen2.5-7B-Instruct-AWQ` → `qwen-qwen2.5-7b-instruct-awq` (simpler) or `qwen2.5-7b-instruct-awq` (strip org prefix). Either is fine; implementer picks. Keep the slug stable across runs so git-diff between dated files works reliably.

**Where things live.**
- `tests/drift/voice/*.json` (new, 5 files). Corpus, same shape as `tests/drift/aesthetics/`.
- `daydream/voice_samples.py` (new, single module). Exposes `main(argv)` + `__main__` so `python -m daydream.voice_samples` works.
- `bin/game` (modify). Add `cmd_voice_samples` dispatch that shells to `python -m daydream.voice_samples`. Mirror the `cmd_test` / `cmd_world` pattern.
- `docs/pretty/voice-samples/<today>-<awq-slug>.md` (new; AWQ baseline).
- `docs/pretty/voice-samples/<today>-<rp-ink-slug>.md` (new; RP-Ink A/B).
- `tests/test_voice_samples.py` (new).

**Out of scope for this spec** (deferred; do NOT build):
- **Automated rubric or scoring for voice quality.** Eyeball-review via git diff is v1. The metrics table in each sample file captures objective deltas (latency, token counts); subjective voice judgment stays in the reviewer's head. An LLM-judged rubric (analog to `claude-vision-quality-gate`) is a future `voice-quality-gate` BACKLOG entry if it ever matters.
- **Persisting the A/B outcome as a model-choice change.** Whether to switch `DAYDREAM_VLLM_MODEL` project default to RP-Ink is a decision informed by this A/B but not delivered by this spec. Follow-on commit after reading both files.
- **Per-NPC voice corpora.** Rook is the only NPC. When more NPCs land, corpus entries with different `skill` values cover them; harness dispatches by name from the corpus file, not hardcoded.
- **A/B against additional models beyond RP-Ink.** Running a third model is "swap env var, re-run harness, commit" — operator-driven, no new code once this spec lands.
- **fp8_e4m3 KV cache re-evaluation.** Out of scope per the load-bearing disclaimer above.
- **`calibrated-fp8-kv-scales`.** Separate BACKLOG entry; unlocks the +58% decode win on 7B if anyone ever wants to do the calibration-pass engineering work.
- **Full prefill/decode TPS breakdown.** Localreview-style TPS measurement is nice-to-have; v1 captures only total wall-time + token counts. If the RP-Ink verdict is inconclusive, a follow-on turn can add precision.
- **Aesthetic/image-gen A/B.** `watercolor-lora-ab` is a separate entry.

**zat.env conventions to respect.**
- Small committable increments; tests in the same commit as the code they cover. Natural split: harness + corpus + AWQ baseline as C1; RP-Ink A/B capture (after operator-driven model swap) as C2. Both can also land in one commit.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- WHIMSY.md is the tone bible; `skills/rook.json`'s prompt_template is the voice-critical artifact. If the baseline reads off-tone, fix the prompt template FIRST, re-capture AWQ baseline, and THEN do the RP-Ink A/B — so the A/B compares against a well-tuned baseline, not a draft. Localreview's "precision over recall" principle translates directly: a voice finetune that emits more interesting prose but drifts off-tone is worse, not better.
- The captured markdown is durable human-readable content. Metrics table at the top; prompt+response sections below; a reader months later should be able to orient quickly.

**Critical files to create or modify:**

- `tests/drift/voice/{greeting,forge_question,inner_life,small_talk,open_invitation}.json` (new; 5 files)
- `daydream/voice_samples.py` (new)
- `bin/game` (modify; `voice-samples` dispatch)
- `docs/pretty/voice-samples/<today>-qwen2.5-7b-instruct-awq.md` (new; baseline)
- `docs/pretty/voice-samples/<today>-qwen2.5-7b-rp-ink.md` (new; A/B)
- `tests/test_voice_samples.py` (new)

### Findings (2026-04-24)

**Criterion 4 is blocked on model selection, not operational mechanics.** The BACKLOG entry's named model `Qwen/Qwen2.5-7B-RP-Ink` does not exist on HuggingFace — verified via `huggingface_hub.HfApi().model_info()` returning `RepositoryNotFoundError (401)`. An `HfApi().list_models(search='rp-ink')` sweep surfaces these candidates, none of which match the spec's "drop-in Qwen 2.5 7B swap" contract:

- `allura-org/MN-12b-RP-Ink` — Mistral Nemo 12B base, ~7 GB bf16 or ~4 GB GGUF Q4. *Different base model* from our Qwen baseline; the A/B becomes "Qwen vs Nemo voice" with the finetune layered on top, losing the controlled-variable benefit that justifies an A/B.
- `allura-org/Qwen2.5-32b-RP-Ink` — 32B. Localreview Stage 3 rejected a 32B variant on this exact hardware (max sustainable `max_model_len` dropped to 2336 tokens, below the 4347 minimum for real prompts).
- `estrogen/teleut-7b-rpink-*-adpt` — 7B LoRA *adapters* (not standalone models). Would require the base `teleut-7b` plus vLLM's LoRA-serving flags; also a different base model from Qwen.

Per criterion 4's own language ("the spec is blocked on quant selection; the implementer surfaces the blocker and the turn does not ship until resolved"), the turn does not close with 5/5. BACKLOG entry `qwen-2.5-7b-rp-ink-trial` has been updated in the same commit with the HF-search result + the three re-pick options so a future turn doesn't repeat the research.

The harness, corpus, unit tests, and AWQ baseline capture ALL landed (criteria 1/2/3/5, 4/5 met). The voice-bench infrastructure is now production-ready for any subsequent A/B — `voice-samples-capture` from BACKLOG is effectively shipped by this turn even though the entry isn't formally deleted, because the harness + corpus + baseline chronology are all in-tree.

---
*Prior spec (2026-04-24): NPC dialogue shipped 5/5 — `skills/rook.json` authors Rook as a data skill at r-forge (context_predicate, WHIMSY-toned prompt_template, refusal schema), `tests/test_ws_rook.py` covers install + happy path + player_input tag-wrap + hidden-in-meadow + banned-input + refusal. Zero Python changes; pure content + tests.*

<!-- SPEC_META: {"date":"2026-04-24","title":"voice-bench + Qwen RP-Ink A/B","criteria_total":5,"criteria_met":4} -->
