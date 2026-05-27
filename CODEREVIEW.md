## Review — 2026-05-27 (commit: 46321a9)

**Summary:** Light review of the docs-only `GOAL.md` update (`46321a9`) that fills in the attempt-2 `/goal` retrospective and adds two "read-first" sections: "Observations and conclusions" (when to use `/goal`, what to expect / not, anti-patterns) and a field-grounded section + "Before you start" pre-flight checklist synthesized from three research passes (Anthropic's official `/goal` docs, practitioner autonomous-loop write-ups, and the verification / alignment literature). No code or configuration touched.

**Review scope:** Light review (docs-only). Focus set since the prior review (`89697ad`): `GOAL.md` only. Per light-tier rules: no test-suite run, no security chain, no external reviewers, no fix loop. Reduced-scope checks applied: broken links/references, secret leaks in prose, factual accuracy.

**External reviewers:** Skipped (light review).

### Findings

No issues found. Verified: the three commit hashes the doc cites (`89697ad`, `76f8b82`, `46321a9`) all resolve and match their descriptions; no broken local markdown links; the cited test counts (short 324, medium 496) and the "0 BLOCK / 0 WARN" claims for both `/goal` runs match this branch's history; no secrets in the prose (env vars referenced by name only; the lone secret-scan hit was a false positive, `sk-` matching "ta**sk-**per"). The external citations (arXiv IDs for the reward-hacking / LLM-judge papers, the DeepMind and Anthropic posts, the practitioner blogs) are attributed to the sources surfaced by the three research agents; URLs are well-formed but were not each independently re-fetched in this light pass.

### Fixes Applied

None.

### Carry-forwards (open NOTEs in untouched code, unchanged this review)

This docs-only review changed no code, so none of the prior entry's findings could be resolved or aggravated. The open NOTEs from `89697ad` remain open:

[NOTE] daydream/admin.py:421 — `cmd_snapshot_restore`'s read-only probe builds the URI by raw f-string interpolation; a snapshot path containing a literal `?` is misparsed (safe failure: refuses, no copy; default snapshot paths never contain `?`).
[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode).
[NOTE] daydream/drift.py:119 — `_GENERIC_DRIFT_POOL` comment says "Same dict-of-dicts shape ... as `_DRIFT_POOLS`", but the generic pool is one level shallower; comment phrasing only.
[NOTE] daydream/llm/bootstrap.py:366-474 — `_write_db` is not transactional; a mid-pipeline INSERT failure leaves a half-populated output DB.
[NOTE] daydream/llm/bootstrap.py:340-343 — Skill `context_predicate.room_slug` not cross-checked against the rooms list.
[NOTE] tests/test_ws_iris.py:169-171 — Stale docstring re. snapshot toons-list contract.
[NOTE] daydream/llm/safety.py:83 — `_CLOSE_TAG` constant dead after switch to `_CLOSE_TAG_RE`.
[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc.
[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s.
[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual catcher is `tests/drift/test_drift_constants.py`.
[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384.
[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.
[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.
[NOTE] README.md:82 and CLAUDE.md — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.
[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`.
[NOTE] daydream/events.py:117-122, daydream/api/ws.py, bin/game (`cmd_logs`) — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.
[NOTE] daydream/skills/data.py:366 — Cosmetic "Rook said: Rook lifts..." stutter in capture format string.
[NOTE] tests/conftest.py:21 — `test-session-secret-not-for-production` placeholder is an accepted-risk test fixture, not a real secret.
[NOTE] daydream/toons.py:create_toon_in_slot (~165-185) — TOCTOU between `_slot_occupied` SELECT and the subsequent INSERT. Non-exploitable in single-process v1.

### Accepted Risks

Unchanged vs prior entry:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.
- `bin/vllm-bootstrap` and `bin/memory-bootstrap` interpolate `$MODEL` into an unquoted heredoc. Operator-trust class.
- Stored prompt-injection via captured memory text (defense-in-depth gap surfaced earlier).
- `/status/drift` endpoint is unauthenticated by design (`AccessMiddleware` is the gate).
- v1 friend-scope on slot endpoints — any auth'd session can claim/kick any slot; per-session ownership lands with v2 multi-user-shared-world.
- `_ensure_session_id` stamps fresh UUIDs in tailscale mode even without `/api/login`.
- Unbounded request body on `POST /api/slots/{slot}/create`. Accepted under documented friend-scope threat model.

---
*Prior review (2026-05-27, commit 89697ad): refresh review of the snapshot-restore-commands feature (`daydream/admin.py` `cmd_snapshot` / `cmd_snapshot_restore` + 11 tier_medium tests + README/CLAUDE.md). 0 BLOCK / 0 WARN / 1 NOTE (the `?`-in-path URI probe edge, carried forward above); `/security` 0/0/0; short 324 / medium 496 green.*

<!-- REVIEW_META: {"date":"2026-05-27","commit":"46321a9","reviewed_up_to":"46321a94c68f3b039b064488ad7250a40a79ad33","base":"origin/main","tier":"light","block":0,"warn":0,"note":0} -->
