# The edge: Worker, flag, secrets, tokens

The Cloudflare side of the village. Credentials: the operator's
`~/.config/daydream/cloudflare.env` (API token + account id, 0600); the
Access service token lives only as the Worker's secrets.

```sh
bin/game edge status     # the flag in KV, and the public answer
bin/game edge test       # the Worker's unit tests (node)
bin/game edge deploy     # tests, then wrangler deploy of edge/
bin/game edge tail       # live Worker logs (needs the token's Workers Tail read)
bin/game edge sleep "<note>" | wake    # the flag only
bin/game edge secrets    # set ACCESS_CLIENT_ID / ACCESS_CLIENT_SECRET (typed or piped)
```

## Deploy a Worker change

Change `edge/src/` or `edge/public/`, run `bin/game edge test`, commit, then
`bin/game edge deploy` and `bin/game prod check`. A Worker change takes
effect worldwide within seconds; there is no rollback verb, so a bad Worker
is fixed forward (or `git checkout <good> -- edge && bin/game edge deploy`).

Every response the Worker returns, including a WebSocket's 101 and any
refusal of an upgrade, must pass through `stripAccessCookies`: Access sets a
`CF_Authorization` cookie on the origin's answers, and a browser that gets it
holds a token for the origin (the 2026-09-28 BLOCK). `prod check` probes for
it every run.

## Rotate a credential

- **Service token** (Access): create a new one in the dashboard, add it to
  the `worker only` policy (a direct reference, which also exempts it from
  inactivity cleanup), `bin/game edge secrets` with the new values, `prod
  check`, then delete the old token.
- **API token**: roll it in the dashboard (keep the same permissions and IP
  filter; the box reaches Cloudflare over IPv6 first), replace the line in
  `~/.config/daydream/cloudflare.env`, then `bin/game edge status`.
- **Tunnel token**: refresh it on the tunnel's page, write it to
  `/etc/cloudflared/daydream.env` with sudo (the operator), then
  `sudo systemctl restart cloudflared-daydream`.

## Things that surprised us

- Cloudflare's Browser Integrity Check refuses Python's default User-Agent
  (error 1010): scripted requests to the public site set their own.
- A WebSocket upgrade must be probed over HTTP/1.1.
- `wrangler secret put` on a Worker that doesn't exist yet creates a
  placeholder Worker: deploy first, then set secrets.
- Dashboard menu names drift; `docs/CLOUDFLARE-SETUP.md` records the layout
  as of its last walk-through.
