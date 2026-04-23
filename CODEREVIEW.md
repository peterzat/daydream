## Review — 2026-04-23 (commit: 9c37a0d)

**Review scope:** Refresh review. Focus: 4 files changed since prior review (commit 293a4a4): `bin/game`, `tests/test_frontend.py`, `web/assets/style.css`, `web/index.html`. All 4 are new modifications since the prior review; full-depth review applied to all.

**Summary:** Two small commits since `293a4a4`: `881a6dc` (logout control fix — GET `<a>` to POST `<form>` + test) and `9c37a0d` (`bin/game up` UX polish — readiness poll, quieter curl probes, tailnet URL emit, drop of the wrong `command -v vllm` check). ~45 lines across 4 files. Tests remain green: short=156, medium=212 (+1 for new `test_logout_link_posts_not_gets`), long=221 available. Security scan ran over the 3 files new to the scanned surface (`tests/test_frontend.py`, `web/assets/style.css`, `web/index.html`) plus `bin/game`; zero findings. No BLOCK or WARN in this review; 3 new NOTEs (two follow-ons from the logout fix — a dormant fallback and an orphan CSS rule — plus a comment-precision nit in the `bin/game` poll). The 9 NOTEs from the prior review all remain in-scope carry-forwards (unchanged files).

**External reviewers:**
None reported findings (review-external.sh ran with empty stdout and no cost log content).

### Findings

[NOTE] daydream/server.py:124 — `_PRE_FRONTEND_HTML` fallback still uses `<a href="/api/logout">leave</a>`. This fallback is rendered only when `web/index.html` is missing from disk (server.py:57-60). Today `web/index.html` is git-committed and always present, so the fallback never fires in practice. However, the exact bug that commit `881a6dc` just fixed in `web/index.html` (GET on POST-only endpoint produces 405) is still latent in this fallback. If a future refactor deletes or moves `web/index.html`, the fallback's "leave" link would 405.
  Suggested fix: Either replace with `<form action="/api/logout" method="post" style="display:inline"><button type="submit">leave</button></form>`, or delete `_PRE_FRONTEND_HTML` outright since the v1 SPA has shipped and `web/index.html` is a permanent tree artifact.

[NOTE] web/assets/style.css:156-157 — `footer a` and `footer a:hover` rules are dead after `881a6dc`. No anchor tags exist anywhere in `web/` (`grep '<a ' web/` returns nothing). The rules will only re-activate if someone adds an `<a>` to the footer, which would likely want fresh styling anyway.
  Suggested fix: Delete lines 156-157. One-line cleanup, no functional impact either direction.

[NOTE] bin/game:132-144 — `cmd_up` readiness-poll comment says "~3s" but the worst-case wall-clock is ~13s (10 curl calls × 1s `--max-time` + 10 × 0.3s sleeps) when curl hangs rather than refusing fast. In practice curl against an unbound port returns ECONNREFUSED within milliseconds, so the "~3s" estimate matches the normal case — just a comment-precision nit.
  Suggested fix: Either drop the "~3s" estimate or note that it's the typical case (fast-refuse) rather than worst-case.

### Carry-forwards (still applicable, from the 2026-04-23 entry against 293a4a4)

None of these were touched by `881a6dc`/`9c37a0d`; they apply unchanged to the current HEAD:

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual drift catcher is `tests/drift/test_drift_constants.py::test_whimsy_prompt_suffix_matches_code_constant`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384. Field is currently dead (unread); wiring it up would trip all three probes.

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide. Doc/impl drift, not a detection gap for the advertised tripwire.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning (removal in Pillow 14 / 2027-10-15); `pyproject.toml` pins `Pillow>=10.0` with no upper bound.

[NOTE] README.md:70 and CLAUDE.md:201 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`. The `images/test/human-review/` sub-path is also missing from the CLAUDE.md file-layout block.

[NOTE] README.md:36 — `bin/game world` one-liner still lists "list / archive / delete"; missing `restore` and `verify`.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`. Latent today (WS production path never passes overrides).

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB is in autocommit mode).

[NOTE] daydream/events.py:117-122, daydream/api/ws.py:200, bin/game:215-224 — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.

### Fixes Applied

None. Only NOTE-level findings; no auto-fix by policy.

### Accepted Risks

The following remain documented in SECURITY.md's Accepted Risks and are not re-reported here: `https_only=False` cookie (LAN/Tailscale only), no CSRF token on `/api/login` and `/api/logout` (friend-scope phishing impact only), the 100.64.0.0/10 hardcoding for Tailscale CGNAT, `AccessMiddleware` reading `scope["client"][0]` directly (secure default; documented operator caveat for reverse-proxy deployments), `bin/game` sourcing `.env` + `secrets.env` as shell (operator-controlled gitignored files), and `bin/qpeek-bootstrap` cloning + installing from `github.com/peterzat/qpeek` (supply-chain trust on the project owner's own account).

---
*Prior review (2026-04-23, commit 293a4a4): no BLOCK or WARN findings; 9 NOTEs covering doc/impl drift in drift-probe corpora, Pillow deprecation, README/CLAUDE path references, a latent override-path cache-key inconsistency, a non-atomic delete cascade, and carry-forwards from earlier reviews. The prior entry before that (commit 5de20c9) found one BLOCK (tar path-traversal, CVE-2007-4559) which was auto-fixed in 88e1763.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"9c37a0d","reviewed_up_to":"9c37a0db38992e66a3a3c485ec18aef150fc5cb0","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":12} -->
