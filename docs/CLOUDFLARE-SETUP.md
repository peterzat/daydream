# Cloudflare setup for daydream prod (one time)

The operator's hands-on steps for SPEC 2026-09-27 criteria 14 and 15. The
reasons behind each piece are in `docs/GOING-LIVE.md`.

Everything happens in the Cloudflare dashboard for the account that owns
eidolon.com, plus a few `bin/game` commands. No step opens a port on the box,
and no secret passes through a Claude Code session: you paste each token
where it is used.

The order matters: each step names what the next one needs.

## 1. An API token for daydream (routine operations)

Dashboard: My Profile > API Tokens > Create Token > Custom token.

- **Name:** `daydream-edge`
- **Permissions:**
  - Account, Workers Scripts, Edit
  - Account, Workers KV Storage, Edit
  - Zone, Workers Routes, Edit
- **Zone resources:** Include, Specific zone, `eidolon.com`
- **Optional:** Client IP address filtering, limited to the box's public
  addresses (`ip -br addr show` on the box; not written here because this
  repo is public)

This token cannot touch DNS, Access, tunnels or other zones. Save it on the
box, owner-only:

```sh
install -m 600 /dev/null ~/.config/daydream/cloudflare.env
cat >> ~/.config/daydream/cloudflare.env <<'EOF'
CLOUDFLARE_API_TOKEN=<paste>
CLOUDFLARE_ACCOUNT_ID=<dashboard > Workers & Pages > Account ID, right sidebar>
EOF
```

## 2. Zero Trust (free)

Dashboard: Zero Trust. Pick a team name if you have not already. The free
plan covers everything here; it may ask for a payment method on file.

## 3. A service token (the Worker's key to the origin)

Zero Trust > Access > Service auth > Service Tokens > Create.

- **Name:** `daydream-edge`
- **Duration:** Non-expiring. An expiring token would silently put the
  village to sleep one day.
- Copy the **Client ID** and **Client Secret**. The secret is shown once;
  you paste both in step 8.

## 4. An Access application on the origin hostname

Zero Trust > Access > Applications > Add an application > Self-hosted.

- **Application name:** `daydream origin`
- **Application domain:** `daydream-origin.eidolon.com`
- **Policy:** exactly one. Name `worker only`; Action = Service Auth;
  Include = Service Token = `daydream-edge`. No other policy, no identity
  provider.

Only the Worker can reach the origin now: a browser or scanner gets Access's
403 before anything touches the box.

## 5. The tunnel

Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared.

1. Name it `daydream`.
2. On the install page, copy the token: the long string at the end of the
   `cloudflared service install <TOKEN>` command. Do NOT run that command.
3. On the box, run the installer yourself. It prompts for the token and
   stores it root-only in `/etc/cloudflared/daydream.env`:

   ```sh
   sudo ops/install-prod.sh
   ```

   Log out and back in afterwards (the installer adds you to the
   `daydream` group).
4. Back in the dashboard, add a Public Hostname (now called "Published
   application routes"):
   - **Subdomain:** `daydream-origin`
   - **Domain:** `eidolon.com`
   - **Service:** HTTP, `127.0.0.1:54322`
   - Under Additional application settings > Access, turn on **Protect with
     Access** and choose `daydream origin`. With this on, cloudflared itself
     checks the Access token, and it fails closed if the Access app is ever
     deleted.

The dashboard creates the `daydream-origin` DNS record for you.

## 6. Cache and rate-limit rules (zone eidolon.com)

**Cache Rules** (Caching > Cache Rules > Create rule):

- **Name:** `daydream origin: never cache`
- **When:** Hostname equals `daydream-origin.eidolon.com`
- **Then:** Bypass cache

Without this, Cloudflare would cache the origin's `.png`/`.js` responses by
file extension on the Worker's behalf.

**Rate limiting** (Security > WAF > Rate limiting rules > Create; the free
plan allows one rule):

- **Name:** `daydream sign-in`
- **When:** URI Path starts with `/daydream/api/login`, OR URI Path starts
  with `/daydream/api/invite`
- **Counting characteristic:** IP
- **Threshold:** 5 requests per 10 seconds
- **Action:** Block for 10 seconds

The app has its own throttles as well (per address, per username, and a
global cap on invite guesses).

## 7. The KV namespace

```sh
bin/game edge kv-create
```

Put the printed id into `edge/wrangler.toml` (`[[kv_namespaces]] id = "..."`)
and commit it. The id is not a secret.

## 8. The Worker's secrets (the service token from step 3)

```sh
bin/game edge secrets
```

Wrangler asks for `ACCESS_CLIENT_ID`, then `ACCESS_CLIENT_SECRET`; paste each.
They are stored on the Worker only.

## 9. First deploy, asleep

```sh
bin/game edge sleep "opening soon"
bin/game edge deploy
```

Then open https://www.eidolon.com/daydream/. It should show the storybook
asleep page. That proves the Worker's route wins over the Pages site on the
same host, before anything on the box is exposed.

## 10. Check the locks

```sh
curl -sI https://daydream-origin.eidolon.com/healthz | head -1   # 403: Access refuses
curl -s  https://www.eidolon.com/daydream/edge/status             # {"state":"asleep",...}
```

## 11. Wake the village

```sh
bin/game prod deploy            # the first release
bin/game prod world reset --yes # a fresh prod village
bin/game prod prebake --from-cache ~/data/daydream/images/cache   # graded art, no renders
bin/game prod wake              # engines, tunnel, service; the edge flag -> awake
bin/game prod account create peter --admin
```

After that, `/invite <name>` in a Claude Code session.

## Later: rotating things

- **Service token:** create a new one, add it to the Access policy,
  `bin/game edge secrets`, then remove the old one.
- **API token:** roll it in the dashboard and replace the line in
  `~/.config/daydream/cloudflare.env`.
- **Tunnel token:** refresh it on the tunnel page, write it to
  `/etc/cloudflared/daydream.env` with sudo, then
  `sudo systemctl restart cloudflared-daydream`.

## Seen along the way (not part of daydream)

`www.eidolon.com/generate` accepts anonymous POSTs that spend Workers AI
neurons. On the free plan these hard-stop at the daily allowance; on a paid
plan they bill. Consider a Turnstile check or an Access policy on that route.
