## Security Review — 2026-04-22 (scope: paths)

**Summary:** One WARN finding: the SessionMiddleware secret defaults to a public, source-committed value, and a deployment that omits the override silently allows session-cookie forgery that bypasses the password gate. Otherwise the in-scope code is consistent with its documented friend-scope threat model: parameterized SQL, whitelisted skill dispatch, escaped event rendering, and Tailscale-only network posture.

### Findings

[WARN] daydream/config.py:48-49 — SessionMiddleware secret defaults to a publicly known string
  Attack vector: An attacker who reaches the FastAPI port (anyone on the box's tailnet, plus anyone who later widens exposure or runs locally) can craft a session cookie signed with the published default and present it to /ws or /. SessionMiddleware accepts it as `{"authed": True}`, fully bypassing the documented password gate. The default is labeled "not_prod" in source but nothing at startup refuses to boot with it, and bin/game does not enforce that DAYDREAM_SESSION_SECRET is set in the sourced secrets.env.
  Evidence: `daydream/config.py:48-49` returns `os.environ.get("DAYDREAM_SESSION_SECRET", "daydream-dev-secret-not-prod")`; `daydream/server.py:29` passes it directly to SessionMiddleware; `bin/game:25-31` sources `~/.config/daydream/secrets.env` but never checks the variable is set.
  Remediation: Either (a) generate a per-install random secret on first boot and persist it under `~/.config/daydream/` (mirrors the password-source pattern), or (b) make `session_secret()` raise at startup when the env var is unset / equals the default sentinel, with a one-line message pointing at the secrets.env file. Document the variable next to `DAYDREAM_PASSWORD` in CLAUDE.md / README so operators know to set both.

[NOTE] daydream/events.py:117-122 — Unbounded subscriber queue allows a slow WS consumer to grow memory without bound
  Attack vector: Authenticated friend-scope only; an attacker who has already passed the password gate can hold a websocket open without reading and force events to accumulate in `asyncio.Queue` instances forever. Memory growth is the only impact; no escalation.
  Evidence: `daydream/events.py:120-121` calls `q.put_nowait(event)` on every subscriber, with no `maxsize`. The code comment (`# Unbounded queues, so put_nowait never blocks; the slow-consumer escape hatch lands in v2`) explicitly defers this.
  Remediation: Cap queue size and drop or disconnect on overflow once v1 introduces additional event sources. Tracked in code as a v2 item; flagging here for visibility, not as a blocker.

### Accepted Risks

- ~~Hardcoded default password in `daydream/config.py:45` is intentional per the friend-scope, Tailscale-only threat model.~~ **Resolved 2026-04-23:** the source no longer carries any default password. `password()` returns `""` when `DAYDREAM_PASSWORD` is unset and the auth endpoint refuses logins with a 503. The shared password lives in `.env` (gitignored, sourced by `bin/game`) or `~/.config/daydream/secrets.env`.
- Cookie `https_only=False` in `daydream/server.py:32` is documented inline ("friend-scope; box is on a private LAN/Tailscale only").
- No CSRF token on `/api/login` and `/api/logout`. Worst-case impact under the documented threat model is forced-logout from a phishing page; consistent with friend-scope posture.

---
*No prior review.*

<!-- SECURITY_META: {"date":"2026-04-22","commit":"f34121b7ea8f83aab4ae520e289328b06e60999b","scope":"paths","block":0,"warn":1,"note":1,"scanned_files":[".gitignore","bin/game","daydream/__init__.py","daydream/__main__.py","daydream/api/__init__.py","daydream/api/auth.py","daydream/api/ws.py","daydream/config.py","daydream/db.py","daydream/events.py","daydream/items.py","daydream/llm/__init__.py","daydream/llm/client.py","daydream/llm/prompts.py","daydream/rooms.py","daydream/server.py","daydream/skills/__init__.py","daydream/skills/core.py","daydream/skills/interpreter.py","daydream/skills/registry.py","daydream/toons.py","migrations/001_initial.sql","pyproject.toml","tools/gen_placeholder.py","web/assets/main.js","web/assets/style.css","web/index.html"]} -->
