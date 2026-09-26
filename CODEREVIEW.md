## Review — 2026-09-26 (commit: e765561) — refresh

**Summary:** Refresh review of the LLM re-evaluation turn against origin/main:
the model bake-off harness (`daydream/model_eval.py`, `bin/game model-eval`,
corpus + tier_short tests, refusal-probe talk-path fix) and the model/engine
switch (Qwen3.5 9B AWQ on vLLM 0.30.0: bootstrap, launcher flags, config
default, retell rule, docs, re-ratified LLM goldens).

**Review scope:** Refresh review. Focus: every code file changed since the
prior review (6c73a8f), read in full; /security over the 14 changed paths
(0 BLOCK / 0 WARN / 3 NOTE, SECURITY.md updated). Tests: short 840 -> 841,
medium 1224 -> 1225 after the fix (the new regression test); tier_long 1262
green on the shipped config earlier this turn.

**External reviewers:** None configured.

### Findings

```
[WARN] daydream/model_eval.py:706 — a subset re-run merges into an existing
       label's results without checking the model is the same
  Evidence: `if args.suites and prior.exists():` updates old["suites"] with the
  new run's suites and prepends the old calls, but never compares
  old["model"] to results["model"]; the merged file keeps the NEW model name.
  Reusing a label for a different model (`run --label x --model B --suites
  dialogue` after a full run of model A under `x`) silently produces a
  results.json whose parser/growth/... scores are model A's while its header
  and dialogue are model B's, and `compare` then reports a model that never
  ran those suites. This is the harness whose output decides model swaps.
  Suggested fix: when merging, refuse (exit non-zero with a message naming
  both models) if old.get("model") != results["model"]; keep the merge for
  the same-model case.

[NOTE] daydream/model_eval.py:824 — compare supports at most 8 runs
  Evidence: letters = "ABCDEFGH"; a 9th run raises IndexError in the blind
  sheet. Suggested fix: none needed today (6 was the max used); extend or
  validate len(dirs) if bigger fields are compared.

[NOTE] bin/vllm-bootstrap:104, bin/game:526 — new default model is an
       unpinned community HF repo (from /security)
  Evidence: cyankiwi/Qwen3.5-9B-AWQ-4bit, no revision pin; the measured
  revision is 156edc4bbeb8d1910ee7be9196bafaf1bc052156. No trust_remote_code,
  weights-only, output still validated. Suggested fix: pin the revision in
  both places, or run vllm with HF_HUB_OFFLINE=1 after bootstrap.
```

### Fixes Applied

- [WARN] daydream/model_eval.py:659 — a `--suites` re-run now exits 2 naming
  both models when the label's results.json belongs to a different model,
  before any endpoint or GPU work; same-model merges unchanged. Test:
  `test_subset_rerun_refuses_to_merge_a_different_model`. (commit e765561)

### Accepted Risks

Carried forward from the prior entry (unchanged; the standing register lives
in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Friend-scope posture: CSRF-gated slot/session endpoints, Origin-checked /ws,
  liveness-gated claim takeover, AccessMiddleware-gated /status + /cache,
  cookie https_only=False, CGNAT hardcoding, tailscale is_authed bypass,
  stored prompt-injection via captured memory, bootstrap $MODEL heredoc,
  cmd_logs path component, qpeek clone, world-reset rm -rf operator trust,
  slot-create body size unbounded (FastAPI default caps apply).

---
*Prior review (2026-07-07c, 6c73a8f): light docs-only review of the v1.0
release-bow commit, 0 BLOCK / 0 WARN / 1 NOTE (release-notes wording).*

<!-- REVIEW_META: {"date":"2026-09-26","commit":"e765561","reviewed_up_to":"e76556134b98fd010909929cdc8757569a799141","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":2} -->
