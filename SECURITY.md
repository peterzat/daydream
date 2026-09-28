# SECURITY.md

## Security Review — 2026-09-28 (scope: paths)

**Summary:** Path-scoped review of the 28 files in scope, covering the work
committed from `0aa9792` to HEAD `1e65f3a`: the root-owned admin helper
(`ops/root/daydream-root`) and its sudoers line and installer, the instances
layer (`daydream/instance.py`, prodctl's `--instance` and `root`
pass-through, the per-instance cookie and words), the art keep
(`daydream/images/keep.py` and its callers), `account delete`, the daily
dreamer cap, and the Worker's uptime watch and per-instance words. One WARN:
the helper's unit validator strips Unicode whitespace (e.g. U+00A0) where
systemd does not, so a unit with a no-break space in a sandbox directive's
key passes the validator while systemd silently drops that directive. One
NOTE carries over from prior reviews and was re-verified on the box: the
installed keepsakes/offsite units still set `NoNewPrivileges`, so the hourly
keepsakes sync still fails while prod is awake (0 BLOCK / 1 WARN / 1 NOTE).

### Scope and method

The 28 scanned files are every path in the review argument. Each file's diff
from `0aa9792` to HEAD was read in full, along with the code it touches or
calls: the helper end to end against the committed units and its own tests;
prodctl's new `data_root`/`instance_dir`/`--instance` parsing, `root`
dispatch, and instance verbs; `config.data_dir` resolution and the
per-instance cookie/operator words; the Worker's `watch`, `publicState`,
`asleep`, `keepsakesHtml`, `cookieNameFor` and header helpers; `edge.set_state`
words and `get_uptime`; the server's `_page` word substitution and lifespan;
`door.js`/`main.js` sinks for the instance words; `accounts.delete_account`,
`accounts_cli._delete_account` and `inputs.forget_toon`; the art keep's
content-addressed store, `sync`, and the prebake/admin/refresh/bin-game
callers; and the slots dreamer cap. The unit validator was differentially
tested against systemd 249's own parser on this box. Recent history of every
scanned file (last 3 commits each) and the full outgoing diff
(`origin/main..HEAD`, 17 commits) were scanned for credential patterns, the
Cloudflare account id, the box's addresses and hostname, the operator's
surname, and this instance's account and invite names; `instance/` is still
gitignored. The 281 tests covering the scanned code pass.

### Findings

[WARN] ops/root/daydream-root:272,320,335 (parse_unit) — The unit validator
strips Unicode whitespace where systemd strips only ASCII, so a sandbox
directive can be present to the validator and absent to systemd.
  Attack vector: `parse_unit` uses Python `str.strip()`/`str.split()`, which
treat U+00A0 (no-break space) and other Unicode spaces as whitespace; systemd
(verified on this box, v249) treats only space and tab as whitespace around a
key or value. A release unit line `ProtectHome<U+00A0>=yes` is read by the
validator as the required, valid key `ProtectHome=yes` (the NBSP is stripped
off the key, `_KEY_RE` then matches), so `validate_unit` returns clean; systemd
reads the key as `ProtectHome<U+00A0>`, an unknown key it ignores, leaving
`ProtectHome` at its weaker default. The same holds for a value
(`NoNewPrivileges=yes<U+00A0>` fails systemd's boolean parse and is ignored).
The NBSP is invisible in the diff `bin/game prod root units` prints, so the
human ask-gate review of `units --apply` would not catch it either. This
defeats the validator's stated invariant (docs/ADMIN-ROOT.md: "the prod
sandbox no weaker than the committed unit"; "cannot weaken the prod sandbox").
Reachability is gated: the validated input is the deployed release's unit
files, i.e. committed repo content, which the threat model treats as
operator-owned ("local attackers: best efforts only"); the one
adversary-reachable path (an injected agent) still faces the human ask prompt
on `units --apply` plus a committed, deployed malicious unit. It is a
defense-in-depth gap in a security-critical control, not an independently
reachable escalation, hence WARN.
  Evidence: `ops/root/daydream-root:272` (`s = line.strip()`), `:320`
(`s = line.strip()`), `:335` (`key, value = key.strip(), value.strip()`); the
control-character guard at `:312-316` catches ord<32 and 127 but not NBSP
(ord 160). Differential test on this box: validator returns `[]` for
`ProtectHome<U+00A0>=yes`, while `systemd-analyze verify` reports
`Unknown key name 'ProtectHome '`.
  Remediation: reject any non-ASCII (or specifically any non-ASCII whitespace)
in unit text before parsing, the same way `parse_unit` already rejects control
characters. The committed units are pure ASCII, so an ASCII-only guard breaks
nothing. Add a hostile variant to `tests/test_root_helper.py`.

[NOTE] Installed daydream-keepsakes.service / daydream-offsite.service
(`/etc/systemd/system/*`, line 1 `NoNewPrivileges=yes`) — Carried from prior
reviews, re-verified on the box, outside this review's paths.
The repo units no longer set the flag; the installed copies still do, and the
hourly keepsakes sync fails whenever prod is awake.
  Attack vector: Unchanged. While the village is awake, a disabled account or
a revoked session stays on the Worker's pass list, and the Worker serves that
pass its keepsakes whenever the origin is unreachable. The weekly offsite run
(next 2026-10-04 05:33 UTC) fails the same way.
  Evidence: The 16:02 UTC run today exited 1 with `sudo: The "no new
privileges" flag is set`; the unit is `failed`. `bin/game prod check` fails on
the job line (daydream/prodcheck.py). The repo now installs the fix through
`bin/game prod root units --apply`, which needs one last `sudo
ops/install-prod.sh` first (docs/ADMIN-ROOT.md).
  Remediation: `sudo ops/install-prod.sh`, then `bin/game prod root units
--apply`, start `daydream-keepsakes.service` once, and confirm `bin/game prod
check` passes its job lines.

### Traced and cleared this run (not findings)

- **The root helper.** Runs `python3 -I` (isolated), reads its fixed facts
  from root-owned `/etc/daydream/root.conf` not its arguments or environment,
  and its one command runner (`_run`) admits only systemctl/logger/runuser
  with a clean env from `/`, refuses any path argument to systemctl/logger,
  and lets runuser drop only to the service user. File reads go
  component-by-component with `O_NOFOLLOW` (`_open_dir`/`_read_at`), reject
  symlinks, hard-linked files, non-regular files and >64 KiB. The validator
  pins each unit's identity, forbids privilege prefixes/`AmbientCapabilities`/
  `LoadCredential`/root groups/`%` specifiers, requires the prod sandbox keys,
  and rejects CR and whitespace-after-backslash. `env set` refuses the
  trust-deciding keys, validates each allowlisted value, and runs the
  release's boot guard as the service user before writing. The one gap is the
  WARN above.
- **The sudoers line.** `NOPASSWD: /usr/local/sbin/daydream-root` with any
  arguments is by design: the root-owned helper, installed only by the
  password-gated installer, decides what it will do. Installed 0440 via
  `visudo -cf`.
- **prodctl `--instance` and `root`.** `--instance` is accepted only as the
  last two arguments and its name is regex-checked, so it cannot split a
  two-word verb past an ask rule; a leading `--instance` is refused. `root`'s
  arguments are forwarded to the helper before `--instance` is parsed, so the
  ask rule on `prod root units --apply` cannot be walked around.
- **The Worker's words.** `place`, `title`, `operator` and the session-cookie
  name ride on the KV flag; every one is HTML-escaped (`escapeHtml`) before it
  reaches the asleep page, `place` is clamped to 80 chars (`placeOf`), and the
  cookie name is accepted only if it matches `^dd_session_[a-z0-9_-]{1,60}$`
  (`cookieNameFor`), so a malformed flag falls back to the configured cookie.
  Template fills use function replacements, so player text cannot inject `$&`
  substitution patterns. The `uptime` KV key is never exposed on a public
  route. CSP and the page headers are unchanged.
- **The server and SPA words.** `server._page` substitutes the instance words
  with `html.escape(quote=True)`; `instance.validate` bounds every value
  (printable, <=200 chars) and shape-checks `door_image` and `envelope`
  (`^assets/...\.(png|jpg|webp)$`, `^worlds/[a-z0-9_-]+\.json$`), so neither
  can point outside the assets dir or at an arbitrary file. `door.js`/`main.js`
  read the words from `body.dataset` into `textContent` and template literals,
  and the door image only through `assetUrl(...).src`. A malformed
  `instance.json` refuses boot rather than serving half-worded.
- **`account delete`.** Behind an ask rule; deletes the account, its sessions,
  every tied invite, its throttle counters, its dreamers (carried things drop
  to the room), and the dreamers' private input lines; parameterized SQL
  throughout. The shared event history is intentionally kept.
- **The art keep.** Content-addressed by sha256, hard-linked from the cache,
  append-only provenance; `sync` walks only `generated_assets` rows and PNGs
  under the world's own cache dir, skips symlinks, and bounds path shape;
  `keep_render` never fails a render. Runs as the owner of the data dir.
- **The dreamer cap.** 6/day per account through the same throttle table, on
  both create routes (`_create`), admins exempt; refuses with 429, no mutation.

### Secrets, PII and the instance

The scanned diffs and each scanned file's last three commits hold only test
constants (an empty username/password body, throttle key strings). The 17
commits not yet on `origin/main` (full diff, every file) contain no
token-shaped value, not the Cloudflare account id, none of the box's global
addresses, not the operator's surname, and none of this instance's account or
invite names. The `hostname` matches only because the box is named `dev`
(a common substring). `instance/` is gitignored.

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
- World envelopes and `bin/game` are trusted as the operator's own (world
  load/reset content, `reset`'s `rm -rf`, dev `.env` sourcing, the dev
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

---
*Prior review (2026-09-28, paths, commit `0aa9792`): covered the 14 files
changed from `7f9af5a` (arrival cut, log lines without model output, the awake
page, the iPad layout) and found 0 BLOCK / 0 WARN / 1 NOTE (the installed
timer units' `NoNewPrivileges`, unchanged here). It closed the Worker's
WebSocket cookie-leak note (fixed `3df294b`). Earlier entry at
`git show 9b738f9:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"1e65f3a36af90f76a4ac43395807b57917474a4d","scope":"paths","scanned_files":["bin/game","daydream/accounts.py","daydream/accounts_cli.py","daydream/admin.py","daydream/api/access.py","daydream/api/slots.py","daydream/api/ws.py","daydream/config.py","daydream/edge.py","daydream/images/client.py","daydream/images/keep.py","daydream/inputs.py","daydream/instance.py","daydream/prebake.py","daydream/prodcheck.py","daydream/prodctl.py","daydream/refresh.py","daydream/server.py","docs/claude-settings.local.example.json","edge/public/daydream/_edge/asleep.html","edge/src/worker.js","edge/wrangler.toml","ops/install-prod.sh","ops/root/daydream-root","ops/sudoers.d/daydream","web/assets/door.js","web/assets/main.js","web/door.html","web/index.html"],"block":0,"warn":1,"note":1} -->
