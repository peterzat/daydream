# SECURITY.md

## Security Review — 2026-09-28 (scope: paths)

**Summary:** Path-scoped review of the 37 files in scope: the code changed
from `1e65f3a` (the last review) to HEAD `8c39d4a`, which is the 15-WARN
codereview fix pass plus the six unpushed commits (comings and goings, the
dreamer panel and door note, Talk on the input line, `prod plan`). No code
vulnerability found. One WARN: an unpushed commit message names the deleted
prod test account's username, which the operator already once rewrote out of
history. One NOTE, outside these paths: a committed test holds the box's
tailnet address. Both prior findings are closed (0 BLOCK / 1 WARN / 1 NOTE).

### Scope and method

The 37 scanned files are every path in the review argument. Each file's diff
from `1e65f3a` to HEAD was read in full, along with the code it touches or
calls:

- `toons.announce_move` and `move_texts`, and their callers (`go`, rule
  teleport).
- The WebSocket broadcast loop's room filter and the new presence
  re-snapshot.
- `events.fetch_since` (`skip_kinds`) and `fetch_for_toon`.
- The SPA's arrival line (`placeArrival`, `escape`, `linkifyEntities`), the
  move/arrive renderer, `askForText`/`sendText`, `refused`/`notice`, and the
  door note.
- `images/client.restore_from_keep` on the live render path, with
  `keep.find`/`_store`/`records`/`put`, and `_generate_and_emit`'s error
  handling.
- `admin.cmd_restore`'s unlink and `cmd_keep_sync`.
- `accounts_cli._forget_dreamer_state` and how toon ids are minted.
- `instance.discard`/`load`/`migrate`.
- prodctl's `plan`, `resolve_ref`, `_detached`, the `--instance` verb
  allowlist, and `instance_create`/`use`/`migrate`.
- `edge.set_state(note=None)`, the Worker's `watch`, the installer's
  operator check, and the root helper's ASCII guard (read against the
  rendered units it validates).

HTML, SQL, subprocess and filesystem sinks in every scoped module were swept
by pattern. Credential-handling files' last three commits and the full
outgoing range (`origin/main..HEAD`, messages included) were scanned for
secrets and instance details. The 418 Python tests in the 13 scoped test
files pass, as do the Worker's 35 tests (`node --test test/*.test.js`).

### Findings

[WARN] commit `67e1db3` (message lines 9-10; not yet pushed) — The commit
message names the prod test account's username, in lowercase and
capitalized forms, as the example of the "name given at the door" feature.
  Attack vector: Not an exploit. It is instance data that becomes public on
the next push, since the GitHub repo is public. `instance/NOTES.md` records
three things: this username belonged to the operator's own test account
(display name the operator's own), the account has since been deleted, and
"History before the push was rewritten once to take a friend's name and the
test account's username out of committed docs". The project's separation
rule (CLAUDE.md, "Before any push, check the separation") covers exactly
this. Because the account is deleted, the name no longer identifies a
working login. The exposure is the name itself.
  Evidence: `git show --no-patch 67e1db3` lines 9-10 (the name itself is
kept out of this file). No tracked file at HEAD contains it. The other five
outgoing commits and all their patches are clean.
  Remediation: Before pushing, reword `67e1db3`'s message so it uses the
neutral example the code comment already uses (`robin_ash` becomes
`Robin Ash`). Do this non-interactively: a rebase from `origin/main` with a
scripted sequence editor and message editor, or
`git filter-branch --msg-filter` limited to `origin/main..HEAD`. Then
re-run the separation check on the rewritten range.

[NOTE] tests/test_config_edge.py:61 (outside this review's paths) — The test
that proves a non-loopback bind host is refused uses this box's real tailnet
IPv4 as its example.
  Attack vector: Minimal. The address belongs to Tailscale's CGNAT range and
is reachable only by members of the operator's tailnet, so disclosing it
gives an outsider nothing to connect to. It is still "the box's addresses",
which CLAUDE.md keeps off GitHub. It has been public since `5f2bd3d`
(2026-09-27, on `origin/main`), and earlier outgoing-diff scans missed it
because it predates them.
  Evidence: An exact match for `tailscale ip -4` on this box, at
`tests/test_config_edge.py:61` (the value is not reproduced here).
  Remediation: The next time the file is touched, replace it with a neutral
address such as `100.64.0.1`; the test needs only a non-loopback address.
No history rewrite is warranted for a tailnet-only address.

### Closed since the last review

- **The unit validator's Unicode whitespace (prior WARN).** Fixed in
  `03a5b08`. `parse_unit` now refuses any non-ASCII line before parsing
  (`ops/root/daydream-root:317-323`). Lines are split on `"\n"` only, so
  Unicode line separators stay inside a line and are refused too. The check
  runs on the rendered text that gets installed. Two hostile tests carry
  real U+00A0 bytes. The installed `/usr/local/sbin/daydream-root` is
  byte-identical to the repo copy, and the prod release (`e1adc76`)
  contains the fix.
- **`NoNewPrivileges` on the installed timer units (prior NOTE).** Resolved
  by the operator's installer run (2026-09-28 17:30 UTC). The installed
  keepsakes unit matches the repo's rendered unit, and the 18:03 UTC
  keepsakes run exited 0.

### Traced and cleared this run (not findings)

- **Comings and goings.** Presence events are room broadcasts: `move` is
  keyed to the room left and `arrive` to the room reached, with no
  recipient. The broadcast loop's room filter and private-event filter are
  unchanged. The mover's own `arrive` does not re-snapshot twice. The line
  text interpolates three things only:
  - the toon's validated name (printable, capped, banlisted, not id-shaped)
  - room titles
  - `direction`, which `_handle_go` accepts only as an existing exit key,
    never raw player text

  Every SPA sink is `textContent` or `escape()`d. `escape` covers
  `& < > "`, and every attribute it feeds is double-quoted. `linkifyEntities`
  escapes before matching. `play.py` prints the same text; a name cannot
  carry ESC because `isprintable()` refuses it. `skip_kinds` adds only
  placeholders, bound to a code constant. Re-snapshots on others' moves are
  bounded by the per-connection rate (3 frames/s, burst 12) among invited
  friends.
- **The live keep restore.** The cache key is seed text plus workflow, and
  the sampler seed derives from the same text. A keep hit is therefore the
  painting a fresh render would produce, and a matching seed is the only way
  to hit another target's painting. `find` takes the newest record, so an
  admin repaint wins over the original.
  - Only `keep.put` writes provenance lines. They are JSON-encoded and read
    by `\n` bytes, and nothing imports provenance back from a backup.
    `rec["sha256"]` is used unvalidated in `art_path`, but no attacker
    input reaches it.
  - The restore replaces its temp file and never writes into it. Kept files
    are 0444, so a write through a hard link fails loudly
    (`SameFileError` and `EACCES` both fall back to a render).
  - `prompt_text` is nullable, and `_generate_and_emit`'s broad catch keeps
    any failure off the session.
  - The only other writer into cache paths, prebake's adopt step, runs only
    when the path is absent.
- **`world restore`'s new unlink.** It removes only a non-symlink regular
  file whose resolved path is inside the data dir. An archive could already
  write any file there, so the unlink adds no reach. Archives remain
  operator-trusted, and the verb is behind an ask rule in prod.
- **`account delete`'s forgetting.** SQL is parameterized. The
  `:<toon id>` suffix match is anchored by the colon, so it cannot catch a
  longer id. Toon ids carry 32 random bits per slot, so a later toon never
  inherits an old one's `pq:`/`talk:` state. It is CLI only, behind the ask
  rule. The dreamer-cap throttle key goes with the account.
- **`instance.discard`.** Reached only from `instance_create`'s failure
  path, run by the release as the service user. It refuses:
  - a symlink or a non-directory
  - the attached instance
  - any dir holding a world or accounts DB

  `rmtree` is symlink-attack resistant on Linux.
- **prodctl.**
  - `plan` is read-only. `resolve_ref` returns a verified full SHA
    (`rev-parse --verify <ref>^{commit}`), and every later git call takes
    that SHA or a release dir name, in list form with no shell.
  - `--instance` is now refused outside the passthrough verbs and `backup`,
    and still only as the last two arguments.
  - `_detached()` compares the resolved `active` link to the name. A
    symlinked `instances/<name>` would mislead it, but only the service user
    can create one there, and the effect would be a consistency risk to its
    own data, not privilege.
- **Edge.** `set_state(note=None)` keeps the flag's note, capped at 280
  characters. Words are still capped, allowlisted and escaped by the Worker.
  `watch` changes only outage bookkeeping, writes KV only on a change, and
  the `uptime` key is on no public route.
- **Installer.** The operator is now `SUDO_USER` and never a guess, and it
  refuses empty or `root`. The name is regex-checked before it reaches
  `root.conf` or sudoers.
- **UI.** Slot refusals now name `instance.place()` (validated operator
  words) and reach `notice()` through `textContent`. `/api/dreamer` returns
  the caller's own username, used only as `textContent` and an input value.
  Talk's words now go from the page's input line as a structured command
  frame, which the server still checks for scope, verb applicability, length
  and rate. The door note keeps criterion 8's two facts.

### Secrets, PII and the instance

- **Credentials.** The Cloudflare API token and account id (read from
  `~/.config/daydream/cloudflare.env` and compared without printing) appear
  in no tracked file, no commit since `1e65f3a`, and no outgoing commit.
  Neither do the zone id, the Zero Trust team, the Access AUD tag, the
  tunnel id, or the invite ids that `instance/NOTES.md` records.
- **Deliberate instance values.** The origin hostname and KV id appear only
  in the deliberately committed places (`edge/wrangler.toml`, the tunnel
  unit, the setup doc, the Worker tests).
- **Addresses.** The box's public IPv4 and IPv6 are absent. Its tailnet
  IPv4 is the NOTE above.
- **Operator identity.** The operator's surname appears only in LICENSE's
  copyright line and in commit author metadata.
- **Pattern scans.** No token-shaped value, invite link or cookie value
  appears in the range. Test fixtures use fictional names.
- **Ignored directory.** `instance/` is still gitignored.
- **The one exception** is the username in `67e1db3`'s message (the WARN).

### Accepted Risks

Accepted by the operator for going live (`docs/GOING-LIVE.md` section 9;
docs/ADMIN-ROOT.md "Security posture", 2026-09-28):

- **The engines run as `peter`.** vLLM (`:8000`) and ComfyUI (`:8188`) listen
  unauthenticated on loopback and run as `peter`, who is in the docker group.
  The prod service user can reach both. Planned fix: a separate engines user.
- **Local attackers are best-efforts only.** The box is single-user; `peter`
  keeps the root-equivalent `docker` group, so a hostile process running as
  the operator is out of scope. The helper, root-only secrets, and the
  validated-and-logged root actions are reasonable precautions, not a boundary
  against the operator's own user.
- **Known local-only residual (docs/ADMIN-ROOT.md):** systemd reads a
  release's `.release.env` as root and releases belong to the operator, so the
  operator's user could point it at the tunnel token; anyone who can do that
  already holds `docker`.
- **The pre-login surface is public** (door, login, invite redemption, static
  assets), throttled in the app and at the edge.
- **Friends drive shared-world verbs on shared objects** (co-op design).
- **What friends type reaches the local LLM**, with role separation, length
  caps, banlists and strict output validation.

Carried register (from prior reviews, still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths (neither exists in the live Lost Hours world; planned v2).
- Raw parser input is not role-separated; output is re-grounded to a closed
  verb and an in-scope id.
- NPC dialogue and growth are exposed to prompt injection; input is wrapped,
  capped and banlisted, output validated before any mutation; refusal `reason`
  text is narrated without an output-banlist pass, through escaped sinks.
- World envelopes, archives and `bin/game` are trusted as the operator's own
  (world load/reset content, `reset`'s `rm -rf`, dev `.env` sourcing, the dev
  `0.0.0.0` bind, the deprecated `bootstrap_world`). None take network input.
- Event queues are bounded (256, drop-oldest).
- DNS (127.0.0.53) and AF_UNIX leave the prod sandbox; any local process can
  reach `127.0.0.1:54322` and choose its own `X-Daydream-Client-IP` (moves
  throttle keys only; the gate still applies); `gpu.lock` is writable by the
  service.
- Invite slugs are unsalted sha256 over ~983,000 phrases (a copy of the
  accounts DB recovers open slugs); strangers can keep invitations paused
  (global cap; `invite unblock` reopens).
- On the Workers Free plan an anonymous client can exhaust the daily request
  quota; the one WAF rule covers login and invite paths.
- The operator's Cloudflare token is account-wide (Workers Scripts edit cannot
  be scoped to one Worker).
- Toon names are not unique and lookalikes are not folded; moderation refuses
  an ambiguous key and `/status/who` shows id and owner.
- A shell rest does not reach an open socket; `account disable` is the stop.
- Supply-chain: the prod lock pins versions but not hashes; CI actions use
  tags.
- The standing prod grant's `ask` rules are text patterns; a quoted word may
  slip past one (a PreToolUse hook would be firmer).
- Player text (names, speech, now also move lines) reaches the agent's
  context through `bin/game play`; the verbs an injected instruction would
  want stay behind ask rules.

---
*Prior review (2026-09-28, paths, commit `1e65f3a`): the root helper,
instances, the art keep, `account delete`, the dreamer cap and the Worker's
uptime watch (28 files). It found 0 BLOCK / 1 WARN / 1 NOTE: the unit
validator's Unicode-whitespace gap and the installed timer units'
`NoNewPrivileges`, both now closed. Earlier entry at
`git show 48c5b2d:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"8c39d4afc45e3f9dbcf5f09c509567ac102a0341","scope":"paths","scanned_files":["daydream/accounts.py","daydream/accounts_cli.py","daydream/admin.py","daydream/api/slots.py","daydream/api/ws.py","daydream/edge.py","daydream/events.py","daydream/images/client.py","daydream/images/keep.py","daydream/instance.py","daydream/play.py","daydream/prebake.py","daydream/prodctl.py","daydream/skills/effects.py","daydream/toons.py","daydream/verbs.py","edge/src/worker.js","edge/test/worker.test.js","ops/install-prod.sh","ops/root/daydream-root","tests/test_account_delete.py","tests/test_art_keep.py","tests/test_browser_flow.py","tests/test_comings_and_goings.py","tests/test_edge_ctl.py","tests/test_frontend.py","tests/test_frontend_zork.py","tests/test_instances.py","tests/test_ops_units.py","tests/test_prodctl.py","tests/test_root_helper.py","tests/test_slots.py","tests/test_ws.py","web/assets/door.js","web/assets/main.js","web/assets/style.css","web/index.html"],"block":0,"warn":1,"note":1} -->
