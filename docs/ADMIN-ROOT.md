# Root and the admin console

Status: **built 2026-09-28** (decided the same day: the validated helper,
with `prod.env` through it). It answers: "I shouldn't have to do the `sudo
ops/install-prod.sh` thing; you should be able to do it from this repo",
without adding sudo scripts carelessly. As shipped (`ops/root/daydream-root`,
`bin/game prod root <verb>`, playbook [`docs/runbooks/root.md`](runbooks/root.md)):
`version` (its own sha256); `doctor` (read-only: root.conf, the sudoers file,
the service user's groups, each unit against the deployed release, drop-ins;
`prod root doctor` adds whether the installed helper is the repo's, since the
helper itself never reads the repo); `units [--apply]`; `start|stop|restart`
for the five daydream services and `status` for those and the three timers;
`env show` and `env set KEY VALUE` for nine allowlisted keys. Its fixed facts
come from `/etc/daydream/root.conf`, which the installer writes. It takes
effect after the operator's one run of `sudo ops/install-prod.sh`, and the
ask rules for `prod root units --apply` and `prod root env set` belong in the
operator's local permission settings (`docs/claude-settings.local.example.json`
carries them).

## Security posture (the operator's policy, 2026-09-28)

- **External attacks: high priority, hardened, documented, tested.** The
  network ingress (the Worker, Access, the tunnel, edge mode on loopback),
  escalation through the game (the sandboxed service, closed verbs, effect
  allowlists, loopback-only egress), the prod scripts (commands as the
  service user, path guards, ask rules on credential and world verbs, the
  helper's validator), the Cloudflare credentials (a 0600 token scoped and
  IP-filtered, the Access service token only on the Worker), and injection
  into the admin agent through player text.
- **Local attackers: best efforts only.** The box is single-user and locked
  down (its own notes live in the operator's environment repo: key-only SSH,
  a deny-by-default firewall, routine access over the tailnet). The operator
  keeps the `docker` group, which is root-equivalent, so a hostile process
  running as the operator is out of scope. Reasonable precautions still
  hold: the sandboxed service user, root-only secrets, root actions through
  the validated helper, and every one logged.
- **Known local-only residuals** (recorded, not fixed, under the posture):
  systemd reads the release's `.release.env` as root, and releases belong
  to the operator, so the operator's user could point that file at the
  tunnel token's file and hand the token to the prod service's environment
  (whose egress is loopback-only). Anyone who can do that already holds the
  operator's `docker` membership.

## Where we are

The design (docs/GOING-LIVE.md section 1) makes a Claude Code session on the
box the admin console. It drives `bin/game prod` and `bin/game edge` under a
standing grant, with ask rules on the verbs that mint credentials or replace
the world. Root stays with the human: "sudo and the dashboard stay human."

What the agent can do without a password today (`/etc/sudoers.d/daydream`):

- start, stop and restart `daydream-prod` and `cloudflared-daydream`, and
  start `daydream-backup`
- run anything as the sandboxed `daydream` user (a loss of privilege)

What still needs the operator's password, and how often:

| Root action | How often | Example |
|---|---|---|
| Install or refresh the systemd units from `ops/systemd/` | whenever a unit changes (the keepsakes/offsite `NoNewPrivileges` fix is waiting on this now) | `sudo ops/install-prod.sh` |
| Start a timer job by hand to prove it | after unit changes, in incidents | `sudo systemctl start daydream-keepsakes.service` |
| Edit `/srv/daydream/etc/prod.env` | occasionally (a log level, a feature flag) | `sudoedit` |
| Change the sudoers entry itself | rarely | the installer |
| System packages | rarely | WebKit's libraries, cloudflared |
| The tunnel token, group membership | rarely | the installer |

## The constraint that shapes the answer

Any rule that lets the operator's user install files as root without a
password lets whoever controls those files decide what root runs. A sudoers
line like `install ops/systemd/X /etc/systemd/system/X` is root for anyone
who can edit the repo or a release (both are the operator's). So the safety
cannot come from *which command* runs; it has to come from **validating what
gets installed**.

One more fact, stated plainly: the operator's user is in the `docker` group,
which is root-equivalent (docs/GOING-LIVE.md section 7). Against a hostile
process running as the operator, sudo's password already protects nothing.
What the password *does* protect is the agent: a Claude session that meets
an injected instruction in player text cannot type it. The design below keeps
that property for everything that shapes privilege, and gives up the
password only for actions that are declared, validated, logged and
reversible.

## Proposal: one root-owned helper with a fixed vocabulary

`/usr/local/sbin/daydream-root`, a small stdlib Python program (run as
`python3 -I`, isolated from the caller's environment), root-owned, installed
only by `ops/install-prod.sh` (so changing it still takes the password). Its
source lives in the repo (`ops/root/daydream-root`) where it is reviewed and
tested like everything else. One sudoers line:

```
peter ALL=(root) NOPASSWD: /usr/local/sbin/daydream-root
```

The helper parses its own arguments and refuses anything outside its verbs:

| Verb | Does | Guard |
|---|---|---|
| `units` | renders the unit set from the deployed release (`/srv/daydream/current/ops/systemd/`), validates each unit, prints a diff against what is installed | read-only |
| `units --apply` | installs the validated units, `daemon-reload`, enables the allowed timers, logs `daydream-root: units from release <sha>` with each file's hash | agent ask rule (a prompt, no password) |
| `start / stop / restart / status <unit>` | for the daydream units only, the timer jobs included | none (routine, like today) |
| `env show` / `env set KEY VALUE` | `prod.env`, for an allowlist of keys each with a validator; the release's boot guard is run against the proposed file before it is written | `set` behind an ask rule |
| `doctor` | read-only: installed helper vs the repo's copy, sudoers vs the repo's, units vs the release, groups | none |

**The unit validator** is the heart, tested in the repo against the
committed units and against hostile variants:

- exactly the known unit names
- each service's `User=` pinned: `daydream` for the prod service and the
  backup, the operator for the keepsakes and offsite jobs, `DynamicUser=yes`
  for cloudflared; never root, never a missing `User=`
- no `Exec*=` prefixes that bypass privilege (`+`, `!`, `!!`), no
  `AmbientCapabilities`, no capability grants, no `Group`/`SupplementaryGroups`
  of root, docker, sudo or adm, no `PermissionsStartOnly`
- only the directive keys the committed units use (an allowlist, not a
  denylist)
- the prod service's sandbox lines present and no weaker than today
  (the same invariants `tests/test_ops_units.py` asserts)
- `ExecStart` under `/srv/daydream/current/` for units running as `daydream`

The worst a hostile edit could install, then, is a unit that runs as
`daydream` (already sandboxed) or as the operator (no new privilege), and it
cannot weaken the prod sandbox.

**What stays human (the password):** installing or changing the helper and
the sudoers file (`ops/install-prod.sh`), system packages, the tunnel token,
group membership. `daydream-root doctor` says when the repo's helper is newer
than the installed one, so the agent can ask for exactly that.

**The agent's side:** `bin/game prod root <verb>` wraps the helper. The local
permission rules gain ask rules for `prod root units --apply` and
`prod root env set`. The agent never edits sudoers or its own permission
settings.

## Alternatives considered

- **Passwordless sudo for everything.** Simplest, and on a box where the
  operator is in `docker` it changes little against a local attacker, but it
  turns every root action into one approval for an agent that reads player
  text. Rejected.
- **Exact-command sudoers lines** (install this file, reload systemd).
  They look narrow and are not (see the constraint above). Rejected.
- **Move the operator's jobs to systemd user units** (`loginctl enable-linger`
  once; then keepsakes and offsite need no root at all). It shrinks the
  helper's surface, and is worth doing later, but it still needs the helper
  for the prod, backup and tunnel units. A possible later step.
- **Status quo** (the operator runs the installer). This is what the
  operator asked to end.

## What it costs, once

One last `sudo ops/install-prod.sh` by the operator: it installs the helper
and the one-line sudoers entry (plus today's pending unit fix). After that,
unit changes, timer jobs and `prod.env` edits flow through the admin console.

## Decisions (2026-09-28)

1. The validated helper, as above.
2. `prod.env` edits go through the helper (`env set`, validated, boot guard
   first, behind an ask rule).
3. The operator keeps the `docker` group; local attackers are best efforts
   only (the posture above).
