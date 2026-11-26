# SECURITY.md

## Security Review — 2026-11-26 (scope: paths)

**Summary:** Path-scoped review of `daydream/prodctl.py` and
`tests/test_prodctl.py` at HEAD `02cf070`, read in full and as their change
from the last scan (`c22f58a`). `02cf070` commits the `_authorized_key` fix
the last post-fix pass checked, and adds three things since:
- a 120 s timeout on wrangler's reads;
- a named by-hand step when a new bucket's expiry rule cannot be added;
- a no-rule note that names the 60-day design (retention stays information
  only, by the decision recorded in that commit).

The new code opens no path. Both in-scope NOTEs are still present. The
recipient parser's divergences from sshd are unchanged. The bucket check now
names a missing rule, but still reads a disabled or off-prefix rule as
expiring (wrangler's output format is now confirmed from its own source).
One new NOTE in older code: an offsite copy carries no proof of origin, so a
restore trusts whatever decrypts, and the restore joins the object's name to
a temporary directory unchecked. Register: 0 BLOCK / 0 WARN / 13 NOTE, 3 in
scope and 10 carried.

**Post-fix re-check** (`/codereview` Step 7, uncommitted over `02cf070`):
`daydream/prodctl.py` and `tests/test_prodctl.py` after `/codefix`'s change
for the code review's WARN (a weekly copy sealed to the box's own key
alone). `age_recipients` now reads `authorized_keys` and the box's
`id_ed25519.pub` apart, and refuses when `authorized_keys` yields no key
but the box's own; a new test covers it. The change opens no path. When the
check passes, the recipients are the same union as before. The refusal
comes before `age` runs, inside `offsite()`'s temporary directory, so the
plaintext tarball goes with it, and its message names no key. Probed over
eleven scratch key files, it refuses the box's key alone (whatever its
options or comment), a missing file, and only ecdsa or `sk-` keys. It
passes on a key the parser misreads as live (a `DISABLED` prefix, a
do-nothing forced command, a key after `\r` inside a commented-out line),
now part of the parser NOTE, and on any other key whose private half lives
only on this box, since it knows the box by `id_ed25519.pub` alone. No
security finding was resolved (the WARN was the code review's). The three
in-scope NOTEs are still present, re-probed and rewritten at the working
tree's line numbers. Register unchanged: 0 BLOCK / 0 WARN / 13 NOTE, 3 in
scope and 10 carried.

### Findings

[NOTE] daydream/prodctl.py:780-801 (`_authorized_key`) and :810, with :813-817 — The recipient parser follows sshd for comment lines, a quoted options field and one well-formed `expiry-time`, but it still takes a key from some lines sshd refuses or splits differently, so a key retired in a less common way stays a recipient of every later offsite copy, and counts as the off-box key that `age_recipients` requires before it seals (:813-817). It accepts any options field, where sshd refuses a line with an unknown option (a `DISABLED` prefix, say) or an `expiry-time` it cannot read (`2020-01-01`, or a `UTC` suffix on this box's OpenSSH 8.9). It reads only the first `expiry-time` (:794), where sshd keeps the earliest. Inside quotes it lets `\` escape any character (:789), where sshd escapes only `\"`, in quotes or out, so `\\"` ends a quoted value here and not in sshd. `splitlines()` (:810) also breaks at `\r`, form feed, vertical tab and a few Unicode separators, where sshd breaks only at `\n`, so text after one of these inside a commented-out line is read as a line of its own. A key pinned to a forced command (a soft disable such as `restrict,command="/bin/false"`, or a single-purpose key for a backup puller) is a recipient too, since sshd still accepts it.
  Attack vector: The operator retires a key by putting a word sshd rejects in front of its line, by adding an earlier `expiry-time` in front of the one the line already carries, or by pinning it to a command that does nothing. The key no longer opens a shell, but each weekly run (`offsite()`, the `age -R` call at :958) still seals to it, and its holder can read any later copy they can fetch (a read of the bucket, or a copy fetched to another machine). When that key is the only one besides the box's, the refusal of a box-only copy passes on it, so the run seals a copy that only the box and the retired key's holder can open, and says nothing. The quote and line-break cases need unusual text in the operator's own file, and anyone who can write that file can already add a key, so they are correctness gaps, not a way in. Separately, an impossible date in `expiry-time` (month 13, 30 February, year 0) raises ValueError, which `main()` does not catch (:1560): every offsite run stops at that line, before any upload, until the line is fixed.
  Evidence: a probe of `_authorized_key` (unchanged by the post-fix change) over 23 lines. `# ...`, `#...` and indented comment lines, and a past `expiry-time` with or without `Z`, return None. These return a key: `DISABLED ssh-ed25519 K`; `no-such-option,no-pty ssh-ed25519 K`; `expiry-time="20990101",expiry-time="20200101" ssh-ed25519 K`; past dates written `20200101UTC` and `2020-01-01`; `command="echo \\" ssh-ed25519 D " ssh-rsa R`, which returns D where sshd reads R; `command="echo C:\\" ssh-ed25519 K`, a line sshd refuses as an unterminated quote; `# retired key`, then `\r`, form feed, vertical tab, `\x85` or U+2028, then `ssh-ed25519 K`; and `restrict,command="/bin/false" ssh-ed25519 K`. The dates `20201301`, `20200230` and `00000101` raise ValueError. A probe of the post-fix `age_recipients` over scratch key files, each beside the box's key: an authorized_keys holding only `DISABLED ssh-ed25519 K`, only `restrict,command="/bin/false" ssh-ed25519 K`, or only `# old`, `\r`, `ssh-ed25519 K` seals to the box and K; one holding `expiry-time="20201301" ssh-ed25519 K` raises ValueError out of it.
  Confidence: high for the parser (probed). Medium for sshd's side: it comes from OpenSSH's parsing code (`sshkey_advance_past_options`, `sshauthopt_parse`, the line reader) and the box's 8.9 man page, not from a running sshd. Low that this box's file holds any of these forms (the agent guard denies reading `~/.ssh`).
  Remediation: split on `\n` only; skip a line whose options do not all parse as sshd options, or whose `expiry-time` does not parse; take the earliest `expiry-time`; let `\` escape only `"`, in quotes or out; treat a bad date as a refused line and say so; decide forced-command keys deliberately. The box-only refusal reads keys through this parser, so these fixes also make it mean what it says. Or seal to an explicit recipients file the operator keeps, and print the recipients' fingerprints on each run (marking those counted as off-box), which ends the parsing question. Add a test case for each.
  Status: found 2026-11-26 at c22f58a; last checked 2026-11-26 at 02cf070

[NOTE] daydream/prodctl.py:888-894 (`bucket_findings`), with docs/DATA-LIFECYCLE.md:40 and :136-143 — The bucket check reads a disabled expiry rule, or one scoped to a prefix no copy has, as "copies expire after N days". It takes the smallest "Expire objects after N days" anywhere in wrangler's answer (:891) and ignores the `enabled:` and `prefix:` lines wrangler prints for each rule. So a disabled 60-day rule reads "copies expire after 60 days", and so does a rule scoped to `prod/` when the copies are named `prod-...`. A rule longer than the design reads as its number, with no word that it departs from the 60 days. Since `02cf070` the check names a bucket with no rule as a departure ("the design is 60 days"). DATA-LIFECYCLE.md:137-143 now says such a bucket keeps every copy, a deleted person's records included, and points to `bin/game prod offsite-bucket` as the way to tell which kind a bucket is; its table row at :40 still reads "offsite 60 days". Every case exits 0, as that commit decided, and `prod check` reads only the offsite timer's last result.
  Attack vector: not attacker-driven; a privacy statement the check can confirm falsely. Someone adds the 60-day rule by hand (the documented path for a bucket made by hand, CLOUDFLARE-SETUP.md step 13) but leaves it disabled or types the prefix as `prod/`. `offsite-bucket` then reads "copies expire after 60 days", the doc's test for the 60-day promise passes, and every weekly copy (the accounts DB and every typed line, sealed to each key that was a recipient at the time) stays in R2 until someone deletes it by hand, `account delete` included. Copies leave R2 through a read of the bucket (a dashboard session or wrangler login on a retired laptop, a leaked token, a bucket made public by mistake) or as a copy fetched to another machine (docs/runbooks/backups.md).
  Evidence: a probe of `bucket_findings` (unchanged by the post-fix change) with private, domain-free answers and five lifecycle answers in wrangler's format. No rule reads "no expiry rule: every copy stays until deleted (the design is 60 days; docs/DATA-LIFECYCLE.md)". A disabled 60-day rule reads "copies expire after 60 days". A 1-day rule on `scratch/` reads "copies expire after 1 days". A 365-day rule reads "copies expire after 365 days". A date rule ("Expire objects on ...") reads as no rule. All five return no problems (exit 0). The format comes from wrangler's bundled source (`tableFromLifecycleRulesResponse` in `edge/node_modules/wrangler`, version 4.130.0, the version the fixtures name): one block per rule with `name`, `enabled: Yes|No`, `prefix` (or `(all prefixes)`) and `action`. The committed fixtures carry no `prefix:` line.
  Confidence: high (probed; the format read from wrangler's source). The live bucket's rules were not read (no Cloudflare call).
  Remediation: count only a rule whose `enabled` is Yes and whose prefix is `(all prefixes)` or a prefix of `prod-`; say so when the shortest such rule is longer than `OFFSITE_EXPIRE_DAYS`, or when a disabled or off-prefix rule is present. Exit 0 can stay if retention is to remain information only. A `prod check` line from `bucket_findings` would show the same words after each deploy and wake. Add the disabled and prefixed cases to the tests, with fixtures that carry wrangler's `prefix:` line.
  Status: found 2026-11-26 at c22f58a; last checked 2026-11-26 at 02cf070

[NOTE] daydream/prodctl.py:969-984 (`offsite_restore`), with :958-961 and docs/runbooks/backups.md:60-77 — An offsite copy carries no proof of where it came from, so a restore trusts whatever decrypts. `age` to SSH recipients authenticates no sender, and the recipients are public keys (`age_recipients`, :804), so anyone who can write the bucket can seal a copy that decrypts like the real ones. `offsite_restore` fetches, decrypts and unpacks whatever object it is named, and the runbook's by-hand path does the same. The runbook's check (compare a restore with the local backup of the same stamp) works only while the box does. Separately, `name` is joined to the temporary directory as given (:977), and wrangler makes the parent directories and writes `--file` where it points, so a name with `/` or `..` writes the fetched object outside that directory, as the operator, before `age` refuses it.
  Attack vector: someone with write access to the bucket seals a crafted backup (an accounts DB holding an admin account whose password they know, or a world of their choosing) to the operator's public SSH keys, and uploads it as `prod-<instance>-<a later stamp>.tar.gz.age`. After the box is lost, the operator restores the newest copy and installs it (`prod world restore-backup` prompts, but nothing tells a planted copy from a real one), and the rebuilt village holds the attacker's account. The object outlives a rotation of the credential that planted it. Every bucket credential the docs describe (the account-wide token, a dashboard session, a wrangler login) can also redeploy the Worker that carries every sign-in, so today this adds persistence into a rebuild rather than new reach; it becomes a new path if an R2-only credential is ever made. The `name` traversal also needs the operator to type, and approve at the prompt, a name with `/` in it.
  Evidence: `offsite()` seals with `age -R` to the recipients file and uploads the result (:958-961). Neither `offsite()` nor `offsite_restore()` makes or checks a signature, a MAC under a secret the bucket's writers lack, or a recorded digest. wrangler 4.130.0's `r2 object get` runs `mkdirSync(dirname(file), {recursive: true})` and `createWriteStream(file)` on the `--file` value.
  Confidence: high for the mechanism; low that it matters while the account-wide token is the only bucket credential.
  Remediation: check `name` against the upload pattern (`prod-([a-z][a-z0-9-]*-)?\d{8}-\d{6}\.tar\.gz\.age`, one path component). Record each sealed copy's sha256 somewhere a bucket writer cannot reach (the operator's own machine, say), and have `offsite-restore` print the digest to compare. Or sign each copy with the box's key (`ssh-keygen -Y sign`) and verify against that public key on restore, which covers a leaked Cloudflare credential but not a compromised box. The backups runbook could say to restore a copy made before any credential incident.
  Status: found 2026-11-26 at 02cf070; last checked 2026-11-26 at 02cf070

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

- **The read timeout** (`prodctl.py:831` and :843-848, new in `02cf070`).
  On expiry it returns a fixed sentence, so no partial wrangler output (whose
  request line names the account) is printed. `bucket_missing` reads it as
  not missing: the weekly job's pre-check falls through to the old path as
  before, and `offsite-bucket` reports a problem and exits 1. `subprocess.run`
  kills `npx` and returns. The wrangler process under it can outlive it until
  its read ends; these are read-only queries, and the token was already in
  that process's environment.
- **The lifecycle-add failure** (:903-909, new). A bucket made without its
  rule now fails with the by-hand step, where the next run would otherwise
  pass with a note. Nothing new is printed: `_wrangler` streams wrangler's
  own words to the terminal, as it did.
- **The side-door refusals** (`_refuse_side_doors`, :278-288). `bin/game
  world patch` switches to check mode on any `--check` token, wherever it
  stands, so prodctl's membership test matches what runs. `daydream.dream`'s
  top-level parser has no options, and argparse on the box's Python 3.10.12
  refuses `--` and abbreviations before the subcommand, so `dream apply`
  cannot reach the live DB with another word at `args[1]`.
- **What `status()` prints** (:1004-1013). The names in `/status/who` come
  from dreamers, which are `isprintable()` and at most 24 characters at
  creation (`daydream/api/slots.py:178`) and JSON-quoted on output
  (`daydream/server.py:175-191`). A friend cannot put a terminal escape into
  the operator's terminal, or more than a short label into the agent's
  context. The arbiter line is numbers.
- **`pull()`'s UPDATE** (:1200-1205) on a DB the service wrote. A trigger
  planted in it runs only SQL against that DB (a trigger body holds only
  INSERT, UPDATE, DELETE and SELECT, and extension loading is off), and the
  dev server opens the same file anyway.
- **The recipient parser's shape** (unchanged since the post-fix pass). Only
  the key type and blob reach the recipients file, so no option text reaches
  `age -R`; the scan and the expiry regex are linear in the line; the file
  sits in a 0700 temporary directory. `cert-authority` lines stay recipients
  (sshd accepts them, and a CA key's holder can already log in), and a `Z`
  suffix is read as UTC.
- **The rest of `prodctl.py`**, re-read in full and unchanged. The
  operator-side reads of the service-writable data dir (the `active` link,
  the path `_backup` parses from the service's output, `offsite()`'s walk of
  `instances/`, `pull()`) hand paths only to commands run as the service
  user. Object names that `offsite()` uploads are one path component.
- **The box-only refusal** (post-fix, `age_recipients`, :804-819). It adds
  no recipient: when it passes, the file holds the same union of the two
  files' keys as before. It raises before `age` runs, inside `offsite()`'s
  temporary directory, so the plaintext tarball is removed with it and
  nothing is uploaded. `main()` reports it and exits 1, so the weekly unit
  fails where `prod status` shows it. Its message names no key. It knows
  the box by `id_ed25519.pub` alone, so another key whose private half
  lives only on this box (the box's own RSA key in its authorized_keys,
  say) still satisfies it: a limit on the durability it proves, and no way
  in. A misread line's key satisfies it too (the parser NOTE).

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 3 items: a dreamer name, its look and a
    username, with no typed lines (the operator's own, per the instance
    notes). Unchanged.
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username. Unchanged.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- Re-run for the post-fix pass: both unchanged (prod 3 items, dev 63),
  nothing flagged, no bursts, the same high-water marks. Verdict: nobody
  steering.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- These hold none of a key, a token, a private-key block, an account id, an
  email, a box or tailnet address, the operator's surname, a friend's name
  or an invite slug: both files as they stand, the last three commits of
  each (`git log -p --follow -3`), the message of `02cf070`, and the
  post-fix diff.
- The fake key comments in `tests/test_prodctl.py:229-232` and :247 use the
  operator's Unix user name (a first name, and the commit author's public
  handle), as earlier reviews recorded; not re-flagged. The post-fix test
  adds two more of the same kind (:264-265). Every key is a placeholder. The fixtures' account (`0123abcd`) and domain
  (`backups.example.com`) are fake, and the bucket name is the committed
  default.
- `instance/` is still ignored.

### Coverage

- All dimensions were reviewed for the two paths, read in full at `02cf070`
  and as their diff from `c22f58a`.
- No suite ran (this skill reads code). Probes, all deterministic and local:
  - `_authorized_key` over 23 lines (comment forms, expiry forms, options
    sshd refuses, the backslash rule, forced-command and `cert-authority`
    lines, five line separators, three impossible dates);
  - `bucket_findings` over five lifecycle answers and a timed-out read;
  - argparse's handling of `--` and abbreviations before a subcommand, on a
    replica parser under the venv's Python 3.10.12.
- Read on the box, outside scope: wrangler 4.130.0's bundled source (the
  lifecycle list format, `r2 object get --file`), `bin/game`'s `world patch`
  and `dream` dispatch, `daydream/dream.py`'s parser, the dreamer name check
  in `daydream/api/slots.py`, `/status/who` in `daydream/server.py`, the
  offsite coverage in `daydream/prodcheck.py`, the guard's ask list for the
  offsite verbs, the installer's bucket step, the restore section of
  `docs/runbooks/backups.md`, and the retention lines of
  `docs/DATA-LIFECYCLE.md`.
- Not checked: this box's authorized_keys (the guard denies `~/.ssh`), the
  live bucket's rules (no Cloudflare call), and sshd's runtime behavior (from
  its source and man page only).
- No dependency manifest is in scope.
- Outside the two paths, `02cf070` also changes `CODEREVIEW.md`,
  `SECURITY.md` and `docs/DATA-LIFECYCLE.md`. The last was read for the
  retention NOTE; the other two are review records.
- Git history checked for secrets: `daydream/prodctl.py` (the Cloudflare
  token through `edge`, the CLI's cookie, the age recipients) and
  `tests/test_prodctl.py`.
- Post-fix pass: the uncommitted diff of `daydream/prodctl.py` and
  `tests/test_prodctl.py` over `02cf070` (one hunk in `age_recipients`, one
  new test), with `age_recipients`' one caller (`offsite()`) and `main()`'s
  error handling read again. Probes, deterministic and local:
  `age_recipients` over eleven scratch key files (the box's key alone
  under other options, no authorized_keys, neither file, only ecdsa and
  `sk-` keys, a `DISABLED` prefix, the box's own RSA key, a forced-command
  soft disable, an impossible date, no box key, both kinds, a `\r` inside a
  commented-out line); `bucket_findings` over the same five lifecycle
  answers. Both player-text scans re-ran against local DBs. No suite,
  wrangler, Cloudflare or GitHub call. The cleared items above that predate
  this pass cite `02cf070`'s line numbers (3 lower than the working tree's
  past :816).

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
*Prior review (2026-11-26, paths, commit `c22f58a`, with a post-fix pass over the fix later committed as `02cf070`): seven paths over `97a1f4e..c22f58a`, the offsite correction (`prod offsite-bucket [--create]`, the installer running it, the weekly job's pre-check). It found a WARN in older code, `age_recipients` sealing offsite copies to commented-out and expired keys, which `/codefix` fixed and the post-fix pass confirmed resolved, plus NOTEs for the new parser's remaining divergences from sshd and for retention being information only; the fork-flood NOTE in `ci.py` was re-checked and still present. The register stood at 0 BLOCK / 0 WARN / 12 NOTE. The full entry is at `git show 02cf070:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-11-26","commit":"02cf070ea1c5a200ea9f12549bd5f5c845cb1d12","scope":"paths","scanned_files":["daydream/prodctl.py","tests/test_prodctl.py"],"block":0,"warn":0,"note":13} -->
