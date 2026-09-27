# SECURITY.md

## Security Review — 2026-09-27 (scope: full)

**Summary:** Full audit at HEAD `5557e2d`, rewritten for internet exposure and weighted toward the going-live surface (accounts, invites and sessions, the sign-in gate and edge mode, toon ownership, prod operations and the sandbox, the Cloudflare Worker). The web boundary holds and nothing is a BLOCK; the gaps are behind it: operator tooling that follows paths the sandboxed service can plant, revocation that misses open sockets, an uncapped command frame, a global invite cap anyone can spend, a wider-than-documented admin, and a real-looking name in the tree (0 BLOCK / 6 WARN / 9 NOTE).

### Scope and method

Read in full: `daydream/accounts.py`, `accounts_cli.py`, `api/{auth,gate,access,csrf,headers,nocache,slots,ws,rooms,world}.py`, `server.py`, `config.py`, `prodctl.py`, `edge.py`, `keepsakes.py`, `announce.py`, `toons.py`, `events.py`, `inputs.py`, the new parts of `admin.py`, `play.py`, `prebake.py`, `gpu/arbiter.py`, `images/client.py`, `llm/client.py`, `bin/game`, `ops/` (installer, units, sudoers, lock, prod.env), `edge/` (Worker, wrangler.toml, asleep page), `web/door.html`, `web/assets/door.js`, the new and changed parts of `web/assets/main.js` and `web/index.html`, migrations 018 and `migrations_accounts/001`, `.claude/settings.json` and the two operator skills, the CI workflow, `docs/GOING-LIVE.md` and `docs/CLOUDFLARE-SETUP.md`. Engine modules unchanged since the 2026-09-27 paths review were re-scanned for dangerous sinks (SQL, subprocess, deserialization, templates, DOM) and their earlier findings re-verified, not re-traced line by line. Git history was scanned for credential patterns. Four candidates were reproduced against throwaway data (no real data, no network): the revocation gap, the command-frame cap, the invite cap, and the keepsakes symlink path. One pre-auth memory figure was measured locally.

### Threat model

**Assets.**
- Accounts and sessions (`accounts-prod.db`: argon2id password hashes, sha256 of session tokens, invite hashes).
- Friends' private play: every typed line (`inputs`), journals, the Book of Stray Minutes, relationships, while-you-slept notes, toons.
- The operator's credentials on the box: the Cloudflare API token (`~/.config/daydream/cloudflare.env`: Workers Scripts, KV, Routes and R2 edit) and whatever other keys and tokens live in `/home/peter`. `peter` is in the docker group, so peter is root-equivalent.
- The edge: the Worker and its Access service token (a Worker secret), KV (state flag, keepsakes, session pass list), the tunnel token (root-only, `/etc/cloudflared`).
- Availability of the village and the GPU for about twelve friends.

**Actors.**
- Anonymous internet clients. They reach only the Worker, and through it the public allowlist (door, login, logout, invite peek and redeem, health, static assets) plus the Worker's own `/edge/status` and `/_edge/*`.
- Invited friends, and anyone holding a friend's session (a reused password, a shared device). Signed-in players drive the shared world, type free text that reaches the local model, send command frames, and own one toon.
- An admin session: the operator's browser, and the CLI's cached `cli-operator` tokens.
- Code running as the `daydream` service user after an application or dependency compromise. This is the case the sandbox exists for.
- Local processes on the box: the dev server and both engines run as `peter`.
- The in-session Claude Code agent, which reads player-authored text (digests, `bin/game play` output, toon names in `prod status`) and holds some pre-allowed prod verbs.

### Trust boundaries

1. **Internet to the edge.** Cloudflare terminates TLS; the Worker route `www.eidolon.com/daydream*` strips the prefix, overwrites `X-Daydream-Client-IP` from `CF-Connecting-IP`, drops client `x-daydream-*` and `cf-access-*` headers, adds the Access service token, never follows origin redirects, and serves the asleep page. One WAF rule rate-limits the login and invite paths.
2. **Worker to origin.** The origin hostname is public but guarded by Cloudflare Access with a single Service Auth policy; cloudflared validates the Access JWT. No inbound port is open; SSH stays the only public port.
3. **cloudflared to the service.** `daydream-prod.service` listens on `127.0.0.1:54322` with `--no-proxy-headers`. Edge mode admits loopback peers only, as a transport rule, never a privilege. Anything local reaches this port without Access, and then chooses its own client-IP header.
4. **Request to account.** `GateMiddleware` requires a session for every route, socket and mount outside the allowlist; sessions are re-read per HTTP request; CSRF and the WS handshake compare Origin to `DAYDREAM_PUBLIC_ORIGIN`; roles are `player` and `admin`, changed only in the CLI.
5. **Player to world.** Toon ownership per account; the closed verb set and per-verb effect allowlists; LLM prompts with role separation and caps; model output validated and banlist-scanned before any mutation.
6. **Service to operator (the sandbox).** Own user, no shell, no docker group, `ProtectHome`, `ProtectSystem=strict`, writes only to `/srv/daydream/data`, loopback-only IP egress, no capabilities, no secrets. What still crosses: the shared data dir that operator tooling reads and writes (WARN 1), the engines' unauthenticated loopback APIs (accepted risk), DNS through the local resolver, AF_UNIX sockets, and the shared `gpu.lock`.
7. **Operator to edge.** The Cloudflare token in peter's home, used by the hourly keepsakes sync, the weekly offsite backup and edge deploys. KV holds keepsakes and a list of session-token hashes.
8. **Players to the agent.** Player text reaches the agent as data: digests render it quoted under an untrusted banner, and `docs/playtests/BRIEF.md` says the same for play output.
9. **The browser origin.** `https://www.eidolon.com` is shared with the eidolon.com Pages site and any other Worker on that host (NOTE 1).

Dev keeps its own boundary: tailnet-only (`tailscale` mode plus UFW), the same account model, a separate data dir under `~/data/daydream`.

### Findings

[WARN] daydream/keepsakes.py:69-77, 100-103, daydream/edge.py:177-190, ops/systemd/daydream-keepsakes.service — operator tooling follows paths inside the service-writable data dir, so code running as the sandboxed `daydream` user can make the operator's hourly keepsakes job read any file the operator can read and publish it on the edge.
  Attack vector: an attacker with code execution as the `daydream` user replaces its own toon's portrait cache file under `/srv/daydream/data/images/cache/<world>/toon/<toon>/` with a symlink to, for example, `/home/peter/.config/daydream/cloudflare.env`. Within the hour, `daydream-keepsakes.timer` runs `bin/game prod keepsakes` as the operator with no filesystem sandbox (the unit sets only `NoNewPrivileges` and `PrivateTmp`). `_portrait_path` accepts the path because `exists()` follows the link, `shutil.copyfile` copies the target, `desired_keys` base64-encodes it into the KV key `portrait:<account>`, and the Worker serves that value at `/daydream/_edge/portrait` to the attacker's own session from anywhere (`edge/src/worker.js:276-282`). The Cloudflare token alone controls every Worker on the account and the routes on eidolon.com; any other key or token the operator can read is reachable the same way. This undoes criterion 9's "holds no Cloudflare credential": the service never holds it, but it can make the operator's job fetch and publish it.
  Evidence: reproduced with scratch files only: a symlink to an operator-only file, planted at a toon's portrait path, came back as the `portrait:<account>` value from `keepsakes.export` plus `edge.desired_keys` (no network call made). The same gap is in the other operator-run readers and writers of `/srv/daydream/data`: `prodctl.sleep_` writes `announce.json` through any link (`daydream/prodctl.py:459`); `admin.cmd_backup`, run as the operator by `prod deploy|pull|backup` and the weekly `prod offsite` timer, opens `live.db` and `accounts-prod.db` through any link and writes the copies into a service-readable directory (`daydream/admin.py:384-417`); `prebake --from-cache` writes to a service-controlled path (`daydream/prebake.py:73-74`); the dream rehearsal writes its report under the data dir (`daydream/dream.py:773, 840`). All of them open SQLite files the service authored, with default settings.
  Remediation: treat `/srv/daydream/data` as attacker-controlled from the operator's side. Run every prod command that touches it as the `daydream` user under the same sandbox (a oneshot unit, or `systemd-run -p User=daydream -p ProtectHome=yes ...` behind a narrow sudoers rule), and keep only the network step (the KV or R2 upload with the operator's token) on the operator side, fed by stdout or one regular file, never by paths inside the data dir. Until then: open data-dir files with `O_NOFOLLOW`, require a regular file whose resolved path is inside the data root, cap sizes, check PNG magic bytes for portraits, and set `PRAGMA trusted_schema=OFF` when operator tooling opens a prod database. Add a test that plants a symlink in a scratch cache and asserts the export refuses it.

[WARN] daydream/api/ws.py:909-925, 953-1000 — disabling an account or revoking its sessions does not stop an open WebSocket from receiving; only the next inbound frame is checked.
  Attack vector: a friend whose account the operator disables, or a lost device whose sessions are revoked with `account sessions --revoke`, keeps an existing tab open and sends nothing. The SPA sends no keepalive frames and uvicorn's protocol pings (every 20 s) keep the socket up, so the tab keeps streaming everything said and done in its toon's room, and the re-snapshots that follow, indefinitely. The socket also keeps counting as live for its toon.
  Evidence: `_receive_loop` re-resolves the session per inbound frame (`ws.py:922`); `_broadcast_loop` checks only toon control (`ws.py:975`), never the session. Reproduced against a throwaway data dir: after `accounts.set_disabled("alice", True)`, alice's idle socket received the next `say` from a co-located player. SPEC criterion 2 and the comment at `ws.py:920-921` say disabling or revoking ends an open socket.
  Remediation: re-resolve the session in the broadcast loop as well (before each send, or on a 15 to 30 s timer) and close with 4401 when it no longer resolves. Test: disable the account, have another player speak, assert the idle socket closes without receiving the line.

[WARN] daydream/api/ws.py:859-881, 937-943, daydream/verbs.py:1037-1048 — the 500-character cap covers only typed `input` frames; a `command` frame carries `verb` and `args` of any length up to the socket's message limit, and `say` broadcasts and stores them.
  Attack vector: any signed-in friend, or a script holding a friend's session, sends `{"kind":"command","verb":"say","args":"<64 KB>"}`. Prod accepts frames up to 64 KiB (`--ws-max-size 65536`) at about 3 frames a second (more by reconnecting, which refills the bucket). Each frame is stored about three times (`inputs.args`, `inputs.resolved_json`, the `say` event), roughly 2 GB an hour for one account before the 14 nightly backup copies, and every co-located client receives each line and receives it again in each room re-snapshot (the last 50 events). `talk` to another player takes the same path; `talk` to an NPC puts the whole text into the dialogue prompt.
  Evidence: `_handle_command` takes `args = str(msg.get("args", ""))` with no cap (`ws.py:871`) and records it (`ws.py:872-877`); only `kind == "input"` is length-checked (`ws.py:939`). Reproduced against a throwaway data dir: a 20,000-character `say` sent as an `input` frame was refused, and the same text as a `command` frame was broadcast to a co-located socket and stored in full in `inputs`. SPEC criterion 7 is checked off on the input-frame cap alone.
  Remediation: apply `MAX_INPUT_CHARS` to command `args` and a short cap to `verb`, `dobj_id` and `iobj_id` at the WS boundary, refused with the same notice; cap `say` and `talk` text in the verb handlers as defense in depth; key the rate bucket on the session, not the connection (criterion 7 says per session). Add a test beside the input-cap test.

[WARN] daydream/api/auth.py:177-203, daydream/accounts.py:53-58, 562-586 — the global invite-guess caps let anyone on the internet shut invitations off: about 20 failed peeks close redemption for the rest of the hour, and about 40 close it for the rest of the day.
  Attack vector: the door page and `/api/invite/peek` are public. An anonymous client posts made-up slugs. Every failure counts toward `redeem-hour` (20) and `redeem-day` (40), global fixed-window counters checked before anything else; once either is spent, every peek and redemption for every invitee, including a friend opening a valid link, returns 429 "too many tries" until the window ends. Blocked attempts do not count, so 20 requests in each of two hours spend the day, and the next day can be spent the same way. The per-address limit (5 per 10 minutes) and the edge rule (5 requests per 10 s per IP) do not stop it; a few addresses or some patience suffice. Password-reset invites go through the same endpoint. No CLI verb clears the counters.
  Evidence: `_redeem_blocked` and `_redeem_failed` (`auth.py:177-186`); peek records failures (`auth.py:196-201`). Reproduced in edge mode against a throwaway data dir: 40 bogus peeks from 40 client addresses, after which the real invitee's peek and redeem both returned 429.
  Remediation: make guessing infeasible without a global hard cap: raise slug entropy (a third word or a short random suffix moves the space from about 2^20 to 2^40 or more), key per-address counters on the /64 for IPv6, and turn the global counter into an alert or a soft delay. Meanwhile add `bin/game account throttle-clear` so the operator can reopen the door.

[WARN] daydream/api/slots.py:79-87, 191-211, daydream/api/ws.py:315-323 — an admin web session can enter, rest or permanently delete any friend's toon, which is more than the "exactly three" admin capabilities in SPEC criterion 4 and `docs/GOING-LIVE.md` section 4.
  Attack vector: anyone holding an admin session (the operator's browser, the CLI's cached `cli-operator` tokens, or script running elsewhere on the shared www.eidolon.com origin while the operator is signed in; see NOTE 1) posts `/api/slots/<n>/delete` for every slot, or claims a friend's toon and opens `/ws`. Deletion is irreversible short of a backup restore. Entering a friend's toon delivers that friend's private journal, Book of Stray Minutes and pending while-you-slept note in the snapshot (marking the note seen) and bumps the friend to "dreaming elsewhere".
  Evidence: `_require_actionable` returns early for admins (`slots.py:84`); `claim_slot` lets an admin take over any toon (`slots.py:211`); `tests/test_slots.py:222` asserts it. GOING-LIVE section 4 says "a stolen admin cookie can repaint a room and read status, and nothing else."
  Remediation: move cross-account toon actions to the CLI (the shell governs) and limit the web admin to its own toons, or amend criterion 4 and GOING-LIVE section 4 to state the real reach. Either way, give the CLI's status session a role that cannot act on toons.

[WARN] daydream/accounts_cli.py:190, docs/GOING-LIVE.md:73, tests/test_accounts.py:189-340, tests/test_auth.py:201-251 — what appears to be a real person's full name is the example invitee in help text, documentation and tests.
  Attack vector: the repository is public. Once these commits are pushed, anyone can read the name and tie it to the operator and to this invite-only service.
  Evidence: 17 occurrences across four tracked files (a first and last name, not a stock placeholder); also in the local, untracked `/invite` skill. It entered history in `69f4b5b` and `6bf3187`, both among the 10 commits not yet on origin/main. Whether the name is real is not verified; treat it as real.
  Remediation: replace it with a placeholder ("Test Friend") before the first push; because the commits are unpushed, amending them keeps it out of public history.

[NOTE] daydream/api/csrf.py:65-67, edge/wrangler.toml:13-15 — the browser trust boundary is the whole www.eidolon.com origin, and the Origin check ignores the scheme.
  Attack vector: the village shares its origin with the eidolon.com Pages site and any other Worker on that host. Script running anywhere on `https://www.eidolon.com` can send same-origin, cookie-bearing requests and WebSockets to `/daydream/` that pass the CSRF and WS Origin checks; the cookie's `Path=/daydream/` is not an isolation boundary. A flaw elsewhere on the host is therefore a flaw here, and with an admin session it reaches the admin WARN. Separately, `origin_allows` compares only the netloc, so `Origin: http://www.eidolon.com` passes; that matters only if a network attacker can serve script on the http origin and the browser sends Lax cookies across schemes. Neither the app nor the Worker sets HSTS.
  Remediation: serve daydream from its own host (for example `daydream.eidolon.com`) so the origin, cookie and CSP are its alone; compare scheme and host against `DAYDREAM_PUBLIC_ORIGIN`; set HSTS at the zone or in the Worker.

[NOTE] edge/src/worker.js:213-219 — the asleep page fills its template with `String.replaceAll(pattern, string)`, where `$&`, `` $` `` and `$'` in the replacement are substitution patterns, and `escapeHtml` does not touch `$`.
  Attack vector: a friend puts `` $` `` or `$'` in a toon name or in text that reaches a journal entry, a book entry or the shared chronicle; every recognized friend's asleep page then splices copies of the template into itself. The spliced text is the Worker's own template, so the page garbles but no script is injected.
  Remediation: pass a function (`() => value`) as each replacement; add a unit test with `$'` in a journal line.

[NOTE] daydream/accounts.py:342-354, daydream/prodctl.py:187-196, 360-364 — the CLI's own identities (`cli-operator`, `agent-<name>`) are found by username, and invitees choose usernames freely.
  Attack vector: a friend redeems an invite as `cli-operator` before the CLI first mints it (on the first `prod status` or deploy health check while awake). `mint_session` then mints the CLI's sessions for that player account without checking its role, so `prod status` shows nothing and every `prod deploy` rolls back as unhealthy (`served_build` reads the admin-only `/status/build`). Squatting `agent-<name>` makes `bin/game prod play <name>` drive the friend's account and toon.
  Remediation: reserve these names (and `admin`, `operator`) in `username_problem`, and have `mint_session` refuse an existing account whose role differs from the one requested.

[NOTE] .claude/settings.json:20 — the pre-allowed `Bash(bin/game prod invite*)` also matches `bin/game prod invite reset <username>`, which mints a password-reset link for any account (the operator's admin account included), and `invite revoke`.
  Attack vector: the agent reads player-authored text (digests, `bin/game play` output, toon names in the also pre-allowed `prod status`). Text that steers the agent into a reset needs no approval. Getting the link out still needs a step that asks, so this is least privilege rather than an open path. The file is local and untracked.
  Remediation: narrow the rule to `bin/game prod invite create*` and `bin/game prod invite list*`; keep `reset` and `revoke` ask-first.

[NOTE] daydream/api/auth.py:92-103 — the public endpoints read and parse the whole request body before anyone is signed in, and nothing in the stack limits body size.
  Attack vector: anonymous POSTs with large JSON bodies to `/api/login`, `/api/invite/peek` or `/api/invite/redeem`. Cloudflare admits up to 100 MB per request on the Free plan. Locally, one 20 MB JSON array raised peak RSS by about 74 MB; a handful of concurrent 100 MB bodies approach the unit's `MemoryMax=4G`, and an OOM kill drops every player's socket until the 5 s restart.
  Remediation: an ASGI middleware that refuses bodies over a small cap (16 KB for the public endpoints, 64 KB elsewhere) by Content-Length and by counting streamed bytes, plus a Content-Length check in the Worker.

[NOTE] daydream/api/auth.py:122-139, daydream/accounts.py:54-55, 301-319 — login throttling and hashing favor a patient or distributed attacker.
  Attack vector: argon2id verification (about 32 ms each on this box) runs synchronously on the event loop, so a login flood from many addresses stalls every player's socket while it lasts; per-address counters key on the full client address, which IPv6 rotation defeats; the per-username limit (5 per 15 minutes) lets anyone who knows or guesses a friend's username keep that friend from signing in; any 10-character password is accepted, and a common one can fall inside the per-username budget of about 480 guesses a day.
  Remediation: run hashing in a small bounded thread pool (keeping the throttle check and record atomic), key per-address counters on the /64 for IPv6, prefer a delay to a hard per-username lockout, and reject the most common passwords.

[NOTE] daydream/api/ws.py:232-236, 893-914, daydream/api/slots.py:154-161, 242-265 — signed-in friends can spend shared capacity with no per-account limit.
  Attack vector: the WS token bucket is per connection, so reconnecting refills it; creating and deleting a toon and connecting costs a portrait render each time; each leave after new events costs a journal LLM call; `/ws?since=0` replays a room's entire event history with no limit.
  Remediation: per-account limits on toon create and delete and on leave, a per-session bucket, and a cap on replayed events (for example the last 200).

[NOTE] docs/CLOUDFLARE-SETUP.md:24-25, 34 — the box's public IPv4 and IPv6 addresses and the Cloudflare account id are in a doc that becomes public on the next push.
  Attack vector: none direct; the box exposes only SSH and an account id is an identifier, not a credential. It names the village's origin host and its SSH endpoint to anyone reading the repo.
  Remediation: use placeholders before the first push; keep the real values in `~/.config/daydream/cloudflare.env` or private notes.

[NOTE] daydream/prodctl.py:271-273, ops/requirements-prod.lock, .github/workflows/test.yml:23-24 — supply-chain pinning stops at versions.
  Attack vector: a compromised or replaced PyPI artifact at a pinned version installs into the next prod venv; CI uses mutable action tags and the repository's default token permissions (carried from earlier reviews).
  Remediation: generate the lock with hashes and install with `--require-hashes`; pin actions to commit SHAs and add `permissions: contents: read`.

### Resolution (same day, after the review)

| Finding | Status |
|---|---|
| WARN 1: operator tooling follows service-planted paths | Fixed in `19ede3f`. Every prod command that touches the data dir runs as the `daydream` user (sudoers `(daydream) NOPASSWD: ALL`, a privilege drop). The operator only receives bytes (keepsakes on stdout, streamed tarballs and pulls). Portraits are read with `O_NOFOLLOW` inside the cache root. Restores refuse symlinks. Graded art is staged in an operator-owned dir the service can only read. Tests: a symlinked portrait never exports; restore refuses a link. |
| WARN 2: revocation missed idle sockets | Fixed in `ea991f1`. A per-socket watchdog re-reads the session every 30 s, and the SPA's 25 s keepalive rides the per-frame check. |
| WARN 3: command frames skipped the cap | Fixed in `ea991f1`. Every frame is size-checked (2000 chars) before parsing, and prod's `--ws-max-size` is 16 KiB. |
| WARN 4: anyone can pause invitations | Mitigated in `c88ce68`. The refusal names the operator, and `bin/game invite unblock` reopens invitations. The global cap stays, since it is the defense against distributed guessing (a residual, below). |
| WARN 5: admin web sessions over friends' toons | Fixed in `05ea503`. No admin bypass on claim/kick/delete; moderation is `bin/game world rest-toon\|delete-toon`. |
| WARN 6: a real name in the repo | Fixed in `8a55e42`: the fictional Robin Ash. The name remains in unpushed local history; scrub before the first push (see the go-live notes). |
| NOTE: Origin ignores the scheme | Fixed in `c88ce68`: scheme and host both. |
| NOTE: `$`-patterns in the asleep template | Fixed in `c88ce68`: function replacements. |
| NOTE: username squatting | Fixed in `c88ce68`: `cli-*`, `agent-*` and a few names are reserved from invites (the CLI may still create them), and keepsakes skip those accounts. |
| NOTE: the pre-allowed invite verbs | Fixed in `c88ce68`: only `prod invite create|list` are pre-allowed. |
| NOTE: unbounded pre-login bodies | Fixed in `ea991f1`: 413 over 64 KiB; streamed bodies are truncated. |
| NOTE: login throttling | Improved in `c88ce68`: argon2 runs off the event loop, and IPv6 keys on /64. The per-username lockout used against a friend remains (15-minute window). |
| NOTE: shared capacity | Partly fixed in `c88ce68`: a reconnect replays at most 300 events. There are still no per-account limits on create/delete/leave (friends only). |
| NOTE: box addresses in docs | Fixed in `8a55e42`. |
| NOTE: supply-chain pinning | Open: the lock has versions, not hashes; CI actions use tags. |

Residual risks closed alongside, in the commit that records this table: the shared GPU-lock wait now times out (90 s), so a held lock file cannot stall another process's text forever; prod runs `--no-access-log`, so invite slugs never reach the journal; sessions end 180 days after sign-in however often they are used.

Traced and cleared this run (not findings):

- **The gate.** The allowlist is exactly `/`, `/login`, `/healthz`, `/api/login`, `/api/logout`, `/api/invite/peek`, `/api/invite/redeem` plus the `/assets/` and `/invite/` prefixes, and `tests/test_edge_access.py` walks every route, mount and socket. Encoded traversal (`/assets/..%2F...`, `/invite/..%2F...`) reaches the gate and the router as the same decoded path, so it lands in StaticFiles' confinement or a 404, never an unguarded route. `/status/*` is admin-only, `/cache/*` needs a session and validates each segment, the API docs routes are off, and the world swap does not exist in edge mode.
- **Edge mode.** The boot guard refuses prod without edge mode, an https public origin, an explicit base and a loopback bind; the unit runs `--no-proxy-headers`; the client address for throttles comes only from the Worker's header.
- **Sessions and passwords.** Tokens are 256-bit and stored as sha256; expiry slides 30 days; a new token is issued at login (no fixation); logout deletes the session; password change and reset end other sessions; disabled accounts never authenticate; unknown usernames pay one argon2id verification and every refusal reads the same. The cookie is HttpOnly, SameSite=Lax, `Path=/daydream/`, Secure over https, and named per environment. Python's cookie parser is linear on backslash-heavy values in this interpreter (checked), so the per-request parse is not a CPU sink.
- **Invites.** Redemption is single-use under `BEGIN IMMEDIATE`; used, expired, revoked and unknown slugs answer the same.
- **Ownership.** A player cannot claim, rest or delete another account's toon (403), and one-toon-per-player is enforced without an await between check and insert. Lost Hours NPCs sit in slots 100 and up (checked in `worlds/lost-hours.json`), outside the human slot range.
- **WebSocket.** Unauthenticated handshakes are refused before accept; Origin is checked on the handshake; typed input is capped; private events are filtered on send and on replay.
- **Headers and XSS.** CSP without `unsafe-inline` (the client has no inline script or style), nosniff, `frame-ancestors 'none'`, same-origin referrers, noindex; the asleep page carries its own CSP. The door uses `textContent`; the "your dreamer" panel builds DOM nodes; say lines and narration go through `escape` and `linkifyEntities`; the Worker escapes every KV value it renders.
- **The Worker.** `workers_dev` and preview URLs are off; `redirect: "manual"`; `CF_*` cookies from Access are stripped; only fixed KV keys are read; keepsakes and portraits are served only for a cookie whose hash is an unexpired pass. The Access setup in `docs/CLOUDFLARE-SETUP.md` is one Service Auth policy with no identity provider, and cloudflared validates the JWT.
- **Prod operations.** Releases are operator-owned `2750`, made read-only, and outside the service's writable paths; the release environment comes from `prod.env` with no dev `.env` or secrets file; the sudoers rule names exactly start, stop and restart of the two daydream units plus starting the backup service; the tunnel token is root-only and read by systemd before dropping to a DynamicUser; the nightly backup runs as the service user with `PrivateNetwork`. vLLM's internal sockets are on loopback (criterion 19).
- **Secrets and history.** No credential patterns (Cloudflare, tunnel, Access, GitHub, AWS, private keys) in the tree or git history; `.env` has never been committed. The local `.env` still holds an unused `DAYDREAM_PASSWORD`; delete it.
- **Earlier findings.** Toon names are capped at 24 printable characters, banlist-checked and truncated in stored facts; the digest quotes player text under an untrusted banner and lives under the data dir; an LLM-origin narrate is reduced to `text`; `world delete` removes `inputs` rows. The per-install session-secret NOTE is obsolete (the signed-cookie session is gone).
- **Code patterns.** SQL is parameterized (the one f-string in `toons._query` takes internal constants); no `shell=True`, `pickle` or `eval`; Jinja runs sandboxed; the image workflow sets prompt text as a dict value, so player text cannot add nodes.

### Residual risks (recorded, not yet decided by the operator)

- **DNS and local sockets leave the sandbox.** `IPAddressAllow=localhost` admits the local resolver at 127.0.0.53, so a compromised service can still exfiltrate through DNS lookups; `AF_UNIX` reaches local services such as D-Bus.
- **Loopback bypasses Access.** Any local process can call `127.0.0.1:54322` directly and set `X-Daydream-Client-IP` to anything, which only moves throttle keys; the gate still applies.
- **`gpu.lock` is service-writable.** A compromised service can hold it; dev's text calls now give up after 90 s (foggy) and renders after 20 s, so this is a nuisance, not a stall.
- **Invite slugs are weakly hashed.** Invite hashes are unsalted sha256 over about 983,000 phrases, so any copy of `accounts-prod.db` (the data dir, local backups) yields every open slug in seconds. Anyone with that copy already holds prod's data; invites expire in 14 days.
- **Invitations can be paused by strangers.** The global failed-redemption cap (20 an hour, 40 a day) is shared, so an attacker can keep invites closed; `bin/game invite unblock` reopens them, and the edge rate-limit rule slows a single address.
- **Free-plan quotas.** If the zone is on the Workers Free plan, an anonymous client can spend the daily request quota (100,000) and take the route down until the next UTC day; the one WAF rule covers only the login and invite paths.
- **The operator's token is account-wide.** Workers Scripts edit cannot be scoped to one Worker, so compromise of `peter` is compromise of every Worker on the account and of routes on eidolon.com.
- **Toon names are not unique.** A player can take an NPC's or another friend's name and speak under it.
- **Side finding, not acted on (another repo's concern).** `www.eidolon.com/generate` accepts anonymous POSTs that spend Workers AI; it also sits on the origin daydream now shares.

### Accepted Risks

Accepted by the operator for going live (`docs/GOING-LIVE.md` section 9, design approved 2026-09-27):

- **The engines run as `peter`.** vLLM (`:8000`) and ComfyUI (`:8188`) listen unauthenticated on loopback and run as `peter`, who is in the docker group. The prod service user can reach both, so an exploitable bug in either engine's API (or a future ComfyUI custom node) is a path from a compromised service to root. Stock ComfyUI here has no custom node that runs code, and vLLM runs without runtime LoRA loading. Later fix: a separate engines user.
- **The pre-login surface is public** (door, login, invite redemption, static assets): throttled in the app and rate-limited at the edge, within the limits of the WARN and NOTEs above.
- **Friends drive shared-world verbs on shared objects:** the co-op design; there is no griefing economy.
- **What friends type reaches the local LLM:** role separation, length caps, input and output banlists, and strict validation apply.

Carried register, updated for this turn:

- **LLM-emitted effects take an unscoped, LLM-chosen target id** on the data-skill paths (talk for NPCs without a voice sheet, room-affordance data skills). Neither path exists in the live Lost Hours world. v2 `skills-authoring-and-security`.
- **Parser raw player input is not role-separated** before the grounding call; the output is strictly re-grounded to a closed verb and an in-scope id.
- **NPC dialogue and growth prompt injection via player input:** role-separator wrapped, length-capped for typed input (command-frame `talk` is the WARN above), input-banlist-checked; output structured, validated and banlist-scanned before mutation. Refusal `reason` text is narrated without an output-banlist pass and renders through escaped sinks.
- **Operator-trust world envelopes and `bin/game`:** `world load`/`reset` content, `reset`'s `rm -rf`, dev `.env` and `secrets.env` sourcing (prod reads neither), the dev `0.0.0.0` bind, the deprecated `bootstrap_world` path. None take network input.
- **Event queues are bounded** (256, drop-oldest).

Retired this turn: tailscale-mode auth as tailnet membership (every mode now requires an account); the cookie without `Secure` (Secure in prod); unauthenticated `/status` and `/cache` (admin and session now); the missing CSP and `nosniff` (added); the repaint tool open to every session (admin-only); liveness-gated takeover between players (ownership now); the unbounded slot-create body as a friend-only concern (superseded by the pre-auth body NOTE).

---
*Prior review (2026-09-27, paths, commit `529398b`): the pivot turn's 111 files. 0 BLOCK / 3 WARN / 2 NOTE: uncapped toon names reaching other players' prompts and a persistent deed fact; the dream digest handing raw player text to the agent; raw digests committed to a public repo; LLM-origin narrate fields the banlist never read; uncapped WS input. The three WARNs and the narrate NOTE were fixed in `98cc8d0` (re-verified at this HEAD); the WS NOTE is fixed for typed input and continues as the command-frame WARN.*

<!-- SECURITY_META: {"date":"2026-09-27","commit":"5557e2d1b7aa28778ac951f7bd20c5d583be1a55","scope":"full","block":0,"warn":6,"note":9} -->
