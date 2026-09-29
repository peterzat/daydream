# Runbooks: running the village

Playbooks for operating a live daydream instance, written to be followed by a
Claude Code agent in a session on the box (and readable by the human who asks
it to). The shell is the admin console: every step here is a `bin/game prod
...` or `bin/game edge ...` command, plus the few things only the operator's
hands can do (sudo, the Cloudflare dashboard).

| Playbook | When |
|---|---|
| [publish.md](publish.md) | The everyday loop: play, say, build, (preview), publish. Start here |
| [verify.md](verify.md) | Any time: is everything that should hold, holding? (`bin/game prod check`) |
| [sleep-and-wake.md](sleep-and-wake.md) | Lend the GPU, a maintenance window, a reboot, waking up |
| [deploy.md](deploy.md) | Ship code; roll back |
| [content.md](content.md) | Authored fixes, dreams and art reaching the live village |
| [reset.md](reset.md) | A deliberate fresh village: what goes, what stays, the art |
| [instances.md](instances.md) | Several games behind one door: list, create, swap, act on a detached one |
| [friends.md](friends.md) | Invites, sign-in trouble, passwords, moderation |
| [backups.md](backups.md) | Nightly and offsite backups; restoring into dev or prod |
| [incident.md](incident.md) | Something is wrong and you don't know what yet |
| [edge.md](edge.md) | The Cloudflare side: the Worker, its flag, secrets, tokens |
| [root.md](root.md) | Root through the helper: refresh the units, run a timer job, change a prod.env key |

First-time setup is not here: it is [`docs/CLOUDFLARE-SETUP.md`](../CLOUDFLARE-SETUP.md).
The design behind all of it is [`docs/GOING-LIVE.md`](../GOING-LIVE.md).

## Before any prod work

1. **Read the instance record**, if this checkout has one: `instance/NOTES.md`
   (gitignored). It says what exists in this Cloudflare account and on this
   box, and what is pending.
2. **Look before acting:** `bin/game prod status`, and for anything
   public-facing `bin/game prod check`.
3. **Know who is playing.** `prod status` lists them. Anything that restarts
   the service drops their sockets for a few seconds (open tabs reconnect by
   themselves); a sleep gives them a 60 s warning.

## Who does what

- **The agent** runs every `bin/game prod` and `bin/game edge` verb when the
  operator asks for the work, with a one-line note per step (CLAUDE.md
  "Agent policy for prod"). Two layers in `.claude/settings.local.json`
  (template: `docs/claude-settings.local.example.json`) decide what prompts:
  its permission rules, and its PreToolUse hook, `tools/agent_guard.py`,
  which reads each command the way the shell will and asks for the same
  verbs however they are spelled (and before any change to itself or to the
  settings files). They always prompt for the verbs that mint
  a credential or a privilege, reach players, replace the world, remove a
  person, or change the edge or what root has installed (`prod invite
  create|reset|revoke|unblock`, `prod account
  create|role|cli-cookie|delete|disable|enable|rename`, `prod account
  sessions --revoke`, `prod world
  reset|delete|restore|snapshot-restore|restore-backup|load|delete-toon|rest-toon|skill|swap`,
  `prod world patch` without `--check`, `prod dream apply`, `prod play`,
  `prod pull`, `prod instance`, `prod sleep`, `prod rollback`,
  `prod offsite-restore`, `prod root units` and `prod root env` in any form,
  `prod deploy` of another ref or with `--skip-tests`,
  `edge secrets|kv-create|sleep`). The hook also denies any command or file
  read that names the box's credential paths, or prints the GitHub token.
  `prod invite list` and `prod status|logs|check|plan|text-scan` never
  prompt. `--instance NAME` must be the last two arguments, so these rules
  always see the whole verb.
- **The root helper** (`bin/game prod root`, [root.md](root.md)) is how the
  agent refreshes the units, runs a timer job, and changes an allowlisted
  prod.env key, with no password: it validates what it installs and logs
  every action.
- **The operator** does what needs a password or a browser: installing or
  changing the root helper and sudoers (`sudo ops/install-prod.sh`), system
  packages, the tunnel token, the prod.env keys the helper refuses, and the
  Cloudflare dashboard.
- **Nobody** mends the great clock with the operator's own account in prod:
  the prologue belongs to the first friend.

## Conventions for writing a playbook

Each playbook says when to use it, the commands in order, how to verify, and
what to do when a step fails. Commands are the real verbs (a tier_short test,
`tests/test_runbooks.py`, fails when a playbook names a `bin/game prod` or
`bin/game edge` verb that doesn't exist). When a playbook is wrong, fix the
playbook in the same session that found out.
