# Going live: the village opens its doors (2026-09-27)

Status: designed and approved 2026-09-27; live since 2026-09-28. SPEC.md is
the contract, and where this file and the spec differ, the spec wins. This is
the durable record of *why* daydream is hosted the way it is and what
bringing it up taught us (section 11). The one-time setup is
`docs/CLOUDFLARE-SETUP.md`; the day-to-day playbooks are `docs/runbooks/`.

## 1. What we are doing

We are hosting The Village of Lost Hours for about twelve invited players, at
a path on a domain the author already serves from Cloudflare as a static Pages
site (`https://www.<domain>/daydream`). The game keeps running on the same GPU
box (an RTX 4000 SFF Ada, 20 GB), and Cloudflare fronts it.

- The box is often down, or lent to other GPU work, for days at a time. That
  is expected. When it happens, a friend who opens the page should know at
  once that the village is asleep and that a note to the Night Warden (the
  operator's title; players never see a name) will wake it.
- The admin console is a Claude Code session on the box. The web surface
  only plays.

### The shape of it: one box, one edge, one repo, one agent

- **One box.** One GPU box runs dev and prod side by side. Prod is a
  second environment, not a second machine: its own system user, releases,
  data and accounts, sharing the GPU engines with dev behind a
  cross-process lock. The runtime stays local-only (the generation policy).
- **One edge.** Cloudflare's Worker is the only always-up piece, so it owns
  the public face: it proxies to an Access-guarded tunnel while the box is
  awake, and tells friends the village is asleep (with their keepsakes)
  when it isn't. The box opens no inbound port.
- **One repo, forkable.** Everything general is committed: the engine, the
  world, `bin/game prod`, `ops/`, `edge/`, the playbooks. Everything that
  makes this instance *this* one stays local: tokens, the dashboard's
  settings, `/srv/daydream/etc/prod.env`, and the gitignored
  `instance/NOTES.md`. A fork changes the few committed instance values
  (hostnames, the operator's title) and brings its own box and Cloudflare
  account (CLAUDE.md "This repo and this instance"; a check before every
  push keeps the split honest).
- **One agent at the console.** Operations happen in a Claude Code session
  on the box: the operator asks, the agent drives `bin/game prod` and
  `bin/game edge` under a standing grant, following `docs/runbooks/` and the
  `/village` and `/invite` skills. The verbs that mint credentials or
  replace the world always ask; root-owned files and the dashboard stay with
  the human.

## 2. The finding that shaped everything

Today's auth trusts the network:
- In the default `tailscale` mode, `auth.is_authed()` returns True.
- `AccessMiddleware` admits any tailnet or loopback client.
- The world hot-swap endpoint is gated by a loopback check.

A Cloudflare tunnel connects to the app from 127.0.0.1, so tunnelling the
existing server would have published the whole game with no login, admin
endpoint included. The rule that follows:

**No network location grants privilege in prod.** Prod runs in a new `edge`
access mode:
- Every route, socket and mount requires an account session, except a short
  public allowlist.
- A test walks the registered routes, so a forgotten guard fails CI.
- A boot guard refuses to start prod in any other mode.

## 3. Architecture

```
browser ── https://www.<domain>/daydream/* ──► Cloudflare
  Worker "daydream-edge" (edge/ in this repo)
   ├─ asleep (KV flag, or origin 502/530/1033/unreachable) → the asleep page,
   │     plus the friend's own keepsakes when their session is on the synced
   │     pass list; the API gets a 503 JSON body; the WebSocket is refused
   ├─ /daydream/edge/status → {state, note, since}
   └─ otherwise strip /daydream and proxy HTTP + WebSocket to the origin
        hostname, adding the Access service token and the client IP
Tunnel hostname (Access: service token only; cloudflared validates the JWT)
  └─► 127.0.0.1:54322  daydream-prod.service (user daydream, sandboxed)
        └─► vLLM :8000 and ComfyUI :8188 (shared engines, loopback only)
```

- **No inbound ports.** cloudflared dials out; UFW is unchanged, and SSH
  stays the only public port.
- **Access on the origin hostname.** Only the Worker can reach the origin.
  cloudflared's own JWT check fails closed if the Access app is ever deleted.
- **The origin always serves at `/`.** The Worker strips the prefix, so dev
  and prod run identical code and the SPA is base-relative (`<base href>`
  from `DAYDREAM_PUBLIC_BASE`).
- **Why a Worker route.** It beats the Pages custom domain on the same host,
  and it is the only always-up piece, so it owns the asleep state.
- **Alternatives set aside:**
  - Workers VPC (private origin, no public hostname) is in beta, and its
    WebSocket support is undocumented.
  - A Durable Objects rewrite of the Python engine is out of scope.
  - A tunnel hostname without a Worker would have no asleep page.

## 4. Accounts, invites, and what "admin" means

- **Invites.** `/invite Robin Ash` mints a single-use two-word slug
  (`dewy-pleat`: 768 gentle adjectives × 1280 nouns, about 983k phrases, curated for reading aloud). It is stored
  hashed and expires in 14 days. A global cap of 40 failed redemptions a
  day keeps worst-case guessing odds under 0.2% with three invites open. The friend gets a link, picks a username and a password, and
  the account is recorded against the name the operator gave. A forgotten
  password gets a reset invite, minted the same way.
- **Accounts live in `accounts-<env>.db`, separate from the world.** A world
  reset, swap or refresh never touches them.
  - Passwords are argon2id.
  - Sessions are random tokens, stored hashed and read fresh on every
    request, so revocation takes effect immediately.
  - The cookie is scoped to `/daydream` and marked Secure, HttpOnly and
    SameSite=Lax.
- **Roles.** Every account is `player` or `admin`. Only the CLI grants
  `admin`. In the browser, admin adds exactly three things: repainting a
  room, a status drawer, and more than one toon. Everything else is the CLI:
  invites, accounts, world ops, dreams, deploys, sleep and wake. That
  command line is only reachable by SSH to the box, the strongest boundary
  there is, so a stolen admin cookie can repaint a room and read status, and
  nothing else.
- **A toon belongs to an account.** It is one per world for players. The
  five-slot picker becomes "your dreamer".

## 5. The first evening for a friend

1. A text from the operator with the `/invite` link.
2. A storybook redeem card that greets them by name. It says honestly that
   the village keeps what they do so its story can answer, and that the Night Warden
   reads summaries of it to write new chapters.
3. Username and password, then "your dreamer" (a name and a one-line
   appearance). The portrait paints in the background.
4. The How to Dream book, then the clock tower.
   - Invites are rolling: the first friend mends the great clock.
   - Everyone after gets the authored latecomer beginning, which a
     walkthrough already proves.
   - The operator's admin account stays out of the prologue, so a friend
     gets that moment.
5. **Coming back.** Straight into their toon, with "previously, in your
   dream" and any dream's while-you-slept note.

**Prod world at launch.** A fresh Lost Hours village. The art is copied from
the graded dev cache, not re-rendered: the cache key is the seed plus the
workflow hash, so the graded files are reused exactly.

**As friends join:**
- Finds, relationships and journals are per toon already.
- Arcs are shared, so a latecomer may meet an arc someone else ended, and
  dreams add new ones.
- Twelve players sit well within SQLite, three shared LLM slots and one
  render queue.
- Things to watch: the 12-room growth cap, and BACKLOG
  `shared-thread-contention`.

## 6. Asleep, and keepsakes while asleep

Planned sleep (`bin/game prod sleep --note "lent to training until Sunday"`)
and an unplanned outage (tunnel down, service down, box off) look the same to
a friend: a watercolor of the village at night, the note, how long it has
slept, and "send the Night Warden a note and the lamps will be lit". An open game tab shows the
note in its reconnect overlay and wakes by itself.

**Keepsakes (operator's choice).** A signed-in friend can still read their
own journal, Book of Stray Minutes and portrait, plus the village chronicle,
while the box is down. The design needs no signing key and no new crypto:
- When the village sleeps, and hourly while it is awake, the box pushes to
  Workers KV each account's keepsakes as render-ready JSON, and a pass list.
- The pass list is the sha256 of every live session token.
- The Worker hashes the friend's session cookie and looks it up.
- **Revocation** takes effect on the next sync.
- **Password hashes** never leave the box.
- **A device not signed in within 30 days** sees only the notice, and the
  page says so.

## 7. Prod on the box

- **A `daydream` system user** runs `daydream-prod.service`: no shell, no
  docker group. Everything runs as `peter` today, and `peter` is in the
  docker group, which is root-equivalent, so a web-facing process running as
  `peter` would turn any exploit into root. The sandbox:
  - `ProtectSystem=strict` and `ProtectHome`, with write access only to
    `/srv/daydream/data`
  - `IPAddressDeny=any` with `IPAddressAllow=localhost`, which enforces the
    generation policy ("no cloud calls at runtime") in the kernel and blocks
    exfiltration
  - `PrivateDevices`, an empty capability set, and `@system-service`
    syscalls

  The service holds no secrets: the Access service token lives only in the
  Worker, and the Cloudflare API token lives in the operator's
  `~/.config/daydream/cloudflare.env`.
- **Releases** are `git archive` snapshots under `/srv/daydream/releases/`,
  with a `current` symlink. Venvs are shared by lockfile hash. Deploys
  back up, switch atomically, health-check and roll back automatically.
- **`bin/game prod <verb>`** runs the prod release's own `bin/game` with a
  clean prod environment, as the `daydream` user. A narrow sudoers entry
  allows starting, stopping and restarting the daydream units (and starting
  the backup job), and dropping to that user; routine root work beyond that
  goes through a validated helper ([`ADMIN-ROOT.md`](ADMIN-ROOT.md)). Every existing flow (refresh, dreams, prebake,
  snapshots) therefore runs prod code against prod data. There is no
  migration skew and no dev `.env` leak.
- **Dev is unchanged** apart from accounts. It keeps its tailnet port and its
  data dir, and still has grab-the-GPU autonomy. Prod verbs that drop
  sessions or mutate state are ask-first for the agent.
- **The engines are shared.** A second environment never double-launches
  them, and a cross-process GPU lock (`/srv/daydream/data/gpu.lock`) makes
  every daydream process on the box take turns on the card; on a box without
  that lock file, GPU-heavy dev commands refuse while prod is up.
- **Backups.** Nightly online backups (14 days) on the box, and a weekly copy
  encrypted with `age` to the operator's SSH keys in a private R2 bucket (60-day
  lifecycle), so a dead box can be restored from any machine holding those keys.

## 8. Generation elsewhere, later

The runtime stays local-only. What this turn adds is a seam:
- An LLM backend profile. Workers AI speaks OpenAI-compatible chat, which
  litellm already handles.
- An image backend protocol. ComfyUI is the only implementation, and its
  cache keys are unchanged.
- A write-up, `docs/remote-reflexes.md`, of what turning Workers AI on would
  take: a generation-policy amendment, a loosened prod egress policy, and
  its own WHIMSY grading (no watercolor LoRA there).

The motivating use: keep the village awake on remote reflexes while the GPU
is lent out.

## 9. Residual risks we accept (for now)

- **The engines run as `peter`.** The prod user can reach ComfyUI's
  unauthenticated API on loopback, and ComfyUI runs as `peter`. Later fix:
  an engines user.
- **The pre-login surface is small but public** (login, invite redemption,
  static assets). It is throttled in the app and rate-limited at the edge.
- **Friends can drive shared-world verbs on shared objects.** That is the
  co-op design; the world has no griefing economy.
- **What friends type reaches the local LLM.** The existing role separation,
  length caps and banlists apply.

## 10. Where it stands (2026-09-28: live)

**Live since 2026-09-28** on the author's own domain, brought up by
following `docs/CLOUDFLARE-SETUP.md` end to end in one session. Criteria 1-8,
14, 18, 19, 21 and 23 are met. `bin/game prod check` now verifies, on
demand, everything the bring-up proved by hand:
- the Worker's route wins over the Pages site on the same host
- the origin refuses anyone without the service token (403)
- `/daydream` and the apex redirect to `https://www.<domain>/daydream/`
- the front door, a 401 for a signed-out API call, a 403 for a cross-origin
  login
- no WebSocket answer carries Access's cookie, and a session's socket
  closes cleanly
- each timer job is installed, its timer active, and its last run succeeded

The bring-up also proved that prod listens only on loopback. `prod check`
does not probe that: the service refuses to boot with any other bind
(`config.boot_problems`).

**Still to demonstrate (criteria 9-13, 15-17, 22):** a live dialogue and
portrait under the sandbox, a rollback drill, a backup restored into dev,
`prod sleep`/`wake` with keepsakes, the first friend's full flow from a
phone, and the R2 offsite bucket.

## 11. What bringing it up taught us

**Rehearsals that skip the real client miss real bugs.** The prod rehearsal
drove the whole flow through the API and passed. A real browser could not
sign in: the front door disabled its inputs before reading the form, and
FormData skips disabled inputs. Now a headless-browser test walks a friend
from an invitation to the start room in the deploy gate (it sits in the
medium tier, but CI has no browser and skips it).

**A gate that never ran is not a gate.** `prod deploy`'s test step had never
passed on the box: its worktree had no venv for the `bin/game` smoke test,
and once prod was awake the suite's blanked GPU lock made `bin/game` refuse.
Both failures were test isolation, not product bugs, and both were invisible
until the first real deploy. The fix was isolation, not a way around the gate.

**Every response path is a security path.** The Worker stripped Access's
`CF_Authorization` cookie on HTTP responses but passed WebSocket answers
through untouched, handing anonymous visitors a day-long token for the
origin. One helper now filters every path, a unit test covers the 101 and
the refusal, and `prod check` probes for the cookie live. The blast radius
was small (the token opened nothing behind the sign-in gate, and expired
within a day), which is the point of layering the gate behind the edge.

**Close sockets properly.** Dropping a WebSocket without a close frame lost
the last frame (`needs_toon`) somewhere between tunnel and browser, on the
first connection after a wake. A 1000 close makes every hop flush.

**Silent jobs fail silently.** The keepsakes and offsite timers could not
drop to the service user (`NoNewPrivileges` blocks setuid sudo), and a hand
run succeeded, so a demonstration would have passed. Job results now show in
`prod status` and `prod check`.

**Review in layers.** A security audit, fresh-eyes code reviewers per area,
and live probes each caught things the others missed. The pre-push review of
this turn found three BLOCKs after the security audit had passed, and live
probing confirmed or ruled out each claim before anything was fixed.

**The dashboard drifts; write down what you clicked.** The API token needed
Workers Tail and Zone Read beyond the plan; the box reaches Cloudflare over
IPv6 first, so an IP filter needs both addresses; `wrangler secret put`
before the first deploy creates a placeholder Worker; Cloudflare refuses
Python's default User-Agent. CLOUDFLARE-SETUP.md records the layout as
walked, and the instance record says what exists where.

**Keep the split honest before the first push.** The unpushed history
carried the box's addresses, an account id, the operator's name and a
friend's surname; they were rewritten out before anything went public. A
separation check now runs before every push.

**An agent can run production when the boundaries are explicit.** A
standing grant lets the agent drive prod in a session like this one; ask
rules keep the credential-minting and world-replacing verbs behind a prompt;
the permission layer refused an agent loosening its own rules; sudo and the
dashboard stay human. The playbooks are written for that agent, and a test
fails when they name a verb that doesn't exist.
