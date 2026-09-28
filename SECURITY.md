# SECURITY.md

## Security Review — 2026-09-28 (scope: paths)

**Summary:** This path-scoped review covers the 35 code, test and web files changed since the previous security review (`e05747c` to `d9a8ac6`): the pre-push fixes, `bin/game prod check`, the session and moderation NOTE fixes, the browser test and the runbook test. There is no BLOCK or WARN. One NOTE is new: `/status/who` now prints toon ids so the operator can moderate by id, but a player can put another toon's id, in brackets, inside their own toon's name, so the id printed after a griefer's name can belong to a friend. One NOTE carries over: the installed timer units still set `NoNewPrivileges`, so the hourly keepsakes sync keeps failing while prod is awake (0 BLOCK / 0 WARN / 2 NOTE).

### Scope and method

The 35 scanned files are every code, test and web file changed from `e05747c` to `d9a8ac6`. Every diff was read in full, along with the code each change touches or calls: all of `prodctl.py`, `prodcheck.py`, `edge.py`, `arbiter.py`, `toons.py`, `api/slots.py`, `api/ws.py`, `server.py`, `worker.js` and `door.js`, and the surrounding code in `main.js`, `accounts.py`, `auth.py`, `admin.py`, `prebake.py` and `review.py` (the previous review read the last four in full). The new NOTE was reproduced through the real HTTP, WebSocket and CLI paths against a throwaway data dir. The previous review's password-change stall was re-run against a loopback uvicorn with the production argon2 profile. The installed units, the timer results and the keepsakes journal were read on the box (read-only). The last three commits of each scanned file, and the 4 commits not yet on origin/main, were scanned for credential patterns. The scanned Python tests pass (257, the browser test included), and so do the Worker's 22 node tests.

### Findings

[NOTE] daydream/server.py:177 — `/status/who` prints each toon as `name [id]` with the raw player-chosen name, and a name may contain brackets and another toon's id. The id printed right after a griefer's name can therefore belong to a friend, and the runbook tells the operator to moderate by the id taken from this output.
  Attack vector: A player shares a room with the target friend and reads the friend's toon id from the state snapshot (every co-located toon card carries `id`, daydream/api/ws.py:401). The player deletes their own toon and creates a new one named, for example, `Wren [t-slot2-f6c40fc9]`, which is 23 characters. Toon creation checks only the 24-character cap, `isprintable()` and the tone banlist (daydream/api/slots.py:112-116). The player then misbehaves as "Wren". `bin/game prod status` shows `Wren [t-slot2-f6c40fc9] [t-slot3-e1f254da]`. docs/runbooks/friends.md tells the operator, or the agent following it, to "name a toon by its id (from `bin/game prod status` or the admin `/status/who`)". Either one runs `bin/game prod world delete-toon t-slot2-f6c40fc9`. `_find_toons` matches only the friend, because the griefer's name is not equal to the key (daydream/admin.py:472), so the ambiguity refusal does not fire and the friend's toon is deleted. The command names the deleted toon only afterwards (admin.py:530), and undoing the delete means restoring a whole-world backup.
  Evidence: Reproduced against a throwaway data dir. A co-located player's snapshot listed the friend's id. Creating a toon with the crafted name returned 200. `/status/who` returned `playing: Mira [t-slot2-f6c40fc9] (away), Wren [t-slot2-f6c40fc9] [t-slot3-e1f254da] (away)`. `cmd_toon_moderate("t-slot2-f6c40fc9", "delete")` printed `deleted Mira (t-slot2-f6c40fc9)` and left the griefer's toon in place. No output on this path shows a toon's owner, so two toons whose names only look alike (the homoglyph case) cannot be told apart either.
  Remediation: Print the id first and quote the name, so nothing inside a name can land in the id column, and add the owner's username and whether the toon is live: `t-slot3-e1f254da "Wren [t-slot2-f6c40fc9]" griefer away`. At creation (`_toon_request` in api/slots.py), refuse `[` and `]` in toon names, and anything shaped like a toon id (`t-slot\d+-[0-9a-f]{8}`, any case). That also closes the id-as-name case at the source. Before acting, have `cmd_toon_moderate` show the resolved toon's name, owner and liveness, and treat a key that appears inside another toon's name as ambiguous.

[NOTE] ops/systemd/daydream-keepsakes.service:11-15, ops/systemd/daydream-offsite.service (the installed copies in /etc/systemd/system) — Carried from the previous review and re-verified: the repo fix is still not installed. Both installed units set `NoNewPrivileges=yes`, and every hourly keepsakes run since prod woke has failed.
  Attack vector: Unchanged. While the village is awake, a disabled account or a revoked session stays on the Worker's pass list, and the Worker serves that pass its keepsakes whenever the origin fails. The weekly offsite run, due Sunday 2026-10-04, will fail the same way.
  Evidence: `systemctl cat` shows the flag in both installed units; the repo copies no longer set it. The keepsakes runs at 02:03 and 03:01 UTC exited 1 with `sudo: The "no new privileges" flag is set`. The runs at 00:04 and 01:00 passed only because the village was asleep and the job had nothing to sync. The failure is now visible: `bin/game prod status` prints each timer job's last result, and `bin/game prod check` fails on it (daydream/prodctl.py:728-730, daydream/prodcheck.py:147-155).
  Remediation: Run `sudo ops/install-prod.sh`, or install the two rendered units and run `systemctl daemon-reload`. Then start `daydream-keepsakes.service` once and confirm that `bin/game prod check` passes its job lines.

### The previous review's findings at this HEAD

| Finding | Status at `d9a8ac6` |
|---|---|
| NOTE 1: moderation by name acts on the wrong friend's toon | **Partly fixed.** An id match no longer wins outright. `_find_toons` returns every toon whose id or name matches the key, and the command refuses when there is more than one (admin.py:463-472; `test_a_toon_named_after_another_toons_id_is_ambiguous`). `/status/who` prints ids. Still open: the id display can be forged (NOTE 1 above), owners are not shown, and lookalike Unicode names are not folded. |
| NOTE 2: password changes stall the event loop | **Fixed.** Every attempt is charged before the await, and the verify and the hash run in a worker thread under the shared 4-slot cap (auth.py:198-209, accounts.py:306-323). This was re-run with the production argon2 profile against a loopback server. 20 concurrent changes by one account produced 5 attempts and 15 refusals (429). A `/healthz` from another client answered in 101 ms during the burst; the previous review measured 1282 ms. |
| NOTE 3: the timer-unit fix is not installed | **Still open on the box** (NOTE 2 above). The visibility half of its remediation is done: `prod status` and `prod check` now report each job's last result. |

### Traced and cleared this run (not findings)

- **Resting and re-entry.**
  - The kick endpoint marks the session left only when the caller's own session holds the toon, and only after the ownership gate (api/slots.py:236-245). The departure line and the journal entry are the same ones leave writes.
  - `_auto_enter` claims only the account's own toon (ws.py:129-139). `?since=` changes only whether it takes the toon from a live session. The `elsewhere` answer comes after the gate and the Origin check (ws.py:802-823).
  - A released toon (no controller, not resting) can be claimed only through the ownership checks in api/slots.py:204-207 or the own-toon list above. So `_release_others` (toons.py:287-293) opens nothing to another account. An open socket on a released toon keeps acting only for the session that held it, and only an admin with several toons can be in that state.
- **Sessions and passwords.**
  - Login looks accounts up by username only (accounts.py:326-348), so an account id is no longer a second name to guess against.
  - The pass list applies the 180-day cap (accounts.py:442-453). `created_at` is written in the same `_iso` format, so the string comparison is exact.
  - Starlette's cookie parser, like SimpleCookie, keeps the last of two same-name cookies (checked), so the swap changes nothing for cookie tossing. The gate, logout, the root page and the WebSocket all read the cookie through the same function.
  - The password change is now split around an await, which opens a window of tens of milliseconds between the old-password check and the write. If a reset invite were redeemed inside that window, a change still in flight from a session the reset had just ended would overwrite the new password and delete the owner's new session. The timing is not attacker-steerable, so this is not a finding. A compare-and-swap in `commit_password_change` would close it: `WHERE id = ? AND password_hash = <the hash read at verify>`, plus a check that the kept session still exists.
- **`bin/game prod check`.** The probes are read-only. The CLI's admin cookie goes only to the configured public origin, over `wss` with certificate verification. The websockets sync client does not follow redirects, and the anonymous probes carry no cookie.
- **Other prodctl and edge changes.**
  - `prod pull` now opens the world DB the service user wrote, as the operator, with default SQLite settings (prodctl.py:792-797). Daydream registers no SQL functions, and Python's sqlite3 leaves extension loading off. So a planted trigger or view can change only that DB's own rows, which the dev server loads next anyway. This is the trust `prod pull` already extends.
  - `needs_stop` and `_refuse_unreadable_paths` are operator conveniences. `bin/game` matches `--yes` and `--check` exactly, so the stop decision agrees with what the command will do.
  - `_node_env` (edge.py:239-251) finds node on PATH or in the operator's own `~/.nvm`.
- **The GPU lock file.** The arbiter opens `/srv/daydream/data/gpu.lock` without `O_NOFOLLOW`, in a directory the service can write (arbiter.py:102-112). `gpu_lock_path()` uses the file only when it exists, following links (config.py:248-257). A dangling link therefore turns the cross-process layer off instead of creating a file, and a link to an existing file is opened read-only and locked. The service could already stall dev's GPU use through the lock itself (carried forward below), so this adds no reach. `XP_YIELD_S` adds no surface.
- **The Worker, the SPA and the door.**
  - A 101 is rebuilt without `CF_*` Set-Cookie, and a refused upgrade goes through `rewriteResponse` (worker.js:69-80, 175-182). Upstream header scrubbing is unchanged.
  - The overlay note, the dreamer panel and the door all write with `textContent`. Narrations, including the new departure line on a kick, are escaped before entity linking (main.js:998-1023).
- **The browser test.** It serves on a loopback port, against a throwaway data dir, for a few seconds. Playwright is a dev extra and stays out of `ops/requirements-prod.lock`.
- **Secrets and PII.**
  - The credential scan found only test passwords and a placeholder token. There are no emails or phone numbers, and the names in tests are fictional.
  - `peter` appears in the ops test as the box's account name, which the installer rewrites (install-prod.sh:126).

### Carried forward (open, recorded 2026-09-27 and 2026-09-28, not yet decided)

- DNS (127.0.0.53) and AF_UNIX sockets leave the prod sandbox.
- Any local process can reach `127.0.0.1:54322` without Access and choose its own `X-Daydream-Client-IP`. This only moves throttle keys; the gate still applies.
- `gpu.lock` is writable by the service. Text calls give up after 90 s and renders after 20 s.
- Invite slugs are unsalted sha256 over about 983,000 phrases, so anyone with a copy of the accounts DB can recover every open slug.
- Strangers can keep invitations paused (20 failures an hour, 40 a day, global). `bin/game invite unblock` reopens them.
- On the Workers Free plan, an anonymous client can use up the daily request quota. The one WAF rule covers only the login and invite paths.
- The operator's Cloudflare token is account-wide, because Workers Scripts edit cannot be scoped to one Worker.
- Toon names are not unique. Moderation refuses any key that matches more than one toon by id or name, and `/status/who` shows ids. The id display can be forged (NOTE 1), and lookalike Unicode names are not folded.
- A rest from the shell does not reach the player's open socket, and their next connect wakes the toon. `account disable` is the stop, and docs/runbooks/friends.md says so.
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
*Prior review (2026-09-28, paths, commit `e05747c`): it covered the ten files changed by the fix commit `e05747c` and found 0 BLOCK / 0 WARN / 3 NOTE. The three NOTEs: moderation by name could act on the wrong friend's toon, because a toon could be named after another toon's id or use a homoglyph; password changes ran argon2 on the event loop and were never throttled when they succeeded; and the timer-unit fix was not installed, so the hourly keepsakes sync was failing. It also confirmed the fixes for the earlier concurrent-login and timer WARNs, and it later recorded the operator's decision on the Worker's cookie leak. Their status at this HEAD is in the table above. That entry is at `git show d9a8ac6:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"d9a8ac63aaec1e1764bca43210054da7377f7239","scope":"paths","scanned_files":["daydream/accounts.py","daydream/admin.py","daydream/api/auth.py","daydream/api/slots.py","daydream/api/ws.py","daydream/edge.py","daydream/gpu/arbiter.py","daydream/images/cli.py","daydream/prebake.py","daydream/prodcheck.py","daydream/prodctl.py","daydream/review.py","daydream/server.py","daydream/toons.py","edge/src/worker.js","edge/test/worker.test.js","pyproject.toml","tests/test_accounts.py","tests/test_admin_surfaces.py","tests/test_arbiter_xp.py","tests/test_auth.py","tests/test_backup.py","tests/test_browser_flow.py","tests/test_dreamer.py","tests/test_edge_ctl.py","tests/test_frontend.py","tests/test_ops_units.py","tests/test_prebake.py","tests/test_prodcheck.py","tests/test_prodctl.py","tests/test_runbooks.py","tests/test_slots.py","tests/test_web_paths.py","web/assets/door.js","web/assets/main.js"],"block":0,"warn":0,"note":2} -->
