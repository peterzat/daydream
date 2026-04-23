## Review — 2026-04-23 (commit: 0d71017)

**Review scope:** Refresh review. Focus: 1 file changed since prior review (commit 1243402): `bin/game`. No already-reviewed files touched since; the focus file is the only diff. Full-depth review applied.

**Summary:** One unpushed commit (`0d71017` — "bin/game up: emit tailnet FQDN + IP, drop localhost and short hostname") adds `_tailnet_fqdn` / `_tailnet_ip` helpers and rewrites `cmd_up`'s URL emission. Review caught one BLOCK: the new helper pipelines crashed `bin/game up` under `set -euo pipefail` when tailscale is installed but the daemon is down (pipefail propagated tailscale's non-zero exit and `set -e` aborted the `local fqdn; fqdn="$(...)"` assignment before the documented hostname-fallback branch could fire). Fix applied via `/codefix`: wrap the fqdn pipeline in `{ ...; } || true` and append `|| true` to the ip pipeline. Fix re-verified end-to-end under a failing-tailscale stub (fallback branch reached, exit 0) and under the healthy case (FQDN + IP still emit). Tests: 212/212 medium tier, matches prior baseline. Security scan ran over `bin/game`; no findings.

**External reviewers:**
review-external.sh ran with empty stdout and no cost log content.

### Findings

[BLOCK] bin/game:92-105 — `_tailnet_fqdn` / `_tailnet_ip` crash `bin/game up` under `set -euo pipefail` when tailscale is installed but the daemon is down. **Fixed.**
  Evidence: Script runs under `set -euo pipefail` (line 15). Both helpers end with a pipeline where the first stage is `tailscale status --json 2>/dev/null` or `tailscale ip -4 2>/dev/null`. When the tailscale daemon is down or the node is logged out, `tailscale` exits non-zero; `pipefail` propagates that as the pipeline exit, and `set -e` aborted at `local fqdn; fqdn="$(_tailnet_fqdn)"` on line 174. Reproduced with a `tailscale` stub that exits 1: the script printed "listening:" and then exited 1 without reaching the hostname-fallback branch at line 182. `_start_fastapi` already ran by that point, so uvicorn WAS up, but the operator saw a silent crash with no URL output and a non-zero exit from `bin/game up`. The commit message's promised hostname fallback fired only when `command -v tailscale` failed (tailscale not installed), not when the daemon was uncontactable.

### Carry-forwards (still applicable from the 2026-04-23 entry against 1243402)

The 11 NOTEs from the prior entry apply unchanged to files this diff does not touch:

[NOTE] web/assets/style.css:156-157 — `footer a` / `footer a:hover` rules dead after 881a6dc. One-line cleanup, no functional impact.

[NOTE] bin/game:132-144 — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s. Matches normal case (curl fast-refuse against unbound ports); comment-precision nit.

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual drift catcher is `tests/drift/test_drift_constants.py::test_whimsy_prompt_suffix_matches_code_constant`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384. Field is currently dead (unread); wiring it up would trip all three probes.

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide. Doc/impl drift, not a detection gap.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning (removal in Pillow 14 / 2027-10-15); `pyproject.toml` pins `Pillow>=10.0` with no upper bound.

[NOTE] README.md:70 and CLAUDE.md:201 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`. The `images/test/human-review/` sub-path is also missing from the CLAUDE.md file-layout block.

[NOTE] README.md:36 — `bin/game world` one-liner still lists "list / archive / delete"; missing `restore` and `verify`.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`. Latent today (WS production path never passes overrides).

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB is in autocommit mode).

[NOTE] daydream/events.py:117-122, daydream/api/ws.py:200, bin/game:215-224 — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.

### Fixes Applied

[BLOCK] bin/game:92-105 — wrapped `_tailnet_fqdn`'s awk/sed pipeline in `{ ...; } || true` and appended `|| true` to `_tailnet_ip`'s `head -1` pipeline, so a non-zero `tailscale` exit no longer trips `set -euo pipefail`. Verified: with a failing `tailscale` stub the helpers return empty strings and the existing `if [[ -z "$fqdn" && -z "$ip" ]]` fallback branch at line 182 emits the hostname URL; healthy case still emits FQDN + IP.

### Accepted Risks

Unchanged from prior entry. Documented in SECURITY.md: `https_only=False` cookie (friend-scope LAN/Tailscale), no CSRF token on `/api/login` and `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly (secure default; documented operator caveat for reverse-proxy deployments), the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env` as shell (operator-controlled gitignored files), `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek` (self-trust boundary), and `bin/game cmd_logs` unvalidated path component (operator-invoked only).

---
*Prior review (2026-04-23, commit 1243402): no BLOCK/WARN/NOTE against the diff; 11 NOTEs carried forward. The fallback-HTML-logout NOTE from 9c37a0d was resolved by 1243402.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"0d71017","reviewed_up_to":"0d71017abe7851b4448f10c03e7a9ea7bf61d2e4","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":11} -->
