## Review — 2026-04-23 (commit: db60c0f)

**Summary:** Full-tier review of 10 unpushed commits against origin/main: the four-increment multi-room navigation slice (migration 004 + `go` core skill + WS dynamic room + SPA exit buttons), Tailscale-mode password bypass, `/assets/*` no-store middleware, CLAUDE.md agent automation policy + coding-turn guidance, and the SPEC consume that closed multi-room nav 7/7 and adopted data-skills-cli + safety-baseline-v1. 233/233 tests pass (short+medium, 2.96s). Security scan across all changed non-test code: no findings. External reviewer (OpenAI o3) flagged one BLOCK claiming `registry.execute(..., HUMAN_ROOM_ID, ...)` still runs with a hardcoded starting room at `daydream/api/ws.py:162`; verified false — `HUMAN_ROOM_ID` is removed (0 occurrences in the file), line 162 is inside `_generate_and_emit`, and the interpreter-routed execute at line 205 uses the dynamically-resolved `room_id = _current_room_id()` (line 191) same as the canonical-bypass path at line 194. No BLOCK, no WARN against this diff.

**External reviewers:**
`[openai] o3 (high) -- 13567 in / 11790 out / 11712 reasoning -- ~$.2151`. One finding returned, verified false; see Summary.

### Findings

No BLOCK or WARN findings against the diff.

### Carry-forwards (still applicable against files this diff does not touch)

The 11 NOTEs from the 2026-04-23 entry carry forward unchanged:

[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc. One-line cleanup.

[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s. Comment-precision nit.

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual drift catcher is `tests/drift/test_drift_constants.py::test_whimsy_prompt_suffix_matches_code_constant`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384. Field currently dead (unread).

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.

[NOTE] README.md:70 and CLAUDE.md:218 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.

[NOTE] README.md:36 — `bin/game world` one-liner still lists "list / archive / delete"; missing `restore` and `verify`.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`. Latent today.

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode).

[NOTE] daydream/events.py:117-122, daydream/api/ws.py (subscriber queue), bin/game (`cmd_logs` unvalidated path component) — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.

### Fixes Applied

None.

### Accepted Risks

Unchanged from prior entry plus one addition surfaced in this round's security scan:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- New (added by this round's SECURITY.md update): Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass). Documented in SECURITY.md; middleware gates non-tailnet source IPs before auth runs, so the bypass is safe by construction.

---
*Prior review (2026-04-23, commit 0d71017): one BLOCK in `bin/game`'s tailnet FQDN/IP helpers (pipefail crash under `set -euo pipefail` when tailscale daemon was down); fixed via `|| true` guards, re-verified. 11 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"db60c0f","reviewed_up_to":"db60c0f42c01cf5cfe355dc73f2f4d10aaa6df29","base":"origin/main","tier":"full","block":0,"warn":0,"note":11} -->
