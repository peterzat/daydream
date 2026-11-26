## Review — 2026-11-26 (commit: c22f58a)

**Summary:** Refresh review of `origin/main..c22f58a`, the offsite correction. It adds `bin/game prod offsite-bucket [--create]`, which checks that the R2 bucket exists and is private and makes a missing one with a 60-day expiry rule. `sudo ops/install-prod.sh` runs it as the operator, the weekly offsite now stops before any work when the bucket is missing, and the docs record the seven failed weeks and the first tried restore. Every file in the full set was in focus. Tests before the fix: short 2094 passed, medium 2807 passed. After: short 2094, medium 2808 (one new test). One /codefix cycle fixed a WARN that /security found in older offsite code (`age_recipients`). The fix is uncommitted (daydream/prodctl.py, tests/test_prodctl.py). The other WARN needs the operator's decision. Security: 0 BLOCK / 1 WARN / 11 NOTE from the paths scan, and 0 / 0 / 12 after the post-fix re-check.

**External reviewers:**
None configured.

**Built-in review:**
`/code-review high`: 10 findings, all 10 kept after Step 6. Three were folded into the retention WARN; the other 7 are NOTEs.

### Findings

[WARN, fixed] daydream/prodctl.py:784-789 (`age_recipients`) (security). This is older code, outside the diff, read in full because the diff touched the file. Offsite backups were sealed to every key found anywhere on a line of authorized_keys that contained `ssh-ed25519 ` or `ssh-rsa `, comment lines included. A key retired by commenting out its line, or one whose `expiry-time` had passed, stayed a recipient of every later offsite copy. Key-like text inside a quoted `command=` option produced a malformed recipient, and `age -R` then failed every run. (high)

[WARN] daydream/prodctl.py:858-889, with docs/DATA-LIFECYCLE.md:40 and :136-137 (also claude-code, also security NOTE). Offsite retention is reported, never enforced, and the design pulls two ways. `offsite-bucket` treats a missing expiry rule as a note and exits 0. DATA-LIFECYCLE.md, unchanged here, promises 60 days offsite and says a deleted account's records age out of the backups (14 days local, 60 offsite). GOING-LIVE.md section 7 now records a bucket made by hand without the rule. So the check passes while `account delete` never ages out of R2. `--create` never changes a bucket that exists, by design. If `r2 bucket create` succeeds and `lifecycle add` then fails, that run errors once, but every later run passes with no rule and nothing can add it (claude-code, :875). Against all of this, an age-only expiry rule deletes every copy 60 days after uploads stop, which is the dead-box case the offsite copy exists for (claude-code, :868). The local instance record gives that as the reason the live bucket has no rule. **Requires a user decision; not for /codefix.** The choice is between enforcing 60 days (a missing, disabled or off-prefix rule becomes a problem, plus a flag to add the rule to an existing bucket) and keeping copies (DATA-LIFECYCLE.md and the 60-day wording in CLOUDFLARE-SETUP.md, backups.md and GOING-LIVE.md change to say so, and `--create` stops adding the rule). The two could also be combined, for example an expiry long enough to outlast a mothball, together with a documented deletion step for the people a copy holds. (medium)

[NOTE] (claude-code) tools/agent_guard.py:119-125. `bin/game prod offsite-bucket --create` creates an R2 bucket and a lifecycle rule in the Cloudflare account with no prompt, under the `bin/game prod *` grant. The analogous `edge kv-create` is in ASK_EDGE. Low harm, because it only creates a private bucket that is missing. Adding the verb to the ask list is a guard change the operator installs, so it is a user decision. (medium)

[NOTE] (claude-code) daydream/prodcheck.py. `prod check`, the gate run after every deploy and wake, does not include the bucket check. A deleted bucket, or an r2.dev URL turned on in the dashboard, shows only when the weekly job fails or someone runs `offsite-bucket`. `bucket_findings` is pure and could feed a check line. This relates to BACKLOG `timer-job-alerts`. (medium)

[NOTE] (claude-code, also security) daydream/prodctl.py:858-863. The expiry note takes the smallest "Expire objects after N days" across all rules and ignores each rule's `enabled` flag and prefix. A disabled 7-day rule therefore reads "copies expire after 7 days". It only affects a note line. (medium)

[NOTE] (claude-code) daydream/prodctl.py:811-821. `_wrangler_read` runs wrangler with no timeout. A stalled Cloudflare call would hang `sudo ops/install-prod.sh` at the bucket step, with its output captured so nothing shows, and would hang the weekly unit at its pre-check. `_wrangler` already had no timeout; the installer is the new exposure. (low)

[NOTE] (claude-code) daydream/prodctl.py:797-821. `_wrangler_read` repeats `_wrangler`'s body, and the two handle a missing token differently. `_wrangler_read` turns EdgeError into ProdError. `_wrangler`, older code, lets EdgeError (a RuntimeError) escape `main`'s except clause as a traceback. A shared runner with optional capture would keep them from drifting. (low)

[NOTE] (claude-code) daydream/prodctl.py:880. The read-only check starts three Node/wrangler processes one after another, each with a cold start of a few seconds, and `offsite()` now adds one more per weekly run. Only the time is affected. (low)

[NOTE] (claude-code) docs/GOING-LIVE.md:218-221, docs/CLOUDFLARE-SETUP.md, docs/runbooks/backups.md and the CLAUDE.md prod bullet. These public docs now record this instance's point-in-time state: the failure dates, and the bucket made without the rule. None of it is in the separation list (no ids, names or addresses). The bucket's current lifecycle state will go stale once the operator changes the rule, and CLAUDE.md puts dashboard state in instance/NOTES.md. (low)

[NOTE] daydream/prodctl.py:879. Right after `--create` makes the bucket, the follow-up `info` read could, if R2 is briefly inconsistent, still answer "does not exist". The run would then exit 1 and the installer would warn about a bucket that does exist. A re-run clears it. This is unverified. (low)

[NOTE] (security, post-fix) daydream/prodctl.py:780-801. The new parser still differs from sshd for rarer ways of retiring a key:
- It accepts unknown options, such as a `DISABLED` prefix that sshd refuses.
- It reads only the first `expiry-time`.
- It lets `\` escape any character inside quotes.
- `splitlines()` also breaks lines at `\r`, form feed and Unicode separators.
- A key pinned to `command="/bin/false"` stays a recipient.

An impossible date (month 13) raises a ValueError that `main` does not catch, so every offsite run fails before uploading until the line is fixed. That fails loud. Sealing to an explicit recipients file, and printing fingerprints on each run, would close all of these. Nobody has checked this box's real authorized_keys against the new parser: the guard denies reading it, so the operator should compare the next run's recipients. (medium for the sshd side)

[NOTE] (security, carried) daydream/ci.py:49-61 and :122-126. About twenty fork pull-request runs on a branch named `main` fill the single page of results, and a red main then reads "unknown". `ci watch` asks by commit and still sees red. Unchanged. (low)

Nine more security NOTEs are carried unchanged in SECURITY.md (files outside this scope).

### Fixes Applied

- [WARN] daydream/prodctl.py: a new `_authorized_key` reads each authorized_keys line the way sshd does. It skips blank and `#` lines and scans a quoted options field, including escaped quotes. The key must follow the options directly. A key whose `expiry-time` has passed is skipped (`Z` means UTC, otherwise local time). `age_recipients` uses it for authorized_keys and for the box's own `id_ed25519.pub`.
- tests/test_prodctl.py: `test_age_recipients_read_authorized_keys_as_sshd_does` covers:
  - both comment styles
  - an expired key and an unexpired key
  - a `command=` option holding a decoy key

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-03b, refresh, `97a1f4e`): main's CI verdict from its tip; 0 BLOCK / 1 WARN (fixed in 8327427) / 11 NOTE.*

<!-- REVIEW_META: {"date":"2026-11-26","commit":"c22f58a","reviewed_up_to":"c22f58ab52f0798f79e9ec9a4291e471fa49b134","base":"origin/main","tier":"refresh","block":0,"warn":2,"note":11} -->
