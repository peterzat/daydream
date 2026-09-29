## Review — 2026-09-29d (commit: dc9a532)

**Summary:** Light review (documentation only) of one commit: the README rewritten around what daydream is for (an agentic-first codebase, frontier models as storytellers, local AI for the reflexes, Zork I as the engine's proof), a current UI screenshot replacing the pre-pivot one, and six new BACKLOG entries. Checked every relative link (all resolve), the stated counts against the world data (17 places, 9 residents, 6 guests, 11 arcs, 29 endings, 172 stray minutes on 12 pages, 38 walkthroughs) and the test tiers (short 1465, medium 2144), the claims about the two client modules, the Worker and the GPU against the code, and the screenshot for anything instance-specific (no browser chrome, URL or real name). No live-instance link, host name or hosting company appears; `tests/test_runbooks.py` (which reads the README's `bin/game prod` verbs) passes.

**External reviewers:**
Skipped (light review).

### Findings

No issues found.

[NOTE] BACKLOG.md (`agent-sessions-without-root`) — describes the operator's agent user as holding the docker group; SECURITY.md's accepted-risk register already says so publicly, so this adds no disclosure.

### Fixes Applied

None.

### Accepted Risks

- **A thing with a `home` handed to a DOZING dreamer** (`verbs._hand_to_player`, the tuck-away branch) waits in their satchel until they rest; declined because walkthrough players count as dozing (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
- (security, carried) daydream/accounts_cli.py:129 — an account deleted while its player waits on a resident's reply leaves that reply and its `talk:`/`rel:` records behind. tests/test_config_edge.py:61 — a real tailnet address in a test fixture.

---
*Prior review (2026-09-29c, refresh, `b488335`): the playtest fixes, what the page offers, the edge rules, the availability limits, the security review's lows and the agent mitigations; 1 BLOCK / 17 WARN found and resolved in two cycles (the guard's tightening made by the main session after /codefix declined to edit its own guard; its credential denial kept strict by decision), 4 NOTE.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"dc9a532","reviewed_up_to":"dc9a5327da64fd82a838a0c10f93da255e7bb6d9","base":"origin/main","tier":"light","block":0,"warn":0,"note":1} -->
