## Review — 2026-09-29e (commit: 3009a51)

**Summary:** Refresh review of seven commits over `5da5d66`: the repo made instance-neutral (no live-instance domain or hosting company outside `edge/wrangler.toml`, `ops/prod.env.example`, SPEC.md's contract and one unit-file comment; test fixtures on example.com), the README's open-weight line, lowercase title and admin paragraph, BACKLOG's credential guidance, CI installing against the prod lock (the two CI-only failures since 2026-09-28), `bin/game ci` with CI on main in `status`, `prod plan`, `prod check` and every publish, and two rounds of agent-guard fixes. Focus set read in full; `/security` ran twice (the fix cycles and guard at `e6c5f99`: 0 BLOCK / 2 WARN / 4 NOTE; the CI tooling and guard at `c50460e`: 0 BLOCK / 3 WARN / 3 NOTE carried), and every WARN was fixed and re-tested (`3009a51`). Tests: short 1493, medium 2172, Worker 38, `ruff check .` clean; a clean venv installed with `-c ops/requirements-prod.lock` passes the two tests that failed in CI.

**External reviewers:**
None configured.

### Findings

No open BLOCK or WARN.

[NOTE] tools/agent_guard.py — residual spellings stay unread (variables and `$'...'` in a verb, globs, interpreter one-liners, `find -exec`, `script -c`); the guard is a pattern check, and the structural fix is BACKLOG `agent-sessions-without-root`. Its raw-text checks deny a line that merely quotes a token-printing command or credential path (commit messages go through a file).

[NOTE] daydream/ci.py — reads through `gh api`, which prompts nothing and needs `gh` signed in; without it, status/plan/check say so and pass. The first push after this commit is the first CI run on the lock-pinned install.

[NOTE] (security, carried) placeholders over letter bodies and appearances; `play` prints a grown place's description unmarked and the server keeps control characters in typed lines; the delete-during-talk gap.

### Fixes Applied

- CI: `pip install -c ops/requirements-prod.lock -e '.[dev]'` (e73fd5b).
- Security scan 1 (e6c5f99), guard: credential paths checked on the raw line (redirection targets), token printers denied on the raw line, a release's edge verbs ask, commands after shell keywords read, the test fixture's tailnet address replaced (c50460e).
- Security scan 2 (c50460e): `bin/game ci` counts only this repository's pushes and prints local git's titles; the guard matches gated verbs on the raw text, denies the old gh's config read, `git -C/-c ... credential fill` and quoted forms, reads of Claude Code's and rclone's credential files, and asks before recursive searches rooted at home or a system directory (3009a51).

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
*Prior review (2026-09-29d, light, `dc9a532`): the README rewrite, a current screenshot and six BACKLOG entries; no issues, 1 NOTE.*

<!-- REVIEW_META: {"date":"2026-09-29","commit":"3009a51","reviewed_up_to":"3009a517083d8973f00379896a40655ed033955f","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":3} -->
