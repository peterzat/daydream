## Review — 2026-04-22 (commit: f34121b)

**Summary:** Reviewed 11 unpushed commits totaling ~2.5k lines: v0 daydream from project skeleton through frontend SPA + lifecycle dispatcher (Inc 1-9). Tests are green (66/66). All BLOCK/WARN findings are resolved across two codefix cycles: session-secret default no longer bypasses the password gate (now per-install random with on-disk persistence), the WS event-loss race between snapshot and subscribe is closed (subscribe-first + dedup), and the cycle-1 regression that wrote to the developer's real `~/.config/daydream/` during tests is contained by a new `tests/conftest.py`.

**External reviewers:**
None reported findings (review-external.sh ran with empty output).

### Findings

[WARN-RESOLVED] daydream/config.py:50-66 — session_secret() writes outside the project tree during tests (FIXED)
  Resolution: Codefix added `tests/conftest.py` setting `DAYDREAM_SESSION_SECRET` and `HOME` via `os.environ.setdefault` before any test module imports. Verified the `~/.config/daydream/session_secret` mtime is unchanged after a fresh test run.

[WARN-RESOLVED] daydream/config.py:48-49 — SessionMiddleware secret defaults to a publicly known, source-committed string (FIXED)
  Resolution: Codefix replaced the hardcoded default with `secrets.token_urlsafe(48)` persisted at `~/.config/daydream/session_secret` (mode 0600), keyed off env-var override. CLAUDE.md updated to document the new behavior.

[WARN-RESOLVED] daydream/api/ws.py:91-93 — Event-loss race between snapshot send and subscribe (FIXED)
  Resolution: Codefix moved `events.subscribe()` before snapshot construction, pinned `last_seq = events.max_seq()` after subscribe, and added a dedup filter in `_broadcast_loop` for events with `seq <= snapshot_seq`. All 66 tests still pass.

[NOTE] daydream/events.py:117-122 — Unbounded subscriber queues
  Evidence: `_broadcast` calls `q.put_nowait(event)` on every subscriber; `subscribe()` returns a default `asyncio.Queue()` with no maxsize. An authenticated WS client that holds the connection open without reading grows memory unboundedly. Already noted inline as a v2 escape hatch.
  Suggested fix: Track in v2 backlog (concurrency / multi-CCU); no action for v0.

[NOTE] daydream/api/ws.py:97-104 — `asyncio.wait` done-set tasks are not awaited or `.exception()`-ed
  Evidence: `done, pending = await asyncio.wait(...)`; pending is cancelled but done is discarded without retrieving the result. If `_broadcast_loop` or `_receive_loop` raises something not caught by their `(WebSocketDisconnect, RuntimeError)` clauses (e.g., a transport-level `ConnectionResetError`), asyncio logs "Task exception was never retrieved" noise. Cosmetic; not a correctness bug.
  Suggested fix: After cancelling pending, iterate `done` and call `.exception()` on each; log if non-None. Optional.

[NOTE] bin/game:124-133 — `cmd_logs` accepts an unvalidated path component
  Evidence: `_log_file()` does `printf '%s/%s.log' "$RUNDIR" "$1"` with no sanitization, so `bin/game logs ../foo` reads `$RUNDIR/../foo.log`. Friend-scope, same-uid: no escalation, just messy. The `[[ -f "$logf" ]]` guard limits the harm to a `tail` of an existing file the operator can already read.
  Suggested fix: Restrict `$1` to a known allowlist (`fastapi`, plus future `vllm`, `comfyui` in v1) and reject anything else.

### Fixes Applied

Cycle 1 (codefix):
- [WARN] daydream/config.py:48-49 — replaced default secret with per-install random secret persisted to `~/.config/daydream/session_secret` (mode 0600); CLAUDE.md updated.
- [WARN] daydream/api/ws.py:91-93 — subscribe before snapshot, pin last_seq, broadcast loop dedups events with seq <= snapshot_seq.

Cycle 2 (codefix):
- [WARN] daydream/config.py:50-66 (regression from cycle 1) — added tests/conftest.py with `os.environ.setdefault` for `DAYDREAM_SESSION_SECRET` and `HOME` so fresh test runs no longer write to `~/.config/daydream/`.

### Accepted Risks

None carried forward (no prior review).

The following are documented in SECURITY.md's Accepted Risks and not re-reported here: hardcoded `REDACTED` default password (intentional friend-scope), `https_only=False` cookie (LAN/Tailscale only), no CSRF token on `/api/login` (friend-scope phishing impact only).

---

<!-- REVIEW_META: {"date":"2026-04-22","commit":"f34121b","reviewed_up_to":"f34121b7ea8f83aab4ae520e289328b06e60999b","base":"origin/main","tier":"full","block":0,"warn":0,"note":3} -->
