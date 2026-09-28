# Hosting the village: one-time setup

How to put daydream on the internet the way this repo's own instance runs, at
`https://www.eidolon.com/daydream`, behind a Cloudflare Worker and an
Access-guarded tunnel, with no inbound port on the box. The reasons behind each
piece are in [`GOING-LIVE.md`](GOING-LIVE.md); the day-to-day verbs are in
`CLAUDE.md` ("Prod").

These steps were last walked end to end on 2026-09-27/28, in the Cloudflare
dashboard's layout of that date. Menu names drift; where a name has changed,
the older one is given too.

## What you need

**Required**

- **The dev setup working first**: a Linux box (Ubuntu 22.04 here) with an
  NVIDIA GPU of about 20 GB (an RTX 4000 SFF Ada here), sudo, the repo's venv,
  both engines bootstrapped (`bin/vllm-bootstrap`, `bin/comfyui-bootstrap`),
  `bin/game test medium` passing, and the village's art painted and graded in
  the dev cache (`bin/game prebake`). See the README's "Running it".
- **Node.js 20 or newer** on the box, for wrangler (pinned in
  `edge/package.json`; `bin/game edge` runs `npm ci` itself).
- **A Cloudflare account with a domain whose DNS is on Cloudflare.** The free
  plan covers everything below except R2, which needs a payment method on
  file even within its free tier. Services used: Workers and Workers KV
  (free), Zero Trust (Free plan; daydream uses no seats), Cloudflare Tunnel
  (free), R2 (free tier, for offsite backups).
- **About an hour** the first time, most of it in the dashboard.

**Installed for you** by `ops/install-prod.sh`: `cloudflared` (from
Cloudflare's apt repo), `age` (offsite backup encryption), `acl`.

**For a fork, change these first** (they are this instance's values):

| File | Values |
|---|---|
| `edge/wrangler.toml` | the two `routes`, `ORIGIN`, `PUBLIC_HOST`, `OPERATOR`; `[[kv_namespaces]] id` comes from step 8 |
| `ops/prod.env.example` | `DAYDREAM_PUBLIC_ORIGIN`, `DAYDREAM_OPERATOR_NAME` |
| these steps | `eidolon.com`, `www.eidolon.com/daydream`, `daydream-origin.eidolon.com` |

`OPERATOR` / `DAYDREAM_OPERATOR_NAME` is how players see whoever runs the
village ("Send the Night Warden a note and the lamps will be lit"). This
instance uses a title, not a name. Unset, both fall back to "the person who
invited you".

## Where the secrets end up

No secret is committed, and the prod service holds none.

| Secret | Lives in | Set in step |
|---|---|---|
| Cloudflare API token + account id | `~/.config/daydream/cloudflare.env` (your user, 0600) | 1 |
| Access service token (client id + secret) | Worker secrets only | 9 |
| Tunnel token | `/etc/cloudflared/daydream.env` (root, 0600) | 7 |

Keep your own record of what you create (names, ids, rules) outside the repo.
This instance keeps it in the gitignored `instance/NOTES.md`.

## 1. An API token for daydream

My Profile > API Tokens > Create Token > Custom token (Get started).

- **Name:** `daydream-edge`
- **Permissions:**

  | Scope | Permission | Level | Used by |
  |---|---|---|---|
  | Account | Workers Scripts | Edit | `edge deploy`, `edge secrets` |
  | Account | Workers KV Storage | Edit | `edge sleep`/`wake`, keepsakes sync |
  | Account | Workers R2 Storage | Edit | offsite backups |
  | Account | Workers Tail | Read | `edge tail` |
  | Zone | Workers Routes | Edit | the Worker's routes |
  | Zone | Zone | Read | wrangler looks the zone up by name |

- **Account resources:** your account. **Zone resources:** Include, Specific
  zone, your domain.
- **Client IP address filtering** (recommended): Is in, the box's public
  addresses from `ip -br addr show`. List the IPv6 address as well as the
  IPv4 one: a box with both usually reaches Cloudflare over IPv6.
- **TTL:** none.

This token cannot touch DNS, Access, tunnels or other zones. Save it on the
box with an editor (a heredoc would land the token in your shell history):

```sh
install -m 600 /dev/null ~/.config/daydream/cloudflare.env
$EDITOR ~/.config/daydream/cloudflare.env
```

```
CLOUDFLARE_API_TOKEN=<the token>
CLOUDFLARE_ACCOUNT_ID=<32 hex characters: the zone's Overview page, API section>
```

Check it: `bin/game edge status` should print `edge flag: not configured`
(no KV id yet) rather than an authentication error.

## 2. Zero Trust

Account home > Zero Trust > Get started. Accept or pick a team name (it can
appear in Access URLs, so keep it neutral) and choose the **Free** plan. It may
ask for a payment method. Skip every guided setup it offers (WARP, DNS
filtering, device enrollment, identity providers): daydream uses none of them,
and an identity provider would give people a way to sign in to the origin.

## 3. A service token (the Worker's key to the origin)

Access controls > Service credentials > Service Tokens > Create Service Token
(older layouts: Access > Service auth).

- **Name:** `daydream-edge`
- **Duration:** Non-expiring. An expiring token would silently put the
  village to sleep one day.

Copy the **Client ID** and **Client Secret** (the secret is shown once) for
step 9.

Access can also clean up inactive service tokens: the "Automatically clean up
inactive service tokens" switch under Access controls > Access settings. It is
off by default, and a token referenced directly by a policy (step 4) is exempt
even when it is on. That matters here: while the village sleeps, the Worker
never uses the token.

## 4. An Access application on the origin hostname

Access controls > Applications > Add an application > **Self-hosted and
private**.

- **Destination:** a public hostname, `daydream-origin` . your domain, empty
  path. It need not exist in DNS yet; step 5 creates the record.
- **Access policies:** create exactly one:
  - **Name:** `worker only`
  - **Action:** Service Auth (not Allow)
  - **Include:** Service Token, `daydream-edge`, chosen by name (not "Any
    Access Service Token", not a rule group: only a direct reference is
    exempt from the inactivity cleanup)
  - Nothing under Require or Exclude; session duration as the application
- **Authentication:** leave as is. No policy admits a person.
- **Name:** any label (the dashboard suggests `daydream-origin`).

The preview should read Sources: Services, Policies: worker only,
Destinations: `daydream-origin.<your domain>`.

## 5. The tunnel and its route

Networks > Tunnels (or Tunnels & Mesh) > Create a tunnel > Cloudflared.

1. Name it `daydream`.
2. On "Install and run connectors", copy the token: the `eyJ...` string after
   `service install`. **Do not run any command on that page**: the installer
   (step 7) stores the token root-only and runs cloudflared in its own
   sandboxed unit.
3. Next, to **Route tunnel**, tab **Published applications** (older layouts:
   Public hostname):
   - **Hostname:** `daydream-origin`, **Domain:** yours, **Path:** empty
   - **Service:** HTTP, `127.0.0.1:54322`
   - **Enforce Access JSON Web Token (JWT) validation:** On, application
     `daydream-origin` (older layouts: "Protect with Access"). cloudflared
     then checks the Access token itself, so the origin stays shut even if
     the Access application is ever deleted.
4. Save. The dashboard creates the DNS record. The tunnel list may show `--`
   under Routes for a while.

Check from anywhere: `curl -sI https://daydream-origin.<domain>/healthz`
returns 403 (Access refuses). With the service token's two headers
(`CF-Access-Client-Id`, `CF-Access-Client-Secret`) it returns 530 / error 1033
until the box connects.

## 6. Cache and rate-limit rules (your zone)

**Cache rule** (Caching > Cache Rules > Create rule):

- **Name:** `daydream origin: never cache`
- **Custom filter expression:** Hostname equals `daydream-origin.<domain>`
- **Cache eligibility:** Bypass cache

The Worker fetches the origin through your zone; without this, Cloudflare
would cache `.png`/`.js` responses by extension on its behalf.

**Rate limiting rule** (Security > Security rules > Rate limiting rules >
Create rule; older layouts: Security > WAF). The free plan allows one.

- **Name:** `daydream sign-in`
- **Expression** (Edit expression):
  ```
  (starts_with(http.request.uri.path, "/daydream/api/login")) or (starts_with(http.request.uri.path, "/daydream/api/invite"))
  ```
- **Characteristics:** IP. **Rate:** 5 requests per 10 seconds.
  **Action:** Block for 10 seconds. **Status:** Active.

These cover the only routes an anonymous visitor can POST to (login, invite
peek, invite redeem). The app throttles them as well: per address, per
username, and a global cap on invite guesses.

## 7. The box

Run the installer yourself (it asks for your sudo password, then the tunnel
token from step 5 at a hidden prompt):

```sh
sudo ops/install-prod.sh
```

It creates the `daydream` system user and `/srv/daydream`, installs
cloudflared, age and acl, the systemd units, three timers (nightly backup,
hourly keepsakes sync, weekly offsite) and a narrow sudoers entry, and adds you
to the `daydream` and `systemd-journal` groups. It opens no port, starts
nothing, and enables nothing at boot except the timers. Until the first
release exists (step 11), the hourly keepsakes timer logs a harmless failure.

Then **log out completely and back in** (a new SSH login) so the new groups
apply. A Claude Code session started before the install lacks them too: quit
it and resume with `claude --continue` from the new login. Without the
`daydream` group, the prod commands cannot read `/srv/daydream/etc/prod.env`.

Optional proof that the tunnel token works, before anything listens on the
prod port: `sudo systemctl start cloudflared-daydream`, then the step 5 curl
with the service token returns 502 (cloudflared answered, nothing behind it);
`sudo systemctl stop cloudflared-daydream`.

## 8. The KV namespace

```sh
bin/game edge kv-create
```

Put the printed id in `edge/wrangler.toml` (`[[kv_namespaces]] id = "..."`)
and commit it. It is not a secret.

## 9. First Worker deploy, asleep, then its secrets

Deploy the Worker **before** setting its secrets: `wrangler secret put` on a
Worker that doesn't exist yet creates a placeholder Worker. The flag goes to
asleep first, so the new Worker serves the asleep page and never calls the
origin while it has no secrets.

```sh
bin/game edge sleep "opening soon"
bin/game edge deploy        # runs the Worker's unit tests, then wrangler deploy
bin/game edge secrets       # paste ACCESS_CLIENT_ID, then ACCESS_CLIENT_SECRET (step 3)
```

Open `https://www.<domain>/daydream/`: the storybook asleep page with "opening
soon". That proves the Worker's route beats a Pages site on the same host
before anything on the box is exposed. `bin/game edge status` shows the flag
and what the public URL answers.

## 10. Check the locks

```sh
curl -sI https://daydream-origin.<domain>/healthz | head -1   # 403: Access refuses
curl -s  https://www.<domain>/daydream/edge/status             # {"state":"asleep",...}
curl -sI https://<domain>/daydream/ | grep -i location         # 301 to https://www.<domain>/daydream/
```

## 11. First release, and wake

```sh
bin/game prod deploy          # short + medium tiers at HEAD in a throwaway worktree, build, preflight, switch
bin/game prod world reset --yes                                   # a fresh village
bin/game prod prebake --from-cache ~/data/daydream/images/cache   # the graded dev art; renders nothing
bin/game prod wake            # engines (if down), tunnel, service; the edge flag -> awake
bin/game prod status
```

`prod deploy` refuses a dirty tree; commit first. Check the live site:
`https://www.<domain>/daydream/` shows the front door, `.../api/me` answers
401, and the origin's responses carry `cf-cache-status: DYNAMIC` (the cache
rule). The WebSocket path is proven by the first real play.

## 12. Invite yourself

In a Claude Code session: `/invite <your name>` (or
`bin/game prod invite create --for "<name>"`). Open the link on your phone or
laptop over the public internet, choose a username and password, make a
dreamer, and play: look around, talk to a resident, then leave (which writes
your journal). This is the same path every friend takes. The CLI has its own
admin account already; promote yours only if you want the browser extras
(`bin/game prod account role <username> admin`).

**Leave the great clock alone.** Mending it is the prologue, and the first
friend should get that moment. If you mend it while testing, run
`bin/game prod world reset --yes` before inviting anyone (accounts survive a
reset; toons and world progress do not).

## 13. Offsite backups (can wait)

Enable R2 for the account (a payment method on file; 10 GB free), then create
the bucket with the token loaded (a bare `npx wrangler` would try a browser
login):

```sh
(set -a; . ~/.config/daydream/cloudflare.env; cd edge && npx wrangler r2 bucket create daydream-backups)
```

In the dashboard, R2 > daydream-backups > Settings > Object lifecycle rules:
delete objects older than 60 days. The bucket stays private (no public
access, no custom domain). Backups are encrypted with `age` to the SSH keys in
`~/.ssh/authorized_keys` plus the box's own key before they leave, so R2 only
ever holds ciphertext. Prove the round trip once:

```sh
bin/game prod offsite
bin/game prod offsite-restore prod-<stamp>.tar.gz.age /tmp/daydream-restore-check
```

## Later: rotating things

- **Service token:** create a new one, add it to the `worker only` policy,
  `bin/game edge secrets`, then remove the old one.
- **API token:** roll it in the dashboard and replace the line in
  `~/.config/daydream/cloudflare.env`.
- **Tunnel token:** refresh it on the tunnel page, write it to
  `/etc/cloudflared/daydream.env` with sudo, then
  `sudo systemctl restart cloudflared-daydream`.
