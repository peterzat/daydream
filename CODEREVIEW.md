## Review — 2026-06-30 (commit: 195e73b)

**Summary:** Full-depth review of the session-and-presence + world-hot-swap stack
against `origin/main` (originally the 14-commit stack at `00889a8`, 26 files
+1576/-81): the **world-hot-swap** feature (`POST /api/world/swap` +
`db.swap_live_db` + `events.WORLD_CHANGED` + `bin/game world swap`) and the
**session & presence** pass (room descriptions on entry, fresh-session empty log,
"leave the dream" → picker, permanent toon delete, per-world starting room, keyless
`world load`, GPU-assuming `bin/game up`). The prior CODEREVIEW entry (`46321a9`) was
a docs-only light review that predates this stack, so all of it was reviewed at full
depth. **2 WARN were found and both fixed in this push** (`195e73b`); see Fixes
Applied. Tests green after the fixes: `bin/game test medium` 527 passed / 9 deselected.
Security chain run on the 16-file code surface, CSRF WARN resolved (see SECURITY.md).
0 BLOCK / 0 WARN outstanding.

**External reviewers:** None configured. (`review-external.sh` is on PATH but no
provider keys are set in `~/.config/claude-reviewers/.env`.)

### Findings

[WARN — FIXED] daydream/api/slots.py:134-157 — CSRF on the new bodyless POST endpoints
(`leave_session`, `delete_toon`) in the default `tailscale` access mode.
  Evidence: `auth.is_authed()` returns `True` unconditionally in tailscale mode
  (`daydream/api/auth.py`), so the `daydream_session` cookie's `SameSite=Lax` is never
  consulted; `AccessMiddleware` gates only on source IP ∈ `100.64.0.0/10`; and
  `delete`/`kick`/`leave` read nothing from the body, so a cross-origin top-level form
  POST is a "simple request" (no CORS preflight). A tailnet member who loads an
  attacker page becomes a confused deputy: a forged POST to
  `http://<victim-tailnet-ip>:54321/api/slots/N/delete` carries the victim's own
  tailnet source IP (AccessMiddleware passes), needs no cookie (auth ignores it), and
  needs no body. Effect: permanent toon deletion cascading to its items + memories
  (`toons.delete_slot`), or kick, or forced leave. This turn adds `delete`, the first
  *irreversible* verb in the family, and the prior accepted-risk rationale ("SameSite
  blocks the cookie; AccessMiddleware blocks off-tailnet POSTs") does not hold in the
  default mode. Recorded in SECURITY.md (path-scoped scan, 00889a8).
  Suggested fix: an Origin/Referer check on the state-changing POST endpoints that
  rejects ONLY when the header is present AND its scheme+host+port mismatches the
  request's — requests with no Origin/Referer pass, preserving the non-browser
  `bin/game world swap` CLI (`urllib`, no Origin) and the TestClient suite. Classified
  WARN, not BLOCK: bounded to game-state griefing in an explicitly friend-scoped app,
  requires knowing the victim's tailnet address+port. Whether to harden now vs. carry
  to v2 (with the per-session-ownership work) is a human decision — not auto-fixed.

[WARN — FIXED] daydream/server.py:29,33 + daydream/drift.py:589-612 — the FastAPI lifespan
stores its own `drift_handle` and stops drift via that explicit handle, but a world
swap replaces the module-level `drift._handle` with a fresh task. After any swap, the
lifespan's local points at the old (already-cancelled) task, so shutdown-after-swap
takes the early-return branch in `stop_drift_loop(stale_handle)` and never cancels the
live post-swap drift task — it leaks to event-loop teardown.
  Evidence: `perform_world_swap` calls `await drift.stop_drift_loop()` (no arg → stops
  `_handle`) then `drift.start_drift_loop()` (sets `_handle = T1`); the lifespan still
  holds `T0` and calls `stop_drift_loop(T0)`, where `T0.done()` is True and
  `T0 is _handle` is False, so `_handle`/`T1` is untouched. Impact is low (shutdown
  path only; loop teardown cancels T1 anyway, possibly with a "Task pending" warning or
  a drift tick re-opening the connection after `close_db()`); no data corruption (drift
  writes are atomic single appends). But it is a dual-source-of-truth defect introduced
  by this change. `tests/test_ws_swap.py::test_drift_loop_survives_swap` covers the
  runtime swap but not shutdown-after-swap.
  Suggested fix: have the lifespan shutdown call `await drift.stop_drift_loop()` with no
  argument (always targets the live module handle); drop the unused `drift_handle` local.

[NOTE] daydream/db.py:swap_live_db / daydream/api/world.py:perform_world_swap — swapping
to the live DB path itself (`target` resolves to `live.db`) fails: `os.replace(live,
backup)` moves the file out from under the subsequent `shutil.copyfile(target, live)`,
raising FileNotFoundError. The rollback path restores the original world cleanly and the
endpoint returns 500, so it is safe (no data loss), just a confusing error for a no-op
request. Optional: short-circuit when `resolved == config.live_db_path()`.

### Fixes Applied

Both WARNs fixed in commit `195e73b` (operator approved fixing all findings before
pushing):

- [WARN] CSRF on bodyless POSTs → new `daydream/api/csrf.py` `CsrfOriginMiddleware`
  (pure ASGI, registered in `daydream/server.py` ahead of `AccessMiddleware`). Rejects
  403 any unsafe-method HTTP request whose `Origin`/`Referer` netloc != `Host`;
  absent-Origin passes (non-browser CLI / curl / tests), safe methods incl. the WS
  upgrade GET are never gated. Compares against the request's own `Host`, so it needs no
  hostname allowlist. Paired tests: `tests/test_csrf_middleware.py` (6 cases).
- [WARN] drift-handle staleness → `daydream/server.py` lifespan now calls
  `await drift.stop_drift_loop()` with no argument (targets the module-tracked live task
  instead of the stale startup handle). Paired regression test:
  `tests/test_ws_swap.py::test_lifespan_shutdown_after_swap_stops_live_drift` drives the
  real lifespan through a swap + context-exit.

The remaining NOTE (swap-to-the-live-DB-itself FileNotFoundError-then-safe-restore) was
left as-is: it is benign (no data loss; returns 500 on a no-op request).

### Accepted Risks

Carried forward from the prior security/review history (unchanged), with this turn's
extension noted:

- **Friend-scope on the slot/session endpoints (EXTENDED this turn).** Any authed
  session may create/claim/kick/**delete**/leave any slot; `delete` additionally and
  permanently destroys the toon's items + memories. Per-session ownership is v2
  (`multi-user-shared-world`), documented in SPEC 2026-06-29. The CSRF WARN above is the
  confused-deputy sharpening of this same surface and is the one item this turn newly
  exposes as irreversible.
- Cookie `https_only=False` (`daydream/server.py:42`); friend-scope, LAN/Tailscale only.
- No CSRF token on `/api/login`, `/api/logout`, or the slot endpoints (see WARN; the
  prior SameSite/AccessMiddleware rationale is now known not to cover tailscale mode).
- The `100.64.0.0/10` Tailscale CGNAT hardcoding (`daydream/api/access.py`).
- `AccessMiddleware` reads `scope["client"][0]` directly (no forwarded-for trust).
- Tailscale-mode `POST /api/login` short-circuit to `authed=True`; `is_authed` bypass.
- `_ensure_session_id` stamps a fresh UUID in tailscale mode without `/api/login`.
- `/cache/...` static route and `/status/drift` intentionally unauthenticated;
  `AccessMiddleware` is the gate.
- LLM-controllable `toon_id` in `set_mood` effects; stored prompt-injection via captured
  memory text; `bin/{vllm,memory}-bootstrap` `$MODEL` heredoc interpolation;
  `bin/game cmd_logs` unvalidated path component; `bin/qpeek-bootstrap` clone — all
  operator-trust / v2-`skills-authoring-and-security` class.
- Unbounded request body on `POST /api/slots/{slot}/create`; unbounded event-subscriber
  queues (`daydream/events.py`).

### Carried-forward open NOTEs (pre-existing, not aggravated this turn)

The prior entry's register of small NOTEs in untouched code persists (admin.py cascade
non-transactional; bootstrap.py `_write_db` non-transactional + skill `room_slug` not
cross-checked; drift.py `_GENERIC_DRIFT_POOL` comment depth; various stale comments /
dead CSS / docstring drifts). None are in code this turn changed in a way that resolves
or worsens them; see git history at `46321a9` for the full list.

---
*Prior review (2026-05-27, commit 46321a9): light docs-only review of the `GOAL.md`
attempt-2 retrospective. 0 BLOCK / 0 WARN; verified commit hashes, links, test counts,
no secrets. Predates this code stack entirely (it is an ancestor of origin/main).*

<!-- REVIEW_META: {"date":"2026-06-30","commit":"195e73b","reviewed_up_to":"195e73bb299266c52632281f17874e52fcb8293e","base":"origin/main","tier":"full","block":0,"warn":0,"note":1} -->
