## Spec — 2026-05-07 — MN-Instruct + MN-RP-Ink controlled-base A/B

**Goal:** Definitively close the voice-A/B thread by adding `mistralai/Mistral-Nemo-Instruct-2407` (Q4_K_M GGUF) as a third leg alongside the existing 2026-05-06 AWQ baseline and 2026-05-06 MN-RP-Ink capture, then write a verdict that attributes voice differences across two clean axes: (a) base-architecture (Qwen-AWQ-Instruct vs MN-Instruct, both Instruct-tuned, no creative-writing finetune) and (b) finetune (MN-Instruct vs MN-RP-Ink, controlled-base, isolates the RP-Ink contribution). A side-effect goal: exercise the just-shipped `bin/vllm-bootstrap` gguf-`__version__` patch on a second model to confirm it generalizes beyond the RP-Ink leg.

### Acceptance Criteria

- [x] **Mistral Nemo Instruct Q4_K_M loads in vLLM at the same flags as the 2026-05-06 MN-RP-Ink leg, OR a clean blocker is surfaced.** Implementer downloads `bartowski/Mistral-Nemo-Instruct-2407-GGUF/Mistral-Nemo-Instruct-2407-Q4_K_M.gguf` (~7 GB, verified on HF) and brings vLLM up serving it with `--enforce-eager`, `--gpu-memory-utilization 0.45`, `--max-model-len 4096` (the documented GGUF-specific deviation from the 8192 AWQ baseline; the 12B Q4 KV-cache budget at 0.45 mem-util has the same 7248 ceiling as MN-RP-Ink), `VLLM_LOGGING_LEVEL=ERROR`, no `--kv-cache-dtype fp8_e4m3`, and a clean `--served-model-name` (e.g. `mistralai/Mistral-Nemo-Instruct-2407`) so the captured filename slug is human-readable. `/v1/models` returns the named model. The `bin/vllm-bootstrap` patch (commit 210bb51) must apply cleanly without modification. If vLLM cannot serve this GGUF cleanly (architecture quirk, OOM, tokenizer mismatch), the implementer surfaces the blocker via commit-message + this criterion marked `(BLOCKED: <reason>)` rather than checked.

- [x] **A/B baseline captured at `docs/pretty/voice-samples/<today>-<mn-instruct-slug>.md`.** Same 5-prompt corpus rendered against MN-Instruct via `bin/game voice-samples` with `DAYDREAM_LLM_MODEL=hosted_vllm/<served-model-name>` and `DAYDREAM_VLLM_MAX_MODEL_LEN=4096` (so the captured config block reflects vLLM's actual launch flags, working around the latent env-var-name mismatch noted in the prior spec). The captured config block + per-prompt narrate matches the markdown shape of the 05-06 captures so eyeball comparison across the three files is straightforward.

- [x] **Verdict written across both axes.** A short comparison lands in the C2 commit message and (for durability without git-blame) as a `## Verdict` section near the top of the new MN-Instruct capture markdown. Covers: (a) base-architecture axis — Qwen-AWQ-Instruct vs MN-Instruct, which voice felt closer to WHIMSY across the 5 prompts and where they differed; (b) finetune axis — whether MN-Instruct produces usable narrate (i.e., does NOT degrade to `{"effects":[{}]}` like MN-RP-Ink did) AND if so whether the RP-Ink finetune offers any voice gain visible past the JSON-following degradation. Verdict explicitly attributes any difference to its axis (don't conflate base vs finetune effects). If MN-Instruct ALSO degrades to content-empty effects, the verdict explicitly classifies that as a Nemo-arch + Q4-quantization + our pipeline-prompt interaction issue (not RP-Ink-specific) and the finetune-axis conclusion is "indeterminate at this quantization."

- [x] **The MN-Instruct baseline either passes the tic-detection probe heuristic (5/5 distinct openers) when fed through the existing parser, OR the verdict notes why it does not** (e.g., the model converges on a stock opener, returns content-empty effects, or doesn't follow Rook's prose-shape contract). The probe at `tests/test_voice_baseline.py` is NOT extended to include the new file as a parametrized fixture — the probe's job stays scoped to the AWQ regression-detection track. Implementer runs the probe's parsing helpers against the new capture as a one-off in the verdict-writing step.

- [x] **Existing test suite stays green and tier budgets are unchanged.** `bin/game test short` and `bin/game test medium` pass. `bin/vllm-bootstrap` re-runs cleanly (idempotent patch step works on the existing venv). No new tier_long tests; no GPU-dependent tests added.

### Context

**Adopted from `### Proposal (2026-05-07)` option 1.** User picked controlled-base A/B over options 2 (second NPC), 3 (watercolor-lora-ab revisit), 4 (hygiene fixes). BACKLOG manifest applied at consume: deleted `qwen-2.5-7b-rp-ink-trial (ACTIVE in spec 2026-05-06)` (fully tried and answered).

**Why this spec exists.** The 2026-05-06 RP-Ink A/B closed at 5/5 with the verdict that MN-12b-RP-Ink is not pipeline-fit (returns `{"effects":[{}]}` under strict-JSON, verbose roleplay continuation without it). That outcome left the original 2026-04-24 question unanswered: does a creative-writing finetune flex meaningfully on Rook's voice? The MN-RP-Ink result told us this finetune doesn't fit, but didn't tell us whether the question itself is answerable. This spec adds the controlled-base leg (MN-Instruct, no finetune) so two clean comparisons are possible.

**Three baselines after this turn.**
- `2026-05-06-qwen2.5-7b-instruct-awq.md` — current default model, post-fix substrate.
- `2026-05-06-mn-12b-rp-ink-q4_k_m.md` — RP-Ink finetune; degenerate output documented.
- `<today>-<mn-instruct-slug>.md` — the new MN-Instruct capture.

**Why MN-Instruct should be JSON-fit when MN-RP-Ink wasn't.** Mistral Nemo Instruct is a chat-tuned model trained on instruction-following + tool-use data. Its structured-output capability is preserved (in fact emphasized) relative to a base completion model. The RP-Ink finetune optimizes for prose continuation, deprioritizing JSON. So the prediction is that MN-Instruct produces well-formed `narrate` effects and the harness writes 5 real captures, comparable to the AWQ baseline.

**Risk flags.**
- Quantization sensitivity: MN-Instruct at Q4 might also struggle with strict JSON (less data points than the BF16 base). If so, criterion 3's "indeterminate" branch applies.
- vLLM tokenizer for Mistral Nemo (Tekken tokenizer): vLLM 0.19.1 supports it, RP-Ink loaded fine, MN-Instruct should too. Same arch, same weight format.
- Cold-start latency: 12B Q4 on a 20 GB Ada is memory-bandwidth-bound; expect ~6-8 s per prompt cold (per the RP-Ink first-capture timings). The harness's wall-time field captures this; the verdict can note it but it's not a deciding factor (the RP-Ink result was decided on output content, not latency).

**vLLM flag deviation, recap.** The MN-RP-Ink leg established that `--max-model-len 4096` is the documented "GGUF-specific deviation" forced by the 12B Q4 KV-cache budget at `--gpu-memory-utilization 0.45`. MN-Instruct has the same VRAM footprint at the same quantization, so the same flag applies. The captured config block makes the deviation auditable.

**Pipeline note.** The harness reads `config.llm_model()` which honors `DAYDREAM_LLM_MODEL`. Set it to `hosted_vllm/<served-model-name>` so litellm dispatches via vLLM's OpenAI-compatible endpoint. For the captured file's slug to be readable (not the full GGUF filesystem path), use vLLM's `--served-model-name` to alias the model.

**zat.env conventions to respect.**
- Small committable increments. Natural split: model bootstrap + first capture as C1, verdict as C2.
- HuggingFace cache stays at `~/.cache/huggingface`. Never override `HF_HOME`.
- Commits attribute to `user.name` only; no Co-Authored-By trailers.
- Do not introduce new abstractions for this work. The change is operational (download a GGUF, run the harness, write a markdown verdict).
- Latent env-var-name mismatch (`voice_samples._vllm_config_snapshot` reads `DAYDREAM_VLLM_MAX_MODEL_LEN`; `bin/game vllm-up` honors `DAYDREAM_VLLM_MAX_LEN`) flagged in 4084bab's commit body. Worked around by setting both. Optional fix in this turn (low scope-creep risk; one-line config edit) but not required by any criterion.

**Out of scope for this spec** (deferred; do NOT build):
- Extending the tic-detection probe to parametrize over the new captures. The probe's job stays scoped to AWQ regression-detection.
- Pipeline change to accept free-form prose + post-parse. Only relevant if MN-Instruct ALSO fails JSON; even then, that's a separate spec.
- A fourth model leg (e.g., a different Q-level of MN-RP-Ink, or a different finetune entirely). One controlled-base leg is the contract.
- Sampler / temperature tuning for voice-bench. Out of this spec; the prior proposal flagged it as a hygiene direction.
- Authoring a second NPC. Separate proposal direction.
- Repo / CI / packaging changes to upstream the gguf-version-patch fix to vLLM or to the gguf project. Out of scope; the patch lives in `bin/vllm-bootstrap` durably enough.

**Critical files to create:**
- `docs/pretty/voice-samples/<today>-<mn-instruct-slug>.md` (new MN-Instruct capture; criterion 2)

**Critical files to modify** (only as needed):
- None expected. The harness, bootstrap patch, and `bin/game` infrastructure all generalize; this spec is operational.

### Findings (2026-05-07)

**Hypothesis falsified.** The spec predicted (Context: "Why MN-Instruct should be JSON-fit when MN-RP-Ink wasn't") that MN-Instruct's chat-tuning would preserve structured-output capability and yield 5 well-formed `narrate` effects, comparable to the AWQ baseline. It does not. Under daydream's actual prompt template (long, multi-instruction), MN-Instruct produces 0/5 usable narrates: 3/5 emit non-JSON-shaped output that fails `json.loads` (88, 74 tokens, plus 1 timeout at 10s), 2/5 emit `{"refused":true}` with no `reason` (resolved by the safety layer to its default reason text). A direct vLLM probe with a simpler system prompt confirmed MN-Instruct DOES return `{"effects":[{}]}` (the same content-empty pattern as MN-RP-Ink) when the prompt is short and clear.

**Both Mistral Nemo legs fail; failure mode varies but conclusion is identical.** RP-Ink: deterministic 5/5 `{"effects":[{}]}`. Instruct: varied per input. Either way, the data-skill pipeline does not work on Mistral-Nemo + 12B Q4 + this prompt template, regardless of finetune. Voice-quality A/B is moot across both Nemo legs.

**Original 04-24 question (does a creative-writing finetune flex on Rook's voice?) remains open, but the answer space has shrunk.** Forward paths from here: (i) a creative-writing finetune of a JSON-fluent base (Qwen, Llama 3.x) at fitting quantization, none currently published in a drop-in form; (ii) daydream pipeline change to accept free-form prose + post-parse; (iii) a Mistral 7B Instruct (smaller, less Q4-sensitive, fits BF16 in our budget without GGUF). All three are operator-research or architectural-change scope; no one is a small follow-on of this turn. The voice-A/B thread is effectively closed against Nemo-arch.

**Side-effect goal met.** The `bin/vllm-bootstrap` gguf-`__version__` patch (commit 210bb51) applied unmodified to a second model (MN-Instruct), confirming it generalizes beyond the RP-Ink leg. The bootstrap step is idempotent and survives venv re-install.

**Tic-detection probe parser exercised on the new file** (one-off per criterion 4): 2 distinct openers across 5 sections (3× FOGGY fallback, 2× default-refusal text). Probe heuristic fails as expected; the captured text is system-emitted fallback prose, not Rook responses. Probe is NOT extended to parametrize over this file.

**Three baselines now in tree** for future audit-trail comparison: `2026-05-06-qwen2.5-7b-instruct-awq.md` (the working substrate), `2026-05-06-mn-12b-rp-ink-q4_k_m.md` (RP-Ink failure mode), `2026-05-07-mistral-nemo-instruct-2407.md` (Instruct failure mode). C5 holds at tier_short 271 / tier_medium 360.

---
*Prior spec (2026-05-06): RP-Ink A/B + tic-detection probe closed 5/5. Tic-detection probe shipped at `tests/test_voice_baseline.py` (parametrized regression-detection over the 04-24 vs 05-06 AWQ baselines); `bin/vllm-bootstrap` extended with an idempotent post-install patch that injects `__version__` into the installed gguf package (fixing a transformers 5.6 + gguf >=0.17.0 packaging-metadata bug); MN-12b-RP-Ink Q4_K_M loaded under `--max-model-len 4096` and produced content-empty `{"effects":[{}]}` under strict-JSON, verbose roleplay continuation without — verdict: this finetune is not pipeline-fit. Captured at `docs/pretty/voice-samples/2026-05-06-mn-12b-rp-ink-q4_k_m.md`.*

### Proposal (2026-05-07)

**What happened (this turn).** Two commits closed the controlled-base A/B at 5/5: `3a2d58a` (SPEC consume of 2026-05-07 proposal option 1, with BACKLOG sweep deleting `qwen-2.5-7b-rp-ink-trial`), `55fffd0` (C1+C2: bootstrapped MN-Instruct GGUF, ran the harness, wrote the verdict in the captured markdown's `## Verdict` section + the commit body). The hypothesis was falsified: MN-Instruct (Q4_K_M GGUF, controlled-base, no creative-writing finetune) ALSO fails the data-skill pipeline. Failure mode varies per input under the actual harness prompt (3/5 non-JSON output that fails `json.loads`, 2/5 emit `{"refused":true}` resolved by the safety layer to its default reason text, 1 timeout at 10 s) but a direct probe with a simpler system prompt confirmed MN-Instruct ALSO returns `{"effects":[{}]}` like MN-RP-Ink — the harness's longer prompt template fragments behavior across inputs. Side-effect goal met: the `bin/vllm-bootstrap` gguf-`__version__` patch from `210bb51` applied unmodified to a second model, confirming generality.

**What was learned.** Both Mistral Nemo Q4 legs fail the data-skill pipeline; failure modes differ but the conclusion is identical. Pipeline incompatibility is **base-architecture + Q4-quantization + prompt-shape**, not RP-Ink-specific. The original 2026-04-24 question (does a creative-writing finetune flex on Rook's voice?) remains open with shrunken forward paths, all operator-research or architectural. The voice-A/B thread is effectively closed against Nemo-arch; three baselines now exist in tree as durable audit-trail substrate (working AWQ + 2 Mistral failure modes).

**Questions and directions for the next turn.**

1. **Author a second NPC.** Was option 2 of the prior proposal; still the natural follow-on now that the voice-bench thread is closed. Concrete and well-scoped: one new JSON skill file + prompt template (with the 2026-05-06 prompt-template-variety lessons baked in), context_predicate scoping, tests mirroring `tests/test_ws_rook.py`. Unblocks BACKLOG `npc-drift-loop` and `npc-memory-retrieval` (both gated on >=2 NPCs). Independently improves the world's surface area regardless of the voice-A/B outcome.

2. **`watercolor-lora-ab` revisit.** Image audit-trail half landed in 2026-04-23 (qpeek + `docs/pretty/aesthetic-samples/`); one of the entry's revisit OR-gates is met. Cheap A/B against `ntc-ai/SDXL-LoRA-slider.watercolor` and `lora-library/B-LoRA-watercolor` via `bin/game image-test`. Independent of the voice-bench thread, small turn.

3. **Hygiene round.** Carry-over follow-ons from the recent voice-bench work: env-var-name mismatch (`voice_samples._vllm_config_snapshot` reads `DAYDREAM_VLLM_MAX_MODEL_LEN`, `bin/game vllm-up` honors `DAYDREAM_VLLM_MAX_LEN`); optional sampler tuning for voice-bench (non-zero temperature to reduce greedy-decoding tax); optionally extend the tic-detection probe to also check that any future captures don't reintroduce a tic. All small, independently committable, low-risk cleanup.

4. **Mistral 7B Instruct A/B** (forward path iii from the spec's Findings). Definitively closes the voice-A/B question against Mistral arch by testing a 7B model at fp16 (~14 GB, just fits at `--gpu-memory-utilization 0.7` with ComfyUI down) — separating the quantization axis from the architecture axis. If 7B fp16 ALSO fails, the issue is base-arch + prompt (quant innocent). If it works, the issue is quant + arch (suggesting a 7B AWQ Mistral would be fine). Worth a half-turn only if the voice-A/B closure feels load-bearing for a future decision; otherwise diminishing returns after 3 turns of voice-bench work.

Strongest read: **option 1** (author a second NPC). The voice-A/B infrastructure is now robust and the substrate is healthy; the natural pivot is to use it for content rather than continue investigating model fitness. Option 3 (hygiene) is a reasonable small companion if option 1 lands fast.

### Revisit candidates

- `watercolor-lora-ab` — image audit-trail half landed in 2026-04-23 (qpeek output to `docs/pretty/aesthetic-samples/`); one of the entry's revisit OR-gates is met. Was surfaced in the prior proposal too; user did not pick it then.

<!-- SPEC_META: {"date":"2026-05-07","title":"MN-Instruct + MN-RP-Ink controlled-base A/B","criteria_total":5,"criteria_met":5} -->
