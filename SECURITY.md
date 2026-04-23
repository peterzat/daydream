## Security Review — 2026-04-23 (scope: paths)

**Summary:** Reviewed 15 files covering the new tiered-test dispatcher (`daydream/testing/`), the `bin/qpeek-bootstrap` external-engine installer, the drift-probe test harness under `tests/drift/`, and the already-reviewed `daydream/admin.py` / `daydream/config.py` / `bin/game` / test scaffolding. The BLOCK from the prior review (tar path-traversal in `cmd_restore`, CVE-2007-4559) is verified fixed: `daydream/admin.py:302,309` pre-rejects `..` / absolute-path members AND passes `filter="data"` to `t.extract`, with regression coverage at `tests/test_admin.py:186-219`. No new findings. Subprocess usage in `daydream/testing/human_eval.py:84-99` is list-form (no shell) with arguments derived from project-tree files only; SQL in `daydream/admin.py` and `daydream/assets.py` is fully parameterized; `config.session_secret()` uses `secrets.token_urlsafe(48)` with 0o600 permissions; `tests/conftest.py` correctly sandboxes HOME and test-only credentials so production secrets never leak through the test harness.

### Findings

No security issues identified.

### Accepted Risks

- Cookie `https_only=False` in `daydream/server.py:37` is documented inline ("friend-scope; box is on a private LAN/Tailscale only").
- No CSRF token on `/api/login` and `/api/logout`. Worst-case impact under the documented threat model is forced-logout from a phishing page; consistent with friend-scope posture.
- The 100.64.0.0/10 hardcoding in `daydream/api/access.py:25` is correct because Tailscale's CGNAT range is fixed by their design. A self-hosted Headscale with a custom range would need that constant updated. Documented in CLAUDE.md.
- `AccessMiddleware` reads `scope["client"][0]` directly rather than honoring forwarded-for headers. This is the secure default given uvicorn is not started with `--proxy-headers`. Operators who later put the app behind a reverse proxy must add `--forwarded-allow-ips` themselves AND audit that the proxy strips inbound `X-Forwarded-For`.
- `bin/game` sources `.env` and `~/.config/daydream/secrets.env` via `set -a; source`; a writable env file is equivalent to arbitrary code execution. Operator-controlled, gitignored, standard practice.
- `bin/qpeek-bootstrap` clones `https://github.com/peterzat/qpeek` and runs `pip install -e` against it. Supply-chain dependency on the project owner's own GitHub account; same trust boundary as the rest of the dev toolchain.

---
*Prior review (2026-04-23, paths): one BLOCK (CVE-2007-4559 tar path-traversal in `cmd_restore`), now resolved with pre-check plus `filter="data"`; all other dimensions were clean.*

<!-- SECURITY_META: {"date":"2026-04-23","commit":"293a4a413374df2171282d29cc0b37e4f904fc89","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["bin/game","bin/qpeek-bootstrap","daydream/admin.py","daydream/config.py","daydream/testing/__init__.py","daydream/testing/__main__.py","daydream/testing/human_eval.py","tests/conftest.py","tests/drift/conftest.py","tests/drift/test_arbiter_smoke.py","tests/drift/test_drift_constants.py","tests/drift/test_image_perceptual.py","tests/drift/test_llm_json_adherence.py","tests/test_admin.py","tests/test_assets.py"]} -->
