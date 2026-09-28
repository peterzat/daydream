# SECURITY.md

## Security Review — 2026-09-28 (scope: paths)

**Summary:** This path-scoped review covers the 14 code, test and web files changed from `7f9af5a` to `0aa9792`: arrivals that skip ambient beats and keep their cut for the whole visit, four log lines that no longer print model output, the awake page's visible notices, and the iPad layout work with its screen matrix. There is no BLOCK or WARN, and nothing new. One NOTE carries over from outside these paths and was re-verified on the box: the installed timer units still set `NoNewPrivileges`, so the hourly keepsakes sync still fails while prod is awake (0 BLOCK / 0 WARN / 1 NOTE).

### Scope and method

The 14 scanned files are every code, test and web file changed from `7f9af5a` to `0aa9792`: `a71a119` (ambient beats), `7624e4a` (the iPad and the layout matrix) and `842a856` (the fixes for the pre-push code review's 11 WARNs). Every diff was read in full, along with the code each change touches or calls: `_state_snapshot`, the WebSocket endpoint and the broadcast loop in `api/ws.py`; `events.fetch_since`; the drift tick; the LLM client's error messages and every runtime site that catches `LLMUnavailable`; and in `main.js` the awake page, the dreamer panel, `asleepText` and every sink the changed code writes to. The rest of `drift.py`, `growth.py`, `journal.py` and `skills/data.py`, new to this review's paths, was searched for logging calls, SQL, template rendering and other sinks. A scratch test drove the fresh-connect replay path through the real WebSocket against a throwaway data dir. The installed units, the timer results and the keepsakes journal were read on the box (read-only). The last three commits of each scanned file were scanned for credential patterns and token-shaped values, and the full diff of the seven commits not yet on origin/main for this instance's ids, account names and the operator's name. The scanned tests pass (100 passed; the two WebKit screens skip, because WebKit needs system libraries on this box).

### Findings

[NOTE] ops/systemd/daydream-keepsakes.service, ops/systemd/daydream-offsite.service (the installed copies: /etc/systemd/system/daydream-keepsakes.service:13, daydream-offsite.service:12) — Carried from the previous three reviews and re-verified; outside this review's paths. The repo fix is still not installed. Both installed units set `NoNewPrivileges=yes`, and the hourly keepsakes sync fails whenever prod is awake.
  Attack vector: Unchanged. While the village is awake, a disabled account or a revoked session stays on the Worker's pass list, and the Worker serves that pass its keepsakes whenever the origin is unreachable. The weekly offsite run, due Sunday 2026-10-04, will fail the same way.
  Evidence: Both installed units set the flag; the repo copies no longer do. The 05:01 UTC run exited 1 with `sudo: The "no new privileges" flag is set`, and the unit is `failed`. The next run is at 06:02 UTC. `bin/game prod check` fails on the job line (daydream/prodcheck.py:151-168).
  Remediation: Run `sudo ops/install-prod.sh`, or install the two rendered units and run `systemctl daemon-reload`. Then start `daydream-keepsakes.service` once and confirm that `bin/game prod check` passes its job lines.

### The previous review's findings at this HEAD

| Finding | Status at `0aa9792` |
|---|---|
| NOTE: the timer-unit fix is not installed | **Still open on the box** (the NOTE above). |
| Its statement that no log line carries typed text | **It missed one path, now closed.** The pre-push code review found it. An `LLMUnavailable` for a non-JSON reply carries up to 200 characters of raw model output (llm/client.py:171). The journal, growth, data-skill and drift prompts can quote the player's own words, so four log lines, one of them at WARNING, could put typed text in the prod journal. `842a856` logs only the exception's type at all four (journal.py:129-130, growth.py:520, skills/data.py:401, drift.py:487), and `test_an_outage_is_logged_without_the_models_words` holds it. No other runtime site logs that message at INFO or above. The parser keeps it in the private input log beside the typed line itself (ws.py:666-671). Dialogue collects failures as values (dialogue.py:404-410). The director and examine discard it (director.py:266, verbs.py:694), and retell logs it only at DEBUG (retell.py:188). |

### Traced and cleared this run (not findings)

- **The arrival cut.**
  - `skip_ambient` adds a constant clause with no parameters (events.py:151-152).
  - The cut keeps an event only if its seq is above the arrival's `last_seq` or in the arrival's kept set, and that set is built from the same filtered result (ws.py:246-258). Both only narrow a list the unchanged private-event filter already produced, so neither can show a toon a row addressed to someone else.
  - `view` belongs to one connection, whose toon is fixed at connect (ws.py:836, 865), so a cut never carries one toon's rows to another. A world swap clears it (ws.py:1053). The kept set holds at most 50 ints.
  - After a fresh page load or a reconnect there is no arrival, so the first same-room re-snapshot still replays the room's last 50 events whatever their age, ambient beats included. The scratch test confirmed this. Those are room broadcasts the private-event filter allows, so this is the playtest's reading problem on a second path, not an exposure. It was passed to the code review.
- **The `ambient` flag.** Only the drift tick sets it (drift.py:691), and only the arrival replay reads it. A line marked ambient is left out of a late arrival's replay and nothing else, so even a forged flag could only hide a line.
- **The awake page.** `notice` writes with `textContent` (main.js:1607-1616). `refused` navigates only to `document.baseURI`, the server-stamped `<base href>` (main.js:1618-1623). A 503 body's `operator` and `note` reach the page only through `asleepText`, into `textContent`. The retry button takes a function handler, and `#awake-note` is static markup in index.html.
- **The stylesheet and the viewport.** `viewport-fit=cover`, `env(safe-area-inset-*)` and `@supports` load no URLs and add no inline style, so the CSP is unchanged.
- **Image error text (pre-existing, ws.py:517-530).** A failed render puts the ComfyUI or exception message into the `room_image_ready` or `toon_image_ready` payload the room receives. The SPA never shows it (main.js:872). It can hold the loopback ComfyUI URL, a prompt id or a data-dir path, all documented in the public repo. The httpx errors carry no request body, so a typed appearance never rides along.
- **The layout matrix and the new browser tests.** They serve on a loopback port against a throwaway data dir with fictional accounts. `DAYDREAM_LAYOUT_SHOTS` only saves screenshots where the operator points it. The `sudo ... playwright install-deps` hint is skip-reason text and is never run.
- **Secrets, PII and the instance.** The scanned diffs and each scanned file's last three commits hold only the test password constant. The seven commits not yet on origin/main (their full diff, every file) hold no token-shaped value, none of this instance's ids or account names, and not the operator's name. The names in the playtest additions are Lost Hours residents, and `instance/` is still ignored.

### Carried forward (open, recorded 2026-09-27 and 2026-09-28, not yet decided)

- DNS (127.0.0.53) and AF_UNIX sockets leave the prod sandbox.
- Any local process can reach `127.0.0.1:54322` without Access and choose its own `X-Daydream-Client-IP`. This only moves throttle keys; the gate still applies.
- `gpu.lock` is writable by the service. Text calls give up after 90 s and renders after 20 s.
- Invite slugs are unsalted sha256 over about 983,000 phrases, so anyone with a copy of the accounts DB can recover every open slug.
- Strangers can keep invitations paused (20 failures an hour, 40 a day, global). `bin/game invite unblock` reopens them.
- On the Workers Free plan, an anonymous client can use up the daily request quota. The one WAF rule covers only the login and invite paths.
- The operator's Cloudflare token is account-wide, because Workers Scripts edit cannot be scoped to one Worker.
- Toon names are not unique, and lookalike Unicode names are not folded. Moderation refuses any key that matches more than one toon by id or name, and `/status/who` shows each toon's id first and its owner, which tells two lookalike names apart.
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
*Prior review (2026-09-28, paths, commit `7f9af5a`): it covered the 26 files changed from `d9a8ac6` to `7f9af5a` (the operating turn's 18 WARN fixes, the service's own log lines, the arrival replay window and the SPA's awake page) and found 0 BLOCK / 0 WARN / 1 NOTE: the installed timer units still set `NoNewPrivileges`, so the hourly keepsakes sync was failing. It confirmed the fix for the forgeable `/status/who` id column. Its statement that no log line carries typed text missed the model-error path (see the table above). That entry was not committed on its own; the one before it is at `git show 9b738f9:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"0aa9792b438eabe81c839a40ff8ebdaba5fa4230","scope":"paths","scanned_files":["daydream/api/ws.py","daydream/drift.py","daydream/events.py","daydream/growth.py","daydream/journal.py","daydream/skills/data.py","tests/test_browser_flow.py","tests/test_drift.py","tests/test_journal.py","tests/test_layout_screens.py","tests/test_ws_limits.py","web/assets/main.js","web/assets/style.css","web/index.html"],"block":0,"warn":0,"note":1} -->
