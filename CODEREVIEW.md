## Review — 2026-10-03b (commit: 97a1f4e)

**Summary:** Refresh review of `origin/main..97a1f4e`, with all three files in focus. `ci.main_status` now reads main's tip from the ref API. When the list's newest run is not for the tip, it asks GitHub for the tip's runs by commit, and if none are listed it says "unknown". verify.md gains a row for the CI check. Tests before and after the fix: short 2093 passed, medium 2800 passed. One /codefix cycle fixed the WARN; the fix is uncommitted (daydream/ci.py, tests/test_ci.py, docs/runbooks/verify.md). Security: 0 BLOCK / 0 WARN / 10 NOTE, both from the /security paths scan and from the post-fix re-check; nothing new.

**External reviewers:**
None configured.

**Built-in review:**
`/code-review high`: 8 findings, all 8 kept after Step 6. One became the WARN, one was folded into the WARN's fix, and 6 are NOTEs.

### Findings

[WARN, fixed] (also claude-code) daydream/ci.py:127. When the tip could not be read (`branch_head` returns None after a rate limit, a 5xx, or a timeout in `_gh`), `main_status` fell back to the newest run in the list. A stale list, as in the 2026-10-03 incident, could then still show an older commit's "passed" as main's. That is the hole this change exists to close. The new verify.md row said the line never reports an older commit's run, and `test_an_unreadable_tip_leaves_the_list_to_speak` asserted the "passed". The older main_status tests passed through the unreadable-tip path without exercising it, because the call-ordered `_fake` fed run-list JSON to `branch_head` (claude-code, tests/test_ci.py:20). (medium)

[NOTE] docs/runbooks/verify.md:30 (after the fix). The row says "a tip GitHub cannot name ... is a note" and "The line never reports an older commit's run as main's". When the tip cannot be read and the newest listed run failed or is running, the line still reports that listed run. It may be an older commit's run. It reads red (failed) or as a note (running), never green, so any error is loud. "Never ... green" would be exact. (low)

[NOTE] (claude-code) daydream/ci.py:133. If no run is listed for the tip and the newest listed run is red, the line reads "unknown" (a warn-only note), not "failed". The words still name it ("the newest listed is failed at ..."), but `prod plan` prints its "CI is RED" banner only for a "failed" verdict. Before this change, the first few seconds after a push read "failed", then "running" (also warn-only) once the tip's run appeared. (low)

[NOTE] (also claude-code) daydream/ci.py:136. When the tip's run is in progress, "the last finished run" comes from the possibly stale list. It can therefore name an old failure as main's last finished run, or miss the parent commit's failure. `test_a_red_tip_behind_a_stale_list_is_red` codifies this. The verdict is "running" either way. (low)

[NOTE] daydream/ci.py:133. If the query for the tip's runs itself fails (`runs` returns None), the words say "no run listed for main's tip (just pushed, or GitHub's list is stale)". The verdict ("unknown") is right; the stated reason is wrong. (low)

[NOTE] (claude-code) daydream/ci.py:132. The tip query sends `branch=main` along with `head_sha`. If the branch index is the one that lagged, this query may also come back empty, which reads "unknown" (the safe direction). Querying by `head_sha` alone, keeping the push-event and `_ours` filters, would avoid that index. Which index lagged is unverified. (low)

[NOTE] (claude-code) daydream/ci.py:196. `bin/game ci` prints the tip-aware verdict, then lists `runs(limit=8)` from the raw list. When that list is stale, the listing can have no row for the tip and contradict the verdict. (low)

[NOTE] (also claude-code) bin/game:573. `main_status` now makes two or three `gh` calls in sequence, each with a 30 s timeout, where it made one. `bin/game status` runs it under `timeout 20 ... || true`, so a slow GitHub drops the CI line silently more often. Measured live today: 1.3 s. (low)

[NOTE] (claude-code) daydream/ci.py:59. `runs()` shapes every filtered run, forking one `git log` each, before slicing to `limit`. This predates the change, but the tip query adds another such call. (low)

[NOTE] (security) daydream/ci.py:122-126. This predates the change. About twenty fork pull-request runs on a branch named `main` fill the single page of results. A red main then reads "unknown" (a note), because the `not got` check returns before the new tip read is reached. `ci watch` asks by commit and still sees red. Reading the tip before giving up on an empty list, and asking by commit, would close it. (low)

[NOTE] (security) daydream/ci.py:100. `_SHA` uses `^...$`, which accepts a trailing newline; `fullmatch` is exact. `_subject` passes GitHub's `head_sha` to `git log` as a positional argument; validating it with `_SHA` in `_shape`, or passing `--end-of-options`, would close that. No security effect found. (low)

[NOTE] (security) edge/src/worker.js:45. Carried and unchanged: a thrown read of the `uptime` record erases the outage history. (low)

### Fixes Applied

- [WARN] daydream/ci.py. When the tip cannot be read and the newest listed run passed, the line now reads "unknown". Its words say main's tip could not be read from GitHub and name that listed run. A failed or running newest run still speaks.
- tests/test_ci.py. `test_an_unreadable_tip_never_passes_for_main` expects "unknown" for a listed pass and "failed" for a listed red. The three older verdict tests patch `ci.branch_head` to return their newest run's sha, so they exercise a readable tip and keep their assertions.
- docs/runbooks/verify.md. The CI row lists "a tip GitHub cannot name" among the cases that read as a note.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-03, refresh, `968da2b`): the asleep link preview at the edge; 0 BLOCK / 1 WARN (fixed in 7efca17) / 18 NOTE.*

<!-- REVIEW_META: {"date":"2026-10-03","commit":"97a1f4e","reviewed_up_to":"97a1f4e26bc3a08d32527bb73513d20b1b796010","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":11} -->
