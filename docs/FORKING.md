# Make it yours: forking daydream

This repo serves one live instance, the author's invite-only village. Your
fork serves yours. Everything general is committed; everything that makes an
instance *yours* (tokens, the Cloudflare dashboard, the box's prod
environment, your record of what exists where) stays off GitHub. This page is
the path, in order, with the values you change.

## What you need

- **A GPU box you control.** An NVIDIA GPU with about 20 GB (the author's is
  an RTX 4000 SFF Ada), a driver new enough for CUDA 13
  (vLLM 0.30's wheels; [`gpu-and-models.md`](gpu-and-models.md)), Ubuntu
  22.04 (the prod installer uses apt and Cloudflare's `jammy` repo), Python
  3.10 or newer, `git` and `wget`, and about 30 GB of disk for the engines
  and model weights.
- **A way to reach the dev server.** It admits only tailnet and loopback
  clients: Tailscale, a browser on the box, or an SSH tunnel
  (`ssh -L 54321:127.0.0.1:54321 <box>`, then `http://127.0.0.1:54321`).
- **For hosting friends:** Node.js 20 or newer, and a Cloudflare account with
  a domain on Cloudflare DNS. The free plan covers the Worker, KV, Zero Trust
  (no seats used) and the tunnel; R2, for offsite backups, needs a payment
  method on file. The box itself is the only real cost.
- **Claude Code is optional.** Every step and every playbook is a plain
  `bin/game` command. Claude Code is how the author runs this instance (the
  agent follows `docs/runbooks/`), and it is what writes new content and
  dreams (Opus, in a session), but the game and its operations need nothing
  but the shell.

## The order

1. **Run it in dev first** ([README](../README.md), "Running it"): the
   engines, a world, your own account, a game in your browser. No Cloudflare.
2. **Change this instance's values** (the table below), commit.
3. **Host it**: [`CLOUDFLARE-SETUP.md`](CLOUDFLARE-SETUP.md), steps 1 to 12,
   in order. The design behind it is [`GOING-LIVE.md`](GOING-LIVE.md).
4. **Operate it** with [`runbooks/`](runbooks/); keep your instance record
   (below) as you go.

## The values that are this instance's

| Where | What to set |
|---|---|
| `edge/wrangler.toml` | the two `routes`, `ORIGIN`, `PUBLIC_HOST`, `OPERATOR`, and `[[kv_namespaces]] id`: the committed id is the author's namespace, so set it to `REPLACE_WITH_YOUR_KV_ID` before CLOUDFLARE-SETUP step 1 and fill in yours at step 8 |
| `ops/prod.env.example` | `DAYDREAM_PUBLIC_ORIGIN`, `DAYDREAM_OPERATOR_NAME` (a title players see; unset, "the person who invited you") |
| `ops/sudoers.d/daydream` | nothing: `peter` there is a placeholder the installer replaces with the user who runs `sudo` |
| the prose of CLOUDFLARE-SETUP | `<domain>` stands for your domain throughout |

`tests/test_ops_units.py` checks that `edge/wrangler.toml` and
`ops/prod.env.example` describe the same site, so change them together.

## Instances

A fresh box starts with its first instance (CLOUDFLARE-SETUP step 11 runs
`bin/game prod instance migrate village`), so friends' accounts, the world
and the art live in `instances/village/` from the start, and you can add
more games behind the same door later ([`INSTANCES.md`](INSTANCES.md),
[`runbooks/instances.md`](runbooks/instances.md)).

## The agent's permission rules

If you run operations through Claude Code, give it a standing grant for the
prod verbs and keep the dangerous ones behind a prompt. Copy
[`claude-settings.local.example.json`](claude-settings.local.example.json) to
`.claude/settings.local.json` (gitignored). It allows `bin/game prod *` and
`bin/game edge *`, and always asks before the verbs that mint a credential or
a privilege, replace a world, remove a person, or change what root installed.
`--instance NAME` must be the last two arguments (prodctl refuses it
anywhere else), so those rules always see the whole verb.

## Your instance record

Keep one, outside the repo (the author's is the gitignored
`instance/NOTES.md`). A shape that works:

```markdown
# This instance
## Secrets (where they live, never what they are)
## Cloudflare (account, zone, token scopes and IP filter, Access app and policy,
   tunnel id and route, cache and rate-limit rules, Worker, KV id)
## The box (what the installer set up; groups; timers)
## Pending (what is not done yet)
## History (dated: what changed, and why)
```

Update it in the same session whenever prod state changes.

## Staying current with upstream

```sh
git remote add upstream https://github.com/peterzat/daydream.git   # once
git fetch upstream && git merge upstream/main                      # resolve your values if they conflict
bin/game test medium
bin/game prod deploy
```

A release changes code, not your box's config. When a merge touches
`ops/systemd/`, `ops/sudoers.d/` or `ops/install-prod.sh`, apply it as
[`runbooks/deploy.md`](runbooks/deploy.md) ("After changing ops files") says.

## Security expectations

The external surface is the priority and is hardened, documented and tested:
the edge (Worker, Access, the tunnel, an origin on loopback), escalation
through the game (a sandboxed service user with loopback-only egress, closed
verbs, allowlisted effects), the prod scripts, and the Cloudflare
credentials. A single-user box's local attackers are handled on a best-effort
basis ([`ADMIN-ROOT.md`](ADMIN-ROOT.md), "Security posture"). The threat model
and its residual risks are [`SECURITY.md`](../SECURITY.md).
