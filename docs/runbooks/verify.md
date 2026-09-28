# Verify: is the village holding?

```sh
bin/game prod check     # exit 0 when everything holds; read-only
bin/game prod status    # the box's view: release, units, engines, jobs, who is playing
bin/game edge status    # the flag in KV, and what the public URL answers
```

Run `prod check` after every deploy, wake, edge deploy or dashboard change,
and whenever something feels off. It makes a handful of GETs, one
cross-origin POST that the CSRF check refuses before any handler runs, one
anonymous WebSocket upgrade, and (while awake) one WebSocket handshake with
the CLI's own account, which has no toon, so nothing is created.

## What each check means, and what to do when it fails

| Check | Holds when | If it fails |
|---|---|---|
| release | a release is deployed; a note when it is behind HEAD | `bin/game prod deploy` ([deploy.md](deploy.md)). "Not in HEAD's history" means a history rewrite: redeploy. |
| edge status | the public status agrees with the box (awake only when the service runs and the flag isn't asleep) | Awake box, awake flag, asleep edge: the tunnel or the service is down ([incident.md](incident.md)). A stale awake flag on an asleep box is not a failure: the Worker reads an unreachable origin as asleep. |
| edge flag | the flag isn't asleep while the service runs (listed only when it fails) | Friends see the asleep page while the village runs (say, a `prod wake` that could not flip the flag): `bin/game edge wake`, unless a note over a running village is intended ([sleep-and-wake.md](sleep-and-wake.md) "The flag alone"). |
| front door | awake: 200 with `<base href="/daydream/">`; asleep: the 503 asleep page | A 200 without the base href means the prefix isn't reaching the app (`DAYDREAM_PUBLIC_BASE`); Pages content means the Worker's route is gone ([edge.md](edge.md)). |
| api signed out | awake: 401; asleep: 503 JSON with `asleep: true` | A 200 would mean the sign-in gate is off: stop and read SECURITY.md before anything else. |
| cross-origin login | 403 | The CSRF origin check is off or `DAYDREAM_PUBLIC_ORIGIN` is wrong in prod.env. |
| no-slash / apex redirect | 301 to `https://www.<domain>/daydream/` | The Worker's routes or its redirect logic changed ([edge.md](edge.md)). |
| origin locked | the tunnel hostname answers 403 without the service token | **Serious**: the origin is reachable around the Worker. Check the Access application and its single `worker only` policy, and the tunnel route's JWT validation, in the dashboard. |
| anonymous ws upgrade | no `CF_Authorization` cookie on the answer | **Serious**: the Worker is leaking Access's cookie (the 2026-09-28 BLOCK). Redeploy the Worker from main; `node --test edge/test/*.test.js`. |
| session ws | 101 with no Access cookie, then `needs_toon` and a clean 1000 close | No 101: the WebSocket path through Worker and tunnel is broken. No 1000: the app is dropping sockets without a close frame (a proxy can then lose the last frame). |
| backup / keepsakes / offsite job | the unit is installed, its timer is active, and its last run succeeded (or it hasn't run yet) | "not installed" or an inactive timer: `bin/game prod root units --apply` (it installs the units and enables the timers; [root.md](root.md)), or, before the helper is installed, the operator runs `sudo ops/install-prod.sh`. A failed run: `journalctl -u daydream-<job>.service`; "no new privileges" means the units are the old ones, so the same. The offsite job also needs the R2 bucket ([backups.md](backups.md)). |

The unit tests for these checks are `tests/test_prodcheck.py`; they replay
the failures this list describes, so a check that stops catching one fails
in CI.

## By hand, when you need to see the raw answer

```sh
curl -sI https://daydream-origin.<domain>/healthz | head -1          # 403
curl -s  https://www.<domain>/daydream/edge/status                   # {"state": ...}
curl -s --http1.1 -o /dev/null -D - https://www.<domain>/daydream/ws \
  -H 'Upgrade: websocket' -H 'Connection: Upgrade' -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' | grep -i set-cookie   # nothing
```

A WebSocket probe must use HTTP/1.1: over HTTP/2 the upgrade headers are
dropped and the request takes the ordinary path. Python's default User-Agent
is refused by Cloudflare's Browser Integrity Check (error 1010), so scripted
probes set their own.
