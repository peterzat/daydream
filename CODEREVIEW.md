## Review — 2026-05-27 (commit: c6c59c2)

**Summary:** Refresh review of one unpushed commit (`c6c59c2`, drift-bootstrapped-npcs 7/7) that opens the drift loop to every NPC, not just `t-rook` / `t-iris`. `daydream/drift.py` drops the `_DRIFT_POOLS` membership check from `_eligible_npcs`, adds a name-templated `_GENERIC_DRIFT_POOL` (4 mood buckets, 16 lines), routes `_pick_canned_line` / `_maybe_transition_mood` through the generic pool when an NPC has no per-NPC entry, and plumbs the toon name into the canned path via `str.replace`. `tests/test_drift.py` adds 6 tests + replaces the unknown-npc test; the seeded slot-1 Wren (r-meadow, no pool) is now drift-eligible, so the occupancy and Rook-isolation tick tests occupy r-meadow / delete Wren to keep their premises deterministic (assertions unchanged). README drift bullet + tier counts rolled forward.

**Review scope:** Refresh review. Focus: 3 file(s) changed since prior review (commit `ed51c43`) — `daydream/drift.py`, `tests/test_drift.py`, `README.md`. 0 already-reviewed files checked for interactions only (focus set equals the full unpushed set vs `origin/main`). Test baseline: `bin/game test medium` 485 passed / 9 deselected (was 479 pre-change; +6 new), `short` 324 (was 320; +4). No regressions.

**External reviewers:** Skipped (session constraint: no GPU / no real LLM). `review-external.sh` is on PATH but would dispatch the diff to external cloud LLM reviewers and/or a local GPU Qwen — both disallowed by this session's explicit constraint and out of scope for the DONE criteria. Claude's own review + the `/security` chain stand as the review of record.

### Findings

New this review:

[NOTE] daydream/drift.py:119 — The `_GENERIC_DRIFT_POOL` comment says "Same dict-of-dicts shape ... as `_DRIFT_POOLS`", but the generic pool is `dict[str, list[str]]` (one level shallower); it matches the shape of a single `_DRIFT_POOLS` *value* (one NPC's bucket-dict), not the top-level dict. The code is correct (`_pick_canned_line` / `_maybe_transition_mood` consume `_DRIFT_POOLS.get(id) or _GENERIC_DRIFT_POOL`, where `.get(id)` already unwraps one level); only the comment phrasing is loose. Informational; no fix applied.

No correctness, security, regression, or spec-alignment issues found in the focus set. The eligibility-opening behavior change was traced to its only call sites (all within `drift.py`) and to every drift test; the now-eligible Wren interaction is handled in the tests, not papered over.

### Carry-forwards (open NOTEs in untouched code, unchanged this review)

These predate this commit and live in files outside the focus set; none were resolved or aggravated by the drift change:

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

### Fixes Applied

None. The single new finding is a NOTE (comment phrasing); NOTEs are not auto-fixed.

### Accepted Risks

Unchanged vs prior entry:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`. (This review's drift change calls `toons.set_mood` only with hardcoded pool keys, never LLM/attacker input, so it does not widen this risk.)
- `bin/vllm-bootstrap` and `bin/memory-bootstrap` interpolate `$MODEL` into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Operator-trust class.
- Stored prompt-injection via captured memory text (defense-in-depth gap surfaced earlier).
- `/status/drift` endpoint is unauthenticated by design (`AccessMiddleware` is the gate). Same trust class as `/login` and `/cache/...`.
- v1 friend-scope on slot endpoints — any auth'd session can claim/kick any slot; per-session ownership lands with v2 multi-user-shared-world.
- `_ensure_session_id` stamps fresh UUIDs in tailscale mode even without `/api/login` (consistent with "tailnet membership IS the auth").
- Unbounded request body on `POST /api/slots/{slot}/create`. Accepted under documented friend-scope threat model; v2 may add explicit length caps.

---
*Prior review (2026-05-27, commit ed51c43): light docs-only review of the `GOAL.md` journey-log commit. No issues found; no code touched. Carried forward 18 open NOTEs and the Accepted Risks set from the `dd983fa` refresh, all of which remain open here.*

<!-- REVIEW_META: {"date":"2026-05-27","commit":"c6c59c2","reviewed_up_to":"c6c59c245824b4facd3287802b6be64b3213389d","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":1} -->
