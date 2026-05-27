## Review — 2026-05-27 (commit: ed51c43)

**Summary:** Light review of one unpushed docs-only commit (`ed51c43`) that adds `GOAL.md`, a 170-line human-readable journey log for the first use of Claude Code's `/goal` feature in daydream. The doc records project state (prose + git facts), the exact `/goal` condition to be run (drift-bootstrapped-npcs 0/7 to a committed increment), pre-run predictions, and a fill-in-after review checklist. No code or configuration touched.

**Review scope:** Light review (docs-only). 1 file changed (+170). Per light-tier rules, no test-suite run, no security chain, no external reviewers, and no fix loop. Reduced-scope checks applied: broken links/references, secret leaks in prose, factual accuracy.

**External reviewers:** Skipped (light review).

### Findings

No issues found. Internal references (`daydream/drift.py`, `tests/test_drift.py`, `tests/test_ws.py`, `tests/test_slots.py`, `SPEC.md`, `README.md`, `CODEREVIEW.md`, `SECURITY.md`) resolve to real paths; the six cited commit hashes and the full HEAD sha match `git log`; the remote (`git@github.com:peterzat/daydream.git`) and the docs URL (`code.claude.com/docs/en/goal.md`) are correct; the embedded git snapshot is intentionally pre-run (HEAD shown as `b032517`, the parent of this commit); no secrets in prose (`DAYDREAM_PASSWORD` referenced by name only).

### Fixes Applied

None.

### Carry-forwards (unchanged vs prior entry — no code touched this review)

The 2 NOTEs and 16 carry-forward NOTEs from the prior (`dd983fa`) entry remain open. This docs-only review changed no code, so none could be resolved or aggravated:

[NOTE] daydream/llm/bootstrap.py:366-474 — `_write_db` is not transactional (autocommit `isolation_level=None`); a mid-pipeline INSERT failure leaves a half-populated output DB. Same root issue as the `cmd_delete` carry-forward.
[NOTE] daydream/llm/bootstrap.py:340-343 — Skill `context_predicate.room_slug` is not cross-checked against the rooms list; a typo'd predicate yields a skill that never matches but inserts cleanly.
[NOTE] tests/test_ws_iris.py:169-171 — Stale docstring re. snapshot toons-list contract.
[NOTE] daydream/llm/safety.py:83 — `_CLOSE_TAG` constant dead after switch to `_CLOSE_TAG_RE`.
[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc.
[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s.
[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual catcher is `tests/drift/test_drift_constants.py`.
[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384.
[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.
[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.
[NOTE] README.md:82 and CLAUDE.md:218 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.
[NOTE] README.md:48 — `bin/game world` one-liner missing `restore` and `verify`.
[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`.
[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode).
[NOTE] daydream/events.py:117-122, daydream/api/ws.py, bin/game (`cmd_logs`) — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.
[NOTE] daydream/skills/data.py:366 — Cosmetic "Rook said: Rook lifts..." stutter in capture format string.
[NOTE] tests/conftest.py:21 — `test-session-secret-not-for-production` placeholder is an accepted-risk test fixture, not a real secret.
[NOTE] daydream/toons.py:create_toon_in_slot (lines ~165-185) — TOCTOU between `_slot_occupied` SELECT and the subsequent `INSERT`. Non-exploitable in single-process v1; v2 multi-process would need `try/except sqlite3.IntegrityError` mapping to 409.

### Accepted Risks

Unchanged vs prior entry:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.
- `bin/vllm-bootstrap` and `bin/memory-bootstrap` interpolate `$MODEL` into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Operator-trust class.
- Stored prompt-injection via captured memory text (defense-in-depth gap surfaced earlier).
- `/status/drift` endpoint is unauthenticated by design (`AccessMiddleware` is the gate). Same trust class as `/login` and `/cache/...`.
- v1 friend-scope on slot endpoints — any auth'd session can claim/kick any slot; per-session ownership lands with v2 multi-user-shared-world.
- `_ensure_session_id` stamps fresh UUIDs in tailscale mode even without `/api/login` (consistent with "tailnet membership IS the auth").
- Unbounded request body on `POST /api/slots/{slot}/create`. Accepted under documented friend-scope threat model; v2 may add explicit length caps.

---
*Prior review (2026-05-07, commit dd983fa): refresh review of the world-bootstrap-opus mega-commit (`bootstrap.py` + `admin.py` + SPEC consume + BACKLOG sweep). 0 BLOCK / 1 WARN (duplicate skill-name dedup, auto-fixed) / 2 NOTE; 16 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-27","commit":"ed51c43","reviewed_up_to":"ed51c4382fbf778a9b8c46d99e87f3cf769324e7","base":"origin/main","tier":"light","block":0,"warn":0,"note":0} -->
