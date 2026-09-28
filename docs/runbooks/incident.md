# Incident: something is wrong

Start by looking, in this order, and stop at the first thing that is off.

```sh
bin/game prod check       # which invariant broke?
bin/game prod status      # units, engines, jobs, health, who is playing
bin/game prod logs        # the service and the tunnel (add -f to follow)
bin/game edge status      # the flag, and what the public URL answers
nvidia-smi                # is the card free, full, or held by something else?
```

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
