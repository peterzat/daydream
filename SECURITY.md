## Security Review — 2026-04-23 (scope: paths)

**Summary:** Reviewed `bin/game` (the lifecycle dispatcher: FastAPI, vLLM, and ComfyUI daemon control; `cmd_status`, `cmd_logs`, `cmd_image_test`, `cmd_world`, `cmd_test`; tailnet URL emission). The recent diff (`0d71017`) added `_tailnet_fqdn` / `_tailnet_ip` helpers that parse `tailscale status --json` and `tailscale ip -4` and interpolate results into printed URL strings only (not into subsequent command lines), so a hostile tailnet controller returning an unusual DNSName cannot reach a shell-execution sink. All external-engine CLI args (`$VLLM_MODEL`, `$VLLM_HOST`, `$VLLM_GPU_FRACTION`, `$VLLM_MAX_LEN`, `$COMFY_HOST`, `$COMFY_PORT`, `$PORT`) are operator-controlled environment inputs passed as properly-quoted argv elements, not eval'd. Git history for `bin/game` across the last 3 commits (`0d71017`, `9c37a0d`, `4d606e6`) shows no secret leaks. Accepted risks from prior reviews still apply unchanged.

### Findings

No security issues identified.

### Accepted Risks

- Cookie `https_only=False` in `daydream/server.py:37` is documented inline ("friend-scope; box is on a private LAN/Tailscale only").
- No CSRF token on `/api/login` and `/api/logout`. Worst-case impact under the documented threat model is forced-logout from a phishing page; consistent with friend-scope posture.
- The 100.64.0.0/10 hardcoding in `daydream/api/access.py:25` is correct because Tailscale's CGNAT range is fixed by their design. A self-hosted Headscale with a custom range would need that constant updated. Documented in CLAUDE.md.
- `AccessMiddleware` reads `scope["client"][0]` directly rather than honoring forwarded-for headers. This is the secure default given uvicorn is not started with `--proxy-headers`. Operators who later put the app behind a reverse proxy must add `--forwarded-allow-ips` themselves AND audit that the proxy strips inbound `X-Forwarded-For`.
- `bin/game` (lines 64-75) sources `.env` and `~/.config/daydream/secrets.env` via `set -a; source`; a writable env file is equivalent to arbitrary code execution. Operator-controlled, gitignored, standard practice.
- `bin/game cmd_logs` (`bin/game:251-260`) passes `$1` through `_log_file` without validation; an operator typing `bin/game logs ../../etc/passwd` would resolve into `$RUNDIR/../../etc/passwd.log`. Operator-invoked only; anything the operator can `tail` through this path they can already read directly on the box. Carry-forward NOTE from CODEREVIEW.md, not a security finding under the friend-scope threat model.
- `bin/qpeek-bootstrap` clones `https://github.com/peterzat/qpeek` and runs `pip install -e` against it. Supply-chain dependency on the project owner's own GitHub account; same trust boundary as the rest of the dev toolchain.
- `/cache/{world}/{target_kind}/{target_id}/{filename}` in `daydream/server.py:77` is intentionally unauthenticated so pre-auth `<img src>` fetches render. `AccessMiddleware` is the real gate; segment validation blocks traversal.

---
*Prior review (2026-04-23, paths): reviewed `daydream/server.py`; verified four-segment `/cache/...` path-traversal validation, `SessionMiddleware` secret source, static-HTML safety, and clean git history; no findings.*

<!-- SECURITY_META: {"date":"2026-04-23","commit":"0d71017abe7851b4448f10c03e7a9ea7bf61d2e4","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["bin/game"]} -->
