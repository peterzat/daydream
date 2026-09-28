# Going live: the village opens its doors (2026-09-27)

Status: design approved by the operator on 2026-09-27. Building is in
progress; SPEC.md is the contract, and where this file and the spec differ,
the spec wins. This is the durable record of *why* daydream is hosted the way
it is. The operator's one-time steps are in `docs/CLOUDFLARE-SETUP.md`, and
the day-to-day verbs are in CLAUDE.md.

## 1. What we are doing

We are hosting The Village of Lost Hours for about twelve invited friends at
`https://www.eidolon.com/daydream`. The game keeps running on the Hetzner
GEX44 (RTX 4000, 20 GB). Cloudflare, which already serves eidolon.com as a
static Pages site, fronts it.

- The box is often down, or lent to other GPU work, for days at a time. That
  is expected. When it happens, a friend who opens the page should know at
  once that the village is asleep and that a note to the Night Warden (the
  operator's title; players never see a name) will wake it.
- The admin console is a Claude Code session on the box. The web surface
  only plays.

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
browser ── https://www.eidolon.com/daydream/* ──► Cloudflare
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
- **Accounts live in `accounts.db`, separate from the world.** A world
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
  allows exactly two things: starting and stopping the daydream units, and
  dropping to that user. Every existing flow (refresh, dreams, prebake,
  snapshots) therefore runs prod code against prod data. There is no
  migration skew and no dev `.env` leak.
- **Dev is unchanged** apart from accounts. It keeps its tailnet port and its
  data dir, and still has grab-the-GPU autonomy. Prod verbs that drop
  sessions or mutate state are ask-first for the agent.
- **The engines are shared.** A second environment never double-launches
  them. Until a cross-process GPU lock lands, GPU-heavy dev commands refuse
  while prod is up.
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

**Live since 2026-09-28** at www.eidolon.com/daydream, following
`docs/CLOUDFLARE-SETUP.md` end to end in one session. Criteria 1-8, 14, 18,
19, 21 and 23 are met. Verified on the real edge:
- the Worker's route wins over the Pages site on the same host (the asleep
  page showed there before anything on the box was exposed)
- the origin refuses a request without the service token, or with a wrong
  one (403); `cf-cache-status: DYNAMIC` shows the never-cache rule
- `/daydream` and the apex redirect to `https://www.eidolon.com/daydream/`;
  workers.dev and preview URLs are off; prod listens only on loopback
- the front door, a 401 for a signed-out API call, a 403 for a cross-origin
  login
- a WebSocket through Worker, Access and tunnel (`needs_toon`, then a clean
  close)

**Found and fixed during the bring-up:**
- `prod deploy`'s test gate could never pass on a real box: its worktree had
  no `.venv` for the `bin/game` smoke test, and with prod awake the suite's
  blanked GPU lock made `bin/game` refuse `image-test`. The worktree now
  borrows the dev venv, and the smoke test ignores an awake prod.
- The app dropped the socket right after `needs_toon` without a close frame;
  through the tunnel that last frame was lost on the first connection after
  a wake. It now closes with 1000.
- `bin/game edge status` read the public edge as down: Cloudflare's Browser
  Integrity Check refuses Python's default User-Agent.
- The setup runbook gained what the real dashboard needed: two token
  permissions (Workers Tail Read, Zone Read), the IPv6 address in the token's
  IP filter, deploying the Worker before its secrets, the JWT-validation
  switch on the tunnel route, and the R2 command with the token loaded.

**Still to demonstrate (criteria 9-13, 15-17, 22):** a live dialogue and
portrait under the sandbox, a rollback drill, a backup restored into dev,
`prod sleep`/`wake` with keepsakes, the first friend's full flow from a
phone, and the R2 offsite bucket. This instance's own record of what exists
where is the gitignored `instance/NOTES.md`.
