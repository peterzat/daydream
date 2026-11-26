## Review — 2026-11-26c (commit: 36e7c24)

**Summary:** Refresh review of `origin/main..36e7c24`, one test-only commit: an autouse fixture in `tests/test_prodctl.py` points `ROOT_HELPER` at a missing path, the sleep fakes record `egress()` calls, the Cloudflare-error test asserts sleep stops the gateway and wake starts it, and a new test proves `egress("start")` cannot reach the helper. The fix is correct. Tests: short 2094 passed; test_prodctl + test_ops_units + test_runbooks 73 passed. Medium (the tier that holds these tests and that `prod deploy` runs) passed 2812, run with a logging `sudo` shim first on PATH: no test in the medium tier made any `sudo` call. Security: 0 BLOCK / 0 WARN, one new NOTE (paths scan of daydream/prodctl.py and tests/test_prodctl.py; player-text scan unchanged, nobody steering).

**External reviewers:**
None configured.

**Built-in review:**
`/code-review high`: 6 findings, 6 kept after Step 6 (all NOTE; two merged with this review's own).

### Findings

[NOTE] (also claude-code, security) tests/test_prodctl.py:47-53. The guard is local to this file and covers only the root helper. `systemctl()` (`sudo -n /usr/bin/systemctl`), `AS_USER` (`sudo -n -u daydream`), the real `SRV`, and the operator's HOME (edge credentials) stay reachable from any test that misses a fake, and `prod deploy` runs the suite on this box while prod is awake. `test_instance_is_refused_on_verbs_that_act_on_the_attached_one` calls `main()` with wake, rollback, offsite and deploy before faking anything and is safe only because the `--instance` gate refuses first. No test reaches these paths today (verified by the medium run above). Suggested: a suite-wide autouse guard in tests/conftest.py that fails any subprocess whose argv starts with `sudo`, or moves `SRV`/`ROOT_HELPER` to missing paths and clears `AS_USER`. (medium)

[NOTE] (claude-code) daydream/prodctl.py:733 (code already on origin). `sleep_` stops the egress gateway only when `unit_active(EGRESS)`, while the comment above it stops the tunnel and unit unconditionally because a failed or auto-restarting unit is not "active". `ops/systemd/daydream-egress.service` has `Restart=on-failure`, so a gateway in auto-restart keeps looping through a sleep. `test_sleep_stops_a_unit_that_is_not_exactly_active` does not assert the egress stop. Suggested: stop the gateway whatever its state (as for TUNNEL and UNIT) and assert `("stop", EGRESS)` in that test. (medium)

[NOTE] (claude-code) tests/test_prodctl.py:547-549. The guard test calls the real `egress("start")` behind only a literal-path inequality. If the fixture were dropped and the install path also changed, the test itself would start the prod gateway. Suggested: assert `not prodctl.ROOT_HELPER.exists()` before the call. (low)

[NOTE] (also claude-code) tests/test_prodctl.py:511. The egress fake returns None (from `list.append`), so the "egress: up" and "egress: stopped" success branches are never exercised. Suggested: `... or True`. (low)

[NOTE] (claude-code, security) The commit message says "A full short run now makes no helper call", but test_prodctl.py is `tier_medium`; a short run never collected these tests. This review's medium run with the sudo shim supplies the missing verification. (high)

[NOTE] (security, carried with new facts) daydream/prodctl.py `offsite_restore`. Besides the carried points (no proof of origin, unchecked object name): the unpack runs as the operator, GNU tar keeps symlinks pointing outside `dest`, and a copy made only of symlinks to the local backup unpacks with exit 0 and passes the runbook's byte compare while holding no data. `tarfile` with `filter="data"` (available in the venv's 3.10.12) would close this. (low)

The 2026-11-26b entry's other twelve NOTEs (recipient parser vs sshd, the month-13 `expiry-time` traceback, wrangler timeouts and the grandchild process, the expiry-rule parse, `_wrangler_read` duplication, serial wrangler queries, the r2.dev fixture wording, the install-prod.sh warning text, DATA-LIFECYCLE.md:40, the box-key-only recognition) are in code this push does not change and carry unchanged. Nine further security NOTEs are carried in SECURITY.md, plus the `ci.py` fork-flood NOTE.

### Fixes Applied

None.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-11-26b, refresh, `02cf070`): the offsite fixes; 0 BLOCK / 1 WARN (`age_recipients` sealing to the box's key alone, fixed in cf4a451) / 13 NOTE; security 0/0/13.*

<!-- REVIEW_META: {"date":"2026-11-26","commit":"36e7c24","reviewed_up_to":"36e7c24adc71e888a5155e9930c5e8bb5f14171d","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":18} -->
