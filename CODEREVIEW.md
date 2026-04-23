## Review — 2026-04-22 (commit: 54f84bc)

**Summary:** Reviewed 2 unpushed commits (~410 lines): `35997ac` adds the `DAYDREAM_ACCESS` toggle (new `AccessMiddleware` ASGI middleware, port move 8080→54321, internal services to 127.0.0.1) plus a 172-line ASGI-direct test file; `54f84bc` refreshes README/CLAUDE for the new state. Tests are green (153/153) and the security scan returned 0 findings on the in-scope files. One NOTE on a bash/Python case-sensitivity gap in the UFW-reminder warning.

**External reviewers:**
None reported findings (review-external.sh ran with empty output).

### Findings

[NOTE] bin/game:25, bin/game:195 — `DAYDREAM_ACCESS` comparison is case-insensitive in Python (`config.access_mode()` does `.strip().lower()`) but case-sensitive in bash. An operator who writes `DAYDREAM_ACCESS=Public` (capitalized) in `.env` gets pass-through at the middleware (Python lowercases) but `bin/game status` does NOT print the UFW reminder (bash compares the raw value to `"public"`). Cosmetic / UX gap, not a security or correctness bug — the UFW warning is a reminder, not a guard.
  Suggested fix: lowercase in bash too: `ACCESS_MODE="${DAYDREAM_ACCESS:-tailscale}"; ACCESS_MODE="${ACCESS_MODE,,}"` (bash 4+ parameter expansion). Or document explicitly in `.env.example` that the value must be lowercase.

[NOTE] daydream/events.py:117-122 — Unbounded subscriber queues (carried forward from prior review).
  Evidence: `_broadcast` calls `q.put_nowait(event)` on every subscriber; `subscribe()` returns a default `asyncio.Queue()` with no maxsize. Already noted inline as a v2 escape hatch.
  Suggested fix: track in v2 backlog; no action for v0/v1.

[NOTE] daydream/api/ws.py:171 — `asyncio.wait` done-set tasks not `.exception()`-ed (carried forward from prior review).
  Evidence: `done, pending = await asyncio.wait(...)`; pending is cancelled but done is discarded without retrieving the result. Cosmetic; not a correctness bug.
  Suggested fix: after cancelling pending, iterate `done` and call `.exception()` on each. Optional.

[NOTE] bin/game:78, bin/game:202-211 — `cmd_logs` accepts an unvalidated path component (carried forward from prior review).
  Evidence: `_log_file()` does `printf '%s/%s.log' "$RUNDIR" "$1"` with no sanitization. Friend-scope, same-uid: no escalation, just messy.
  Suggested fix: restrict `$1` to a known allowlist (`fastapi`, `vllm`, `comfyui`).

### Fixes Applied

None. (No BLOCK/WARN findings; nothing to auto-fix.)

### Accepted Risks

The following are documented in SECURITY.md's Accepted Risks and not re-reported here: `https_only=False` cookie (LAN/Tailscale only) and no CSRF token on `/api/login` (friend-scope phishing impact only). The previously accepted hardcoded-default-password risk is now resolved: source carries no default; the password lives in `.env`.

---
*Prior review (2026-04-22, commit f34121b): reviewed 11 unpushed commits totaling ~2.5k lines (v0 daydream from skeleton through frontend SPA + lifecycle dispatcher, Inc 1-9). Two codefix cycles resolved all BLOCK/WARN findings: session-secret default no longer bypasses the password gate, the WS event-loss race between snapshot and subscribe was closed, and the test-time write to the developer's real `~/.config/daydream/` was contained by `tests/conftest.py`. Tests were green at 66/66 then. Original commit no longer in history (rewritten via `git filter-repo` to purge "mellon" cleartext per SPEC.md proposal).*

<!-- REVIEW_META: {"date":"2026-04-22","commit":"54f84bc","reviewed_up_to":"54f84bc734d04896a96990df5626a6ea216cb041","base":"origin/main","tier":"full","block":0,"warn":0,"note":4} -->
