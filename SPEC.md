## Spec — 2026-05-06 — RP-Ink A/B + tic-detection probe

**Goal:** Resume the RP-Ink-class A/B that was blocked at 2026-04-24 now that the substrate is healthy after the prompt-template variety pass. Re-pick is `allura-org/MN-12b-RP-Ink` Q4_K_M GGUF since BF16 weights are 24.5 GB (verified) and AWQ/GPTQ variants do not exist on HuggingFace; capture a voice-bench A/B against the 2026-05-06 AWQ baseline and write a verdict. Companion: ship a programmatic tic-detection probe in `tests/` that automatically catches future template regressions like the 04-24 tic, locking in this turn's gain.

### Acceptance Criteria

- [x] **Programmatic tic-detection probe ships in `tests/`.** Loads a captured baseline markdown (`docs/pretty/voice-samples/<date>-<model>.md`), parses the 5 narrate sections, and asserts that all 5 body-language openers (the substring of each narrate text from its start through the dialog-opening single-quote that precedes Rook's spoken line, NOT the apostrophe inside `Rook's`) are pairwise distinct as exact strings. The probe runs in `tier_short` or `tier_medium` (no GPU; parses static markdown). Demonstrated regression-detection: probe passes against `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md` (post-fix substrate; 5/5 distinct) and FAILS against `docs/pretty/voice-samples/2026-04-24-qwen2.5-7b-instruct-awq.md` (pre-fix substrate; 4/5 share an opener). Both behaviors verified by a small parametrized test that exercises both files.

- [x] **MN-12b-RP-Ink Q4_K_M loads in vLLM at the documented flags, OR a clean blocker is surfaced.** Implementer downloads the GGUF (`bartowski/MN-12b-RP-Ink-GGUF`'s `MN-12b-RP-Ink-Q4_K_M.gguf` is the recommended pick, ~7 GB) and brings vLLM up serving it with the same flags as the AWQ baseline (--enforce-eager, --gpu-memory-utilization 0.45, --max-model-len 8192, VLLM_LOGGING_LEVEL=ERROR, no --kv-cache-dtype fp8_e4m3) plus whatever GGUF-specific flag vLLM 0.19.1 requires for Mistral-arch GGUF. `/v1/models` returns the model. If vLLM cannot serve the GGUF cleanly (architecture incompatibility, OOM, tokenizer mismatch, decode garbage like the fp8-KV regression), the implementer surfaces the blocker exactly as 04-24 did: commit message documents the failure mode, BACKLOG `qwen-2.5-7b-rp-ink-trial` status note updates with the new finding, and this criterion is explicitly marked "blocked: <one-line reason>" in the SPEC evolve rather than checked.

- [x] **A/B baseline captured at `docs/pretty/voice-samples/<today>-<rp-ink-slug>.md`.** Same 5-prompt corpus rendered against the RP-Ink model via `bin/game voice-samples` (with `DAYDREAM_VLLM_MODEL` pointing at the GGUF). The captured config block in the markdown documents the GGUF model path, quantization (Q4_K_M), and any GGUF-specific flag deviations so the comparison against the 2026-05-06 AWQ baseline is auditable at a glance. If criterion 2 is blocked, this criterion is also "blocked: depends on C2."

- [x] **A/B verdict written.** A short comparison lands in the C2 commit message (or alongside the captured file if a paragraph is more readable there), covering: which voice felt closer to WHIMSY across the 5 prompts, where the two voices differed, and whether the new opener-variety substrate held under the RP-Ink finetune. Verdict explicitly attributes differences to BOTH the base architecture (Qwen→Nemo) AND the finetune content, since this is not a controlled-base A/B (the 2026-05-06 proposal noted this caveat). If criteria 2 or 3 are blocked, this criterion is also "blocked."

- [x] **Existing test suite stays green.** `bin/game test short` and `bin/game test medium` pass, including the new tic-detection probe from criterion 1. No new tier_long tests; no GPU-dependent tests added in this turn.

### Context

**Adopted from `### Proposal (2026-05-06)` options 1 + 2.** The user agreed on the recommendation. BACKLOG manifest applied at consume: deleted `voice-samples-capture` and `voice-and-aesthetic-audit-trail (PARTIALLY LANDED 2026-04-23)` (both fully shipped); annotated `qwen-2.5-7b-rp-ink-trial` as ACTIVE in spec 2026-05-06.

**Model-sizing reality check (correction to the proposal).** The 2026-05-06 proposal said "MN-12b-RP-Ink ~7 GB bf16 fits under 0.45 mem-util." That was wrong. Verified via `huggingface_hub.HfApi().model_info('allura-org/MN-12b-RP-Ink')`: 12.25B parameters in BF16, ~24.5 GB resident — far over the 20 GB card. Verified via `HfApi.list_models(search='MN-12b-RP-Ink')`: no AWQ or GPTQ variants exist. The realistic re-pick is therefore a GGUF quantization. `bartowski/MN-12b-RP-Ink-GGUF` is the highest-traffic re-quantizer and publishes the full Q-ladder; Q4_K_M is the "best 4-bit" recommendation (~7 GB resident). vLLM 0.19.1 supports GGUF for Mistral-arch models in principle, but the integration is less battle-tested than AWQ; criterion 2's blocker-surfacing language acknowledges this risk.

**Why the probe (criterion 1) lands first.** It is the smaller, certain piece of work, has zero GPU dependency, and locks in the variety gain from the prior turn. Land C1 before C2-4 even start: if C2-4 block, C1 alone is a complete shippable increment (option 2 of the proposal). The 04-24 and 05-06 baselines are both in tree as durable test fixtures via the audit-trail design, so the probe gets a clean pass/fail demonstration without needing a synthetic fixture.

**Apostrophe-vs-dialog-quote heuristic edge.** The SPEC heuristic from the prior turn used "first single-quote" to detect the body-language opener. In the 2026-05-06 baseline, several narrate texts contain "Rook's" (apostrophe) before the dialog quote. Under a strict char-level interpretation, the opener would be just "Rook" for those, which the spec author did not intend. The probe should match the SPIRIT of the heuristic: skip apostrophes inside words and detect the dialog-opening quote (the `'` that precedes Rook's spoken line, typically `, '` or `, "` patterns; in the captured baselines it is always a standalone `'` after `says,` or `saying,` or comma + space). Implementer's call on the exact regex. The test assertion is "no two responses produce equal openers as defined by the probe."

**vLLM GGUF mechanics (best-effort guidance for the implementer).** Loading a GGUF in vLLM 0.19.1: pass the local `.gguf` file path (or HF repo containing GGUF) as the model arg, plus `--quantization gguf` if vLLM does not auto-detect. The current `bin/game vllm-up` does NOT pass `--quantization`. Three plausible extension paths: (a) add a `DAYDREAM_VLLM_EXTRA_ARGS` env var that gets appended to the launch command; (b) auto-detect a `.gguf` model path and pass `--quantization gguf` automatically; (c) launch vLLM manually for this one A/B and skip `bin/game vllm-up` entirely. Implementer picks the cheapest path that does not regress the AWQ launch. The bartowski/MN-12b-RP-Ink-GGUF repo can be passed by repo ID + filename (`--model bartowski/MN-12b-RP-Ink-GGUF --hf-config-path mistralai/Mistral-Nemo-Instruct-2407` or similar) so the model file ends up in the shared HF cache (zat.env convention: never override `HF_HOME`).

**A/B verdict shape.** Not an automated rubric; eyeball-review per the original voice-bench design. The verdict belongs in the implementing commit message so a future reader can find it via `git log` against the captured baseline file. No new doc file needed.

**zat.env conventions to respect.**
- Small committable increments. Natural split: tic-detection probe + tests-still-green as C1; GGUF bootstrap + A/B capture + verdict as C2.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- Verify build and tests pass before committing each increment.
- HuggingFace cache stays at `~/.cache/huggingface`. Never override `HF_HOME`.
- Models go under `~/data/` if outside the HF cache, never in the project tree.
- Do not introduce a new inference engine or framework for this work. vLLM serves the GGUF or this criterion blocks; switching to llama.cpp / ollama for the A/B is out of scope.

**Out of scope for this spec** (deferred; do NOT build):
- Comprehensive vLLM GGUF testing infrastructure. One model loading is enough for this A/B; broader GGUF support is a separate concern.
- A third A/B leg against a different finetune. Operator-driven future work; voice-bench harness already supports any model swap via `DAYDREAM_VLLM_MODEL`.
- Sampler tuning (option 3 of the proposal). The greedy-decoding tax was real this turn but solving it is a separate spec.
- Authoring a second NPC (option 4 of the proposal). Separate spec.
- Rewriting `bin/game vllm-up` to support arbitrary inference backends. Only the minimum extension required for this A/B.
- Probe extension to semantic similarity, quoted-line content variety, or "soft tic" detection beyond exact-string opener-distinctness. Criterion 1's scope is the strict heuristic.
- Updating the `qwen-2.5-7b-rp-ink-trial` BACKLOG status note's contents beyond what naturally follows from this turn's outcome (handled at turn close, not in this spec's criteria).

**Critical files to create:**
- `tests/test_voice_baseline.py` (or similar) — the tic-detection probe (criterion 1)
- `docs/pretty/voice-samples/<today>-<mn-12b-rp-ink-slug>.md` — the A/B capture (criterion 3, depends on criterion 2)

**Critical files to modify** (only as needed):
- `bin/game` — to support GGUF launch if vLLM auto-detection is insufficient (criterion 2; minimal extension)

### Findings (2026-05-06)

**Two findings, in order. (1) gguf packaging bug, resolved via path (c). (2) MN-12b-RP-Ink finetune is not pipeline-fit, even with the gguf bug fixed.**

**(1) gguf packaging bug.** vLLM 0.19.1's startup crashed during `engine_args.create_engine_config` → `maybe_override_with_speculators` → `transformers.configuration_utils.PretrainedConfig.get_config_dict` → `transformers.modeling_gguf_pytorch_utils.load_gguf_checkpoint` → `is_gguf_available()` → `version.parse('N/A')` → `packaging.version.InvalidVersion: Invalid version: 'N/A'`. Root cause: `transformers.utils.import_utils._is_package_available('gguf')` consults `importlib.metadata.packages_distributions()`, which does not register the gguf import name; the fallback path tries `getattr(gguf, '__version__', 'N/A')` and the gguf module exposes no `__version__` attr, yielding "N/A". Path (a) was tried first: every gguf version satisfying vLLM's `>=0.17.0` constraint (0.17.0, 0.17.1, 0.18.0, 0.19.0) reproduces the bug — no version in the supported range registers correctly in `packages_distributions()`. Path (c) was then applied: `bin/vllm-bootstrap` extended with an idempotent post-install patch step that appends `__version__ = "<installed-version>"` to the installed `gguf/__init__.py`. Verified: `is_gguf_available()` returns True after bootstrap, and re-running bootstrap detects the prior patch and skips. The AWQ path is unaffected (verified by re-launching `bin/game vllm-up` post-experiment and serving Qwen 2.5 7B Instruct AWQ cleanly). Remove the patch block whenever upstream gguf fixes its packaging metadata.

**(2) MN-12b-RP-Ink Q4_K_M does not fit the data-skill pipeline.** With the gguf bug worked around, vLLM loaded the GGUF cleanly under `--max-model-len 4096` (the documented "GGUF-specific deviation"; at `--gpu-memory-utilization 0.45`, Q4_K_M weights leave only ~1.11 GiB for KV cache, vLLM reports 8192 needs 1.25 GiB and the actual ceiling is 7248). The harness ran end-to-end. All five corpus prompts returned the soft fallback narrate `The dream is quiet; nothing stirs just yet.` — a direct vLLM probe confirmed the raw model output is `{"effects":[{}]}` under the strict-JSON `response_format` constraint, which fails the effect-allowlist validation, leaves `applied` empty, and triggers the soft fallback. Without the JSON constraint, the same model produces verbose free-form roleplay continuation that overshoots the "1-2 sentences" instruction. The MN-12b-RP-Ink finetune is trained for prose continuation; its structured-output capability is degraded relative to the Mistral Nemo Instruct base. **Voice-quality A/B against the AWQ baseline is moot for this candidate.** The captured markdown at `docs/pretty/voice-samples/2026-05-06-mn-12b-rp-ink-q4_k_m.md` includes a `## Verdict` section explaining what the reader is seeing without git-blame. A meaningful next-turn A/B would need either (i) a creative-writing finetune that preserves JSON-following capability, (ii) a daydream pipeline change that accepts free-form prose and post-parses, or (iii) a fairer base-vs-finetune A/B (Mistral Nemo Instruct vs. Mistral Nemo + RP-Ink) that factors out the base-architecture axis.

C1 (tic-detection probe) shipped as a durable independent gain — any future template tic regression surfaces as a `tier_short` failure. C5 (tests stay green) holds at 271/360.

---
*Prior spec (2026-05-06): Rook prompt-template variety pass closed 4/4. `skills/rook.json` revised with kind-specific input-mapping anchors + 3 distinct exemplars + explicit ban on the 04-24 tic phrase; new AWQ baseline at `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md` shows all 5 body-language openers exact-string distinct (the 04-24 tic phrase appears 1/5 vs 4/5 in the prior baseline). 8 prompt-template iterations under greedy decoding; lessons in commit bodies of 102d6aa and 6013b6c.*

### Proposal (2026-05-07)

**What happened (commits since SPEC consume cd68c22).** Six commits closed the RP-Ink A/B + tic-detection probe spec at 5/5: `c41d534` (C1: probe at `tests/test_voice_baseline.py`, parametrized regression-detection demo over the 04-24 vs 05-06 baselines), `2c3edb5` (C2 blocker surfacing — gguf packaging-metadata bug, full traceback chain captured), `1a5d99d` (codereview/security refresh that gated the push), `210bb51` (C2 fix — `bin/vllm-bootstrap` extended with an idempotent post-install patch that injects `__version__` into the installed gguf package), `4084bab` (C3+C4 — MN-12b-RP-Ink Q4_K_M GGUF capture + verdict).

**What was learned.** Two distinct findings in order: (1) the gguf packaging bug reproduces at every gguf version in vLLM 0.19.1's supported `>=0.17.0` range (0.17.0, 0.17.1, 0.18.0, 0.19.0); `bin/vllm-bootstrap` is the right place to patch around it. (2) `MN-12b-RP-Ink` does not fit daydream's data-skill pipeline shape: under the strict-JSON `response_format` constraint it returns `{"effects":[{}]}` (content-empty), and without the constraint it produces verbose free-form roleplay continuation. RP-Ink-class finetunes optimize for prose continuation at the cost of structured-output capability relative to their Instruct base. Voice-quality A/B against the AWQ baseline is moot for this candidate.

**Questions and directions for the next turn.**

1. **Mistral Nemo Instruct + MN-RP-Ink controlled-base A/B.** The voice-quality question RP-Ink claims to answer is still open. Adding MN-Instruct as a third leg (also GGUF, same `bin/vllm-bootstrap` patch path now in place) yields two clean comparisons: Qwen-AWQ-Instruct vs MN-Instruct (Qwen-vs-Nemo voice, both Instruct-tuned, no finetune), AND MN-Instruct vs MN+RP-Ink (controlled-base, isolates the finetune contribution). Each leg captures via the existing harness. Confirms whether the JSON-following degradation is RP-Ink-specific or an axis of the Nemo arch generally, and whether RP-Ink offers any voice gain when the substrate works. Most directly answers the original 2026-04-24 question and exercises the `bin/vllm-bootstrap` patch on a second model.

2. **Author a second NPC.** Unblocks BACKLOG `npc-drift-loop` and `npc-memory-retrieval` (both gated on ≥2 NPCs). Same shape as the Rook authoring (one JSON skill file, prompt template, context_predicate), now with the variety-pass lessons baked in from the start. Opens up multi-NPC narration territory.

3. **`watercolor-lora-ab` revisit.** The image audit-trail half (`bin/game test human` qpeek output to `docs/pretty/aesthetic-samples/`) landed in 2026-04-23, satisfying one of the entry's revisit OR-gates. Cheap A/B against `ntc-ai/SDXL-LoRA-slider.watercolor` and `lora-library/B-LoRA-watercolor` via `bin/game image-test`. Independent of the voice-bench thread.

4. **Hygiene fixes** as a small turn: env-var-name mismatch (`voice_samples._vllm_config_snapshot` reads `DAYDREAM_VLLM_MAX_MODEL_LEN`, `bin/game vllm-up` honors `DAYDREAM_VLLM_MAX_LEN`); optional sampler tuning for voice-bench (non-zero temperature to reduce greedy-decoding tax). Both small. Appropriate as a cleanup turn between bigger pieces, or folded into option 1 as a prerequisite.

Strongest read: **option 1**. Definitively closes the voice-A/B thread by getting controlled-base data, exercises the just-shipped bootstrap patch on a second model (more confidence the patch generalizes), and uses the harness as-is. **Option 2** is the natural follow-on if option 1 reads as "voice-bench is done as a thread; move on to content."

### Revisit candidates

- `watercolor-lora-ab` — image audit-trail half landed in 2026-04-23 (qpeek output to `docs/pretty/aesthetic-samples/`); one of the entry's revisit OR-gates is met. Independent thread from the voice-bench work, small turn.

### Backlog Sweep

- **Delete:** `qwen-2.5-7b-rp-ink-trial (ACTIVE in spec 2026-05-06)` — fully tried and answered. The original premise (drop-in Qwen 2.5 7B finetune swap) was disproven 2026-04-24 (no such model exists on HF); the alt (Mistral Nemo finetune via GGUF) was disproven 2026-05-06 (not pipeline-fit). The three documented forward paths (i/ii/iii in the spec's Findings) are independent units of work that warrant new BACKLOG entries if anyone wants to revisit them.

<!-- SPEC_META: {"date":"2026-05-06","title":"RP-Ink A/B + tic-detection probe","criteria_total":5,"criteria_met":5} -->
