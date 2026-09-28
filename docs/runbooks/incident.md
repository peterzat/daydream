# Incident: something is wrong

Start by looking, in this order, and stop at the first thing that is off.

```sh
bin/game prod check       # which invariant broke?
bin/game prod status      # units, engines, jobs, health, who is playing
bin/game prod logs        # the service and the tunnel (add -f to follow)
bin/game edge status      # the flag, the uptime watch (DOWN since ...?), what the public URL answers
nvidia-smi                # is the card free, full, or held by something else?
```

## Reading the log

`bin/game prod logs` carries the service's own lines (daydream/logs.py, since
2026-09-28): sign-ins and refusals, invitations opened and redeemed, dreamers
made, entered, rested and let go, each WebSocket session
(`ws: <user> dreaming as <dreamer> in <room>` through `closed after Ns`),
every model call (`llm purpose=... wait_ms=... call_ms=...`), each painting
with its time, each journal entry written or skipped, and any session that
ended on an error, with its traceback. They name accounts and dreamers, never
a password, an invitation link or what anyone typed (that stays in the
world's private input log). `DAYDREAM_LOG_LEVEL=WARNING` in prod.env quiets
the app's own lines (uvicorn's WebSocket lines follow its --log-level). To see
what a friend actually did (their input log, the events around them),
`bin/game prod pull` brings a fresh backup into dev ([backups.md](backups.md));
never open the live file.

## Symptoms and causes

| What friends see | Likely cause | Do |
|---|---|---|
| The asleep page without a note | The service, the tunnel or the box is down (the Worker answers for an unreachable origin) | `bin/game prod wake` (idempotent); read `prod logs` if it fails |
| "the dream is foggy" on everything they type | vLLM is down or unreachable | `bin/game vllm-up` (dev's engines are prod's too), then `prod status` |
| Grey placeholders instead of portraits | ComfyUI is down, or the GPU is busy elsewhere | `bin/game comfyui-up`; renders catch up on their own |
| Slow replies | Another process is rendering (dev prebake, image-test, tier_long) | Text calls get the card between renders; stop the dev GPU work if it matters now |
| The door refuses a correct password | Throttles, or a disabled account | [friends.md](friends.md) |
| A page from the Pages site at /daydream | The Worker's route is gone | `bin/game edge deploy` ([edge.md](edge.md)) |

## When wake fails

- `engines did not come up`: `bin/game vllm-up` and `bin/game comfyui-up`
  directly, and read their logs (`~/.local/state/daydream/engines/`). A GPU
  held by another process (`nvidia-smi`) is the usual cause.
- `the service did not answer /healthz`: `bin/game prod logs`. A boot guard
  refusal names its reason (prod must run in edge mode, on loopback, with an
  https public origin); a WORLD_VERSION MAJOR mismatch names
  `world reset`. Roll back if a deploy just went out ([deploy.md](deploy.md)).
- The service came up but the edge still says asleep: the flag could not be
  set (the Cloudflare API was unreachable). `bin/game edge wake`.

## Afterwards

Write down what happened and what fixed it in the instance record
(`instance/NOTES.md`), and fix the playbook that didn't cover it.
