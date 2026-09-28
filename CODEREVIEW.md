## Review — 2026-09-28d (commit: 26ae2da) — light

**Summary:** Light review of one docs-only commit on top of the pushed `be789fc`: docs/runbooks/reset.md (a fresh village, written from the first prod reset) and its line in the runbooks index. Checked every claim against the code and the box (the reset's steps and timings, the art wiped with the world, what survives, the probe account's session file under /srv/daydream/data/play/, the undo through restore-backup), the links, and for secrets or instance details. `tests/test_runbooks.py` passes (every verb named exists).

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
*Prior review (2026-09-28c, full, `cca5c50`): the first prod evening's turn; 0 BLOCK / 12 WARN, all fixed over two /codefix passes (reading-column scroll, the awake page's errors, the arrival cut on every first snapshot, log lines without model text, dvh in @supports, honest layout rules), 2 NOTE (effect-moved toons get no cut; the installed timer units); pushed as `be789fc`.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"26ae2da","reviewed_up_to":"26ae2da63d591a62761ba8caa8b6c67d5aea06b8","base":"origin/main","tier":"light","block":0,"warn":0,"note":0} -->
