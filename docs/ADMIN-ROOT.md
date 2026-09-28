# Root and the admin console

Status: **proposal, 2026-09-28, for the operator's decision.** Nothing here
is built. It answers: "I shouldn't have to do the `sudo ops/install-prod.sh`
thing; you should be able to do it from this repo", without adding sudo
scripts carelessly.

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

## Decisions for the operator

1. Adopt the helper design (or passwordless sudo, or the status quo)?
2. Should `prod.env` edits be in the helper at all, or stay `sudoedit`?
3. Is the operator's membership in `docker` needed? Leaving it would make
   the password mean what it seems to (a separate, optional hardening).
