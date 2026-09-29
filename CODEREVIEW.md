## Review — 2026-09-29f (commit: d2f7538)

**Summary:** Refresh review of `e63f319` (the quiet watch skips time spent handling a command) and `d2f7538` (the satchel glints only for a new thread, words for a chosen verb wait out a drop, quiet chips after "+N more", a two-object verb's chosen thing is not a chip target, a close speaks only for the current socket). These fix the findings of a fresh-agent review of `56c985d`, `3ccf3df` and `f0dc83a`, which reached origin without this gate: the push ran as `timeout 120 git push`, and the gate reads `git` as a command only first or after a shell operator (0 BLOCK / 2 WARN / 4 NOTE, all fixed here). `/security` on the paths changed since `c50460e`: 0 BLOCK / 1 WARN (the guard, open for the operator) / 5 NOTE. Tests: medium 2182 before and after the fix.

**External reviewers:**
None configured.

### Findings

[WARN, fixed] tests/test_browser_flow.py:701 — the Talk drop test races `ws.close()` against Enter.
  Evidence: `page.evaluate("() => ws.close()")` returns with the socket CLOSING; the drop timer is armed only in `onclose` (main.js `showDropSoon`), and `connectionDown()` reveals the overlay only when that timer exists. If Enter lands before the close event, the overlay waits the full DROP_GRACE (2.5 s) and `to_have_text(..., timeout=500)` at :704 fails. The test runs in `prod deploy`'s gate, so a flake aborts a deploy.
  Suggested fix: after the close, `page.wait_for_function("() => ws.readyState === WebSocket.CLOSED")` before filling the input (readyState turns CLOSED in the same task that dispatches the close event, so the handler has armed the timer by then).

### Open WARN (needs the operator; not for /codefix)

[WARN] (security) tools/agent_guard.py:36-38, :47, :264-267 — a recursive search one folder below home (for example under `~/.config` or `~/.claude`, by grep, rg or find with -exec) gets no opinion and prints the Cloudflare or GitHub token; a combined short-flag spelling of gh's show-token option on `auth status` does the same (gh 2.4.0 splits a flag group).
  Suggested fix: ask when a search starts at any parent of a credential path; treat a short-flag group holding the token flag after `gh auth status` as the long option; deny any command naming the hosts file's token key.
  Why open: the guard asks the operator before any change to itself (`PROTECTED`, tools/agent_guard.py:199-202), deliberately, since this session carries player text. The fix waits for a session with the operator present. Not accepted; not downgraded. SECURITY.md has the detail.

[NOTE] (security) tools/agent_guard.py:246-255 — the gated-verb check stops at the first redirection, does not read a Python list-form subprocess call, and asks before the credential checks deny.
[NOTE] (security) daydream/ci.py:49-61 — about twenty pushes to a fork PR fill the one page of runs, so a red main reads "unknown" in `prod check` and `prod plan` (`ci watch` filters by commit and is unaffected).
[NOTE] The zat.env push gate misses a push behind a wrapper command (`timeout`, `nice`, `env`): for a zat.env session.
[NOTE] (security, carried) placeholders over letter bodies and appearances; `play` prints a grown place's description unmarked and the server keeps control characters in typed lines; the delete-during-talk gap.

### Fixes Applied

- [WARN] tests/test_browser_flow.py:701 — the Talk drop test waits for `ws.readyState === WebSocket.CLOSED` after the close, before typing (/codefix; re-reviewed: the page stays on the closed socket at least a second before a retry replaces it, so the wait cannot miss).
- From the fresh-agent review of the ungated push: the quiet watch skips time spent handling a command (`e63f319`); the satchel glints only for a new thread and once; words for a chosen verb wait out a drop; quiet chips survive "+N more"; a two-object verb's chosen thing is not a chip target; a close speaks only for the current socket (`d2f7538`).

### Accepted Risks

- **A thing with a `home` handed to a DOZING dreamer** (`verbs._hand_to_player`, the tuck-away branch) waits in their satchel until they rest; declined because walkthrough players count as dozing (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
- (security, carried) daydream/accounts_cli.py:129 — an account deleted while its player waits on a resident's reply leaves that reply and its `talk:`/`rel:` records behind.

---
*Prior review (2026-09-29e, refresh, `3009a51`): the instance-neutral repo, CI on the prod lock and in every publish, and two rounds of agent-guard fixes; 0 BLOCK / 0 WARN / 3 NOTE after fixes.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"d2f7538","reviewed_up_to":"d2f753829bad66be183720fd6d989df33e8c533a","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":4} -->
