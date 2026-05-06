## Spec — 2026-05-06 — Rook prompt-template variety pass

**Goal:** Fix the template-induced opener tic in Rook's voice (four of five responses in the 2026-04-24 AWQ baseline open with the exact phrase `Rook pauses the steady rhythm of the bellows, wiping hands on the apron, and says,`) so the substrate is healthy enough that a future finetune A/B measures voice content rather than template stickiness. Revise `skills/rook.json` to demand opener variety, then re-capture the AWQ baseline and confirm distinct openers across all 5 corpus prompts.

### Acceptance Criteria

- [x] **`skills/rook.json` is revised to instruct opener variety with at least 3 distinct exemplars.** The skill file (whether in `prompt_template`, `effects_schema.example`, or a new field surfaced to the model at inference time) includes (a) an explicit instruction that the sensory beat opening Rook's response must vary across turns and not echo a sticky template, and (b) at least 3 short example responses demonstrating distinct opening gestures grounded in different sensory anchors (e.g., one anvil-grounded, one chimney/ember-grounded, one tool-or-wildflower-grounded; the implementer picks the trio). A reader of the file can see why varied openers are expected.

- [x] **A re-captured AWQ baseline lands at `docs/pretty/voice-samples/2026-05-06-qwen2.5-7b-instruct-awq.md` with distinct openers across all 5 corpus prompts.** Comparing the 5 narrate outputs section by section, no two responses share the body-language opener, defined as the substring of the narrate text from its start through the character preceding the first single-quote. Same vLLM flags as the prior baseline (`--enforce-eager`, `--gpu-memory-utilization 0.45`, `--max-model-len 8192`, `VLLM_LOGGING_LEVEL=ERROR`, no `--kv-cache-dtype fp8_e4m3`); the captured config block in the markdown documents these so the comparison against the 2026-04-24 file is auditable at a glance.

- [x] **The new baseline holds the WHIMSY tone.** Each of the 5 captured narrate texts is 1-2 short sentences in third-person prose plus a single quoted line in single-quotes, free of banned moods per WHIMSY.md (no urgency, modern tech, harsh edges, sarcasm, violence). The response shape contract from the prior spec (one `narrate` effect carrying prose plus a single quoted line) is preserved.

- [x] **Existing test suite stays green and tier budgets are unchanged.** `bin/game test short` and `bin/game test medium` pass. `tests/test_ws_rook.py` continues to cover install, happy path, player_input tag-wrap, hidden-in-meadow, banned-input, and refusal without modification (Rook's response shape is unchanged; only prompt content varies). `tests/test_voice_samples.py` stays green (it mocks LiteLLM, so prompt-template content does not affect it). No new tier_medium or tier_long tests.

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

### Proposal (2026-05-06)

**What happened.** Three commits ship the Rook prompt-template variety pass: `f41606a` SPEC consume, `102d6aa` C1 (revise `skills/rook.json` for opener variety), `6013b6c` C2 (re-capture 2026-05-06 AWQ baseline with all 5 openers exact-string distinct). The 04-24 tic phrase "pauses the steady rhythm of the bellows" went from 4/5 in 04-24 to 1/5 in 05-06 (and only as a subordinate clause). Each response now answers the player's specific input rather than a generic Rook-being-Rook stock answer. Tier_short (267) and tier_medium (356) green throughout.

**Lessons (eight prompt-template iterations under greedy decoding).** `acompletion_json` defaults to `temperature=0.0`; that makes capture deterministic but funnels the model into ONE preferred response shape regardless of input. Things that bit hard:
- A short, light-pressure prompt collapses to a single high-prior anchor (5/5 same opener on "cooling kettle").
- A "PREFER" list of good spoken lines triggers direct phrase copying ("kettle's nearly done" appeared verbatim 4/5 in one iteration).
- An "AVOID" list ("no 'X whispers secrets'") primes the topics it bans ("whispers secrets" appeared 4/5 in a different iteration).
- Over-constrained prompts cause truncation: model gives up mid-quote and returns JSON with an unclosed in-fiction quote.
- Working configuration: explicit per-input-kind anchor mapping (workpiece for "what are you making", eyes-up for greeting, embers for thoughts, wildflowers for open invitations, listening-to-room for quiet-day) plus three illustrative exemplars plus an explicit ban on the 04-24 phrase by name.

**Soft residuals in the new baseline** (documented in C2 commit body): open_invitation's body-language opener mirrors exemplar 2 verbatim (quoted line is fresh); small_talk uses "pausing the steady rhythm of the bellows" as a subordinate clause despite the explicit ban; inner_life's "the fire's a good friend" personifies. All within WHIMSY range; spec criteria all strictly met.

**Questions and directions for the next turn.**

1. **Resume the RP-Ink-class A/B against a real model.** Picks up the original 04-24 spec's intent. Substrate is now healthy. Most realistic re-pick from BACKLOG `qwen-2.5-7b-rp-ink-trial` is `allura-org/MN-12b-RP-Ink` (Mistral Nemo 12B; ~7 GB bf16 fits under the 0.45 mem-util ceiling). Caveat preserved: A/B becomes "Qwen vs Nemo voice with finetune layered on top" rather than controlled-base; verdict has to attribute differences across two axes.

2. **Programmatic tic-detection probe.** Lock in the gain. Add a small test (`tier_medium` likely) that loads the latest captured baseline, parses the 5 narrate texts, asserts pairwise-distinct body-language openers per the spec heuristic. Cheap turn (one file), catches future template regressions automatically. The SPEC's heuristic note about "first single-quote" has an apostrophe-vs-dialog-quote edge that would also surface during implementation.

3. **Sampler tuning for voice-bench.** The greedy-decoding tax was the dominant cost this turn. A small non-zero temperature override at the voice-bench capture path (e.g., `temperature=0.7` passed through to `acompletion_json` in `daydream/voice_samples.py`) might give natural variety without prompt-engineering acrobatics. Trade-off: less reproducible captures across runs (sampling variance).

4. **Author a second NPC.** Opens up multi-NPC territory and unblocks `npc-drift-loop` and `npc-memory-retrieval` BACKLOG entries (both gated on ≥2 NPCs). Same shape as the NPC dialogue work that shipped 04-24 (JSON skill file, context_predicate, prompt template), now with the variety lessons baked in from the start.

Strongest read: option 1 (RP-Ink A/B) is the natural follow-on of THIS spec since the substrate fix was specifically motivated by making that A/B meaningful. Option 2 (tic-detection probe) is a small companion turn that would land cleanly alongside option 1 or as a standalone "lock in the gain" turn. Options 3 and 4 are bigger pivots.

### Revisit candidates

- `qwen-2.5-7b-rp-ink-trial` — voice-bench fixture exists AND substrate is now healthy after this turn. The "blocked on model selection" status note's three re-pick paths still apply; option 1 above is the most realistic.

### Backlog Sweep

- **Delete:** `voice-samples-capture` — fully shipped: harness, corpus, and dated chronology in tree across 04-24 and 05-06 baselines.
- **Delete:** `voice-and-aesthetic-audit-trail (PARTIALLY LANDED 2026-04-23)` — both halves now landed (image via `bin/game test human` 04-23; voice via voice-bench 04-24 + 05-06).

<!-- SPEC_META: {"date":"2026-05-06","title":"Rook prompt-template variety pass","criteria_total":4,"criteria_met":4} -->
