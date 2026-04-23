## Security Review — 2026-04-23 (scope: paths)

**Summary:** Reviewed 10 paths covering the FastAPI app shell, the outer middleware trio (`AccessMiddleware` wrapper is out of scope but the route guard in `server.py` and the `NoCacheAssetsMiddleware` header rewriter are in), the authenticated WS endpoint (`ws.py`), the password + session auth router (`auth.py`), the deterministic core skills (`core.py` + `registry.py`), the toon read/move helpers (`toons.py`), the multi-room migration (`004_multi_room.sql`), and the entire SPA surface (`web/index.html`, `web/assets/main.js`, `web/assets/style.css`). Every SQL call is parameterized; the `/cache/{world}/{target_kind}/{target_id}/{filename}` route validates all four segments against `/` and `..` and enforces a `.png` suffix. The SPA uses `textContent` for every user-reachable event-payload render except the `say` render, which builds HTML via a template literal and runs both the speaker name and the spoken text through the `escape()` helper that covers `&`, `<`, `>`, and `"` (sufficient for a textual HTML context). The `bg.src` assignment consumes `room.image_url` built server-side from DB-seeded world/room IDs, not attacker input. `FK ON` via `PRAGMA foreign_keys = ON` in `db.py` backs the "invalid target room raises IntegrityError" promise in `toons.set_current_room`. Git history for `daydream/api/auth.py` across the last three commits shows an old `DAYDREAM_PASSWORD` default value that was already externalized to env in commit `4b6cde0`; that prior-state secret is out of scope for this path-scoped review and was resolved before the current HEAD. All prior accepted risks still apply unchanged.

### Findings

No security issues identified.

### Accepted Risks

- Cookie `https_only=False` in `daydream/server.py:38` is documented inline ("friend-scope; box is on a private LAN/Tailscale only").
- No CSRF token on `/api/login` and `/api/logout`. `SessionMiddleware` defaults to `SameSite=Lax`, which blocks cross-site POST from carrying the session cookie; the worst-case residual impact under the documented threat model is forced-logout from a same-site phishing page, consistent with friend-scope posture.
- The 100.64.0.0/10 hardcoding in `daydream/api/access.py:25` is correct because Tailscale's CGNAT range is fixed by their design. A self-hosted Headscale with a custom range would need that constant updated. Documented in CLAUDE.md.
- `AccessMiddleware` reads `scope["client"][0]` directly rather than honoring forwarded-for headers. This is the secure default given uvicorn is not started with `--proxy-headers`. Operators who later put the app behind a reverse proxy must add `--forwarded-allow-ips` themselves AND audit that the proxy strips inbound `X-Forwarded-For`.
- `bin/game` sources `.env` and `~/.config/daydream/secrets.env` via `set -a; source`; a writable env file is equivalent to arbitrary code execution. Operator-controlled, gitignored, standard practice.
- `bin/game cmd_logs` passes `$1` through `_log_file` without validation; an operator typing `bin/game logs ../../etc/passwd` would resolve into `$RUNDIR/../../etc/passwd.log`. Operator-invoked only; anything the operator can `tail` through this path they can already read directly on the box.
- `bin/qpeek-bootstrap` clones `https://github.com/peterzat/qpeek` and runs `pip install -e` against it. Supply-chain dependency on the project owner's own GitHub account; same trust boundary as the rest of the dev toolchain.
- `/cache/{world}/{target_kind}/{target_id}/{filename}` in `daydream/server.py:91` is intentionally unauthenticated so pre-auth `<img src>` fetches render. `AccessMiddleware` is the real gate; segment validation blocks traversal.
- Tailscale-mode `POST /api/login` at `daydream/api/auth.py:32-34` short-circuits to `authed=True` + redirect without checking the password. Deliberate: `AccessMiddleware` has already CGNAT-gated the request, so the password check would be redundant ceremony. Documented in the module docstring and in CLAUDE.md "Auth" + "Network access" sections.

---
*Prior review (2026-04-23, paths): reviewed `bin/game`; verified tailnet FQDN/IP helpers interpolate only into printed URL strings, external-engine CLI args are passed as properly-quoted argv, and recent git history holds no secret leaks; no findings.*

<!-- SECURITY_META: {"date":"2026-04-23","commit":"db60c0f42c01cf5cfe355dc73f2f4d10aaa6df29","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["daydream/api/auth.py","daydream/api/nocache.py","daydream/api/ws.py","daydream/server.py","daydream/skills/core.py","daydream/skills/registry.py","daydream/toons.py","migrations/004_multi_room.sql","web/assets/main.js","web/assets/style.css","web/index.html"]} -->
