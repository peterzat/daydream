## Review — 2026-04-23 (commit: 1243402)

**Review scope:** Refresh review. Focus: 1 file changed since prior review (commit 9c37a0d): `daydream/server.py`. No already-reviewed files touched since; the focus file is the only diff. Full-depth review applied.

**Summary:** One commit unpushed (`1243402` — "Fix _PRE_FRONTEND_HTML fallback: POST form for logout"). Four lines changed in `daydream/server.py`: the fallback HTML's `<a href="/api/logout">leave</a>` became a POST `<form>` with an unbuttoned `<button>`, resolving the dormant NOTE from the 9c37a0d review. Endpoint is POST-only in `daydream/api/auth.py:41`; form shape matches the committed one in `web/index.html:22-25`. Tests remain green at 212/212 in 2.59s (same as baseline). Security scan ran over `daydream/server.py` (new to the scanned surface); zero findings. No BLOCK/WARN/NOTE for this diff.

**External reviewers:**
None reported findings (review-external.sh ran with empty stdout and no cost log content).

### Findings

No issues found.

### Carry-forwards (still applicable from the 2026-04-23 entry against 9c37a0d)

The prior NOTE on `daydream/server.py:124` is resolved by this commit and drops off. The remaining 11 NOTEs apply unchanged to files the current diff does not touch:

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

None. No BLOCK or WARN findings; no auto-fix by policy.

### Accepted Risks

Unchanged from prior entry. Documented in SECURITY.md: `https_only=False` cookie (friend-scope LAN/Tailscale), no CSRF token on `/api/login` and `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly (secure default; documented operator caveat for reverse-proxy deployments), the intentionally-unauthenticated `/cache/...` static route (added in the 1243402 security review), `bin/game` sourcing `.env` + `secrets.env` as shell (operator-controlled gitignored files), and `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek` (self-trust boundary).

---
*Prior review (2026-04-23, commit 9c37a0d): no BLOCK or WARN findings; 3 new NOTEs (fallback-HTML logout GET, dead footer-anchor CSS, cmd_up comment-precision) plus 9 carry-forwards. The fallback-HTML NOTE is fixed by 1243402 and drops off this entry.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"1243402","reviewed_up_to":"124340273a40dc2ec29fb403a81e93ef866da98b","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":11} -->
