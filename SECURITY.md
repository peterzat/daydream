## Security Review — 2026-04-22 (scope: paths)

**Summary:** No findings in the reviewed scope. The new `AccessMiddleware` is a sound HTTP/WS-layer access gate: it reads the TCP-connected peer IP from the ASGI scope (not request headers, so X-Forwarded-For cannot spoof source), default-denies on unknown / non-tailnet / missing client info, fails closed on env-var typos, and runs ahead of session/auth machinery. `bin/game` no longer binds vLLM/ComfyUI to `0.0.0.0` and the FastAPI port moved off 8080 to 54321. Test scaffolding correctly bypasses the middleware via `DAYDREAM_ACCESS=public` for `TestClient` while exercising the middleware contract directly with mocked ASGI scopes.

### Findings

No security issues identified.

### Accepted Risks

- Cookie `https_only=False` in `daydream/server.py:37` is documented inline ("friend-scope; box is on a private LAN/Tailscale only").
- No CSRF token on `/api/login` and `/api/logout`. Worst-case impact under the documented threat model is forced-logout from a phishing page; consistent with friend-scope posture.
- The 100.64.0.0/10 hardcoding in `daydream/api/access.py:25` is correct because Tailscale's CGNAT range is fixed by their design. A self-hosted Headscale with a custom range would need that constant updated. Documented in CLAUDE.md.
- `AccessMiddleware` reads `scope["client"][0]` directly rather than honoring forwarded-for headers. This is the secure default given uvicorn is not started with `--proxy-headers`. Operators who later put the app behind a reverse proxy must add `--forwarded-allow-ips` themselves AND audit that the proxy strips inbound `X-Forwarded-For`.

---
*Prior review (2026-04-22): one WARN — SessionMiddleware secret defaulted to a publicly known string. Resolved: per-install random secret persisted under `~/.config/daydream/session_secret` mode 0600.*

<!-- SECURITY_META: {"date":"2026-04-22","commit":"54f84bc734d04896a96990df5626a6ea216cb041","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":[".env.example","bin/game","daydream/api/access.py","daydream/config.py","daydream/server.py","tests/conftest.py","tests/test_access_middleware.py"]} -->
</content>
</invoke>