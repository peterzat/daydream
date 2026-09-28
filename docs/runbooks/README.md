# Runbooks: running the village

Playbooks for operating a live daydream instance, written to be followed by a
Claude Code agent in a session on the box (and readable by the human who asks
it to). The shell is the admin console: every step here is a `bin/game prod
...` or `bin/game edge ...` command, plus the few things only the operator's
hands can do (sudo, the Cloudflare dashboard).

| Playbook | When |
|---|---|
| [verify.md](verify.md) | Any time: is everything that should hold, holding? (`bin/game prod check`) |
| [sleep-and-wake.md](sleep-and-wake.md) | Lend the GPU, a maintenance window, a reboot, waking up |
| [deploy.md](deploy.md) | Ship code; roll back |
| [content.md](content.md) | Authored fixes, dreams and art reaching the live village |
| [reset.md](reset.md) | A deliberate fresh village: what goes, what stays, the art |
| [friends.md](friends.md) | Invites, sign-in trouble, passwords, moderation |
| [backups.md](backups.md) | Nightly and offsite backups; restoring into dev or prod |
| [incident.md](incident.md) | Something is wrong and you don't know what yet |
| [edge.md](edge.md) | The Cloudflare side: the Worker, its flag, secrets, tokens |

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
  "Agent policy for prod"). A local permission rule lets them run without a
  prompt, except the verbs that mint a credential or a privilege or replace
  the world (`prod invite reset`, `prod account role|create|cli-cookie`, `prod
  world reset|delete|restore|snapshot-restore|restore-backup|load`), which
  always prompt.
- **The operator** does what needs root or a browser: `sudo ops/install-prod.sh`,
  editing `/srv/daydream/etc/prod.env`, and the Cloudflare dashboard.
- **Nobody** mends the great clock with the operator's own account in prod:
  the prologue belongs to the first friend.

## Conventions for writing a playbook

Each playbook says when to use it, the commands in order, how to verify, and
what to do when a step fails. Commands are the real verbs (a tier_short test,
`tests/test_runbooks.py`, fails when a playbook names a `bin/game prod` or
`bin/game edge` verb that doesn't exist). When a playbook is wrong, fix the
playbook in the same session that found out.
