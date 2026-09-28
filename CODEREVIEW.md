## Review — 2026-09-28f (commit: 33d871f) — light

**Summary:** Light review of one docs-only commit on top of the pushed `48c5b2d`: docs/INSTANCES.md's checklist rewritten as engineering status (instance state moved to the local record) and two sentences in docs/ADMIN-ROOT.md that described this box's pending state. Every "done" claim checked against what this turn built, tested and deployed; links and references resolve; no secret or instance detail.

**External reviewers:**
Skipped (light review).

### Findings

No issues found.

### Fixes Applied

None.

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
---
*Prior review (2026-09-28e, full, `03a5b08`): instances, the art keep and lifecycle, `account delete`, the root helper, the uptime watch and the fork path; 0 BLOCK / 15 WARN, all fixed in one /codefix pass; pushed as `48c5b2d`.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"33d871f","reviewed_up_to":"33d871f32f4617244dd6a8b2086eb77ebcacdcd6","base":"origin/main","tier":"light","block":0,"warn":0,"note":0} -->
