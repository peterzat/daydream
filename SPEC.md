## Spec — 2026-05-07 — Voice-bench cleanup hygiene round

**Goal:** Close the carry-overs from the just-shipped 3-turn voice-A/B sequence so the project's durable narrative reflects what was learned and the file system reflects what's actually in use. Four pieces: (a) document the Mistral Nemo + Q4 + data-skill-pipeline finding in `docs/gpu-and-models.md` (today the doc has only a passing line about Mistral 7B; a future reader bumping the LLM model wouldn't know to read the 2026-05-06/05-07 captured baselines); (b) converge the env-var name `voice_samples._vllm_config_snapshot` reads with the one `bin/game vllm-up` honors; (c) capture the three voice-A/B forward paths as durable BACKLOG entries; (d) free ~14 GB of unused GGUF from the HF cache.

### Acceptance Criteria

- [ ] **`docs/gpu-and-models.md` updated with the Mistral Nemo + Q4 + data-skill-pipeline finding.** A reader of the doc should know: the project tested both `bartowski/MN-12b-RP-Ink-GGUF` (Q4_K_M, 12B finetune) and `bartowski/Mistral-Nemo-Instruct-2407-GGUF` (Q4_K_M, 12B controlled-base) and both fail the data-skill pipeline at our prompt template; conclusion is that pipeline incompatibility is base-arch + Q4-quant + prompt-shape, NOT RP-Ink-specific (the controlled-base leg confirms this). Pointers to the captured baselines (`docs/pretty/voice-samples/2026-05-06-mn-12b-rp-ink-q4_k_m.md`, `docs/pretty/voice-samples/2026-05-07-mistral-nemo-instruct-2407.md`) and the relevant commits (`4084bab`, `55fffd0`) so a reader can scroll back to verdict text without re-deriving it. Documents that `bin/vllm-bootstrap` patches a transformers + gguf packaging-metadata bug as an idempotent post-install step (commit `210bb51`), generalizing across both GGUF loads — the patch should be removed when upstream fixes packaging metadata. Lands in an appropriate section (the "Things we have not tried yet" or "LLM stack" sections are natural homes; a sibling section like "Things we tried and rejected" works too — implementer's call).

- [ ] **Env-var name converged across `voice_samples._vllm_config_snapshot` and `bin/game vllm-up`.** Today `daydream/voice_samples.py:168` reads `DAYDREAM_VLLM_MAX_MODEL_LEN` and `bin/game:54` reads `DAYDREAM_VLLM_MAX_LEN`. After this turn, both code sites reference the same env-var name. Implementer picks which name wins; `DAYDREAM_VLLM_MAX_LEN` is the operator-facing entry point (`bin/game vllm-up`'s flag) so it's the natural keeper, but the choice is documented in the implementing commit. The captured config block in future voice-bench markdown reflects vLLM's actual launch flags without a caller-side workaround. Verifiable: `grep DAYDREAM_VLLM_MAX bin/game daydream/voice_samples.py` shows ONE name across both files. If `.env.example` or other docs reference the dropped name, those sites are also updated for consistency.

- [ ] **Three BACKLOG entries added for the voice-A/B forward paths (i, ii, iii) from SPEC 2026-05-07 Findings.** Created via `bin/spec-backlog-apply.sh`'s `append:` op (NOT hand-edited via Write/Edit, per the consume-mode rule that the script owns BACKLOG mutations). Each entry passes the BACKLOG quality gate: specific description (names a *what* and roughly a *where*), concrete revisit criterion (a signal that would make the entry worth picking up again — e.g., a finetune shipping, an architectural change landing, a hardware threshold crossed), concrete why-deferred reason. The three paths are: (a) creative-writing finetune of a JSON-fluent base (Qwen 2.5, Llama 3.x); (b) daydream pipeline change to accept free-form prose + post-parse from the LLM (a `daydream/skills/data.py` change); (c) Mistral 7B Instruct fp16 A/B at `--gpu-memory-utilization 0.7` with ComfyUI down (separates quantization axis from architecture axis). Verifiable: `grep -c "^### " BACKLOG.md` increases by 3 (24 → 27 entries).

- [ ] **Unused GGUF files removed from HF cache.** `~/.cache/huggingface/hub/models--bartowski--MN-12b-RP-Ink-GGUF/` and `~/.cache/huggingface/hub/models--bartowski--Mistral-Nemo-Instruct-2407-GGUF/` (both ~7 GB, both proven not-pipeline-fit). The captured baselines in `docs/pretty/voice-samples/` plus the commit bodies and the `docs/gpu-and-models.md` update from criterion 1 are the durable artifact; the GGUF files are re-downloadable from HF if a future revisit is needed. Verifiable: `du -sh ~/.cache/huggingface/hub/models--bartowski--*GGUF/` returns no output (or "no such file or directory") for the two paths above.

- [ ] **Existing test suite stays green.** `bin/game test short` and `bin/game test medium` pass; in particular the env-var rename in criterion 2 does not regress `tests/test_voice_samples.py` or any other voice-bench-related test. No new tier_long tests; no GPU-dependent tests added.

### Context

**Adopted from `### Proposal (2026-05-07)` option 3 (hygiene round) FIRST, then option 1 (second NPC) as a follow-on spec.** User explicitly requested a full cleanup loop before the second-NPC content turn, with codereview after both. Cleanup scope expanded beyond the proposal's option 3 sketch (env-var fix + optional sampler tuning) to include the docs update, BACKLOG entries for the three voice-A/B forward paths, and the HF-cache cleanup. The second-NPC spec follows in the next consume turn (after the turn-close evolve generates a new proposal).

**Why this matters now.** The 3-turn voice-A/B sequence (2026-04-24 voice-bench, 2026-05-06 prompt-template variety, 2026-05-06 RP-Ink + tic-detection probe, 2026-05-07 controlled-base A/B) shipped a lot of operational knowledge — gguf packaging bug + workaround, MN-12b Q4 pipeline incompatibility, captured failure modes — but most of it lives in commit bodies and SPEC.md `### Findings` sections that aren't naturally read by a future operator deciding whether to bump the LLM model. The cleanup turn is a hygiene pass that consolidates the durable narrative into the canonical model-decisions doc and the BACKLOG, so a future reader of `docs/gpu-and-models.md` or `BACKLOG.md` finds what was learned without git-blame archaeology.

**BACKLOG manifest at consume.** None. The proposal had no `### Backlog Sweep` (no recommend-deletes this turn close), and the only revisit candidate (`watercolor-lora-ab`) was not chosen by the user.

**Risk flags.**
- The env-var rename (criterion 2) might break operator setups that already export the dropped name. Low risk: nothing in the project tree references either name beyond the two code sites; `.env.example` doesn't mention max-len. Implementer should still grep widely before committing.
- The HF-cache deletion (criterion 4) is irreversible per session but recoverable via re-download. The captured markdown files preserve the empirical findings.

**zat.env conventions to respect.**
- Small committable increments. Natural split: criterion 1 (doc update), criterion 2 (env-var rename), criterion 3 (BACKLOG entries), criterion 4 (cache cleanup) are each independently committable, but bundling 1+2+3 into one `Cleanup C1` and criterion 4 into `Cleanup C2` (or all four into a single commit) is fine if iteration converges fast. C5 (tests green) is verified before each commit.
- No new abstractions. The change set is content edits + an env-var rename + tooling-driven BACKLOG additions + filesystem cleanup. No new modules, harnesses, or test infrastructure.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- HuggingFace cache stays at `~/.cache/huggingface`. Never override `HF_HOME`. Removing a model directory from the cache is consistent with the convention (it just frees disk; a future `snapshot_download` would re-create it).

**Out of scope for this spec** (deferred):
- Author the second NPC. Separate follow-on spec; consumed from the turn-close proposal generated after this spec closes.
- CLAUDE.md update beyond optional cross-reference. The substantive narrative lives in `docs/gpu-and-models.md`; CLAUDE.md is for behavioral conventions.
- Refactor `voice_samples.py` beyond the env-var rename. The `_vllm_config_snapshot`'s reliance on env-var probing (rather than live querying vLLM) is documented as intentional in its docstring; not in scope to revisit here.
- Pre-emptively add a regression test that the env-var rename can't drift again. Hygiene; not load-bearing for this spec.
- Sampler tuning for voice-bench (non-zero temperature). Mentioned in the prior proposal's option 3 but separated out: it's a behavioral change, not pure cleanup, and would alter future captures' reproducibility.

**Critical files to modify:**
- `docs/gpu-and-models.md` (criterion 1)
- `daydream/voice_samples.py` (criterion 2)
- `bin/game` (criterion 2)

**Critical files to create:**
- None. BACKLOG.md gains 3 entries via `spec-backlog-apply.sh`'s `append:` op (criterion 3); no new file.

**Filesystem mutations outside the project tree:**
- `rm -rf ~/.cache/huggingface/hub/models--bartowski--MN-12b-RP-Ink-GGUF/` and `~/.cache/huggingface/hub/models--bartowski--Mistral-Nemo-Instruct-2407-GGUF/` (criterion 4). Reversible via re-download.

---
*Prior spec (2026-05-07): MN-Instruct + MN-RP-Ink controlled-base A/B closed 5/5. Hypothesis falsified — both Mistral Nemo Q4 legs (RP-Ink finetune AND Instruct controlled-base) fail the data-skill pipeline; failure modes differ in shape (RP-Ink: deterministic content-empty `{"effects":[{}]}`; Instruct: varied per input) but the conclusion is identical (pipeline incompatibility is base-arch + Q4-quant + prompt-shape, not RP-Ink-specific). Voice-A/B thread effectively closed against Nemo-arch; three baselines durable in tree as audit-trail substrate. `bin/vllm-bootstrap` gguf-`__version__` patch from `210bb51` applied unmodified to the second model, confirming generality. Captured at `docs/pretty/voice-samples/2026-05-07-mistral-nemo-instruct-2407.md`.*

<!-- SPEC_META: {"date":"2026-05-07","title":"Voice-bench cleanup hygiene round","criteria_total":5,"criteria_met":0} -->
