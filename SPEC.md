## Spec — 2026-09-27 — Going live: the village opens its doors

**Goal:** Host The Village of Lost Hours for about twelve invited friends at
`https://www.eidolon.com/daydream`. Friends get real accounts from invite
links. Prod runs sandboxed on the Hetzner box behind Cloudflare, with no
inbound port. Code, content and dreams reach prod in pinned, reversible
steps. Whenever the box is down or lent to other GPU work, friends see that
the village is asleep, and can still read their own keepsakes. Dev keeps
working exactly as it does now.

### Acceptance Criteria

- [x] **1. Prod fails closed.** With `DAYDREAM_ACCESS=edge`, no HTTP route,
  WebSocket or mount answers without a valid account session. The only
  exceptions are an explicit public allowlist: the cover, login and redeem
  pages, static assets, login, invite redemption and a health check. This
  holds for requests arriving from loopback and from tailnet addresses, and
  with spoofed forwarding or client-IP headers. A test walks the app's
  registered routes, so a newly added unguarded route fails it automatically.
  With `DAYDREAM_ENV=prod`, the server refuses to boot unless edge mode, a
  public origin, a public base path and a loopback bind are all configured.
  In edge mode the API docs routes are off and the world hot-swap endpoint
  does not exist.

- [x] **2. Accounts come from invites.**
  - `invite create --for "<name>"` prints a single-use, two-word invite link
    that expires after 14 days. Redeeming it lets the invitee choose a
    username and a password of at least 10 characters, and signs them in.
  - A used, expired, revoked or unknown slug is refused with one
    indistinguishable message. A slug stays single-use under concurrent
    redemption (tested).
  - A reset invite lets an existing account set a new password.
  - Passwords and session tokens are stored only as hashes (passwords with a
    memory-hard hash).
  - `invite list|revoke` and `account list|disable|role|sessions --revoke`
    exist. Disabling an account or revoking its sessions ends its access on
    the next request, including reconnects.
  - The shared `DAYDREAM_PASSWORD` and the signed-cookie session are gone.

- [x] **3. Guessing is throttled.** Failed logins are limited per client
  address and per username. Failed invite redemptions are capped globally per
  hour. No response distinguishes "no such user" from "wrong password" (tested).

- [x] **4. Two roles, and the shell governs.** Every account is `player` or
  `admin`, and only the CLI can change a role. The admin-only web
  capabilities are exactly three: repaint a room, read server status, and
  hold more than one toon. A player session is refused each of them. Every
  other admin operation (invites, accounts, world, dreams, deploys,
  sleep/wake) exists only in the CLI.

- [x] **5. Your dreamer is yours.** Each human toon belongs to exactly one
  account. A player account can create one toon per world and can enter, rest
  or delete only its own; it cannot claim, kick or delete another account's
  toon. Opening the game in a second tab or device takes control, and the
  earlier connection is told quietly. At least 12 player accounts can each
  hold a toon in one world. Every existing walkthrough, including the
  latecomer, passes with account-owned toons.

- [x] **6. It works under a path prefix.** The same code serves correctly at
  `/` (dev) and behind a proxy that strips `/daydream/` (prod). No page,
  script, stylesheet, WebSocket, API call, redirect or image URL resolves
  outside the configured base, including image URLs persisted in old events.
  A test fails on any root-absolute path literal in the web client.
  Cross-site POSTs and WebSockets are refused by comparing Origin to the
  configured public origin, not to Host.

- [x] **7. Sessions and transport are hardened.**
  - The session cookie is HttpOnly and SameSite=Lax, scoped to the public
    base path, Secure in prod, named per environment, and expires after 30
    days without use.
  - Responses carry a CSP plus nosniff, `frame-ancestors 'none'`, a referrer
    policy and noindex.
  - WebSocket input frames over a length cap, and commands over a
    per-session rate, are refused with no effect.
  - Generated images require a session and are marked not publicly
    cacheable.

- [x] **8. The front door.** A friend with an invite link reaches, in order:
  1. a storybook redeem card that greets them by name
  2. account creation
  3. a "your dreamer" form (name and appearance, with no browser prompt
     dialogs)
  4. the How to Dream book
  5. the start room

  A returning friend logs in and lands straight in their toon. The redeem card
  says plainly that the village keeps what players do and that the operator
  reads summaries of it. An expired or revoked session goes to the login page
  instead of looping on "the dream is sleeping". The flow endpoints are tested
  automatically; the look is one checklist item in `bin/game review`.

- [ ] **9. Prod runs sandboxed as its own user.** A one-time install script
  (the operator runs it with sudo) creates the prod layout, the service units
  and a `daydream` system user with no login shell and no docker membership.
  It also adds a sudoers entry that permits only start, stop, restart and
  status of the daydream units. The running prod service:
  - listens only on loopback
  - cannot read `/home/peter`
  - cannot open network connections except to localhost (shown by a probe
    run under the same policy)
  - holds no Cloudflare credential or signing secret
  - rates "OK" or better under `systemd-analyze security`

  A live dialogue and a portrait render work under the sandbox.

- [ ] **10. Releases are pinned and reversible.** `bin/game prod deploy <ref>`:
  - refuses a dirty tree, or a ref whose short or medium tier fails
  - builds an immutable release of that ref
  - backs up the prod world and accounts databases
  - refuses a WORLD_VERSION MAJOR mismatch
  - switches over atomically and health-checks

  A release that fails its health check is rolled back automatically and the
  previous release keeps serving (shown with a deliberately broken build).
  `prod rollback` restores the previous release. `prod status` reports the
  release against HEAD, the service, tunnel reachability, the asleep state and
  who is online. Every prod admin command runs the prod release's code with
  prod's environment, never dev's.

- [ ] **11. Dev and prod coexist.**
  - Dev keeps working on the tailnet as today (same port, same data dir), now
    with accounts.
  - Prod has its own data root, accounts, world, image cache and backups, and
    nothing in dev (including `world reset`) can delete prod data.
  - The engines are shared: starting either environment never launches a
    second vLLM or ComfyUI while one is reachable.
  - While prod is active, GPU-heavy dev commands (tier_long, prebake, review,
    model-eval, image-test) refuse to run, until criterion 21 replaces that
    guard.

- [ ] **12. Content reaches prod incrementally.** Each path works against the
  prod world:
  - authored fixes, via `prod world refresh`
  - dreams, via `prod dream digest|check|rehearse|install`
  - art, via `prod prebake --from-cache`, which copies only the graded dev
    images whose content hash matches, records them, and renders nothing
  - `prod pull`, which installs a prod backup into dev to reproduce a
    friend's bug

  Commands that must not run against a live service refuse while it is
  running.

- [ ] **13. Backups happen.** A nightly job writes consistent online-backup
  copies of the prod world and accounts databases, keeping 14 days. Restoring
  the latest one into dev is demonstrated.

- [ ] **14. The edge fronts an unexposed origin.** A Cloudflare Worker on
  `www.eidolon.com/daydream*` proxies HTTP and WebSocket traffic to the
  origin. Its source is in the repo and it is deployed by `bin/game edge
  deploy`. The origin is reachable only through a Cloudflare Tunnel whose
  hostname admits only the Worker's Access service token; a direct request
  is refused by Access. No inbound port is opened on the box: UFW is
  unchanged, and the prod port is closed on both the public and the tailnet
  address. The Worker:
  - passes the app's redirects to the browser rather than following them
  - is not reachable on `workers.dev`
  - overwrites any client-sent client-IP header
  - redirects `/daydream` and the apex host to
    `https://www.eidolon.com/daydream/`

  Unit tests cover these behaviors with mocked fetch and KV.

- [ ] **15. The village sleeps visibly.** The Worker serves the asleep state
  within 60 s whenever the operator has run `prod sleep --note "..."` or the
  origin is unreachable (tunnel down, service down or box off):
  - `www.eidolon.com/daydream/` shows a storybook asleep page with the note
    (or a default), how long the village has slept, and an instruction to
    text Peter.
  - API calls get a 503 JSON body, and WebSockets are refused.
  - An open game tab shows the note in its overlay and reconnects by itself
    on wake.
  - A 503 from the app itself is not mistaken for sleep.

  `prod sleep` rests connected players (their journals are written) and frees
  the GPU. `prod wake` brings the engines and service up and clears the
  notice. `prod drill` exercises service down, tunnel down, planned sleep and
  a bad service token, then restores.

- [ ] **16. Keepsakes while asleep.** While the village is asleep, a friend
  whose browser holds a session from the last 30 days that was synced before
  sleep sees their own journal, Book of Stray Minutes and portrait, plus the
  village chronicle, under the notice. They never see anyone else's.
  - A revoked or disabled account's keepsakes and access disappear at the
    next sync.
  - Password hashes never leave the box.
  - Sync runs at sleep, and at least hourly while awake.

  (May land after the first friends are invited.)

- [ ] **17. Launch.**
  - The prod world is a fresh Lost Hours village, and the operator has an
    admin account in it.
  - At least one friend was invited with `/invite`, and that friend's account
    and toon exist in prod.
  - From a phone on a cellular network, invite → account → dreamer → talk →
    portrait → leave → journal completes through
    `www.eidolon.com/daydream/`.
  - An idle WebSocket survives 5 minutes.
  - Ten rapid logins from one address are rate-limited at the edge.

- [x] **18. Operator skills.**
  - `/invite <name>` produces the link, its expiry and a message ready to
    paste, and records who it is for.
  - `/village status|wake|sleep "<note>"|deploy [ref]` wraps the prod verbs.
  - The project's agent permissions pre-allow only the read-only prod verbs
    and `prod invite`. Prod commands that drop sessions or mutate state still
    ask first.

- [x] **19. vLLM listens only on loopback.** After `bin/game vllm-up`, no vLLM
  process has a listening socket on a non-loopback address (checked with
  `ss`), and a tier_short test pins the launch setting that ensures it.

- [x] **20. The docs tell the truth.**
  - SECURITY.md is rewritten for internet exposure: threat model, trust
    boundaries, and residual risks, including engines that run as peter.
  - CLAUDE.md documents prod and dev, the CLI as admin console, "no network
    location grants privilege", and the prod agent policy.
  - `docs/GOING-LIVE.md` records the design.
  - `docs/CLOUDFLARE-SETUP.md` lists the operator's one-time steps.
  - The GEX44 README records the exposure design and the vLLM finding; this
    edit stays uncommitted, for the operator.

- [x] **21. The GPU is safe across processes.** An image render in one
  daydream process never overlaps an LLM call or render in another. A
  two-process test shows it, and a cancelled waiter never leaves the lock
  held. This replaces criterion 11's prod-active guard. (May land after the
  first friends.)

- [ ] **22. Backups leave the box.** A weekly encrypted copy of the prod
  backups lands in a private Cloudflare R2 bucket, and a restore from it is
  demonstrated. (May land after the first friends.)

- [x] **23. A seam for remote reflexes.** Choosing the LLM backend or the
  image backend is configuration. The local default changes no image cache
  key and no existing test, and the GPU arbiter gates only local backends.
  `docs/remote-reflexes.md` records the Cloudflare Workers AI path and the
  generation-policy amendment that enabling it would require. The shipped
  runtime stays local-only, and `tests/test_no_cloud_keys.py` stays green.
  (May land after the first friends.)

### Context

**Adopted from the approved plan** `~/.claude/plans/i-want-to-host-idempotent-hoare.md`.
It is the design narrative: architecture diagram, the reasoning behind each
choice, the Cloudflare setup, and the verification drill. `docs/GOING-LIVE.md`
becomes its durable, in-repo record.

**Operator decisions (2026-09-27):**
- Sign-in is an invite link plus a username and password. A `/invite` skill
  mints two-word slugs such as `amber-thimble`.
- While asleep, friends see a notice, and signed-in friends can also read
  their own keepsakes from Cloudflare.
- Invites are rolling. The first friend mends the clock (the `mended`
  ending) and later friends take the walkthrough-proven latecomer path, so
  the operator's admin account should not mend the clock in prod.
- Prod runs as a sandboxed `daydream` system user, with a narrow sudoers
  rule.
- Build in auto mode.

**The critical finding that shapes criterion 1.** In today's default
`tailscale` mode, `auth.is_authed()` returns True and `AccessMiddleware`
admits loopback. `/api/world/swap` is gated only by a loopback check. A
Cloudflare tunnel connects from 127.0.0.1, so tunnelling the current server
would expose everything. "No network location grants privilege in prod" is
the rule.

**Operator's hands (Claude cannot sudo; secrets never pass through Claude):**
- `sudo ops/install-prod.sh`, then log out and back in for group membership.
  The tunnel token is typed into the script's prompt directly.
- Cloudflare dashboard: the Zero Trust team, a non-expiring service token,
  the Access app on the origin hostname, the tunnel and its public hostname
  with "Protect with Access", a cache-bypass rule for the origin host, one
  WAF rate-limit rule, and an API token for Workers Scripts, KV and eidolon.com
  routes saved to `~/.config/daydream/cloudflare.env`.
- `wrangler secret put` for the service token.
- The first `/invite` and the phone check.

**Constraints:**
- **Generation policy unchanged.** The runtime calls only local engines, and
  prod's sandbox enforces that in the kernel. Criterion 23 builds a seam
  only; turning on a remote backend is a separate policy change.
- **Other repos.** The only allowed action outside this repo is editing
  `~/src/GEX44-security-audit/README.md` (no commit). zat.env is not touched.
  Report other cross-repo findings; don't act on them.
- **Agent policy.** Dev keeps its grab-the-GPU autonomy. Prod verbs that drop
  sessions or mutate state are ask-first. Never push, tag or release without
  asking. `APP_VERSION` may move to 1.1.0 at go-live, bumped together with
  `pyproject.toml`. The new accounts database and migration 018 are additive,
  so `WORLD_VERSION` does not change.
- **Test discipline (zat.env practices).** Work in small increments, with
  tests in the same increment, and the medium tier green at every commit.
  About 25 test files log in through the shared password today; moving them
  to one authed-client fixture is a deliberate contract change, named in its
  commit message, with behavioral assertions unchanged. Never loosen a test
  to hide a regression. After two failed fix attempts, revert and rethink.
- **Engine purity.** `tests/test_no_world_literals.py` scans `daydream/**`
  and `web/assets/**`. The invite wordlist and front-door copy must avoid
  Lost Hours proper nouns in engine files. The redeem card's in-world
  greeting belongs in world data or edge assets.

**Code pointers (from the research pass):**
- **Auth and access:**
  - `daydream/api/auth.py` holds the shared password and `is_authed`.
  - `daydream/api/access.py` is the tailscale/public middleware.
  - `daydream/api/csrf.py` compares Origin to Host.
  - `daydream/api/world.py` has the loopback-gated swap.
  - `daydream/server.py` has `SessionMiddleware`, and
    `config.session_secret()` writes under `~/.config` at import, which
    crashes under `ProtectHome`.
- **URLs and routes:**
  - `/status/*` and `/cache/*` have no session check.
  - `daydream/images/cache.py` `cache_url`/`versioned_url_for_path` URLs are
    persisted in event payloads.
  - Root-absolute paths appear in `web/index.html`, `web/assets/main.js`
    and `web/assets/style.css`.
- **Toons and sessions:**
  - `toons.HUMAN_SLOT_RANGE = range(1, 6)`.
  - `daydream/play.py` logs in over HTTP.
  - `daydream/admin.py` snapshot is checkpoint plus copyfile, which is not
    safe while prod writes; `dream.py` already uses `sqlite3.backup`.
- **bin/game:**
  - It sources the dev `.env` before dispatching; prod must re-exec with a
    clean environment.
  - Engine PID files are per-environment under `/run/user/1000`, which
    vanishes at logout, so a second environment double-launches engines.
- **Edge and proxy gotchas:**
  - The Worker must fetch with `redirect: "manual"` and set
    `workers_dev = false`.
  - Cloudflare would otherwise cache origin `.png`/`.js` after Access.
  - uvicorn trusts `X-Forwarded-For` from 127.0.0.1 unless started with
    `--no-proxy-headers`.
  - A pre-accept WebSocket refusal reads as 1006 in the browser.
  - Asleep means 502, 530/1033 or a thrown fetch; a plain 503 is the app's
    own.
  - Idle sockets need a client ping (about 25 s).
- **systemd:**
  - Skip `MemoryDenyWriteExecute`, `PrivateUsers` and `PrivateNetwork`.
  - `IPAddressAllow=localhost` still permits DNS through 127.0.0.53.
  - Data dir sharing between peter and the service user needs setgid plus
    default ACLs.
  - `tempfile` creates 0600 files.
- **Residual risk to record, not fix now.** The service user can reach
  ComfyUI's unauthenticated API on loopback, and ComfyUI runs as peter, who
  is in the docker group. The later fix is an engines user.
- **Side findings to report:**
  - `www.eidolon.com/generate` accepts unauthenticated POSTs that spend
    Workers AI.
  - The GEX44 README has stale facts (root is on md2, the driver version).

**BACKLOG entries this turn touches:**
- `multi-env-layout`: prod lands; a preview env does not.
- `multi-user-shared-world`: its nightly-snapshot line, via criterion 13.
- `litellm-proxy-fallbacks`: the seam, with no proxy.
- `staging-probes` and `prod-verify-probes`: the prod verify sweep.
- `shared-thread-contention`: watch it as 12 friends arrive.

Annotate or close them at turn end.

**The prior turn's criterion 22** (the operator plays the morning after the
first dream) remains open. It is operator-paced and does not gate this turn.

---
*Prior spec (2026-09-26): The Village of Lost Hours, the pivot turn. Closed
21/22; criterion 22 (the operator playtest) stays open, operator-paced.*

<!-- SPEC_META: {"date":"2026-09-27","title":"Going live: the village opens its doors","criteria_total":23,"criteria_met":13} -->
