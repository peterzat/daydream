# Root: units, timer jobs and prod.env through the helper

Root on this box goes through one program: `/usr/local/sbin/daydream-root`,
the root helper (source `ops/root/daydream-root`, design
[`docs/ADMIN-ROOT.md`](../ADMIN-ROOT.md)). It is root-owned, installed only
by `sudo ops/install-prod.sh`, and reached through one sudoers line, so the
agent can use it without a password. It parses its own arguments and refuses
anything outside a fixed vocabulary, never runs the release's or the repo's
code as root, and logs every action.

Use it when:

- a deploy changed `ops/systemd/*` and the installed units should follow
- a timer job (backup, keepsakes, offsite) should run now, to prove it or in
  an incident
- a `prod check` job line says "not installed", an inactive timer, or "no new
  privileges" (the installed units are older than the release's)
- an allowlisted `prod.env` key should change (a log level, a feature flag,
  the operator's title)

Look first, every time: `bin/game prod root doctor`.

## The verbs

| Command | Does | Prompts? |
|---|---|---|
| `bin/game prod root doctor` | Read-only. root.conf; the sudoers file (present, root 0440, names the helper); the service user's groups; each unit against the deployed release; drop-in directories; whether the installed helper is the repo's | no |
| `bin/game prod root units` | Renders the deployed release's units, validates each, prints a diff against what is installed | no |
| `bin/game prod root units --apply` | Installs the validated units that differ, `daemon-reload`, `enable --now` the three timers | yes (ask rule) |
| `bin/game prod root start\|stop\|restart <service>` | `daydream-prod`, `cloudflared-daydream`, `daydream-backup`, `daydream-keepsakes`, `daydream-offsite` (`.service`) | no |
| `bin/game prod root status <unit>` | those, and the three `.timer` units | no |
| `bin/game prod root env show` | prints `/srv/daydream/etc/prod.env` (it holds no secrets) | no |
| `bin/game prod root env set KEY VALUE` | one allowlisted key; the release's boot guard runs first, as `daydream` | yes (ask rule) |
| `bin/game prod root version` | the installed helper's sha256 | no |

The two verbs that change what root installs or what prod runs with are
behind ask rules in the operator's local permission settings (the template,
`docs/claude-settings.local.example.json`, carries them): the agent runs
them when the operator asked for the work, and the prompt shows the command.
Put `--instance` nowhere in a `prod root` command: the helper has no
instances and refuses it.
For waking and sleeping the village use `bin/game prod wake|sleep`, not
`start|stop`: those also handle the engines, the edge flag and the players.

## Refresh the units after a deploy

The units come from the DEPLOYED release (`/srv/daydream/current/ops/systemd/`),
not the working tree, so deploy first.

```sh
bin/game prod deploy
bin/game prod root units            # read the diff: is this the change you meant?
bin/game prod root units --apply    # prompts; installs, reloads, enables the timers
bin/game prod root doctor           # every unit "matches release <sha>"
```

A changed service unit applies at its next start. For a timer job, prove it
now: `bin/game prod root start daydream-keepsakes.service`, then
`bin/game prod check` (its job line). For `daydream-prod.service` the next
start is the next `prod wake`, or `bin/game prod root restart
daydream-prod.service`, which drops every player's socket for a few seconds:
ask the operator first unless they asked for it.

## Change a prod.env key

| Key | Values |
|---|---|
| `DAYDREAM_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DAYDREAM_OPERATOR_NAME` | one printable line, at most 60 characters, no quotes, backslashes, `$` or backticks ("the Night Warden"). The box-wide fallback: an instance whose `instance.json` sets `operator` uses its own ([instances.md](instances.md)) |
| `DAYDREAM_JOURNAL_ENABLED`, `DAYDREAM_REGEN_UI`, `DAYDREAM_MEMORY_ENABLED`, `DAYDREAM_DRIFT_ENABLED`, `DAYDREAM_VILLAGE_ENABLED`, `DAYDREAM_DIRECTOR_LLM` | `0` or `1` |
| `DAYDREAM_LLM_CONCURRENCY` | `1` to `8` (keep it at or below vLLM's `--max-num-seqs`, 4 by default) |

```sh
bin/game prod root env show
bin/game prod root env set DAYDREAM_LOG_LEVEL DEBUG     # prompts
bin/game prod root restart daydream-prod.service        # it reads prod.env at start; drops sessions
bin/game prod check
```

`env set` rewrites that one line in place (or appends it) and keeps every
other line and comment. Before writing, it runs the deployed release's own
boot guard (`config.boot_problems`) over the proposed file as the `daydream`
user; if the guard objects, nothing is written.

The keys that decide where prod listens, what it trusts or where its data
lives are refused: `DAYDREAM_ENV`, `DAYDREAM_ACCESS`, `DAYDREAM_PUBLIC_ORIGIN`,
`DAYDREAM_PUBLIC_BASE`, `DAYDREAM_BIND_HOST`, `DAYDREAM_PORT`,
`DAYDREAM_DATA_DIR`, `DAYDREAM_LLM_BASE_URL`, `DAYDREAM_COMFYUI_BASE_URL`.
Those, and anything not on the list above, stay with the operator
(`sudoedit /srv/daydream/etc/prod.env`).

## When the helper refuses

| It says | Meaning | Do |
|---|---|---|
| `... is not installed: the operator runs sudo ops/install-prod.sh` | no helper on this box yet | ask the operator to run it once |
| `the repo's helper is newer` (from `prod root doctor`) | `ops/root/daydream-root` changed since the last install | ask the operator to run `sudo ops/install-prod.sh` |
| `refused: these units would not install` and a list | a release unit asks for something the validator does not allow (a new key, another user, a weaker sandbox) | If the change is a mistake, fix the unit and redeploy. If it is deliberate, widen the helper's allowlist in `ops/root/daydream-root` with a test in `tests/test_root_helper.py`, commit, and have the operator run `sudo ops/install-prod.sh`. Never route around the validator. |
| `release <sha> has a unit this helper does not know` | a new unit file in the release | the same: teach the helper, then the operator installs it |
| `... masked or linked by hand? the operator decides` | an installed unit is a symlink, not a file | the operator looks; the helper does not replace it |
| `drop-ins: ... exists` (from `doctor`) | a `<unit>.d/` directory overrides the unit | the operator reviews it; the helper does not manage drop-ins |
| `the boot guard rejects the proposed prod.env` | the new value would stop prod from booting | nothing was written; read the guard's message |
| `... stays with the operator` | a key that decides trust | the operator edits it with `sudoedit` |

## What stays with the operator

The password is still how these change, through `sudo ops/install-prod.sh`
or by hand:

- installing or changing the helper itself and the sudoers entry
- system packages (`cloudflared`, `age`, a browser's libraries)
- the tunnel token (`/etc/cloudflared/daydream.env`)
- group membership (the operator's, the service user's)
- the `prod.env` keys the helper refuses, and any drop-in
- the Cloudflare dashboard

The agent never edits the sudoers file, the installed helper, or its own
permission settings.

## The record

Every action the helper takes is one line in the journal, with the release
it came from and each installed file's sha256:

```sh
journalctl -t daydream-root --since today
```

sudo logs each call too (`journalctl _COMM=sudo`).
