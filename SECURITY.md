## Security Review — 2026-04-23 (scope: paths)

**Summary:** Reviewed `daydream/server.py` (the FastAPI app factory + middleware wiring + `/cache` route + static login/pre-frontend HTML). Verified the four-segment `/cache/{world}/{target_kind}/{target_id}/{filename}` route's path-traversal validation is sound (checks `/` and `..` on all segments plus `.png` suffix on filename; FastAPI URL-decodes before the handler so `..%2f` collapses to `../` which is caught). The cache route is intentionally unauthenticated so `<img src>` fetches work from the pre-auth login page; `AccessMiddleware` is the outer gate. `SessionMiddleware` uses `config.session_secret()` (env override or a 0600-mode per-install 48-byte urlsafe random file). `_LOGIN_HTML` and `_PRE_FRONTEND_HTML` are static constants with no user-input interpolation. Git history for `daydream/server.py` shows no secret leaks across the last 3 commits (logout form fix, unified image-gen cache layout, port-hygiene/access-middleware addition). No findings.

### Findings

No security issues identified.

### Accepted Risks

- Cookie `https_only=False` in `daydream/server.py:37` is documented inline ("friend-scope; box is on a private LAN/Tailscale only").
- No CSRF token on `/api/login` and `/api/logout`. Worst-case impact under the documented threat model is forced-logout from a phishing page; consistent with friend-scope posture.
- The 100.64.0.0/10 hardcoding in `daydream/api/access.py:25` is correct because Tailscale's CGNAT range is fixed by their design. A self-hosted Headscale with a custom range would need that constant updated. Documented in CLAUDE.md.
- `AccessMiddleware` reads `scope["client"][0]` directly rather than honoring forwarded-for headers. This is the secure default given uvicorn is not started with `--proxy-headers`. Operators who later put the app behind a reverse proxy must add `--forwarded-allow-ips` themselves AND audit that the proxy strips inbound `X-Forwarded-For`.
- `bin/game` sources `.env` and `~/.config/daydream/secrets.env` via `set -a; source`; a writable env file is equivalent to arbitrary code execution. Operator-controlled, gitignored, standard practice.
- `bin/game cmd_logs` (`bin/game:215-224`) passes `$1` through `_log_file` without validation; an operator typing `bin/game logs ../../etc/passwd` would resolve into `$RUNDIR/../../etc/passwd.log`. Operator-invoked only; anything the operator can `tail` through this path they can already read directly on the box. Carry-forward NOTE from CODEREVIEW.md, not a security finding under the friend-scope threat model.
- `bin/qpeek-bootstrap` clones `https://github.com/peterzat/qpeek` and runs `pip install -e` against it. Supply-chain dependency on the project owner's own GitHub account; same trust boundary as the rest of the dev toolchain.
- `/cache/{world}/{target_kind}/{target_id}/{filename}` in `daydream/server.py:77` is intentionally unauthenticated so pre-auth `<img src>` fetches render. `AccessMiddleware` is the real gate; segment validation blocks traversal.

---
*Prior review (2026-04-23, paths): reviewed 4 files (`bin/game`, `tests/test_frontend.py`, `web/assets/style.css`, `web/index.html`); `bin/game` unchanged from accepted posture; the new `test_logout_link_posts_not_gets` regression preserves the CSRF-aware logout shape; `web/index.html` is a static SPA shell; `web/assets/style.css` is presentational only; no findings.*

<!-- SECURITY_META: {"date":"2026-04-23","commit":"124340273a40dc2ec29fb403a81e93ef866da98b","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["daydream/server.py"]} -->
