## Spec — 2026-05-06 — Rook prompt-template variety pass

**Goal:** Fix the template-induced opener tic in Rook's voice (four of five responses in the 2026-04-24 AWQ baseline open with the exact phrase `Rook pauses the steady rhythm of the bellows, wiping hands on the apron, and says,`) so the substrate is healthy enough that a future finetune A/B measures voice content rather than template stickiness. Revise `skills/rook.json` to demand opener variety, then re-capture the AWQ baseline and confirm distinct openers across all 5 corpus prompts.

### Acceptance Criteria

- [ ] **`skills/rook.json` is revised to instruct opener variety with at least 3 distinct exemplars.** The skill file (whether in `prompt_template`, `effects_schema.example`, or a new field surfaced to the model at inference time) includes (a) an explicit instruction that the sensory beat opening Rook's response must vary across turns and not echo a sticky template, and (b) at least 3 short example responses demonstrating distinct opening gestures grounded in different sensory anchors (e.g., one anvil-grounded, one chimney/ember-grounded, one tool-or-wildflower-grounded; the implementer picks the trio). A reader of the file can see why varied openers are expected.

- [ ] **A re-captured AWQ baseline lands at `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md` with distinct openers across all 5 corpus prompts.** Comparing the 5 narrate outputs section by section, no two responses share the body-language opener, defined as the substring of the narrate text from its start through the character preceding the first single-quote. Same vLLM flags as the prior baseline (`--enforce-eager`, `--gpu-memory-utilization 0.45`, `--max-model-len 8192`, `VLLM_LOGGING_LEVEL=ERROR`, no `--kv-cache-dtype fp8_e4m3`); the captured config block in the markdown documents these so the comparison against the 2026-04-24 file is auditable at a glance.

- [ ] **The new baseline holds the WHIMSY tone.** Each of the 5 captured narrate texts is 1-2 short sentences in third-person prose plus a single quoted line in single-quotes, free of banned moods per WHIMSY.md (no urgency, modern tech, harsh edges, sarcasm, violence). The response shape contract from the prior spec (one `narrate` effect carrying prose plus a single quoted line) is preserved.

- [ ] **Existing test suite stays green and tier budgets are unchanged.** `bin/game test short` and `bin/game test medium` pass. `tests/test_ws_rook.py` continues to cover install, happy path, player_input tag-wrap, hidden-in-meadow, banned-input, and refusal without modification (Rook's response shape is unchanged; only prompt content varies). `tests/test_voice_samples.py` stays green (it mocks LiteLLM, so prompt-template content does not affect it). No new tier_medium or tier_long tests.

### Context

**Adopted from `### Proposal (2026-05-06)` option 1.** The proposal observed the AWQ baseline tic and traced it to `skills/rook.json`'s structure: the body lists four candidate sensory beats as a flat parenthetical, the `prompt_template`'s "Example shape" carries one example (anvil + spectacle), and `effects_schema.example` carries another (bellows + nod). The model averages across these and converges on a single sticky opener. This work is the prerequisite the original 2026-04-24 spec called out ("if the baseline reads off-tone, fix the prompt template FIRST, re-capture AWQ baseline, and THEN do the RP-Ink A/B").

**The 2026-04-24 baseline is preserved as the before-shot.** `docs/pretty/voice-samples/2026-04-24-qwen2.5-7b-instruct-awq.md` stays in tree; the new 2026-05-06 file lands alongside as the after-shot. The dated audit-trail chronology is intentional (per `voice-and-aesthetic-audit-trail` and `voice-samples-capture` in BACKLOG); a reader six months later should be able to scroll back and see when the substrate improved. Do not delete or overwrite the prior file.

**Re-capture mechanics.** `bin/game voice-samples` is the dispatch (shipped in the prior turn, see `daydream/voice_samples.py`). It writes `docs/pretty/voice-samples/<today>-<model_slug>.md`. Same-day re-runs overwrite the same file (per the original spec criterion 2), so iterating on the prompt template plus re-running is cheap. Inputs needed: vLLM up at the documented flags, the corpus already in `tests/drift/voice/`, and the model unchanged (`Qwen/Qwen2.5-7B-Instruct-AWQ`). The harness installs `skills/rook.json` into a tmp DB hermetically, so the captured baseline reflects the checked-in skill file rather than any operator live-DB state.

**Heuristic for "distinct opener."** Compute the substring from the start of each narrate text through the character preceding the first single-quote (the body-language clause before Rook speaks). For the 2026-04-24 baseline, four of these substrings are exactly identical: `Rook pauses the steady rhythm of the bellows, wiping hands on the apron, and says,` (only `open_invitation` drifts to `wipes their hands` and only `greeting` is fully distinct). For the new baseline, all 5 must differ pairwise as exact strings. Whitespace and punctuation count: the failure mode is exact-string repetition like the existing tic, not stylistic similarity. A reader can verify by eye in under a minute by reading down the 5 sections of the captured markdown.

**Localreview "precision over recall" framing.** A voice change that introduces opener variety at the cost of off-tone responses is worse, not better. Iteration order: edit `skills/rook.json`, re-capture, read all 5 responses for tone first, then check opener distinctness. If tone slipped, the variety instruction or exemplars need rebalancing toward WHIMSY-anchored language (warm late-day light, soft watercolor, kept-room cosiness), not loosened.

**`voice-samples-capture` BACKLOG entry effectively closed.** The proposal observed that the harness, corpus, and dated capture chronology are all in tree, fulfilling the original deferral's intent. Not formally deleted in this turn (the proposal lacked a `### Backlog Sweep` subsection and `/spec` only mutates BACKLOG via the manifest path), but a future turn-close evolve sweep is a natural place to remove it. No action required this turn.

**zat.env conventions to respect.**
- Small committable increments. Natural split: prompt-template revision plus tests-still-green as C1; baseline re-capture as C2. Both can land together if iteration converges fast.
- Commits attribute to `user.name` only; no Co-Authored-By trailers. Push only when explicitly asked.
- Verify build and tests pass before committing each increment. Tier_short mocks the LLM, so prompt-template edits do not break it.
- Do not introduce abstractions for this work. The change is a content edit to one JSON file plus a re-run of an existing harness. No new module, no new harness flag, no new test infrastructure. If the implementer wants programmatic tic-detection later, that is a separate BACKLOG entry.

**Out of scope for this spec** (deferred; do NOT build):
- RP-Ink-class finetune A/B (option 2 of the proposal). Worth doing only after the substrate is healthy. Re-pick path in BACKLOG `qwen-2.5-7b-rp-ink-trial`.
- Drift-loop or memory retrieval (option 3 of the proposal). Separate BACKLOG entries (`npc-drift-loop`, `npc-memory-retrieval`) with their own revisit criteria.
- World authoring with Opus (option 4 of the proposal). `world-bootstrap-opus` BACKLOG entry; heavier turn.
- Programmatic tic-detection probe in `tests/`. Criterion 2 is checked by inspection; making it an automated test would couple to non-deterministic LLM output and probably need a `tier_medium` flag plus a fixed sampling seed. Worth its own BACKLOG entry if the prompt-template work needs ongoing monitoring.
- Corpus revision. The 5 prompts in `tests/drift/voice/` are fixed inputs for both the before-baseline and the after-baseline; changing them invalidates the comparison.
- Sampler / temperature tuning. The harness uses whatever defaults `daydream.llm.client.acompletion_json` ships with; revisiting those is a separate concern.

**Critical files to modify:**
- `skills/rook.json` (revise prompt content for variety plus at least 3 distinct exemplars)

**Critical files to create:**
- `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md` (new baseline)

---
*Prior spec (2026-04-24): voice-bench + Qwen RP-Ink A/B closed 4/5. Voice-bench harness, 5-prompt corpus, AWQ baseline, and unit tests shipped (`daydream/voice_samples.py`, `tests/drift/voice/*.json`, `bin/game voice-samples`, `tests/test_voice_samples.py`); RP-Ink leg blocked because `Qwen/Qwen2.5-7B-RP-Ink` does not exist on HuggingFace; three re-pick paths recorded in BACKLOG `qwen-2.5-7b-rp-ink-trial`.*

<!-- SPEC_META: {"date":"2026-05-06","title":"Rook prompt-template variety pass","criteria_total":4,"criteria_met":0} -->
