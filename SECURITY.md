# SECURITY.md

## Security Review — 2026-11-26 (scope: paths)

**Summary:** Path-scoped review of the seven paths the caller named, read in
full and as their change from the last scan (`97a1f4e`) to HEAD `c22f58a`.
Two commits touch them:
- `8327427`: the CI fix the last entry's post-fix pass checked, now
  committed (an unreadable tip turns a listed "passed" into "unknown").
- `c22f58a`: `bin/game prod offsite-bucket [--create]` says whether the R2
  bucket exists, is private and how long copies stay, and with `--create`
  makes a missing one with a 60-day expiry rule. `sudo ops/install-prod.sh`
  runs it as the operator, and the weekly offsite now stops before any work
  when the bucket is missing.

The new code opens no exploitable path. The installer drops to the operator
before it runs repo code, a bucket that exists is never changed, and the
printed errors leave out the request line that names the account. Reading
`prodctl.py` in full found a WARN in older code: the offsite copies are
sealed to commented-out and expired keys in `authorized_keys`, so revoking a
key there never reaches the encryption. One new NOTE: the bucket check
treats a missing or ineffective expiry rule as information, so the 60-day
offsite retention that docs/DATA-LIFECYCLE.md promises can fail without a
sign. The fork-flood NOTE in `ci.py` is still present. Register: 0 BLOCK /
1 WARN / 11 NOTE, 3 in scope and 9 carried.

**Post-fix re-check** (`/codereview` Step 7, uncommitted over `c22f58a`):
`daydream/prodctl.py` and `tests/test_prodctl.py` after `/codefix`'s change
for the WARN. `age_recipients` now reads each line through
`_authorized_key`, which skips comment lines, scans a quoted options field
and leaves out a key whose `expiry-time` has passed. The WARN is resolved:
a commented-out key, an expired key and key-like text inside a quoted
option no longer reach `age -R` (probed; the new test covers each). One new
NOTE: the parser still reads some lines differently from sshd (an option
sshd refuses, a second `expiry-time`, the backslash rule inside quotes,
line breaks other than `\n`) and keeps a key pinned to a do-nothing forced
command, so a key retired in one of those less common ways stays a
recipient, and an impossible expiry date stops every offsite run. The retention NOTE is still present (probed again). Register: 0 BLOCK /
0 WARN / 12 NOTE, 3 in scope and 9 carried.

### Findings

[NOTE] daydream/prodctl.py:780-801 (`_authorized_key`) and :812 — The recipient parser follows sshd for comment lines, a quoted options field and one well-formed `expiry-time`, but it still takes a key from some lines sshd refuses or splits differently, so a key retired in a less common way stays a recipient of every later offsite copy. It accepts any options field, where sshd refuses a line with an unknown option (a `DISABLED` prefix, say) or an `expiry-time` it cannot read (`2020-01-01`, or a `UTC` suffix on this box's OpenSSH 8.9). It reads only the first `expiry-time` (:794), where sshd keeps the earliest. Inside quotes it lets `\` escape any character (:789), where sshd escapes only `\"`, in quotes or out, so `\\"` ends a quoted value here and not in sshd. `splitlines()` (:812) also breaks at `\r`, form feed, vertical tab and a few Unicode separators, where sshd breaks only at `\n`, so text after one of these inside a commented-out line is read as a line of its own. A key pinned to a forced command (a soft disable such as `restrict,command="/bin/false"`, or a single-purpose key for a backup puller) is a recipient too, since sshd still accepts it.
  Attack vector: The operator retires a key by putting a word sshd rejects in front of its line, by adding an earlier `expiry-time` in front of the one the line already carries, or by pinning it to a command that does nothing. The key no longer opens a shell, but each weekly run (`offsite()` at :944) still seals to it, and its holder can read any later copy they can fetch (the R2 and copy paths in the retention NOTE below). The quote and line-break cases need unusual text in the operator's own file, and anyone who can write that file can already add a key, so they are correctness gaps, not a way in. Separately, an impossible date in `expiry-time` (month 13, 30 February) raises ValueError, which `main()` does not catch (:1546): every offsite run stops at that line, before any upload, until the line is fixed.
  Evidence: a probe of `_authorized_key` over the working tree. The fix's own cases hold: `# ...`, `#...` and indented comment lines and a past `expiry-time` return None, and the escaped-quote decoy returns the line's real key. These return a key: `DISABLED ssh-ed25519 K`; `no-such-option,no-pty ssh-ed25519 K`; `expiry-time="20990101",expiry-time="20200101" ssh-ed25519 K`; past dates written `20200101UTC` and `2020-01-01`; `command="echo \\" ssh-ed25519 D " ssh-rsa R`, which returns D where sshd reads R; `command="echo C:\\" ssh-ed25519 K`, a line sshd refuses as an unterminated quote; `# retired key`, then `\r`, form feed, vertical tab, `\x85` or U+2028, then `ssh-ed25519 K`; and `restrict,command="/bin/false" ssh-ed25519 K`. The dates `20201301`, `20200230` and `00000101` raise ValueError.
  Confidence: high for the parser (probed). Medium for sshd's side: it comes from OpenSSH's parsing code (`sshkey_advance_past_options`, `sshauthopt_parse`, the line reader) and the box's 8.9 man page, not from a running sshd. Low that this box's file holds any of these forms (the agent guard denies reading `~/.ssh`).
  Remediation: split on `\n` only; skip a line whose options do not all parse as sshd options, or whose `expiry-time` does not parse; take the earliest `expiry-time`; let `\` escape only `"`, in quotes or out; treat a bad date as a refused line and say so; decide forced-command keys deliberately. Or seal to an explicit recipients file the operator keeps, and print the recipients' fingerprints on each run, which ends the parsing question. Add a test case for each.
  Status: found 2026-11-26 at c22f58a; last checked 2026-11-26 at c22f58a

[NOTE] daydream/prodctl.py:880-885 and :895-911 (with ops/install-prod.sh:185, and docs/DATA-LIFECYCLE.md:40 and :136-137) — The bucket check treats retention as information only. A bucket with no expiry rule passes `offsite-bucket` with a note and exit 0. A rule that is disabled, scoped to another prefix, or longer than 60 days reads as "copies expire after N days". `--create` never adds the rule to a bucket that exists. DATA-LIFECYCLE.md promises 60 days offsite, and says a deleted account's records leave the backups as they age out (14 days local, 60 offsite).
  Attack vector: not attacker-driven; a privacy control that can fail without a sign. A bucket made by hand keeps every weekly copy until someone deletes it, and each copy holds the accounts DB and every typed line. CLOUDFLARE-SETUP.md's by-hand path adds the expiry rule in the dashboard as a separate step, and buckets made before this change had to do the same. `account delete` then never ages out of R2, and every copy stays readable by each key that was a recipient when it was sealed, a key since retired included. Copies leave R2 through a read of the bucket (a dashboard session or wrangler login on a retired laptop, a leaked R2 token, a bucket made public by mistake) or as a copy fetched to another machine, as docs/runbooks/backups.md describes. The installer's check passes, so nothing warns.
  Evidence: a probe of `bucket_findings` with private, domain-free answers and four lifecycle answers: no rule, a disabled 60-day rule, a 1-day rule scoped to `scratch/` and a 365-day rule. All four returned no problems (exit 0). The notes read "no expiry rule: every copy stays until deleted", "copies expire after 60 days", "copies expire after 1 days" and "copies expire after 365 days".
  Confidence: high for the code. The disabled and prefixed cases assume wrangler prints `enabled:` and `prefix:` lines beside `action:`, as the committed fixtures suggest.
  Remediation: report a missing rule, a disabled one, or one that does not expire the `prod-` objects within `OFFSITE_EXPIRE_DAYS` as a problem (exit 1). Add the rule to an existing bucket only through an explicit flag (for example `offsite-bucket --set-expiry`), so `--create` keeps its promise never to change what exists. `prod check` could carry the same line.
  Status: found 2026-11-26 at c22f58a; last checked 2026-11-26 at c22f58a

[NOTE] daydream/ci.py:49-61 and :122-126 (with daydream/prodcheck.py:227-234) — A run of a pull request from a fork's branch named `main` is listed under `branch=main`. About twenty of them fill the one page `runs()` reads, the push-only, same-repository filter leaves it empty, and `main_status` returns "unknown" ("no runs on main") before it reads the tip. `prod check` then passes a red main with a note.
  Attack vector: A stranger forks the public repo and pushes about twenty times to a pull request from their `main`. Each push lists a `pull_request` run, one waiting for approval included. Until our next push, `prod check`, `prod plan`, `bin/game ci` and `bin/game status` read main as "unknown" instead of red. `bin/game ci watch`, the publish's gate, asks by commit and still sees the red run.
  Evidence: `ci.py` is unchanged since `8327427`. A probe of `main_status` with GitHub's paging honored (newest first, `per_page`, and the `branch` and `head_sha` filters): 19 fork runs over a red tip read "failed" after two `gh` calls; 20 and 40 read "unknown" ("no runs on main") after one, so the tip read at :127 is never reached.
  Confidence: high for the mechanism; medium that every push of an unapproved first-time contributor lists a run.
  Remediation: read the tip before giving up on an empty list, and ask by commit (`runs(branch, sha=head)`) whenever the filtered list is empty or its newest is not the tip. A fork's runs carry their own head commits, so they cannot fill that page.
  Status: found 2026-09-29 at d2f7538; last checked 2026-11-26 at c22f58a

Carried (still open; their files are outside this scope and unchanged since `97a1f4e`):

[NOTE] edge/src/worker.js:45-54 and :85 (`watch`) — A failed read of the `uptime` record is taken as an empty record and written back, which erases the recorded outages.
  Status: found 2026-10-03 at 968da2b; last checked 2026-10-03 at 97a1f4e; carried, not re-checked

[NOTE] daydream/llm/safety.py:57-59 (with daydream/api/slots.py:201, daydream/growth.py:286 and :364-381, and node "4" of daydream/images/workflows/painterly_room.json and painterly_portrait.json) — The content banlist is per word, and the two paths that put a friend's words into SDXL (a dreamer's portrait and a grown room's painting) have nothing else between them and a synonym.
  Status: found 2026-10-01 at adc00ff; last checked 2026-10-01 at 2a8d93b; carried, not re-checked

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt.
  Status: found 2026-09-30 at 68125c8; last checked 2026-09-30 at 068a34c; carried, not re-checked

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list.
  Status: found 2026-09-30 at 68125c8; last checked 2026-09-30 at 68125c8; carried, not re-checked

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling on Jev calls.
  Status: found 2026-09-30 at 68125c8; last checked 2026-09-30 at 068a34c; carried, not re-checked

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision.
  Status: found 2026-09-30 at 6981ba7; last checked 2026-09-30 at 068a34c; carried, not re-checked

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing.
  Status: found 2026-09-29 at c50460e; last checked 2026-09-30 at 68125c8; carried, not re-checked

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks.
  Status: found 2026-09-29 at 69760f7; last checked 2026-09-30 at 068a34c; carried, not re-checked

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days).
  Status: found 2026-09-28 at 4cef786; last checked 2026-09-30 at 68125c8; carried, not re-checked

### Traced and cleared this run (not findings)

- **The installer's new step** (`ops/install-prod.sh:184-188`). Root drops to
  the operator with `sudo -u "$OPERATOR" -H`, so no repo code runs as root.
  sudo resets the environment, and `-H` points the run at the operator's own
  token file. It runs after the sudoers install, and a failure only warns.
  What it runs (`bin/game`, `prodctl`, wrangler and its npm tree) already
  runs as the operator whenever the edge verbs do. Nothing after it reads
  the terminal, so when the script is started as documented, input the
  child pushes into the terminal lands in the operator's own shell. Started
  from a root shell instead, that shell would read it as root; the
  operator's user is already root-equivalent (Accepted Risks). If a tunnel
  token was typed earlier in
  the same run, the `umask 077` at :113 carries into the child, which only
  tightens what it creates. Without `XDG_RUNTIME_DIR` under sudo, `bin/game`
  makes its run dir under `/tmp`, and the `prod` verb writes nothing there.
- **The bucket itself.** R2 bucket names are per account, so there is
  nothing to squat. A create against a bucket that exists fails before the
  rule is added, and `--create` never touches an existing bucket. The
  privacy checks fail closed: anything other than "is disabled" and "no
  custom domains" is a problem. They cover the r2.dev URL and custom
  domains, not every way a bucket can be read (an R2 API token, a presigned
  URL, a Worker binding); the copies are age ciphertext in every case.
- **What the new verb prints.** `_wrangler_read` keeps stdout and stderr,
  but only `_cf_error`'s one Cloudflare line, or a fixed sentence, is
  printed. The request line that names the account is dropped. A Cloudflare
  message that itself names an account path (a 7003 "Could not route to
  ...") would still print, to the operator's terminal or the agent's context
  only. The wrangler debug logs the fixed sentence points to hold no
  authorization header (counted, not read: 49 files, none matching `Bearer`,
  `authorization` or the token's variable names).
- **The offsite pre-check** (`prodctl.py:898`). It is one read-only wrangler
  call with the operator's token before any backup. Any error other than a
  missing bucket falls through to the old path.
- **`DAYDREAM_R2_BUCKET`** steers both verbs (it already steered `offsite`).
  Under the standing grant, an injected instruction could make the agent
  create a private, empty bucket under another name, or send ciphertext to
  another bucket in the same account. Neither mints a credential or exposes
  plaintext. `offsite-bucket` is not on the guard's ask list, and needs no
  place there.
- **`ci.py`**, unchanged since `8327427`. The last entry's cleared items
  still hold: the tip must be 40 hex before any query, `_SHA`'s `^...$`
  admits only a trailing newline GitHub never sends, `_subject` passes a
  `head_sha` that only our own push runs supply, and the list passthrough
  serves only the tests' fakes.
- **The rest of `prodctl.py`**, re-read in full. The operator-side reads of
  the service-writable data dir (the `active` link in `instance_dir`, the
  path `_backup` parses from the service's output, `offsite()`'s walk of
  `instances/`, `pull()`) hand paths only to commands run as the service
  user. Those commands run outside the unit's sandbox, but the operator's
  home is 0750 (checked), so they still cannot read it.
- **The fix's own shape** (post-fix, `prodctl.py:777-816`). Only the key
  type and blob reach the recipients file, so no option text reaches
  `age -R`. `split()[0]` runs only on a non-empty stripped line, and the
  scan and the expiry regex are linear in the line. The file sits in a 0700
  temporary directory and holds public keys only. A malformed blob still
  makes `age -R` fail, which `main()` reports before any upload.
- **`cert-authority` lines** (post-fix) stay recipients. sshd accepts
  them, and a CA key's holder can already mint a certificate that logs in
  as the operator, so this widens nothing while the line stands.
- **The `Z` suffix** (post-fix). The box's OpenSSH 8.9 man page gives
  `expiry-time` as `YYYYMMDD` or `YYYYMMDDHHMM[SS]` in the system time
  zone, with no `Z`, so sshd there likely refuses such a line. The parser
  reads it as UTC, and the new test asserts that. Until the stated time the
  key stays a recipient, which is what the line asks for; after it, the
  parser drops it.
- **sshd's configuration** (post-fix). The box's sshd_config and its one
  drop-in set no `RevokedKeys`, `AuthorizedKeysFile` or
  `AuthorizedKeysCommand` (keywords grepped), so `~/.ssh/authorized_keys`
  is a file sshd reads and no revocation list sits beside it. The default
  also reads `authorized_keys2`, which the parser does not: a key kept there
  would only be missing from the recipients.

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 3 items: a dreamer name, its look and a
    username, with no typed lines (the operator's own, per the instance
    notes).
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username, unchanged since the last scan.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- Re-run for the post-fix pass: both unchanged (prod 3 items, dev 63),
  nothing flagged, no bursts, the same high-water marks. Verdict: nobody
  steering.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- These hold none of a key, a token, a private-key block, an account id, an
  email, a box or tailnet address, the operator's surname, a friend's name
  or an invite slug:
  - the seven paths as they stand, and the last three commits of each
    (`git log -p --follow -3`);
  - the range `97a1f4e..c22f58a` (every text file) and its two commit
    messages.
- The operator's Unix user name (a first name, and the commit author's
  public handle) appears as the sudoers template's placeholder
  (`ops/install-prod.sh:173`), in `tests/test_ops_units.py` (with a
  `/home/<user>/src/daydream` path) and in the fake key comments of
  `tests/test_prodctl.py:229-232`. All of it predates this range, and
  earlier reviews treated only the surname as sensitive. Not re-flagged.
  The post-fix test adds one more fake key comment of the same kind
  (`tests/test_prodctl.py:247`); its other comments are generic, and every
  key in it is a placeholder.
- The fixtures are fake: account `0123abcd`, `backups.example.com`, and
  repositories named `x/y`, `me/daydream` and `stranger/daydream`. The R2
  info fixture carries the real bucket's location hint, a continent-scale
  region code that names no address.
- The range records the instance's offsite outage, by date, in CLAUDE.md,
  the docs, BACKLOG, CHANGELOG and test docstrings. Incident history of that
  kind is the repo's style and names nothing on CLAUDE.md's separation list.
- `instance/` is still ignored.

### Coverage

- All dimensions were reviewed for the seven paths, read in full and as
  their diff from `97a1f4e`. CLAUDE.md was read in full; its one changed
  line was checked against the code.
- No suite ran (this skill reads code). Probes, all deterministic and local:
  - `age_recipients` over a scratch authorized_keys (commented-out keys, an
    expired key, an option-quoted decoy);
  - `bucket_findings` over four lifecycle answers;
  - `ci.main_status` with GitHub's paging honored (19, 20 and 40 fork runs
    over a red tip).
- No wrangler, Cloudflare or GitHub call was made. The two text scans read
  local DBs. Nothing was written outside the scratchpad except this file
  and the local instance notes.
- Not checked: whether this box's authorized_keys holds a commented-out or
  expired key (the agent guard denies reading `~/.ssh`), and the live
  bucket's lifecycle rules (no Cloudflare call).
- Read in context, outside scope: `daydream/edge.py` (`_creds`,
  `_wrangler_env`, `_ensure_node_modules`, `_node_env`), `bin/game`'s
  preamble and `prod` dispatch, `ops/systemd/daydream-offsite.service`,
  `docs/runbooks/backups.md`, `docs/DATA-LIFECYCLE.md`, step 13 of
  `docs/CLOUDFLARE-SETUP.md`, `prodcheck.check_ci`, and the guard's ask
  list for the offsite verbs.
- No dependency manifest is in scope.
- Outside the named paths, the range also changes `BACKLOG.md`,
  `CHANGELOG.md`, `docs/CLOUDFLARE-SETUP.md`, `docs/GOING-LIVE.md`,
  `docs/runbooks/backups.md`, `docs/runbooks/verify.md`, `CODEREVIEW.md`
  and `SECURITY.md`. They were pattern-scanned for secrets and instance
  facts only.
- Post-fix pass: the uncommitted diff of `daydream/prodctl.py` and
  `tests/test_prodctl.py` over `c22f58a`, the recipient code and its one
  caller (`offsite()`) in full, and `main()`'s error handling. Probes,
  deterministic and local: `_authorized_key` over 26 inputs (the fix's own
  cases, options sshd refuses, two expiry times, the backslash rule,
  `cert-authority` and forced-command lines, five line separators, five
  impossible dates), and `bucket_findings` over the
  same four lifecycle answers. Read on the box: the OpenSSH version, the
  sshd man page's `expiry-time` entry, and sshd_config keywords. Not
  checked: what the new parser returns for this box's authorized_keys (the
  guard denies `~/.ssh`), so whether the next run's recipients match the
  keys the operator means to hold is unverified.
- Git history checked for secrets: `daydream/prodctl.py` (the Cloudflare
  token through `edge`, the CLI's cookie, the age recipients),
  `ops/install-prod.sh` (the tunnel token prompt), `daydream/ci.py` (the
  operator's `gh` credentials, which it never reads), `CLAUDE.md`, and the
  three test files.

### Accepted Risks

Accepted by the operator for going live (`docs/GOING-LIVE.md` section 9;
docs/ADMIN-ROOT.md "Security posture", 2026-09-28):

- **The engines run as `peter`.** vLLM (`:8000`) and ComfyUI (`:8188`)
  listen unauthenticated on loopback and run as `peter`, who is in the
  docker group. The prod service user can reach both. Planned fix: a
  separate engines user.
- **Local attackers are best-efforts only.** The box is single-user, and
  `peter` keeps the root-equivalent `docker` group, so a hostile process
  running as the operator is out of scope. The helper, the root-only
  secrets, and the validated and logged root actions are reasonable
  precautions, not a boundary against the operator's own user.
- **Known local-only residual (docs/ADMIN-ROOT.md).** systemd reads a
  release's `.release.env` as root, and releases belong to the operator. So
  the operator's user could point it at the tunnel token or at the
  gateway's key file. Anyone who can do that already holds `docker`.
- **The pre-login surface is public** (the door, login, invite redemption,
  static assets). The app and the edge both throttle it.
- **Friends drive shared-world verbs on shared objects** (the co-op
  design).
- **What friends type reaches the local LLM.** Role separation, length
  caps, banlists and strict output validation stand between them.

Accepted by the operator for Jev (docs/EXTERNAL.md, 2026-09-30; the exact
judge list confirmed in `1768691`):

- **While a key is set, TypeSafe receives** friends' typed lines to
  residents and the judge's context. That context includes other dreamers'
  names, whereabouts and deeds. TypeSafe states no retention, and the door
  does not say so.

Accepted in the 2026-09-29 codereview (CODEREVIEW.md):

- **A village thing handed to a dozing dreamer** (`verbs._hand_to_player`,
  the tuck-away branch) waits in their satchel until they rest. A page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. BACKLOG `dozing-handover-of-village-things`.

Carried register (from prior reviews; still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths. Neither path exists in the live Lost Hours world
  (planned for v2).
- Raw parser input is not role-separated. The output is re-grounded to a
  closed verb and an in-scope id. One reply may carry up to three commands,
  and each passes the same check.
- NPC dialogue and growth are exposed to prompt injection. Input is
  wrapped, capped and banlisted, and output is validated before any
  mutation. A promise judge (with Jev beside it when a key is set) only
  chooses among drafts or the authored deflection.
- World envelopes, archives, the installer and `bin/game` are trusted as
  the operator's own. That covers world load and reset content, `reset`'s
  `rm -rf`, dev `.env` sourcing, the dev `0.0.0.0` bind, and the deprecated
  `bootstrap_world`.
- Event queues are bounded (256, drop-oldest).
- DNS (127.0.0.53) and AF_UNIX leave the prod sandbox.
- Any local process can reach `127.0.0.1:54322` and set its own
  `X-Daydream-Client-IP`. That moves throttle keys only; the gate still
  applies.
- `gpu.lock` is writable by the service.
- Invite slugs are unsalted sha256 over about 983,000 phrases, so a copy of
  the accounts DB recovers open slugs.
- Strangers can keep invitations paused (a global cap); `invite unblock`
  reopens them.
- On the Workers Free plan, an anonymous client can exhaust the daily
  request quota. The one WAF rule covers the login and invite paths.
- The operator's Cloudflare token is account-wide: Workers Scripts edit
  cannot be scoped to one Worker.
- Toon names are not unique, and lookalikes are not folded. A new
  dreamer's name must be unique under case, spacing and compatibility
  folding; confusable alphabets and legacy duplicates remain.
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one.
  - `tools/agent_guard.py` has backed them since 2026-09-29, and since
    `8eb8107` the hook runs an installed copy that the operator promotes.
    It is a pattern check, not a boundary: spellings through variables,
    `$'...'`, extglob, interpreter one-liners, script files and the like
    remain (BACKLOG `agent-sessions-without-root`). The allow list runs
    interpreters with no prompt (NOTE above).
- Player text reaches the agent's context through `bin/game play` (names,
  speech, moves, gestures; letters and looks marked) and through
  `bin/game jev report --disagreements` (labelled as data). The verbs an
  injected instruction would want stay behind ask rules.

---
*Prior review (2026-10-03, paths, commit `97a1f4e`, with a post-fix pass over the fix later committed as `8327427`): `daydream/ci.py`, `edge/src/worker.js`, `edge/test/preview.test.js` and `tests/test_ci.py` over `968da2b..97a1f4e`, main's CI verdict read from its tip (a 40-hex tip from the ref API, the tip's runs by commit when the list's newest belongs to another commit, "unknown" when none is listed or when an unreadable tip sits under a listed pass) and the asleep link preview's committed fix. No new finding; the uptime-watch and fork-flood NOTEs were re-checked and still present. The register stood at 0 BLOCK / 0 WARN / 10 NOTE. The full entry is at `git show 8327427:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-11-26","commit":"c22f58ab52f0798f79e9ec9a4291e471fa49b134","scope":"paths","scanned_files":["CLAUDE.md","daydream/ci.py","daydream/prodctl.py","ops/install-prod.sh","tests/test_ci.py","tests/test_ops_units.py","tests/test_prodctl.py"],"block":0,"warn":0,"note":12} -->
