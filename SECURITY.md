## Security Review — 2026-04-23 (scope: paths)

**Summary:** Reviewed 4 files (`bin/game`, `tests/test_frontend.py`, `web/assets/style.css`, `web/index.html`). `bin/game` is the lifecycle dispatcher reviewed in prior rounds; re-checked for secret leaks and path-handling drift since the `cmd_up` readiness-poll refactor (9c37a0d) and found both unchanged from accepted posture. The new `test_logout_link_posts_not_gets` regression (881a6dc) asserts the logout control is a POST form, preserving the CSRF-aware shape for logout which was documented as an accepted risk. `web/index.html` is a static SPA shell with no server-side templating (nothing for injection to reach) and the logout form shape matches the test. `web/assets/style.css` is presentational only — no selectors or content pulled from user input. No findings.

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

---
*Prior review (2026-04-23, paths): reviewed 15 files covering the tiered-test dispatcher, `bin/qpeek-bootstrap`, drift-probe harness, and `daydream/admin.py` / `config.py` / `bin/game` / test scaffolding; the prior BLOCK (tar path-traversal CVE-2007-4559 in `cmd_restore`) was verified fixed with pre-check plus `filter="data"` and regression test; zero new findings.*

<!-- SECURITY_META: {"date":"2026-04-23","commit":"9c37a0db38992e66a3a3c485ec18aef150fc5cb0","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["bin/game","tests/test_frontend.py","web/assets/style.css","web/index.html"]} -->
