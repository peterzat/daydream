## Review — 2026-09-30b (commit: 922c122) — PRELIMINARY (fix loop in progress)

**Summary:** Refresh review of `9ae775d..922c122`: the agent-guard fix for the WARN carried since 2026-09-29 (folders that hold credentials, the gh short-flag bundle, deny before ask, the raw pass past redirections and list calls), the click-scope NOTE (`ws.clicked_in_scope`), and the whitespace fix below. A fresh reviewer probed the guard; `/security` re-scanned everything since `a7cdb15` (it verified the tea-cup, click-scope and guard fixes). Tests at 922c122: `ruff check .` clean, short + medium 2468 passed.

**External reviewers:**
None configured.

### Findings

[WARN] (security) daydream/parser.py:156, :64 — `_THEN_SPLIT` and `_AND_JOIN` backtracked on a long whitespace run: a 500-character line cost about 0.38 s of the event loop. Fixed in 922c122 (whitespace collapses at the top of `parse_line`; a timing test).

The rest are in tools/agent_guard.py. A deny is the guard's answer for a credential read; an ask for a folder that holds one. The hook's timeout is 5 s (docs/claude-settings.local.example.json:54): a timeout or a crash is a non-blocking error and the command runs with no opinion.

[WARN] tools/agent_guard.py:67 (TOKEN_PRINTERS, the git-credential branch; pre-existing) — catastrophic backtracking: `--git-dir=x` matches both alternatives of the repeated group.
  Evidence: a denied command followed by `; git` + ` --git-dir=x`×17 + ` y` (239 characters) times the real hook out; the same suffix hides a gated `bin/game prod` verb.
  Suggested fix: replace the branch with an unambiguous one, e.g. `\bgit\b[^\n;|&]*?\bcredential(?:-\w+)?\s+(?:fill|get)\b`; add a test that times a 500-character adversarial line under 50 ms.

[WARN] tools/agent_guard.py:342 with :98, :269-281 — the raw pass splits segments on `[;&|\n]+` before `_raw_words`, so `2>&1`, `>&` and `&>` are cut apart, and a redirection target holding `=`, `,` or a quoted space leaks a word.
  Evidence: `out="$(bin/game prod 2>&1 invite create --for M)"`, `...>&/tmp/x...`, `...&>/dev/null...`, `out="$(bin/game prod > /tmp/a=b invite create --for M)"` and a quoted `'/tmp/a b'` target all get no decision.
  Suggested fix: before splitting segments, strip every redirection with its target from the raw text, e.g. `\d*(?:>\||>>?|&>>?|>&|<&|<<?<?)(?:-|\s*(?:"[^"]*"|'[^']*'|[^\s;&|()<>'"]+))?` replaced by a space (a `-` after the operator takes no target: `2>&- invite` keeps `invite`).

[WARN] tools/agent_guard.py:95, :98 — `>|` is not a redirection in either pass (pre-existing).
  Evidence: `bin/game prod >| /tmp/x invite create --for M` and `... >| /tmp/x world reset --yes` get no decision.
  Suggested fix: add `>\|` to `REDIRECT` (shlex tokenizes it as one token) and to the raw strip above.

[WARN] tools/agent_guard.py:365-371 — the cd tracking moves the guard's cwd even when the `cd` never takes effect (a subshell, a failing `cd` then `;`, an untaken branch).
  Evidence: `(cd /tmp/a/b); cat ../../.config/./gh/hosts.yml` and `cd /no/such/dir/x; cat ../../...` get no decision (the same `cat` without the cd is denied); `(cd /tmp/a/b/c); grep -rn token ../..` gets none (without it, asks).
  Suggested fix: keep a capped set of candidate cwds (the payload cwd plus each cd target resolved against each candidate, at most 16, deduplicated) and judge every relative word against all of them; `cd -` adds nothing. This also removes the quadratic cost (`cd a; `×16000 took 6.8 s).

[WARN] tools/agent_guard.py:359-363 — globs get no decision, though the docstring now says "however the path is spelled" (pre-existing gap).
  Evidence: `cat ~/.config/*/hosts.yml`, `head ~/.con*/gh/*`, `cat ~/.s?h/id_ed25519`, `cat /etc/cloudflare?/*`, `cd ~/.config && cat g*/hosts.yml`.
  Suggested fix: compare a resolved path to each credential location component by component with `fnmatch.fnmatchcase` (one helper for literal and glob paths): every compared component matches and the path is as long or longer → inside (deny); shorter → a folder that holds it (ask for tree readers). Apply to words that look like paths. Narrow the docstring: shell variables and command substitution (`D=~/.config; cat $D/...`, `$(echo ~)`) are not modeled.

[NOTE] tools/agent_guard.py:394-405 (security) — the guard fails open: an exception in `decide` exits non-blocking and the command runs; since d98b73f an exception also discards an ask already found.
  Suggested fix: catch `Exception` in `main()` and answer ask ("the guard could not read this command; the operator confirms it").

[NOTE] tools/agent_guard.py:222-233, :367 — asks on ordinary work: `_tree_roots` treats a cp/rsync/scp destination and a grep/rg pattern as roots, appends `.` even when a path operand is given, ignores tar's `-C`, and resolves `cd -` to home.
  Evidence: `cp notes.txt ~`, `rsync -a worlds/ ~/`, `grep -rn /srv/daydream/ docs/`, `tar czf /tmp/r.tgz -C /srv/daydream releases`, `cd /tmp && make && cd - && rg foo`, and with cwd `~` `rg foo src/daydream` all ask.
  Suggested fix: drop the pattern (first operand of grep/rg/ag/ack unless `-e`/`--regexp`/`-f`/`--file` gave it); drop the last operand of cp/rsync/scp; add `.` only when no path operand remains; resolve tar operands after `-C DIR` under DIR and do not treat DIR itself as a root.

Every fix needs a test in tests/test_agent_guard.py (build credential strings from parts, as the file does; pass `cwd` in the payload), and the file's existing tests must keep passing.

### Fixes Applied

- 922c122: the whitespace WARN.
- Pending (/codefix): the guard.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: shell variables, command substitution and programs that build paths at run time are outside what it models (the permission prompts and the operator are the other layers).
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-09-30, refresh, `4aeb1e9`): the reflexes spec; 1 BLOCK and 16 WARN (three reviewers and /security) fixed with 33 regression tests; seven NOTEs.*

<!-- REVIEW_META: {"date":"2026-09-30","commit":"922c122","reviewed_up_to":"922c122","base":"origin/main","tier":"refresh","block":0,"warn":5,"note":2,"preliminary":true} -->
