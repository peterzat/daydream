## Review — 2026-09-29c (commit: b488335)

**Summary:** Refresh review of six commits over `69760f7`: the playtest fixes and "what the page offers" (daydream/heard.py, open/mentions content, the card tab, verb readiness and notes), the Worker's https redirect and encoded-slash refusal, the availability limits (journal guard, presence throttle, socket cap, per-session bucket), the security review's lows (unique names, private things in containers, session cap, Access headers, venv seal, ComfyUI API nodes), and the agent mitigations (the player-text scan, tools/agent_guard.py, play's quoted words, prodctl's side-door refusals). Two independent fresh-context reviewers (server; client/edge/tools) plus this reviewer; `/security` over the 50 non-doc files: 0 BLOCK / 1 WARN / 6 NOTE. Found 1 BLOCK / 20 WARN (the guard finding split into four); all fixed in two cycles. Tests: short 1433 -> 1465, medium 2108 -> 2144, Worker 38, `ruff check .` 4 errors -> clean, `node --check` clean.

**External reviewers:**
None configured.

### Findings

No open BLOCK or WARN.

[NOTE] daydream/skills/effects.py:347, daydream/post.py:257 — Placeholder expansion still runs over letter bodies (names now refuse braces). BACKLOG `placeholders-over-player-text`.

[NOTE] web/assets/main.js (renderTopics) — Topic chips reorder on the next snapshot after an ask, under a finger that may be about to tap again.

[NOTE] tools/agent_guard.py — The credential denial is still a substring test: a commit message, grep pattern or heredoc that merely names one of the listed paths is denied (it blocked this review's own heredoc write of this file). Left strict on purpose: turning a denial into an ask loosens a control on the agent's own actions, which is the operator's call, not a fix loop's. `sed -n` over the guard or settings files also asks (sed counts as a writer); harmless.

[NOTE] (security, carried) daydream/accounts_cli.py:129-136 — the delete-during-talk gap. tests/test_config_edge.py:61 — a real tailnet address in a test fixture.

### Fixes Applied

Cycle 1 (/codefix; re-reviewed: resolved, no new issues):

- [BLOCK] BACKLOG.md — the instance-specific follow-ups moved to the local instance notes (Pending); the shared-origin and sign-in-rule entries rewritten as general guidance; the section intro no longer mentions a local report. The entries had arrived in unpushed commit 2b01510, so the fix is folded into that commit (and its message cleaned) before the push.
- [WARN] web/assets/main.js — prompts clear a pending note's timer; keepNote checks the note class.
- [WARN] web/assets/main.js — sendCommand returns whether it sent; pending shows only then.
- [WARN] web/assets/style.css — dimmed carried things dim.
- [WARN] web/assets/main.js — theName leaves a capitalised possessive bare; a person gets the generic note.
- [WARN] CLAUDE.md, docs/runbooks/README.md — the hook, the full ask set and the credential denial described.
- [WARN] daydream/api/ws.py, slots.py, admin.py, main.js — a rested dreamer's socket closes 4410 and the page wakes without retrying; outside rests (another device, `world rest-toon`, `rest-all`) mark the session left; test in tests/test_dreamer.py.
- [WARN] daydream/heard.py, db.py, tests/conftest.py — the vocabulary cache keys on `db.generation()`; autouse cache reset.
- [WARN] daydream/play.py, verbs.py, skills/effects.py, textscan.py — `from_player` on letter reads and player examines; play marks and quotes them and strips control characters; the scan reads appearances.
- [WARN] daydream/api/slots.py — a leave over the budget still releases, quietly.
- [WARN] daydream/heard.py — only dreaming players hear.
- [WARN] daydream/api/ws.py, story.py — knowledge read once per snapshot; one ownership read per event (`_hold`).
- [WARN] daydream/api/ws.py — a session's rate budget survives reconnects; the test is real.
- [WARN] daydream/prodctl.py — the seal walks before it chmods; the operator-side compile runs `-I -S`.
- [WARN] ruff — clean.
- [WARN] tests/test_browser_playtest.py — the idle-verb note and a staged verb's note on a thing it can't use.

Cycle 2 (/codefix declined: the file is the hook that guards its own tool calls, and a relayed request is not the authority to change it; the main session made the tightening changes at the operator's request for these mitigations, and none that loosens):

- [WARN] tools/agent_guard.py (lexer) — newlines separate commands, `#` is a word character, redirections and their targets are left out (a redirected `deploy` no longer asks).
- [WARN] tools/agent_guard.py (wrappers) — shell flag clusters holding `c`, a shell running a script file, `eval`, wrapper options that take a value (`sudo -u`, `nice -n`, `flock FILE`, `timeout DURATION`), a normalised executable, a release's own bin/game run directly, and a word-by-word fallback for unparseable input.
- [WARN] tools/agent_guard.py (self-protection) — an edit to the guard or to `.claude/settings*.json`, or a writing command on them, asks.
- [WARN] tools/agent_guard.py (credential mentions) — addressed as the NOTE above: kept strict by decision, not loosened.
- tests/test_agent_guard.py — 66 cases (was 35).

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
*Prior review (2026-09-29b, refresh, `69760f7`): the dreamer form's frame sentence, the door's note, DATA-LIFECYCLE, Fen's refusal words and the keeper check; 0 BLOCK / 0 WARN / 4 NOTE with /security 0/0/4.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"6129d7a","reviewed_up_to":"b4883355d41dd2c9530caa23f694a19edd9bc574","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":4} -->
