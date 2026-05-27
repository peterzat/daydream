## Review — 2026-05-27 (commit: 89c14ad)

**Summary:** Light review of the unpushed docs-only `/goal` documentation (`eb5fda5` plus the `89c14ad` follow-up that adds the "~25-min wrong axis" timing note to the attempt-1 review) that updates `GOAL.md` and `README.md` after the first `/goal` run. `GOAL.md` gains an honest attempt-1 retrospective (verdict: mechanically clean but fell short of testing `/goal` because it was below the one-shot ceiling, over-specified the implementation, carried a spec blind spot on the pool-less Wren toon, and leaned on a weak verification tier), a "bitter-lesson lens" lessons section, an attempt-2 plan with a ready-to-paste outcome-framed `/goal` condition targeting `snapshot-restore-commands`, and transferable callouts for other `/goal` users. `README.md` gains a "How this is built (zat.env + /goal)" section with the actual `/goal` command and a pointer to `GOAL.md`. No code or configuration touched.

**Review scope:** Light review (docs-only). Focus set since the prior review (`c6c59c2`): `GOAL.md`, `README.md` — both Markdown. Per light-tier rules, no test-suite run, no security chain, no external reviewers, and no fix loop. Reduced-scope checks applied: broken links/references, secret leaks in prose, factual accuracy.

**External reviewers:** Skipped (light review).

### Findings

No issues found. Verified: every internal reference resolves (`GOAL.md`, `daydream/admin.py`, `daydream/drift.py`, `CLAUDE.md`, `BACKLOG.md`); the attempt-2 command's claims match reality (the `snapshot-restore-commands` BACKLOG entry exists and specifies the `~/data/daydream/snapshots/{world}-{ts}.db` path verbatim; CLAUDE.md documents `PRAGMA wal_checkpoint(TRUNCATE)`; `bin/game world archive`/`restore` live in `daydream/admin.py`); the cited test counts (320→324 short, 479→485 medium) and the `block:0 / warn:0 / note:1` footer for `c6c59c2` are accurate; the article quotes match the fetched source; the README `[GOAL.md](GOAL.md)` link resolves; no secrets in the prose (env vars referenced by name only). The attempt-1 review section's "two commits / ahead by 2" wording is a correct point-in-time record of that run's end state, not a claim about current HEAD.

### Fixes Applied

None.

### Carry-forwards (open NOTEs in untouched code, unchanged this review)

This docs-only review changed no code, so none of the prior entry's findings could be resolved or aggravated. The 1 NOTE new in `c6c59c2` plus the 18 older NOTEs remain open:

[NOTE] daydream/drift.py:119 — `_GENERIC_DRIFT_POOL` comment says "Same dict-of-dicts shape ... as `_DRIFT_POOLS`", but the generic pool is `dict[str, list[str]]` (one level shallower); it matches the shape of a single `_DRIFT_POOLS` value, not the top-level dict. Comment phrasing only; code is correct.
[NOTE] daydream/llm/bootstrap.py:366-474 — `_write_db` is not transactional (autocommit `isolation_level=None`); a mid-pipeline INSERT failure leaves a half-populated output DB.
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
*Prior review (2026-05-27, commit c6c59c2): refresh review of the drift-bootstrapped-npcs feature (`daydream/drift.py` + `tests/test_drift.py` + `README.md`). 0 BLOCK / 0 WARN / 1 NOTE (the `_GENERIC_DRIFT_POOL` comment-shape nit, carried forward above). `/security` path-scan of the two code files returned 0/0/0. Verified the eligibility-opening change against its only call sites and every drift test; the now-eligible seeded Wren is handled in the tests. short 320→324, medium 479→485.*

<!-- REVIEW_META: {"date":"2026-05-27","commit":"89c14ad","reviewed_up_to":"89c14adf8cc36f06bdb43abe4da357db97d1a14a","base":"origin/main","tier":"light","block":0,"warn":0,"note":0} -->
