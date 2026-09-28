## Review — 2026-09-28i (commit: 32a32c1)

**Summary:** Refresh review of four unpushed commits over `origin/main` (`63e15c3`): the second playtest's fixes (the margin index key, the margin's scroll on a room change, a `threads` frame after commands, the bottom fade's gap, hyphen-aware linking), its authored lines (WORLD_VERSION 1.7), the playtest record, and the clean-start rule in the reset playbook. Every changed file read at full depth; `/security` over the 21 code and data files. 0 BLOCK / 1 WARN / 2 NOTE; the WARN fixed in one /codefix cycle with a test; tests stable (medium 1989 passed before, 1990 after; `ruff check .` green).

**External reviewers:**
None configured.

### Findings

[WARN] web/assets/main.js:1243 — linking uses a regex lookbehind, which Safari before 16.4 cannot parse
  Evidence: `new RegExp("(?<![\\w-])(" + pattern + ")(?![\\w-])", "gi")`. On iOS/iPadOS 15 and older Safari the constructor throws a SyntaxError, so `linkifyEntities` throws on every narrate, card and arrival line: the reading column stops rendering for anyone on an older iPad or iPhone. It is the only lookbehind in web/assets.
  Suggested fix: match the preceding character instead of looking behind it, e.g. `(^|[^\\w-])(pattern)(?![\\w-])` and put the captured prefix back in the replacement; keep tests/test_linkify.py's hyphen and person-name cases passing, and add a check that main.js holds no `(?<` lookbehind.

[NOTE] (security) daydream/accounts_cli.py:129 — an account deleted while its player waits on a resident's reply leaves that reply and its `talk:`/`rel:` records behind (written after the purge). Rare; nobody can read them. Suggested: prodctl stops the service around `account delete --yes`, or dialogue re-checks the dreamer after the model call.

[NOTE] (security) tests/test_config_edge.py:61 — a real tailnet address in a test fixture (carried).

### Fixes Applied

- [WARN] web/assets/main.js:1243 — the character before the word is matched and put back (`(^|[^\\w-])`) instead of a lookbehind; tests/test_linkify.py gains `test_browser_js_has_no_regex_lookbehind` (any `(?<=`/`(?<!` in web/assets/*.js fails) and a back-to-back mention case. Re-reviewed: resolved. (`32a32c1`)

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
---
*Prior review (2026-09-28h, refresh, `18bcbd0`): the first friend's fix pass (20 commits); 0 BLOCK / 6 WARN / 3 NOTE, all six WARNs fixed in two /codefix cycles.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"32a32c1","reviewed_up_to":"32a32c119d7dc02bf865bba11a23ace8473b66d9","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":2} -->
