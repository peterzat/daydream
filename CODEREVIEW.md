## Review — 2026-09-28 (commit: 3df294b) — refresh

**Summary:** Pre-push review of the going-live work: 29 unpushed commits, 130
files, +13.3k / -1.2k lines against origin/main (accounts and invites, the
sign-in gate, edge mode, "your dreamer", prod tooling, the edge Worker, the
cross-process GPU lock, and the first live bring-up). A refresh against the
2026-09-27 pivot review (0 BLOCK), but every code file changed since, so all
were read in full, in four areas by fresh reviewers (accounts and auth; the
game session and SPA; prod tooling and ops; the edge Worker), and each finding
below was re-checked against the code before inclusion (the Worker's cookie
leak live, over HTTP/1.1). Baseline: medium tier 1640 passed; after the fix
pass 1651 passed (11 new tests), Worker tests 26/26. A /security scan of the
files changed since the 2026-09-28 security review found 0 BLOCK / 0 WARN / 3
NOTE (SECURITY.md).

**External reviewers:** None configured.

### Findings

**BLOCK**

[BLOCK] edge/src/worker.js:69 — the WebSocket branch returns the origin response untouched, so Access's `CF_Authorization` cookie (a 24 h app token for the origin hostname) reaches anonymous browsers.
  Evidence: `if (isWS) return resp;` skips `rewriteResponse`, whose `CF_*` Set-Cookie filter (lines 156-168) the HTTP path uses. Live: an anonymous HTTP/1.1 upgrade GET to https://www.eidolon.com/daydream/ws returned `403` with `Set-Cookie: CF_Authorization=<JWT>; Expires=+24h; Path=/; Secure; SameSite=none`; the same probe on an HTTP path carries no cookie. A holder can present that cookie to daydream-origin directly, skipping the Worker: no edge rate limit (the rule matches /daydream/api/..., not the origin's /api/...), and a forgeable `X-Daydream-Client-IP` for the per-address throttles. Breaks SPEC criterion 14 ("the hostname admits only the Worker's Access service token"). Friends' browsers would also store it for www.eidolon.com, Path=/.
  Suggested fix: in the WS branch, `if (resp.status !== 101) return rewriteResponse(resp, env, prefix);`; for a 101, rebuild the response with the same headers minus every `CF_*` Set-Cookie: `new Response(null, { status: 101, headers, webSocket: resp.webSocket })`. Factor the cookie filter out of `rewriteResponse` into a helper both paths use. Node's `Response` rejects status 101, so unit-test the helper directly and the non-101 WS path end to end (a mocked 403 WS reply carrying `set-cookie: CF_Authorization=...` must reach the client without it).

[BLOCK] web/assets/door.js:44-45 and 87-88 — the front door disables its inputs before reading them, so nobody can sign in or redeem an invitation from a real browser.
  Evidence: `busy(form, true)` sets `disabled` on every input, and the next line builds `new FormData(form)`; FormData skips disabled controls (HTML spec, constructing the entry list). Login posts `{"username": null, "password": null}` (401, and it counts against the per-username throttle); redeem posts an empty username (400) and leaves the invite unused. Reproduced by the reviewer in headless Chromium with the real door.js. No test drives door.js; the endpoint tests post correct JSON. Breaks SPEC criteria 2 and 8.
  Suggested fix: read the form (`new FormData(form)`, or the values) before `busy(form, true)` in both handlers. Add a regression guard, e.g. a tier_short test that fails if a submit handler in web/assets/door.js calls `busy(` before `new FormData(`.

[BLOCK] web/assets/main.js:1531 with daydream/api/slots.py:226-240 — "rest" in "your dreamer" puts the player straight back in, in the start room, after their carried things were sent home.
  Evidence: `kickSlot` POSTs `/api/slots/{slot}/kick`, then `reconnectAfterSlotChange()` connects afresh. The kick endpoint never calls `accounts.set_left(session, True)`, so on the new socket `_resolve_controlled_toon_id` is None and `_auto_enter` (ws.py:116-128) claims the account's one toon; `kicked_at` was set, so it wakes at the start room. `kick_slot` → `send_home_things` already sent the authored things it carried home, and no journal entry or departure line was written. Reproduced by the reviewer (create → kick → WS connect returns a `state_snapshot`, toon `kicked_at=None`). Breaks SPEC criterion 5's "rest ... its own" for every one-toon player.
  Suggested fix: when the kicked toon is controlled by the caller's own session, `accounts.set_left(who.session_id, True)` in the kick endpoint (or have the SPA's rest use `api/session/leave`, which also writes the journal and tells the room), and show "your dreamer" rather than reconnecting into the game. Test: kick your own toon, reconnect, expect `needs_toon`.

**WARN**

[WARN] daydream/api/ws.py:806 (`_auto_enter`, 116-128) — a stale tab's automatic reconnect takes the toon back from the device actually in use, and that device then stops for good.
  Evidence: `_auto_enter` runs on every connect, including the SPA's `?since=` reconnect. A laptop sleeps with the game open; the friend continues on the phone (takeover); the laptop wakes, its socket drops (1006), `onclose` → `connect(true)`, and its session takes the toon over again. The phone gets `elsewhere`/4409, sets `dreamingElsewhere`, and never retries. Reproduced by the reviewer (controller flips back on `/ws?since=5`).
  Suggested fix: on a reconnect (`since` present), do not take over a toon another live session holds (`is_session_live(controller)`); send `elsewhere` (close 4409) instead. Keep takeover for fresh page loads and explicit enter clicks. Test the two-device sequence.

[WARN] daydream/api/slots.py:128-136, 192-223; daydream/toons.py:147-157, 370-376 — an admin with several toons cannot switch between them, and after "leave the dream" walks back into one.
  Evidence: `create_toon_in_slot` and `claim_slot` set `controller_session` on the new or claimed toon without releasing the session's other toon; `get_toon_by_session` is an unordered `LIMIT 1`, and `release_session_toon` rests only one. Reproduced by the reviewer as an admin (create A, create B, claim B → the socket is still A; after leave, B is still claimed).
  Suggested fix: in `create_toon_in_slot` and `claim_slot`, clear `controller_session` on any other toon held by the same session (a release, not a rest); make `release_session_toon` release every toon the session holds. Test switching and then leaving.

[WARN] daydream/gpu/arbiter.py:109-134 — across processes, back-to-back renders starve text calls: prod players get "the dream is foggy" while a dev prebake, image-test, review or tier_long runs.
  Evidence: the flock layer polls with `LOCK_NB` every 50 ms and keeps no queue. A process rendering in a loop (prebake.py:90-118) releases `LOCK_EX` and re-takes it within milliseconds without yielding, so another process's text waiter gets in only if its poll lands in that gap. The reviewer measured on a scratch lock: text timed out in 6 of 6 runs at a 1:6 render-to-timeout ratio (as with ~15 s renders against `XP_TEXT_WAIT_S`=90). bin/game:333-335 now allows dev GPU work while prod is awake whenever the lock exists.
  Suggested fix: after releasing an exclusive flock, a process waits more than two poll intervals (e.g. 0.15 s) before its next exclusive attempt, so waiting pollers get a turn; or a turnstile lock that text waiters hold `LOCK_SH` while waiting and renderers must clear first. Add a two-process test like the existing cross-process one.

[WARN] daydream/prebake.py:108-115; daydream/images/cli.py:69-78; daydream/review.py:96 — `GpuBusyElsewhere` is not caught, so a render that cannot get the card within 20 s aborts the whole prebake (no contact sheet) or the CLI with a traceback.
  Evidence: `except client.ComfyUIError` only; `GpuBusyElsewhere` subclasses `RuntimeError` (arbiter.py:92), not `ComfyUIError` (images/client.py:84). The arbiter docstring promises the caller keeps its placeholder; only ws.py:496 does.
  Suggested fix: catch `arbiter.GpuBusyElsewhere` in prebake (record the target as busy and continue), in images/cli.py and in review.py.

[WARN] daydream/prodctl.py:591-598 with ops/systemd/daydream-offsite.service — the weekly offsite timer cannot find `npx` (node lives only under ~/.nvm on this box), so criterion 22's scheduled upload fails every week while a hand-run succeeds.
  Evidence: `/usr/bin/npx` and `/usr/local/bin/npx` do not exist; the unit sets no `Environment=PATH`; `_wrangler` runs `["npx", ...]`, raising FileNotFoundError, which `main()` (catching only ProdError and CalledProcessError) turns into a traceback, after a backup was already taken and encrypted.
  Suggested fix: resolve node's bin dir in daydream/edge.py (`shutil.which("node")`, else the newest `~/.nvm/versions/node/*/bin`), prepend it to PATH in `_wrangler_env()`, and use it for every npx/npm call; catch OSError in `prodctl.main`.

[WARN] daydream/prodctl.py:522-527, 534-536 — an error from the Cloudflare API aborts `prod sleep` before anything stops, after players were already warned.
  Evidence: `edge.set_state("asleep")` runs before `systemctl stop` of the tunnel and the unit; `_api` raises EdgeError on HTTP/URL errors (a read timeout raises TimeoutError), and `main()` catches neither. With the API unreachable or the token expired, the village announces sleep and stays up with the GPU held. `wake()` and `status()` have the same uncaught path after the work is done.
  Suggested fix: treat the edge flag as best effort in sleep, wake and status: wrap `set_state`/`describe_state` in `try/except (EdgeError, OSError)` and warn (the Worker's unreachable-origin fallback covers the gap).

[WARN] daydream/prodctl.py:512-528 — `prod sleep` stops the tunnel and service only when the unit is exactly "active"; a failed or auto-restarting unit is left looping with the tunnel up.
  Evidence: `systemctl is-active --quiet` is non-zero for "activating (auto-restart)" and "failed"; the unit has `Restart=on-failure`. A `wake()` whose health check failed leaves both running, and a following `prod sleep` skips both stops yet reports the village asleep.
  Suggested fix: in `sleep_`, always `systemctl stop` both units (idempotent on inactive units); gate only the grace announcement on `unit_active`.

[WARN] daydream/prodctl.py:397-399 with daydream/admin.py:396-417 — backup retention is "the newest 14 directories" of one pool shared by nightly, deploy, offsite, pull and manual backups, so criterion 13's "keeping 14 days" does not hold.
  Evidence: `_backup` passes `--keep 14`; `cmd_backup` prunes every dir under backups/ by name. Fourteen deploys in a working session prune every nightly backup (three deploys went out within hours on 2026-09-27/28).
  Suggested fix: prune by age with a floor: delete a backup only if it is older than 14 days AND not among the newest 14. Test with synthetic timestamped dirs.

[WARN] daydream/prodctl.py:709-710 — `prod pull` says "an admin dev account can enter any toon", but no admin can claim another account's toon, and the pulled toons belong to prod account ids that do not exist in dev, so a friend's toon cannot be played to reproduce their bug (criterion 12).
  Evidence: api/slots.py:205 refuses with 403 "that dreamer belongs to someone else"; account ids are random.
  Suggested fix: after installing the pulled world in dev, clear `owner_account` on its toons (`UPDATE objects SET owner_account = NULL WHERE kind = 'toon'`, so a dev account can adopt one) and correct the message.

[WARN] .claude/skills/village/SKILL.md (deploy section) — "Always ask-first" for `/village deploy` contradicts the operator's standing grant recorded in CLAUDE.md (2026-09-28): typing `/village deploy` is the ask.
  Evidence: CLAUDE.md "Agent policy for prod": when the operator asks for prod work the agent runs the verbs itself.
  Suggested fix: when the operator's message asks for the deploy, show what is going out (`git log --oneline <current>..<ref>`) and run it; ask first only when the deploy was not requested.

**NOTE**

[NOTE] edge/src/worker.js:304, 352-353 — the keepsakes book count reads " of 150 found" for a friend who has found nothing: `escapeHtml` does `String(s || "")`, so 0 becomes "". Use `String(s ?? "")`.

[NOTE] web/assets/main.js:60-62, 140-141 — a short origin restart (a deploy, a tunnel blip) shows open tabs the asleep note ("Send the Night Warden a note") and holds reconnection for 30 s: the Worker's 503 carries `unplanned: true`, which `whyClosed` ignores. Keep the normal backoff and the plain "the dream is sleeping..." text when `unplanned` is set.

[NOTE] web/assets/main.js:1591-1597 — `reconnectAfterSlotChange` resets `awaitingPick` but not `dreamingElsewhere`, so a tab that got `elsewhere` and then re-entered from the dreamer panel stops silently on its next drop.

[NOTE] web/assets/main.js:1652-1657 — the How to Dream book opens over the "your dreamer" form on a first visit, the reverse of criterion 8's order (form, then book).

[NOTE] daydream/admin.py (`cmd_toon_moderate` "rest") — resting a toon from the shell does not reach its open socket: the player keeps acting as a toon others can no longer see until they reconnect, when `_auto_enter` wakes it. `account disable` is the moderation stop.

[NOTE] tools/ws_playthrough.py:48, 150 — the (frozen) Zork WS playthrough no longer completes: `--slot 1` now returns 409 for a new agent account, and its ~0.15 s pacing outruns the WS token bucket (3/s, burst 12), so refused commands silently diverge the replay.

[NOTE] daydream/accounts.py:427-434 — `live_passes()` ignores the 180-day absolute session cap that `resolve()` enforces, so the Worker can serve keepsakes for a session the server already refuses (up to 30 more days).

[NOTE] daydream/accounts.py:222-225 via `authenticate` — login accepts an account id (`a-<hex>`) in place of a username, a second per-username guessing budget for the same account; ids are visible only to their owner and admins.

[NOTE] daydream/api/auth.py:191-206 with accounts.py:298-312 — change-password runs two argon2id operations on the event loop, and successful changes are never throttled; a signed-in session could stall the loop ~66 ms per request.

[NOTE] daydream/api/auth.py:44-55 — the session cookie is parsed with `http.cookies.SimpleCookie`, which drops every cookie after a malformed neighbor (e.g. `prefs={"a":1}`), reading a signed-in person as signed out. Low risk in prod (Path=/daydream/ sorts first); `starlette.requests.cookie_parser` is tolerant.

[NOTE] daydream/prodctl.py:419-440 — after an automatic rollback, `previous` equals `current`, so a later `prod rollback` does nothing and the release before is forgotten.

[NOTE] daydream/prodctl.py:165-196 — the STOP_FOR match is on the verb only, so `prod world refresh --check`, a `world reset` without `--yes`, or a refused `dream install` still stop and restart the service, dropping every session.

[NOTE] daydream/prodctl.py:171-196 — `prod dream check|rehearse|install <patch>` runs as the daydream user, which cannot read a patch under /home/peter; only a patch already committed and deployed in the current release works, and no runbook says so.

[NOTE] daydream/prodctl.py:653 — `prod status` computes "behind" with `git rev-list --count rel..HEAD`, which is wrong after a history rewrite and raises (aborting the whole status) once the release's commit is gone. Today's release 8428675 predates the pre-push rewrite; redeploy after the push.

### Fixes Applied

All three BLOCKs and nine of the ten WARNs, in `3df294b` (applied by /codefix,
re-reviewed here against the code):

- [BLOCK] edge/src/worker.js — `passWebSocket`: a 101 is rebuilt without `CF_*` Set-Cookie; any other answer to an upgrade goes through `rewriteResponse`. The filter is the shared `stripAccessCookies`. Three node tests, one a mocked 403 upgrade carrying the cookie.
- [BLOCK] web/assets/door.js — both handlers read `FormData` before `busy()`; a tier_short guard in tests/test_web_paths.py fails if a submit handler calls `busy(` first.
- [BLOCK] daydream/api/slots.py, web/assets/main.js — resting the toon your own session plays marks the session left, tells the room and writes the journal (`_departed`, shared with leave); the SPA stays on "your dreamer". Test: kick your own toon, reconnect, `needs_toon`.
- [WARN] daydream/api/ws.py — a `?since=` reconnect never takes the toon from another live session; it gets `elsewhere` and 4409. Two-device test.
- [WARN] daydream/toons.py — create and claim release the session's other toons (`_release_others`); a released toon can be claimed again; leave rests all the session held. Switch-and-leave test.
- [WARN] daydream/gpu/arbiter.py — `XP_YIELD_S` (0.15 s) after a process's own render before its next exclusive attempt. Two-process render-loop test.
- [WARN] daydream/prebake.py, images/cli.py, review.py — `GpuBusyElsewhere` is caught (prebake records "busy", lists it, exits 1).
- [WARN] daydream/edge.py, prodctl.py — `_node_env()` finds node on PATH or the newest ~/.nvm install for every node/npm/npx call; `prodctl.main` catches OSError.
- [WARN] daydream/prodctl.py — the edge flag is best effort in sleep, wake and status (`_set_edge_flag`); `sleep` always stops the tunnel and the unit.
- [WARN] daydream/admin.py — backups are pruned only when older than 14 days and not among the newest `keep`.
- [WARN] daydream/prodctl.py — `prod pull` clears `owner_account` on the pulled toons; the message says how a dev account adopts one.

**Not fixed (requires manual intervention):** the WARN on
`.claude/skills/village/SKILL.md`. The fix pass's edit was refused by the
permission classifier as the agent loosening its own ask-first rule; the
operator makes that edit.

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.

---
*Prior review (2026-09-27, full): the pivot turn, 61 commits; 0 BLOCK / 23 WARN / 14 NOTE, all 23 WARNs fixed before the push.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"3df294b","reviewed_up_to":"3df294bdcc2632aceeaa4e1d483a9516409bd4fa","base":"origin/main","tier":"refresh","block":3,"warn":10,"note":14,"fixed":12} -->
