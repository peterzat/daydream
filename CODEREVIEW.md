## Review — 2026-09-28g (commit: 44d8690)

**Summary:** Refresh review of seven unpushed commits on `origin/main` (`e1adc76`), every file touched since the prior review: comings and goings (`toons.announce_move`, the `arrive` event, arrival replays without presence kinds, the SPA's arrival line and "earlier" marking, others' moves refreshing "here with you"), the dreamer panel and invitation note, Talk's in-page prompt, player-worded form refusals, `bin/game prod plan`, and the publish loop (docs/runbooks/publish.md, the /publish skill, README "Typical use", CLAUDE.md). Every changed file read in full. 0 BLOCK / 3 WARN / 1 NOTE; all three WARNs fixed in one /codefix pass plus a local commit-message reword; tests stable (medium 1957 passed before and after).

**External reviewers:**
None configured.

### Findings

[WARN] web/assets/main.js:570 — `clearStagedVerb()` hid the Talk hint while the text prompt it belonged to stayed open
  Evidence: `renderSnapshot` calls `clearStagedVerb()` on every snapshot, and presence re-snapshots now fire whenever anyone comes or goes; `textTarget` and the "What do you say?" placeholder survived, so the next Enter still spoke to the earlier person with no cue and no "never mind".
  Resolution: fixed (below).

[WARN] daydream/toons.py:389 — `announce_move`'s `extra` parameter had no caller
  Resolution: fixed (below).

[WARN] (security) commit `67e1db3` message — used the deleted prod test account's username as an example; `instance/NOTES.md` records that history was rewritten once to remove it. Not pushed.
  Resolution: fixed (below).

[NOTE] (security) tests/test_config_edge.py:61 — a real tailnet address in a test fixture (outside this diff; public since `5f2bd3d`). Swap in `100.64.0.1` the next time the file is touched; not worth a history rewrite.

### Fixes Applied

- [WARN] web/assets/main.js:570 — `clearStagedVerb` hides the hint only when no text prompt waits; `onObjectClick` first lets a waiting prompt go (`cancelText()`); the browser test re-renders a snapshot mid-prompt and checks the hint holds (verified to fail against the old line). (`44d8690`)
- [WARN] daydream/toons.py:389 — removed the unused `extra` parameter. (`44d8690`)
- [WARN] (security) the commit message reworded locally (`git filter-branch --msg-filter` over `origin/main..HEAD`, tree byte-identical, backup ref dropped): the example is now `"robin_ash" becomes "Robin Ash"`; the commit is now `4a59178`.

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
---
*Prior review (2026-09-28f, light, `33d871f`): the INSTANCES.md checklist rewrite; no issues.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"44d8690","reviewed_up_to":"44d8690cad800c2740f316da52ef69c2932de12e","base":"origin/main","tier":"refresh","block":0,"warn":3,"note":1} -->
