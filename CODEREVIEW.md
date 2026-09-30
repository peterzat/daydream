## Review — 2026-09-30b (commit: aef3abd)

**Summary:** Refresh review of `9ae775d..aef3abd`: the agent-guard fix for the WARN carried since 2026-09-29 (folders that hold credentials, the gh short-flag bundle, deny before ask, the raw pass past redirections and list calls), the click-scope NOTE (`ws.clicked_in_scope`), and a whitespace fix. A fresh reviewer probed the guard; `/security` re-scanned everything since `a7cdb15` and verified the tea-cup, click-scope and guard fixes. One /codefix cycle. Tests: `ruff check .` clean; short + medium 2468 before, 2517 after (tests/test_agent_guard.py 119 to 165, each new one failing on the old guard).

**External reviewers:**
None configured.

### Findings

[WARN] (security) daydream/parser.py — `_THEN_SPLIT` and `_AND_JOIN` backtracked on a long whitespace run (a 500-character line cost about 0.38 s of the event loop). Fixed in 922c122: whitespace collapses at the top of `parse_line`; a timing test.
[WARN] tools/agent_guard.py (TOKEN_PRINTERS, git-credential branch; pre-existing) — catastrophic backtracking let a padded command time the hook out (no decision). Fixed in aef3abd: one lazy run; a 515-character adversarial line takes 0.5 ms; timing tests.
[WARN] tools/agent_guard.py (raw pass) — `2>&1`, `>&`, `&>` were cut apart and a redirection target with `=`, `,` or a quoted space leaked a word, hiding a gated verb inside a quoted `$( )`. Fixed in aef3abd: redirections and their whole-word targets are stripped before the segment split.
[WARN] tools/agent_guard.py — `>|` was no redirection in either pass (pre-existing). Fixed in aef3abd.
[WARN] tools/agent_guard.py — the cd tracking followed a `cd` that never took effect (subshell, failing cd). Fixed in aef3abd: up to 16 candidate directories, relative words judged against all; more than 16 asks; `cd`'s own options are not its target.
[WARN] tools/agent_guard.py — globs got no decision (`~/.config/*/hosts.yml`, `~/.s?h/...`). Fixed in aef3abd: `_credential_relation` compares component by component with fnmatch (brace groups count); redirection targets get the path checks; the docstring names what is not modeled. `*` matches dotfiles on purpose (dotglob), so `ls ~/*`, `ls /etc/*` and `ls /srv/daydream/*` are denied; no playbook, ops script or tool runs such a command.

[NOTE] (security) tools/agent_guard.py `main()` — the guard fails open: an exception exits non-blocking and the command runs. Left open: a change to the guard costs the operator an approval, so it goes with the next guard change (catch `Exception` in `main()` and answer ask).
[NOTE] tools/agent_guard.py `_tree_roots` — asks on ordinary work: a grep/rg pattern and a cp/rsync/scp destination are treated as roots, and `.` is added even when a path is given (`grep -rn "/srv/daydream/" docs/`, `cp notes.txt ~` ask). Left open for the same reason; it is the main source of needless prompts.
[NOTE] tools/agent_guard.py — not modeled: a here-string carrying a gated verb (`bash <<< '...'`, pre-existing), a redirection glued to its target in the unparseable-line fallback, extglob `@(...)`, shell variables and command substitution.

### Fixes Applied

- 922c122: the whitespace WARN.
- aef3abd (/codefix): the five guard WARNs.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-09-30, refresh, `4aeb1e9`): the reflexes spec; 1 BLOCK and 16 WARN (three reviewers and /security) fixed with 33 regression tests; seven NOTEs.*

<!-- REVIEW_META: {"date":"2026-09-30","commit":"aef3abd","reviewed_up_to":"aef3abd250399776c3875682e8a9cc7340de9622","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":3} -->
