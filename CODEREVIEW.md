## Review — 2026-11-26b (commit: 02cf070)

**Summary:** Refresh review of `origin/main..02cf070`. The focus is 02cf070, the prior review's fixes: `_authorized_key` reads authorized_keys as sshd does, wrangler reads time out after 120 s, a bucket made without its expiry rule names the by-hand step, and the no-rule note names the 60-day design (DATA-LIFECYCLE.md says what holds without it). Tests: before the fix, short 2094 passed and test_prodctl + test_ops_units 64 passed. After: short 2094 passed, and test_prodctl + test_ops_units + test_runbooks 72 passed (one new test). One /codefix cycle fixed the one WARN; the fix is uncommitted (daydream/prodctl.py, tests/test_prodctl.py). Security: 0 BLOCK / 0 WARN / 13 NOTE from the paths scan, unchanged by the post-fix re-check.

**External reviewers:**
None configured.

**Built-in review:**
`/code-review high`: 8 findings, 7 kept after Step 6 (one was about the review-output files).

### Findings

[WARN, fixed] daydream/prodctl.py:804-816 (`age_recipients`) (claude-code). The only refusal is "no keys at all". The box's own `id_ed25519.pub` always yields a key, so when every authorized_keys line is dropped (an expired `expiry-time`, now skipped by 02cf070, or ecdsa / `sk-` keys, which were never read), each weekly offsite is sealed to the box's key alone. That copy cannot be opened once the box is gone, which is the case the offsite copy exists for, and nothing says so: the job succeeds. (high)
  Evidence: `keys += [k for k in map(_authorized_key, ...)]` over both files; `if not keys: raise ProdError(...)`.
  Suggested fix: in `age_recipients`, collect the keys from `authorized_keys` separately from the box's own key, and raise `ProdError` when `authorized_keys` yields no key other than the box's own (for example "no key from ~/.ssh/authorized_keys to encrypt to: a copy only this box can open is not offsite"). Keep the box key as a recipient as now. Add a test: authorized_keys holding only an expired key plus a box key raises; the existing tests still pass.

[NOTE] (also claude-code, security carried) daydream/prodctl.py:794-800. An `expiry-time` that matches the digit pattern but is no date (month 13) raises a ValueError that `main()` does not catch, so every offsite run stops with a traceback before uploading until the line is fixed. sshd skips such a line. Fails loud; operator-controlled input. (medium)

[NOTE] (security, carried) daydream/prodctl.py:780-801. Other differences from sshd: unknown options (a `DISABLED` prefix) are accepted; only the first `expiry-time` is read; `\` escapes any character inside quotes (sshd skips only `\"`, in or out of quotes); `splitlines()` also breaks at `\r`, form feed and Unicode separators; a key pinned to a do-nothing forced command stays a recipient. Nobody has compared this box's real authorized_keys against the parser. (medium)

[NOTE] (also claude-code) daydream/prodctl.py:819-826, :900-909, and `edge._ensure_node_modules`. The timeout covers only `_wrangler_read`. `_wrangler` (bucket create, lifecycle add, the weekly upload) and `npm ci` remain unbounded, and `daydream-offsite.service` is a oneshot with no `TimeoutStartSec`, so a stalled upload holds the unit and the timer does not fire again. The comment at :847 promises more than the code keeps. (medium)

[NOTE] daydream/prodctl.py:843-848. On timeout, `subprocess.run` kills `npx`, but the `node wrangler` it spawned is a grandchild and keeps running. In the weekly unit the cgroup is cleaned at exit; after the installer it lingers. (low)

[NOTE] (also claude-code, security) daydream/prodctl.py:885-891. The expiry note takes the smallest "Expire objects after N days" across all rules and ignores `enabled:` and `prefix:` lines, which wrangler 4.130 prints; a date-based rule ("Expire objects on ...") reads as "no expiry rule". DATA-LIFECYCLE.md now names `offsite-bucket` as the way to tell which kind a bucket is, so the note carries more weight. (medium)

[NOTE] (also claude-code, carried) daydream/prodctl.py:819-849. `_wrangler_read` repeats `_wrangler`, and they have drifted further (timeout and capture on one only). `_wrangler` lets `edge.EdgeError` escape `main()` as a traceback. (low)

[NOTE] (also claude-code, carried) daydream/prodctl.py:913-915. Three wrangler queries run one after another; with the new timeout the installer's bucket step can wait up to 10 minutes with its output captured. (low)

[NOTE] (claude-code) tests/test_prodctl.py:322-323. `test_a_public_bucket_is_a_problem` uses "Public access via the r2.dev URL is enabled.", which wrangler 4.130 never prints (its `dev-url get` says "Public access is enabled at '<url>'."). The check passes either way because it looks for "is disabled", but the fixture sits under a header saying these are wrangler's real words. (medium)

[NOTE] ops/install-prod.sh:185-188. When `--create` makes the bucket but not its rule, the installer's warning says the weekly offsite job fails until `--create` passes. Neither is true then: the bucket exists, the job runs, and a re-run of `--create` passes with a no-rule note. The ProdError printed above it names the right step. (low)

[NOTE] docs/DATA-LIFECYCLE.md:40. The table still says "offsite 60 days" unqualified; the paragraph at :136-143 qualifies it. (low)

[NOTE] (security, post-fix) daydream/prodctl.py:804-819. The new refusal recognises the box only by `id_ed25519.pub`. Another key whose private half lives only on this box (the box's own RSA key listed in authorized_keys, say), or a retired key the parser still treats as live (see the sshd NOTE), lets a copy pass that only the box can open in practice. The last live run sealed to one ed25519 and one RSA key; the operator should confirm where that RSA key's private half lives. (medium)

[NOTE] (security) daydream/prodctl.py:969-984 (`offsite_restore`, older code). age to SSH recipients does not authenticate the sealer, so anyone who can write the bucket can plant a copy that decrypts and restores; the object name is joined to the temp dir unchecked. Low today: every credential that can write the bucket can also redeploy the Worker. (low)

Resolved since the prior review: the retention WARN. 02cf070 records the decision (the design stays 60 days; `offsite-bucket` names a bucket without the rule as departing from it; DATA-LIFECYCLE.md says what holds then), and a bucket made without its rule now fails with the dashboard step instead of passing silently on every later run.

Nine more security NOTEs are carried unchanged in SECURITY.md (files outside this scope), plus the `ci.py` fork-flood NOTE.

### Fixes Applied

- [WARN] daydream/prodctl.py: `age_recipients` reads authorized_keys apart from the box's own `id_ed25519.pub` and raises `ProdError` unless authorized_keys yields a key other than the box's ("a copy only this box can open is not offsite"). The box key stays a recipient. The refusal fires before `age` runs, inside `offsite()`'s temp dir, so nothing is uploaded.
- tests/test_prodctl.py: `test_age_recipients_refuse_when_only_the_box_can_open` (authorized_keys holding an expired key and the box's key raises).

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-11-26, refresh, `c22f58a`): the offsite correction; 0 BLOCK / 2 WARN (the age_recipients WARN fixed and the retention WARN decided, both in 02cf070) / 11 NOTE.*

<!-- REVIEW_META: {"date":"2026-11-26","commit":"02cf070","reviewed_up_to":"02cf070ea1c5a200ea9f12549bd5f5c845cb1d12","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":13} -->
