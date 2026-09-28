# SECURITY.md

## Security Review — 2026-09-28 (scope: changes-only)

**Summary:** The working tree was clean, so this run reviewed what landed after the 2026-09-27 full audit: the fixes for its findings, the versioned operator skills, the Night Warden title, the deploy and WebSocket tweaks, and the docs that go public on the next push. The fixes hold at the web boundary, but three things regressed or slipped through: argon2 moved off the event loop in a way that lets concurrent logins skip the per-username throttle; the privilege drop to the service user broke the hourly keepsakes and weekly offsite timers; and the invite skill carries the surname the last review removed (0 BLOCK / 3 WARN / 4 NOTE).

### Scope and method

Reviewed the tree diff from the last scanned commit (`bb6e82e`, since rewritten out of main) to HEAD `52c7f35`: 38 code files (the API layer, accounts, prodctl, keepsakes, edge, admin, arbiter, `bin/game`, `ops/`, the Worker, `web/assets/main.js`), the two operator skills newly versioned under `.claude/skills/`, every changed Markdown file, and the local agent settings that CLAUDE.md now documents. Functions touched by the diff were read in full with their callers. Three findings were reproduced against throwaway data dirs (the login race, the ambiguous moderation delete, the capped-receive hang), and the sudo check ran `/usr/bin/true` as the service user. Every commit beyond origin/main was scanned for credential patterns, on main and on the local backup refs, and the installed prod units and timers were read on the box.

### Findings

[WARN] daydream/api/auth.py:145-154 — the login throttle is no longer atomic: the budget check runs before `await asyncio.to_thread(accounts.authenticate, ...)` and failures are recorded after it, so concurrent attempts all pass the check.
  Attack vector: an anonymous client, or several addresses acting together, sends a burst of concurrent `POST /api/login` requests for one friend's username. Every request that arrives before the first failures are recorded (roughly the first 100 ms of a burst, while the thread pool works through argon2id) passes `throttled()` and gets a real password check. Behind the edge rule (5 requests per 10 s per address), each address adds up to 5 guesses per burst. The per-username budget of 5 per 15 minutes becomes about 5 per participating address per 15 minutes, so a common 10-character password gets far more tries than the 2026-09-27 review assumed.
  Evidence: `throttled` at auth.py:145-147, the await at auth.py:150, `record_failure` at auth.py:152-154. Reproduced in edge mode against a throwaway data dir with the real argon2id profile (33 ms per verification). 40 sequential wrong-password logins for one username produced 5 password checks and 35 refusals; 200 concurrent ones from distinct client addresses produced 200 password checks and no refusals. Peak RSS reached about 1.7 GB, because up to 24 verifications of 64 MiB each run at once in the default executor. The 2026-09-27 remediation asked for check and record to stay atomic; the synchronous call they replaced kept them so.
  Remediation: charge before the await (record the attempt against both keys on the event loop, run argon2, clear the username key on success), or hold a per-username `asyncio.Lock` across check, verify and record. Either way, bound hashing with a small semaphore (2 to 4) so a flood costs bounded memory. Add a test that fires concurrent logins through `httpx.ASGITransport` and asserts at most 5 password checks.

[WARN] ops/systemd/daydream-keepsakes.service:13, ops/systemd/daydream-offsite.service:12, daydream/prodctl.py:131-135 — the hourly keepsakes sync (while awake) and the weekly offsite backup can no longer run from their timers. Both units set `NoNewPrivileges=yes`, and since `4ab3ab5` both jobs drop to the service user through sudo, which that flag forbids.
  Attack vector: not attacker-driven; a control that fails silently. SPEC criterion 16 makes revocation reach the edge "at the next sync", and while the village is awake the hourly sync is that sync. A friend disabled, or a lost device's session revoked, while awake stays on the Worker's pass list until the operator next runs `prod sleep` or `prod keepsakes` by hand. Meanwhile the Worker serves that pass its keepsakes (journal, book, portrait) whenever the origin fails (`edge/src/worker.js:63-67`, the unplanned-outage fallback). The weekly job (criterion 22) produces no offsite copy. A hand-run `bin/game prod offsite` still succeeds, so a manual demonstration would pass while the timer fails every week.
  Evidence: both units run as the operator with `NoNewPrivileges=yes`, and the installed copies match. `as_prod` prefixes `sudo -n -u daydream` (prodctl.py:134). `run_release_python` uses it for the keepsakes export (edge.py:216) and for `_backup` (prodctl.py:397), which `offsite` calls first (prodctl.py:608); `run_as_prod_bytes` uses it for the offsite tar. On this box, `setpriv --no-new-privs sudo -n -u daydream /usr/bin/true` exits 1 ("The "no new privileges" flag is set, which prevents sudo from running as root"); without the flag it exits 0. The recent keepsakes runs in the journal all found the village asleep, a branch that returns before the export. Prod is awake now, so the next hourly run takes the failing branch. The offsite timer next fires on Sunday, 2026-10-04.
  Remediation: remove `NoNewPrivileges=yes` from these two operator units (they run as the operator, who may already drop to `daydream`; keep `PrivateTmp`), or move the service-user half into its own `User=daydream` unit. Make a failed run visible (`OnFailure=`, or each timer's last result in `bin/game prod status`), and add a test that fails when a unit running `bin/game prod keepsakes|offsite` sets `NoNewPrivileges`.

[WARN] .claude/skills/invite/SKILL.md:13-14 — the example invitee name pairs a fictional first name with the real surname that the 2026-09-27 review asked to remove.
  Attack vector: the repository is public. `d11278c` versions this file and is not yet on origin/main, so the next push publishes the surname in a skill about inviting the operator's friends, tying it to the operator and to this invite-only service. The history was rewritten twice to keep that name out.
  Evidence: the surname occurs 17 times in `6bf3187` (the first rewrite's backup of the pre-scrub history; the prior review counted 17 occurrences of the full name), and nowhere else at HEAD. It is not reproduced here.
  Remediation: use the fictional name the tests use, and fold the change into `d11278c` before the first push so no public commit carries it. Then confirm that `git log -p origin/main..main` has no match for the surname.

[NOTE] local refs `refs/heads/backup/pre-scrub-2026-09-28`, `refs/original-2026-09-28/refs/heads/main`, `refs/original/refs/heads/main` — the pre-rewrite histories are still local refs, and they hold what the rewrites removed.
  Attack vector: none while only main is pushed (`push.default` is unset, so git's `simple` default applies, and origin has no mirror refspec). `git push --all` would publish the backup branch, whose intermediate `docs/CLOUDFLARE-SETUP.md` holds the box's public IPv4 and IPv6 addresses and a 32-hex id (most likely the Cloudflare account id). `git push --mirror` would also publish `refs/original/*`, which holds the removed full name.
  Remediation: once the rewritten main is confirmed, delete the backup branch and the two `refs/original*` refs (`git branch -D`, `git update-ref -d`) and let `git gc` drop the objects, or keep the backup outside this repository.

[NOTE] .claude/settings.local.json:4-5 (local, untracked; documented at CLAUDE.md:204 and in SPEC criterion 18) — the operator's standing grant, `Bash(bin/game prod *)` and `Bash(bin/game edge *)`, removes the permission prompt as a backstop against prompt injection for every prod and edge verb, including those that mint credentials or publish text.
  Attack vector: the agent reads player-authored text by design (`prod dream digest`, `prod play` output, toon names in `prod status`). If such text steers the agent, two pre-allowed commands form a path to the operator's admin account with no prompt: `bin/game prod invite reset <admin>` mints a set-a-new-password link, and `bin/game edge sleep "<note>"` publishes it on the public, pre-login asleep page (`prod play` could also say it in the village). `prod account role <user> admin` and `prod world reset --yes` are covered as well. The written policy ("unasked, a verb that drops sessions or changes prod data still asks first") now rests on the agent's judgment alone, and the 2026-09-27 NOTE's fix (pre-allowing only `invite create|list`) no longer applies.
  Remediation: keep the grant, but add `ask` rules (Claude Code checks them before `allow` rules) for the verbs that mint credentials, change roles, publish text or destroy data: `bin/game prod invite reset*`, `bin/game prod account*`, `bin/game edge sleep*`, `bin/game prod world reset*`, `bin/game prod world delete*`. Otherwise, record the grant under Accepted Risks.

[NOTE] daydream/admin.py:454-460 — `bin/game world rest-toon|delete-toon <name>` acts on the first toon whose id or case-insensitive name matches, and toon names are not unique.
  Attack vector: a griefer names a toon after another friend's, then misbehaves. The operator runs `bin/game prod world delete-toon <name>`, and the innocent friend's toon is deleted instead. The deletion is irreversible short of a backup restore, and the printed id reveals the mistake only afterwards.
  Evidence: `_find_toon` loops over an unordered `_query` (no ORDER BY) and returns the first match. Reproduced against a throwaway data dir: two accounts each created a toon with the same name (slots 2 and 3), and `cmd_toon_moderate(<name>, "delete")` deleted the first friend's toon (slot 2) and left the copycat's.
  Remediation: match an exact id first. For a name, refuse when more than one toon matches, and list each match's slot, id and owner username.

[NOTE] daydream/api/gate.py:78-99 — latent: once `_capped` truncates a streamed body, every later `receive()` returns an empty `http.request` without awaiting, never `http.disconnect`. Any consumer that loops on `receive()` until disconnect therefore never yields, and the event loop freezes.
  Attack vector: none today, because no route returns a streaming response. Starlette's `StreamingResponse` is such a consumer under uvicorn, which reports ASGI spec 2.3. If a streaming route is ever added, one chunked request body over 64 KiB (no Content-Length, so the up-front 413 does not apply) to it would hang the whole server.
  Evidence: a scratch harness that wrapped `StreamingResponse` in `gate._capped` and sent a 120 KiB chunked body hung until killed, and even a 1 s `asyncio.wait_for` never fired. The same harness without the wrapper returned normally.
  Remediation: after truncation, pass later calls through to the real `receive` (or return `{"type": "http.disconnect"}`).

### Resolution (2026-09-28, before the push)

| Finding | Resolution |
|---|---|
| WARN 1: concurrent logins skip the username budget | Fixed: the attempt is recorded against both keys before the await (no await between check and record), a right password takes back its address attempt (`accounts.forgive_one`) and clears the username key, and at most 4 argon2 checks run at once (`_HASH_SLOTS`). Tests: a 20-request concurrent burst gets at most 5 checks; repeated right logins never exhaust the address budget. |
| WARN 2: timers cannot drop to the service user | Fixed in `ops/systemd`: the keepsakes and offsite units no longer set `NoNewPrivileges` (the prod service keeps it); `tests/test_ops_units.py` pins both. The installed copies update on the next `sudo ops/install-prod.sh`. Failure visibility (`OnFailure=`, timer results in `prod status`) is not done yet. |
| WARN 3: the surname in the invite skill | Fixed by rewriting the unpushed commit that versions the skill (the fictional Robin Ash throughout), so no pushed commit carries it. |
| NOTE 1: backup refs hold scrubbed data | Accepted until the push is confirmed; then the backup branch and `refs/original*` are deleted. |
| NOTE 2: the standing grant removes the prompt | Kept the grant (the operator's explicit wish) and added local `ask` rules for `prod invite reset`, `prod account role|create` and `prod world reset|delete`. `edge sleep`/`prod sleep` notes stay unprompted: with `invite reset` prompting, the described chain to an admin reset link is broken. |
| NOTE 3: moderation by name picks the first match | Fixed: an exact id wins; a name matching more than one toon is refused with each match's id and slot. Test in `tests/test_slots.py`. |
| NOTE 4: capped receive spins after the cut | Fixed: after truncation the wrapper awaits the real `receive` and hides further body bytes. Test in `tests/test_edge_access.py`. |

### The 2026-09-27 findings at this HEAD

| Finding | Status |
|---|---|
| WARN 1: operator tooling follows service-planted paths | Fixed. Data-dir work runs as `daydream`, the operator receives only bytes, and no operator-side read or write into the data dir remains in prodctl. The two timer units cannot use the new path (WARN 2 above). |
| WARN 2: revocation missed idle sockets | Fixed: a 30 s session watchdog per socket, plus the SPA's 25 s keepalive through the per-frame check. |
| WARN 3: command frames skipped the cap | Fixed: every frame is capped at 2000 characters before parsing, with `--ws-max-size 16384`. A command's text can still be about four times the 500-character typed cap. |
| WARN 4: strangers can pause invitations | Mitigated: `bin/game invite unblock`. The global cap stays (residual). |
| WARN 5: admin web session over friends' toons | Fixed: no admin bypass in claim, kick or delete. Moderation moved to the shell (NOTE 3 above). |
| WARN 6: real name in the repo | Fixed on main's tracked history. The surname returns in the invite skill (WARN 3), and local backup refs hold the full name (NOTE 1). |
| NOTE: Origin ignored the scheme | Fixed for both CSRF and the WebSocket handshake (one function). |
| NOTE: `$` patterns on the asleep page | Fixed: function replacements, with a test. |
| NOTE: username squatting | Fixed: `cli-*`, `agent-*` and a few names are refused at invite redemption, and keepsakes skip them. |
| NOTE: pre-allowed invite verbs | Superseded by the standing grant (NOTE 2). |
| NOTE: unbounded pre-login bodies | Fixed: 413 over 64 KiB, and streamed bodies are truncated (latent defect: NOTE 4). |
| NOTE: login throttling | IPv6 is keyed on its /64. Moving argon2 off the event loop opened the race in WARN 1. |
| NOTE: shared capacity | Partly fixed: a reconnect replays at most 300 events. There are no per-account limits on create, delete or leave, and the WS bucket is per connection. |
| NOTE: box addresses in docs | Fixed at HEAD; still in a local backup ref (NOTE 1). |
| NOTE: supply-chain pinning | Open, unchanged: the lock has versions, not hashes, and CI actions use tags. |

### Traced and cleared this run (not findings)

- **The privilege drop.** `/home/peter` is 0750, so an unsandboxed `sudo -u daydream` process cannot read the operator's home. The prod venv is an isolated `python3 -m venv` (no user site-packages) under operator-owned, read-only releases. Commands run with `cwd` set to the release and `env -i`. The prod lock has no torch or sentence-transformers, and memories are off, so nothing loads a model from the service-writable `HOME` cache. Under `DAYDREAM_LIFECYCLE=external`, the passthrough verbs reach no `curl` or `git` call, so a planted `.curlrc` or `.gitconfig` in the data dir is never read. Portraits are read with `O_NOFOLLOW` inside a resolved cache root, restore refuses non-regular files, and `prebake --from-cache` stages only the operator's own art into an operator-owned directory.
- **Sessions.** The absolute 180-day cap is enforced in `resolve`, and the watchdog closes an idle socket with 4401 within 30 s of a disable or revoke. Failures in the watchdog close the socket (fail closed). Reserved usernames cannot be taken by invitees.
- **The deploy gate.** The test worktree's `.venv` symlink is removed by `git worktree remove --force` and `shutil.rmtree`, and neither follows links into the dev venv.
- **Secrets and history.** No credentials appear in any commit beyond origin/main, on main or on the backup refs. The only 32-hex value at HEAD is the KV namespace id in `edge/wrangler.toml`, an identifier rather than a credential. Passwords reach the CLI only through `getpass` or stdin, so sudo's command log holds none. The IPv6 literals in the new tests are `2001:db8::/32` documentation addresses.
- **Docs going public.** No emails, phone numbers or box addresses. The hostnames are already public, and `docs/CLOUDFLARE-SETUP.md` now keeps instance values out, pointing to the untracked `instance/NOTES.md` (confirmed ignored).

### Carried forward (open, recorded 2026-09-27, not yet decided)

- DNS (127.0.0.53) and AF_UNIX sockets leave the prod sandbox.
- Any local process can reach `127.0.0.1:54322` without Access and choose its own `X-Daydream-Client-IP`. This moves throttle keys only; the gate still applies.
- `gpu.lock` is service-writable. Text calls now give up after 90 s and renders after 20 s.
- Invite slugs are unsalted sha256 over about 983,000 phrases, so a copy of the accounts DB yields every open slug.
- Strangers can keep invitations paused (20 failures an hour, 40 a day, global); `bin/game invite unblock` reopens them.
- On the Workers Free plan, an anonymous client can spend the daily request quota; the one WAF rule covers only the login and invite paths.
- The operator's Cloudflare token is account-wide (Workers Scripts edit cannot be scoped to one Worker).
- Toon names are not unique (see NOTE 3).
- Another repository's concern: `www.eidolon.com/generate` accepts anonymous POSTs that spend Workers AI, on the origin daydream shares.

### Accepted Risks

Accepted by the operator for going live (`docs/GOING-LIVE.md` section 9, design approved 2026-09-27):

- **The engines run as `peter`.** vLLM (`:8000`) and ComfyUI (`:8188`) listen unauthenticated on loopback and run as `peter`, who is in the docker group. The prod service user can reach both, so an exploitable bug in either engine's API is a path from a compromised service to root. Later fix: a separate engines user.
- **The pre-login surface is public** (door, login, invite redemption, static assets): throttled in the app and rate-limited at the edge, within the limits of WARN 1 above and the residuals.
- **Friends drive shared-world verbs on shared objects:** the co-op design; there is no griefing economy.
- **What friends type reaches the local LLM:** role separation, length caps, input and output banlists, and strict validation apply.

Carried register:

- **LLM-emitted effects take an unscoped, LLM-chosen target id** on the data-skill paths (talk for NPCs without a voice sheet, room-affordance data skills). Neither path exists in the live Lost Hours world. v2 `skills-authoring-and-security`.
- **Parser raw player input is not role-separated** before the grounding call; the output is strictly re-grounded to a closed verb and an in-scope id.
- **NPC dialogue and growth prompt injection via player input:** role-separator wrapped, length-capped, input-banlist-checked; output structured, validated and banlist-scanned before mutation. Refusal `reason` text is narrated without an output-banlist pass and renders through escaped sinks.
- **Operator-trust world envelopes and `bin/game`:** `world load`/`reset` content, `reset`'s `rm -rf`, dev `.env` and `secrets.env` sourcing (prod reads neither), the dev `0.0.0.0` bind, the deprecated `bootstrap_world` path. None take network input.
- **Event queues are bounded** (256, drop-oldest).

---
*Prior review (2026-09-27, full, commit `bb6e82e`): the internet-exposure audit before going live, 0 BLOCK / 6 WARN / 9 NOTE. It found operator tooling following service-planted paths, revocation missing idle sockets, uncapped command frames, a global invite cap strangers could spend, an admin web session reaching friends' toons, and a real name in the repo, plus nine hardening notes. All but the supply-chain NOTE were fixed or mitigated the same day; their status at this HEAD is in the table above. The full entry (threat model, trust boundaries, resolution table) is `git show 97129e2:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"52c7f351ba441aacbd108d2b00f3a729998d3741","scope":"changes-only","base":"bb6e82eec20ecdc43f70968d8835185ce048916b","block":0,"warn":3,"note":4} -->
