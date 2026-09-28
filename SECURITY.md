# SECURITY.md

## Security Review — 2026-09-28 (scope: paths)

**Summary:** This path-scoped review covers the ten files changed by the fix commit `e05747c`. The fixes work where they were aimed. A 200-request concurrent login burst now gets 5 password checks, and the capped receive no longer spins. Three NOTEs remain. First, moderating by name can still act on the wrong friend's toon, because a name can copy another toon's id or use a homoglyph. Second, password changes run argon2 on the event loop, so one signed-in account can stall the server. Third, the timer-unit fix is not yet installed on the box, and the hourly keepsakes sync failed at 02:03 UTC (0 BLOCK / 0 WARN / 3 NOTE).

### Scope and method

Every scanned file was read in full, along with the callers and callees each finding depends on (`toons.py`, `api/slots.py`, `api/ws.py`, `server.py`, `prodctl.py`, `db.py`, `ops/sudoers.d/daydream`, the edge rate-limit rule). The three NOTEs were reproduced against throwaway data dirs through the real HTTP, WebSocket and CLI paths. The previous review's login burst was re-run in edge mode with the production argon2 profile. The installed units, timers and the keepsakes journal were read on the box (read-only). The last three commits of each scanned file, and all 29 commits not yet on origin/main, were scanned for credential patterns. The four scanned test files pass (68 tests).

### Findings

[NOTE] daydream/admin.py:454-464 — `_find_toons` returns an exact id match before it considers names, and a toon's name can be another toon's id. Moderating the name a griefer chose therefore acts on a different friend's toon. A homoglyph name gets past the new ambiguity check in the same way.
  Attack vector: A player shares a room with the target friend and reads that friend's toon id from the state snapshot. Every co-located toon card carries `id` (daydream/api/ws.py:390), and so does a painted portrait's URL. The player deletes their own toon, creates a new one named exactly that id, and then misbehaves. The id (`t-slot2-9f4f6ed2`) is 16 printable characters, inside the 24-character cap at daydream/api/slots.py:112. `bin/game prod status` lists players by name only (daydream/server.py:176), so the operator runs `bin/game prod world delete-toon t-slot2-9f4f6ed2` using the name it shows. The friend's toon is deleted, what it carried is dropped, and the griefer's toon stays. The deletion cannot be undone short of restoring a whole-world backup. The homoglyph variant needs no id at all: a name such as "Мira" (Cyrillic М) next to "Mira" does not count as ambiguous, so typing "Mira" by hand deletes the real Mira.
  Evidence: The id match wins outright at admin.py:460-462. At admin.py:505-516, ambiguity is checked only among name matches. In the reproduction, the griefer's snapshot listed the friend's id, and the create with that name returned 200. `/status/who` printed "playing: Mira (away), t-slot2-9f4f6ed2 (away)". `cmd_toon_moderate("t-slot2-9f4f6ed2", "delete")` printed "deleted Mira" and left the griefer's toon. The homoglyph run also deleted the real Mira. When two names really are the same, the refusal lists ids and slots but not owners, so the operator still cannot tell which id belongs to the griefer.
  Remediation: Resolve the key against ids and names together, and refuse whenever the combined result holds more than one toon. For every candidate, print the id, slot, owner username and whether the toon is live. Have `/status/who` print each toon's id and owner username next to its name, so the operator moderates by id. Optionally, refuse names shaped like toon ids (`t-slot<N>-<8 hex>`) when a toon is created.

[NOTE] daydream/api/auth.py:191-206, daydream/accounts.py:298-312 — A password change runs two argon2id operations on the event loop: it verifies the old password and hashes the new one. Only refusals count against its budget, so one signed-in account can stall the server for everyone.
  Attack vector: Any signed-in account (a friend, or anyone holding a friend's session cookie) can script `POST /api/account/password`, alternating between two passwords it knows. With the production profile (m=64 MiB, t=3, p=4), each success costs about 64 ms of event-loop time on this box (32 ms to verify, 32 ms to hash). No other HTTP request or WebSocket frame is served during that time, so about 16 changes a second keep the village frozen. Three things leave this open:
  - The edge rate-limit rule covers only `/daydream/api/login*` and `/daydream/api/invite*` (docs/CLOUDFLARE-SETUP.md section 6).
  - The `password-change:<account>` key is charged only on a refusal (auth.py:203-205).
  - The login path moved argon2 off the loop for this reason (2026-09-27 NOTE) and now bounds it with `_HASH_SLOTS`, but this path was left out.
  Evidence: Reproduced with the production argon2 profile. 20 concurrent password changes by one account all returned 200. A `/healthz` request from another client, issued alongside them, took 1282 ms (2 ms when idle).
  Remediation: Run the verify and the hash through `asyncio.to_thread` under `_HASH_SLOTS`. Charge every attempt against the account's budget before the await, as login now does (for example, 5 changes per 15 minutes). `redeem_join` and `redeem_reset` also hash on the loop, but each slug can do so only once.

[NOTE] ops/systemd/daydream-keepsakes.service:13-15, ops/systemd/daydream-offsite.service:12-14 (the installed copies in /etc/systemd/system) — The fix is correct in the repo, but the installed units still set `NoNewPrivileges=yes`. Prod is awake, so the hourly keepsakes sync is failing.
  Attack vector: The earlier WARN is still open on the box. While the village is awake, a disabled account or a revoked session stays on the Worker's pass list, and the Worker serves that pass its keepsakes whenever the origin fails. The weekly offsite run, next due Sunday 2026-10-04, will fail the same way.
  Evidence: Both installed units still carry the flag. `daydream-prod.service` has been active since 01:21 UTC. The 02:03 UTC keepsakes run exited 1 with `sudo: The "no new privileges" flag is set, which prevents sudo from running as root`. Nothing outside the journal reported it: neither unit has `OnFailure=`, and `bin/game prod status` does not show timer results.
  Remediation: Run `sudo ops/install-prod.sh`, or install the two rendered units and run `systemctl daemon-reload`. Then start `daydream-keepsakes.service` once and check its result. The failure-visibility half of the earlier remediation is still open, and it is what would have caught this. Options are `OnFailure=`, each timer's last result in `bin/game prod status`, or a check that the installed units match the rendered repo copies.

### The earlier 2026-09-28 findings at this HEAD

| Finding | Status at `e05747c` |
|---|---|
| WARN 1: concurrent logins skip the username budget | **Fixed.** The attempt is charged against both keys with no await between check and record (auth.py:149-158). A right password gives back its address charge and clears the username key, and at most 4 argon2 checks run at once. The earlier burst was re-run: 200 concurrent wrong passwords for one username, from distinct client addresses, in edge mode, with the production profile. It produced 5 password checks, at most 4 at a time, and 195 refusals. Prod runs a single uvicorn process, so atomicity on the event loop is sufficient. |
| WARN 2: timers cannot drop to the service user | **Fixed in the repo, not installed** (NOTE 3 above). `tests/test_ops_units.py` pins the fix. Without the flag, the two operator jobs can use only what the operator's NOPASSWD sudoers entries already allow (the listed units, and acting as `daydream`). No other setting in either unit implies the flag. |
| WARN 3: the surname in the invite skill | Recorded as fixed. Not re-checked here, because the file is outside this run's scope. |
| NOTE 1: backup refs hold scrubbed data | Accepted until the push is confirmed. Outside the scanned files. |
| NOTE 2: the standing grant removes the prompt | **Kept, with local ask rules** (outside the scanned files). One caveat: Claude Code's permissions page says argument-constraining Bash rules do not match variants. Its example is that `Bash(git push *)` stops `git push origin main` but not `git 'push' origin main`. So `bin/game prod invite 'reset' <admin>` would likely still match the broad allow rule `Bash(bin/game prod *)` without triggering the ask rule. This was not tested, because it would mint a credential. A narrow allow list (only the verbs the operator wants unprompted) fails closed on such variants. A PreToolUse hook that tokenizes the command is the other robust option. Two pre-allowed commands still chain without a prompt: `prod invite create` mints a join link, and `edge sleep "<note>"` can publish it, which gives a stranger a player account. |
| NOTE 3: moderation by name picks the first match | **Partly fixed.** Toons with identical names are refused. A name that copies a toon id, or uses a homoglyph, still misleads (NOTE 1 above). |
| NOTE 4: the capped receive spins after the cut | **Fixed.** After the cut, the wrapper awaits the real `receive`, answers further body chunks with an empty final chunk, and passes `http.disconnect` through (gate.py:85-94). A disconnect listener now blocks instead of spinning. |

### Traced and cleared this run (not findings)

- **The login fix under adversarial input.**
  - A right login charges and then gives back exactly one address attempt. An attacker's own correct logins, mixed in with wrong guesses, never bring the address count below the number of wrong guesses.
  - Unknown and existing usernames are charged and refused the same way. A disabled account is refused after the same verification.
  - The worker thread shares the accounts connection (`check_same_thread=False`, autocommit). It reads `accounts` and may write a rehash, but never touches the throttle table, so it cannot interleave with the check and record.
  - In daydream's own code, the default executor serves only this call, so threads waiting on `_HASH_SLOTS` block nothing else.
- **Login by account id.** `get_account` accepts an account id as well as a username. That means `a-<id>` is a second login-throttle key for the same account. An invitee could also pick a username equal to another account's id, and CLI verbs would then resolve it to the other account. Both require knowing a victim's account id, and no player-facing response carries one: toon cards omit `owner_account`, `/api/dreamer` shows only your own, and `/api/slots` is admin-only. Worth closing if ids ever reach players: refuse `a-` usernames at redemption, and key the login throttle on the resolved account id.
- **The gate.**
  - The allowlist matches the registered routes. `/invite/{slug}` takes one path segment, and the `/assets` static mount refuses traversal.
  - The gate and the router both see the same percent-decoded path.
  - A trailing-slash or double-slash variant of a public path is treated as a normal guarded path.
  - An unreadable accounts DB fails closed.
  - The 64 KiB cap also covers chunked bodies, and the server enforces Content-Length framing.
- **admin.py beyond moderation.**
  - Every data-dir verb prodctl calls (`backup`, `restore-backup`, `preflight`, `rest-all`) runs as `daydream`. So the lstat-then-copy in `cmd_restore_backup` and the `rmtree` pruning in `cmd_backup` can only race the service user itself.
  - Archive restore rejects absolute and `..` members and extracts with `filter="data"`, which the 3.10.12 interpreters in dev and prod support.
  - SQL is parameterized throughout.
  - Toon names created through the API passed `isprintable()`, which rules out escape and bidi control characters in the operator's terminal.
- **Removing NoNewPrivileges.** The operator's other sudo rules still need a password, and a service has no cached ticket, so `sudo -n` in these jobs reaches only the NOPASSWD entries.
- **Secrets and PII.** No credential patterns appear in the scanned history or in the unpushed commits. The long random-looking strings are package-lock integrity hashes and test names. The tests use fictional names, `www.eidolon.com` (already public), and loopback, CGNAT and documentation addresses.

### Carried forward (open, recorded 2026-09-27, not yet decided)

- DNS (127.0.0.53) and AF_UNIX sockets leave the prod sandbox.
- Any local process can reach `127.0.0.1:54322` without Access and choose its own `X-Daydream-Client-IP`. This only moves throttle keys; the gate still applies.
- `gpu.lock` is writable by the service. Text calls give up after 90 s and renders after 20 s.
- Invite slugs are unsalted sha256 over about 983,000 phrases, so anyone with a copy of the accounts DB can recover every open slug.
- Strangers can keep invitations paused (20 failures an hour, 40 a day, global). `bin/game invite unblock` reopens them.
- On the Workers Free plan, an anonymous client can use up the daily request quota. The one WAF rule covers only the login and invite paths.
- The operator's Cloudflare token is account-wide, because Workers Scripts edit cannot be scoped to one Worker.
- Toon names are not unique. Moderation now refuses any key that matches more than one toon by id or name, and `/status/who` shows ids; lookalike Unicode names are not folded.
- Supply-chain pinning: the prod lock pins versions but not hashes, and CI actions use tags.
- The standing prod grant's `ask` rules (`.claude/settings.local.json`, local) are text patterns: a quoted word may slip past one (untested, since testing it would mint a real reset link). A PreToolUse hook that parses the command would be firmer.

### Closed by the operator's decision (2026-09-28)

- **The Worker leaked Access's cookie on WebSocket answers** (found by the
  pre-push code review, a BLOCK; fixed in `3df294b`, deployed about 02:40
  UTC on 2026-09-28). For about five hours an anonymous HTTP/1.1 upgrade to
  `/daydream/ws` received a 24-hour `CF_Authorization` token for the origin
  hostname. Every such token has expired by about 02:40 UTC on 2026-09-29.
  The operator chose not to revoke tokens or shorten the Access session in
  the dashboard: a token opens nothing behind the sign-in gate; it only
  skips the edge rate limit and lets the per-address throttle key be forged,
  while the per-username limit, the global invite cap and the 4-slot argon2
  cap still hold; and no accounts existed during the window. Guarded by
  `edge/test/worker.test.js` (a 101 and a refused upgrade, both stripped)
  and by `bin/game prod check`, which probes for the cookie on every run.

### Accepted Risks

Accepted by the operator for going live (`docs/GOING-LIVE.md` section 9, design approved 2026-09-27):

- **The engines run as `peter`.** vLLM (`:8000`) and ComfyUI (`:8188`) listen unauthenticated on loopback and run as `peter`, who is in the docker group. The prod service user can reach both, so an exploitable bug in either engine's API is a path from a compromised service to root. The planned fix is a separate engines user.
- **The pre-login surface is public** (the door, login, invite redemption, static assets). It is throttled in the app (per address, per username, global invite caps) and rate-limited at the edge, within the residuals above.
- **Friends drive shared-world verbs on shared objects.** This is the co-op design; there is no griefing economy.
- **What friends type reaches the local LLM.** Role separation, length caps, input and output banlists, and strict validation apply.

Carried register:

- **LLM-emitted effects take an unscoped, LLM-chosen target id** on the data-skill paths (talk for NPCs without a voice sheet, room-affordance data skills). Neither path exists in the live Lost Hours world. Planned for v2 `skills-authoring-and-security`.
- **Raw player input to the parser is not role-separated** before the grounding call. The output is strictly re-grounded to a closed verb and an in-scope id.
- **NPC dialogue and growth are exposed to prompt injection through player input.** Input is wrapped in role separators, length-capped and banlist-checked. Output is structured, validated and banlist-scanned before any mutation. Refusal `reason` text is narrated without an output-banlist pass and renders through escaped sinks.
- **World envelopes and `bin/game` are trusted as the operator's own.** This covers `world load`/`reset` content, `reset`'s `rm -rf`, sourcing of the dev `.env` and `secrets.env` (prod reads neither), the dev `0.0.0.0` bind, and the deprecated `bootstrap_world` path. None of them take network input.
- **Event queues are bounded** (256, drop-oldest).

---
*Prior review (2026-09-28, changes-only, commit `52c7f35`, rewritten as `2f987a2`): it reviewed the fixes that followed the 2026-09-27 full audit and found 0 BLOCK / 3 WARN / 4 NOTE. The three WARNs: moving argon2 off the event loop let concurrent logins skip the per-username throttle; the privilege drop to the service user broke the keepsakes and offsite timers, whose units set NoNewPrivileges; and the invite skill carried the surname an earlier review had removed. The NOTEs covered local backup refs that still held scrubbed data, the standing prod grant, moderation by an ambiguous name, and a capped receive that could spin. All were addressed in `e05747c`, and their status at this HEAD is in the table above. That entry, including the 2026-09-27 resolution table, is at `git show e05747c:SECURITY.md`; the full 2026-09-27 audit is at `git show 97129e2:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"e05747cff0f3df167692f275ad20447accd7d521","scope":"paths","scanned_files":["daydream/accounts.py","daydream/admin.py","daydream/api/auth.py","daydream/api/gate.py","ops/systemd/daydream-keepsakes.service","ops/systemd/daydream-offsite.service","tests/test_auth.py","tests/test_edge_access.py","tests/test_ops_units.py","tests/test_slots.py"],"block":0,"warn":0,"note":3} -->
