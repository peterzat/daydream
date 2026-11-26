# SECURITY.md

## Security Review — 2026-11-26 (scope: paths)

**Summary:** Path-scoped review of `daydream/prodctl.py` and
`tests/test_prodctl.py` at HEAD `36e7c24`, read in full and as their change
from the last scan (`02cf070`). Two commits touch them since then:
- `cf4a451` commits the `age_recipients` refusal of a box-only copy, as the
  last post-fix pass checked it.
- `36e7c24` keeps this module's tests off the installed root helper. Before
  it, the sleep and wake tests stopped and started prod's egress gateway
  through `sudo -n` on every medium run since 2026-10-01.

The fix holds for this module. One new NOTE: nothing suite-wide keeps a test
off prodctl's other passwordless prod paths. In particular, the `--instance`
refusal test would run a refused verb against the real release if the gate
ever let that verb through. The three in-scope NOTEs are still present,
re-probed at HEAD. The restore NOTE now records that the unpack runs as the
operator and keeps symlinks that leave `dest`. Register: 0 BLOCK / 0 WARN /
14 NOTE, 4 in scope and 10 carried.

### Findings

[NOTE] tests/test_prodctl.py:47-53 and :648-663, with daydream/prodctl.py:66, :122, :183-187 and :325-328 — The new autouse fixture keeps this module's tests off the root helper, but nothing keeps the suite off prodctl's other passwordless prod paths. In a test, `SRV` is the real `/srv/daydream` unless a fixture moves it (:66 reads `DAYDREAM_PROD_ROOT`, which the suite never sets). `AS_USER` is `daydream` (:122), so `run_release_python` and `run_as_prod_bytes` run as the service user against prod data (:183-187), and `systemctl` stops, starts and restarts the prod units (:325-328). The sudoers entry (ops/sudoers.d/daydream) allows all of these without a password, and this box has both the release link and the helper. HOME stays the operator's (tests/conftest.py:99 only sets a default), so `_edge()` finds the real Cloudflare credentials. Each test fakes only what it reaches: `srv` moves `SRV` and clears `AS_USER`, the sleep, deploy and swap fakes replace `systemctl`, and the new fixture moves `ROOT_HELPER`, in this module only. tests/conftest.py keeps every test off Jev's network (`_no_jev`, :143-160) and off the real data dir (:101-107), but has nothing like that for these paths.
  Attack vector: not attacker-driven; the risk is the operator's own tests acting on prod. `prod deploy` runs short + medium as the operator on this box (`run_tests_at`, prodctl.py:435-457), and so does a local `bin/game test medium`. A test that misses one fake acts on prod with no prompt. Until `36e7c24` the sleep and wake tests missed `egress()`, and the root helper's journal, which is the record of root actions, logged their stops and starts. The sharpest remaining case is `test_instance_is_refused_on_verbs_that_act_on_the_attached_one` (:648-663). It calls `main()` with `sleep`, `deploy`, `keepsakes`, `wake`, `status`, `pull`, `offsite`, `rollback` and `instance use` before faking anything, and it passes only because the `--instance` gate (prodctl.py:1457-1460) returns 2. If a change let one of those verbs take `--instance` (offsite per instance is a natural one), the test would run that verb against the real release before failing. `wake` would start the tunnel and the service and set the edge flag awake, `rollback` would repoint `current`, and `offsite` would make a backup and upload it.
  Evidence: the only `sudo` call sites in the package are prodctl.py:186, :326, :337, :1225 and :1243. No test in this module or in tests/test_instances.py reaches an unfaked one today. Every `wake`, `sleep_`, `deploy`, `passthrough`, `instance_use` and `instance_migrate` call runs with `systemctl` and `run_release_python` (or `subprocess.run`) faked, and every `root()` call runs with a stand-in helper. The guard test (:547-549) asserts the path before it calls `egress("start")`, so it cannot itself reach the real helper.
  Confidence: high for the mechanism (read); low that a current test reaches these paths (traced: none does).
  Remediation: move the guard to tests/conftest.py and widen it. An autouse fixture there would point `prodctl.SRV` and `ROOT_HELPER` at missing temporary paths, set `AS_USER` to `""`, and replace `systemctl` and `_edge` with stand-ins that fail the test; `srv`, `prodbox` and the sleep fakes would override them as now. Or fail any `subprocess` call whose argv starts with `sudo`, for the whole session. Have the refusal test check the gate with the verbs faked, so a regression fails without acting.
  Status: found 2026-11-26 at 36e7c24; last checked 2026-11-26 at 36e7c24

[NOTE] daydream/prodctl.py:780-801 (`_authorized_key`) and :810, with :813-817 — The recipient parser follows sshd for comment lines, a quoted options field and one well-formed `expiry-time`. But it still takes a key from some lines that sshd refuses or splits differently, so a key retired in a less common way stays a recipient of every later offsite copy. It also counts as the off-box key that `age_recipients` requires before it seals (:813-817). The divergences:
  - It accepts any options field, where sshd refuses a line with an unknown option (a `DISABLED` prefix, say) or an `expiry-time` it cannot read (`2020-01-01`, or a `UTC` suffix on this box's OpenSSH 8.9).
  - It reads only the first `expiry-time` (:794), where sshd keeps the earliest.
  - Inside quotes it lets `\` escape any character (:789), where sshd escapes only `\"`, in quotes or out. So `\\"` ends a quoted value here and not in sshd.
  - `splitlines()` (:810) also breaks at `\r`, form feed, vertical tab, `\x85` and U+2028, where sshd breaks only at `\n`. Text after one of these inside a commented-out line is read as a line of its own.
  - A key pinned to a forced command (a soft disable such as `restrict,command="/bin/false"`, or a single-purpose key for a backup puller) is a recipient too, since sshd still accepts it.
  Attack vector: The operator retires a key in one of three ways: a word sshd rejects in front of its line, an earlier `expiry-time` in front of the one the line already carries, or a pin to a command that does nothing. The key no longer opens a shell, but each weekly run (`offsite()`, the `age -R` call at :958) still seals to it, and its holder can read any later copy they can fetch (a read of the bucket, or a copy fetched to another machine). When that key is the only one besides the box's, the box-only refusal passes on it. The run then seals a copy that only the box and the retired key's holder can open, and says nothing. The quote and line-break cases need unusual text in the operator's own file, and anyone who can write that file can already add a key, so they are correctness gaps, not a way in. Separately, an impossible date in `expiry-time` (month 13, 30 February, year 0) raises ValueError, which `main()` does not catch (:1560). Every offsite run stops at that line, before any upload, until the line is fixed.
  Evidence: a probe of `_authorized_key` at HEAD over twelve lines.
  - These return None: a `# ...` comment line, and a past `expiry-time` with or without `Z`.
  - These return a key: `DISABLED ssh-ed25519 K`; `no-such-option,no-pty ssh-ed25519 K`; `expiry-time="20990101",expiry-time="20200101" ssh-ed25519 K`; past dates written `20200101UTC` and `2020-01-01`; `command="echo C:\\" ssh-ed25519 K`, a line sshd refuses as an unterminated quote; `# retired`, then `\r`, then `ssh-ed25519 K`; and `restrict,command="/bin/false" ssh-ed25519 K`.
  - `command="echo \\" ssh-ed25519 D " ssh-rsa R` returns D, where sshd reads R.
  - The dates `20201301`, `20200230` and `00000101` raise ValueError.

  A probe of `age_recipients` over scratch key files, each beside a box key:
  - An authorized_keys holding only the box's key is refused.
  - One holding only `DISABLED ssh-ed25519 K`, only `restrict,command="/bin/false" ssh-ed25519 K`, or only `# old`, `\r`, `ssh-ed25519 K` seals to the box and K.
  - One holding `expiry-time="20201301" ssh-ed25519 K` raises ValueError out of it.
  Confidence: high for the parser (probed). Medium for sshd's side: it comes from OpenSSH's parsing code (`sshkey_advance_past_options`, `sshauthopt_parse`, the line reader) and the box's 8.9 man page, not from a running sshd. Low that this box's file holds any of these forms (the agent guard denies reading `~/.ssh`).
  Remediation: split on `\n` only. Skip a line whose options do not all parse as sshd options, or whose `expiry-time` does not parse. Take the earliest `expiry-time`. Let `\` escape only `"`, in quotes or out. Treat a bad date as a refused line and say so. Decide forced-command keys deliberately. The box-only refusal reads keys through this parser, so these fixes also make it mean what it says. Or seal to an explicit recipients file the operator keeps, and print the recipients' fingerprints on each run (marking those counted as off-box), which ends the parsing question. Add a test case for each.
  Status: found 2026-11-26 at c22f58a; last checked 2026-11-26 at 36e7c24

[NOTE] daydream/prodctl.py:888-894 (`bucket_findings`), with docs/DATA-LIFECYCLE.md:40 and :136-143 — The bucket check reads a disabled expiry rule, or one scoped to a prefix no copy has, as "copies expire after N days". It takes the smallest "Expire objects after N days" anywhere in wrangler's answer (:891) and ignores the `enabled:` and `prefix:` lines that wrangler prints for each rule.
  - A disabled 60-day rule reads "copies expire after 60 days", and so does a rule scoped to `prod/` when the copies are named `prod-...`.
  - A rule longer than the design reads as its number, with no word that it departs from the 60 days.
  - A date rule ("Expire objects on ...") reads as no rule.
  - A bucket with no rule is named as a departure ("the design is 60 days").

  DATA-LIFECYCLE.md:137-143 says such a bucket keeps every copy, a deleted person's records included, and names `bin/game prod offsite-bucket` as the way to tell which kind a bucket is. Its table row at :40 still reads "offsite 60 days". Every case exits 0, by the recorded decision that retention is information only, and `prod check` reads only the offsite timer's last result.
  Attack vector: not attacker-driven; this is a privacy statement the check can confirm falsely. Someone adds the 60-day rule by hand (the documented path for a bucket made by hand, CLOUDFLARE-SETUP.md step 13) but leaves it disabled, or types the prefix as `prod/`. `offsite-bucket` then reads "copies expire after 60 days", and the doc's test for the 60-day promise passes. Yet every weekly copy stays in R2 until someone deletes it by hand, `account delete` included. Each copy holds the accounts DB and every typed line, sealed to each key that was a recipient at the time. Copies leave R2 through a read of the bucket (a dashboard session or wrangler login on a retired laptop, a leaked token, a bucket made public by mistake) or as a copy fetched to another machine (docs/runbooks/backups.md).
  Evidence: a probe of `bucket_findings` at HEAD with private, domain-free answers and four lifecycle answers in wrangler's format.
  - No rule reads "no expiry rule: every copy stays until deleted (the design is 60 days; docs/DATA-LIFECYCLE.md)".
  - A disabled 60-day rule reads "copies expire after 60 days".
  - A 1-day rule on `scratch/` reads "copies expire after 1 days".
  - A 365-day rule reads "copies expire after 365 days".
  - All four return no problems (exit 0).

  The date rule follows from the regex at :891. The format comes from wrangler's bundled source (`tableFromLifecycleRulesResponse`), at version 4.130.0, which `edge/node_modules` holds and the fixtures name: one block per rule with `name`, `enabled: Yes|No`, `prefix` (or `(all prefixes)`) and `action`. The committed fixtures (tests/test_prodctl.py:324-326) carry no `prefix:` line.
  Confidence: high (probed; the format read from wrangler's source). The live bucket's rules were not read (no Cloudflare call).
  Remediation: count only a rule whose `enabled` is Yes and whose prefix is `(all prefixes)` or a prefix of `prod-`. Say so when the shortest such rule is longer than `OFFSITE_EXPIRE_DAYS`, or when a disabled or off-prefix rule is present. Exit 0 can stay if retention is to remain information only. A `prod check` line from `bucket_findings` would show the same words after each deploy and wake. Add the disabled and prefixed cases to the tests, with fixtures that carry wrangler's `prefix:` line.
  Status: found 2026-11-26 at c22f58a; last checked 2026-11-26 at 36e7c24

[NOTE] daydream/prodctl.py:969-984 (`offsite_restore`), with :958-961 and docs/runbooks/backups.md:60-77 — An offsite copy carries no proof of where it came from, so a restore trusts whatever decrypts. `age` to SSH recipients authenticates no sender, and the recipients are public keys (`age_recipients`, :804), so anyone who can write the bucket can seal a copy that decrypts like the real ones. `offsite_restore` fetches, decrypts and unpacks whatever object it is named, all as the operator (:978-982), and the runbook's by-hand path does the same. GNU tar keeps every member inside `dest`, but it keeps a symlink that points outside it. The runbook's next steps (`PRAGMA integrity_check` on each `.db`, then a compare with the local backup of the same stamp) follow such a link, and so would a copy into place. That compare also works only while the box does. Separately, `name` is joined to the temporary directory as given (:977), and wrangler makes the parent directories and writes `--file` where it points. So a name with `/` or `..` writes the fetched object outside that directory, and an absolute name drops the directory altogether. That write happens as the operator, before `age` refuses the file.
  Attack vector: someone with write access to the bucket seals a crafted backup to the operator's public SSH keys: an accounts DB holding an admin account whose password they know, or a world of their choosing. They upload it as `prod-<instance>-<a later stamp>.tar.gz.age`. After the box is lost, the operator restores the newest copy and installs it. `prod world restore-backup` prompts, but nothing tells a planted copy from a real one, so the rebuilt village holds the attacker's account. The object outlives a rotation of the credential that planted it. A copy of links alone passes the runbook's round-trip check byte for byte while holding no data: its `.db` names link to the local backup of the same stamp. Every bucket credential the docs describe (the account-wide token, a dashboard session, a wrangler login) can also redeploy the Worker that carries every sign-in. So today this adds persistence into a rebuild rather than new reach; it becomes a new path if an R2-only credential is ever made. The `name` traversal also needs the operator to type, and approve at the prompt, a name with `/` in it.
  Evidence: `offsite()` seals with `age -R` to the recipients file and uploads the result (:958-961). Neither `offsite()` nor `offsite_restore()` makes or checks a signature, a MAC under a secret the bucket's writers lack, or a recorded digest. wrangler 4.130.0's `r2 object get` runs `mkdirSync(dirname(file), {recursive: true})` and `createWriteStream(file)` on the `--file` value. `Path(tmp) / "/abs/x"` is `/abs/x`. GNU tar 1.34 on this box, over crafted archives in scratch directories:
  - A `../` member is skipped ("Member name contains '..'"), and a leading `/` is stripped.
  - A file written through an archived symlink is refused ("Not a directory"), and a regular member named like an archived symlink does not write through it.
  - Symlinks to a directory and to a file outside `dest` are left in `dest`.
  - An archive of links alone unpacks with exit 0.
  Confidence: high for the mechanism; low that it matters while the account-wide token is the only bucket credential.
  Remediation:
  - Check `name` against the upload pattern (`prod-([a-z][a-z0-9-]*-)?\d{8}-\d{6}\.tar\.gz\.age`, one path component).
  - Unpack with Python's `tarfile` and `filter="data"` (present in the venv's 3.10.12), which refuses a link that leaves `dest`, or refuse any link member.
  - Record each sealed copy's sha256 somewhere a bucket writer cannot reach (the operator's own machine, say), and have `offsite-restore` print the digest to compare.
  - Or sign each copy with the box's key (`ssh-keygen -Y sign`) and verify against that public key on restore. That covers a leaked Cloudflare credential but not a compromised box.
  - The backups runbook could say to restore a copy made before any credential incident.
  Status: found 2026-11-26 at 02cf070; last checked 2026-11-26 at 36e7c24

Carried (still open; their files are outside this scope and unchanged since they were last checked):

[NOTE] daydream/ci.py:49-61 and :122-126 (with daydream/prodcheck.py:227-234) — About twenty pull-request runs from a fork's branch named `main` fill the one page `runs()` reads, so `main_status` reads a red main as "unknown" and `prod check` passes it.
  Status: found 2026-09-29 at d2f7538; last checked 2026-11-26 at c22f58a; carried, not re-checked

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

- **The fix** (`36e7c24`; tests/test_prodctl.py:47-53, :511, :540-549).
  In every test of this module, the autouse fixture points `ROOT_HELPER`
  at a path that does not exist, so `egress()` (prodctl.py:331-343) and
  `root()` (:1218-1239) refuse before any `sudo`. A test that wants a helper
  replaces it (`_fake_helper`, :669-688), and monkeypatch restores both in
  order. The sleep fakes now record `egress()` calls, and the
  Cloudflare-error test asserts that sleep stops the gateway and wake starts
  it. `daydream/prodctl.py` did not change. Nothing else calls `egress()` or
  `root()`.
- **How the fix was checked.** The commit and the local notes say a full
  short run made no helper call. But `bin/game test short` is
  `-m tier_short`, and this module is `tier_medium` apart from one test, so
  a short run never ran the sleep and wake tests that made the calls. By
  reading, the fix holds. The runs that exercise it are
  `bin/game test medium`, CI, and the deploy gate's short + medium.
- **An older ref.** `prod deploy <ref>` runs the tests at that ref. A deploy
  of a ref before `36e7c24` (an always-prompt verb) would run the old sleep
  and wake tests once more and leave the gateway started.
- **What the plan test still reads**
  (`test_plan_lists_what_goes_out_and_what_else_it_needs`, :763-780).
  `plan()` reads from the box (the egress gateway's `/routes` on loopback,
  `systemctl is-active`) and from GitHub (`ci.main_status` runs `gh` in the
  real checkout). Every one of these is a read. Jev is off in the suite:
  conftest clears its key and gateway URL, so `status_line` makes no call.
- **The box-only refusal** (`age_recipients`, :804-819), as committed in
  `cf4a451`, matches what the last post-fix pass checked. It adds no
  recipient, raises before `age` runs inside `offsite()`'s temporary
  directory, and names no key. Re-probed: the box's key alone is refused.
- **The rest of `prodctl.py`**, re-read in full and unchanged since the
  last scan apart from `age_recipients`. These stand as the last entry
  cleared them (`git show cf4a451:SECURITY.md`):
  - the read timeout (:834, :846-851);
  - the lifecycle-add failure (:906-912);
  - the side-door refusals (:278-288);
  - what `status()` prints (:1007-1016);
  - `pull()`'s UPDATE (:1203-1208);
  - the operator-side reads of the service-writable data dir.

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 3 items: a dreamer name, its look and a
    username, with no typed lines (the operator's own, per the instance
    notes). Unchanged.
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username. These are probe dreamers and the operator's dev username, with
    no typed lines. Unchanged.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- These hold none of a key, a token, a private-key block, an account id, an
  email, a box or tailnet address, the operator's surname, a friend's name
  or an invite slug:
  - both files as they stand;
  - the last three commits of each (`git log -p --follow -3`):
    `prodctl.py` at `cf4a451`, `02cf070` and `c22f58a`, and
    `test_prodctl.py` at `36e7c24`, `cf4a451` and `02cf070`;
  - the message of `36e7c24`.
- The fake key comments in `tests/test_prodctl.py:238-241`, :256 and
  :273-274 use the operator's Unix user name. It is a first name, and it
  also appears under Accepted Risks below. Earlier reviews recorded this,
  so it is not re-flagged. Every key is a placeholder. The fixtures' account
  (`0123abcd`) and domain (`backups.example.com`) are fake, and the bucket
  name is the committed default.
- `instance/` is still ignored.

### Coverage

- All dimensions were reviewed for the two paths, read in full at `36e7c24`
  and as their diff from `02cf070`.
- No suite ran (this skill reads code). Probes, all deterministic and local,
  in the session's scratch directory:
  - `_authorized_key` over twelve lines and three impossible dates;
  - `age_recipients` over five scratch key files;
  - `bucket_findings` over four lifecycle answers;
  - GNU tar 1.34 over two crafted archives: a `../` member, an absolute
    member, a symlink to an outside directory with a file through it, a
    symlink to an outside file with a regular member of the same name, and
    an archive of links alone;
  - `tarfile.data_filter`, present in the venv's Python 3.10.12.
- Read on the box, outside scope:
  - tests/conftest.py (the HOME default, the data-dir and Jev guards);
  - the prodctl tests in tests/test_instances.py, tests/test_ops_units.py
    and tests/test_runbooks.py;
  - the `sudo` call sites across `daydream/`, and ops/sudoers.d/daydream;
  - the tier markers in `daydream/testing/__main__.py`;
  - `ci.main_status`, `jev.cli.status_line` and `edge._creds`;
  - the restore section of docs/runbooks/backups.md;
  - the wrangler version under `edge/node_modules`;
  - that `/srv/daydream/current` and the installed helper exist (not their
    contents).
- Not checked:
  - this box's authorized_keys (the guard denies `~/.ssh`);
  - the live bucket's rules (no Cloudflare call);
  - sshd's runtime behavior (from its source and man page only);
  - the root helper's journal.
- No dependency manifest is in scope.
- Outside the two paths, `02cf070..36e7c24` also changes `CODEREVIEW.md`
  and `SECURITY.md` (review records, in `cf4a451`).
- Git history checked for secrets: `daydream/prodctl.py` (the Cloudflare
  token through `edge`, the CLI's cookie, the age recipients) and
  `tests/test_prodctl.py`.

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
*Prior review (2026-11-26, paths, commit `02cf070`, with a post-fix pass over the code review's WARN fix, later committed as `cf4a451`): `daydream/prodctl.py` and `tests/test_prodctl.py` over `c22f58a..02cf070` (a 120 s timeout on wrangler's reads, a named by-hand step for a bucket made without its expiry rule, a no-rule note that names the 60-day design). It found no issue in the new code and one new NOTE in older code: an offsite copy carries no proof of origin, and the restore joins its name to a temporary directory unchecked. The post-fix pass found that the box-only refusal in `age_recipients` opens no path. The register stood at 0 BLOCK / 0 WARN / 13 NOTE. The full entry is at `git show cf4a451:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-11-26","commit":"36e7c24adc71e888a5155e9930c5e8bb5f14171d","scope":"paths","scanned_files":["daydream/prodctl.py","tests/test_prodctl.py"],"block":0,"warn":0,"note":14} -->
