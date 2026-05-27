## Review — 2026-05-27 (commit: 89697ad)

**Summary:** Refresh review of the `snapshot-restore-commands` feature (commit `89697ad`): two new operator CLI verbs in `daydream/admin.py` — `cmd_snapshot` (WAL-checkpoint the live DB, copy just the `.db` to `snapshots/{world}-{ts}.db`) and `cmd_snapshot_restore` (install a snapshot as the live DB, refusing to overwrite an existing live DB, a missing/non-DB file, or a newer-schema snapshot) — plus 11 `tier_medium` tests in `tests/test_admin.py` and README/CLAUDE.md roll-forward. Implements SPEC.md 6/6 for the turn.

**Review scope:** Refresh review. Focus set since prior review (`89c14ad`, block:0, base origin/main): `daydream/admin.py`, `tests/test_admin.py`, `README.md`, `CLAUDE.md`. The change is purely additive to `admin.py` (existing `archive`/`restore`/`verify`/`delete`/`list` functions untouched; two new functions, two new argparse subparsers, two new dispatch branches) and `tests/test_admin.py` (new `# ---- snapshot` section + `sqlite3` import), so the already-reviewed code carries forward with no interaction risk. Test baseline: short 324 / medium 496, green before and after (no fixes applied).

**External reviewers:** Ran `review-external.sh` on `89c14ad..HEAD`; no output (providers not configured / fail-open). No external findings.

**Security:** `/security daydream/admin.py tests/test_admin.py` → 0 BLOCK / 0 WARN / 0 NOTE (SECURITY.md updated, commit `89697ad`). Traced SQL injection (all parameterized), path-traversal via `world_id` (gated by `SELECT id FROM worlds WHERE id = ?` before any filesystem sink), foreign-DB content in `snapshot-restore` (read-only + immutable probe, schema-gated, refuse-to-overwrite, `--yes`), and tar extraction (unchanged) — all clean. Operator-only CLI, no network/auth surface.

### Findings

0 BLOCK / 0 WARN / 1 NOTE (new). The feature is clean: the WAL checkpoint before copy matches `cmd_archive`'s proven pattern; the round-trip oracle test uses the post-snapshot mutation as a control (asserts restored == snapshot-time state AND != mutated state), not a tautology; every create- and restore-side refusal is tested; `snapshot-restore` validates the candidate before any write to the live path.

[NOTE] daydream/admin.py:421 — `cmd_snapshot_restore`'s read-only probe builds the URI by raw f-string interpolation (`f"file:{snapshot_path}?mode=ro&immutable=1"`). Verified empirically: a snapshot path containing a space works fine and creates no `-wal`/`-shm` sidecars (immutable mode), but a path containing a literal `?` is misparsed (SQLite treats it as the URI query delimiter and opens a different/empty file). The failure mode is SAFE — it surfaces as `sqlite3.DatabaseError` → "not a readable daydream DB" → exit 2 with no copy — and snapshot filenames produced by `cmd_snapshot` (`{world_id}-{ts}.db`, world_id validated to exist) never contain `?`. Only an operator hand-naming a restore-source path with a `?` would hit it. Cosmetic/robustness only; left as-is.

### Fixes Applied

None. No BLOCK/WARN findings; the change converged at 0 BLOCK / 0 WARN on the first pass with no `/codefix` cycle.

### Carry-forwards (open NOTEs in untouched code, unchanged this review)

This turn touched only `daydream/admin.py` (additively) and `tests/test_admin.py`; none of the code referenced below changed, so the prior entry's open NOTEs remain open and carry forward:

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode). (Pre-existing; not in this turn's diff.)
[NOTE] daydream/drift.py:119 — `_GENERIC_DRIFT_POOL` comment says "Same dict-of-dicts shape ... as `_DRIFT_POOLS`", but the generic pool is one level shallower; comment phrasing only, code correct.
[NOTE] daydream/llm/bootstrap.py:366-474 — `_write_db` is not transactional; a mid-pipeline INSERT failure leaves a half-populated output DB.
[NOTE] daydream/llm/bootstrap.py:340-343 — Skill `context_predicate.room_slug` not cross-checked against the rooms list; a typo'd predicate inserts cleanly but never matches.
[NOTE] tests/test_ws_iris.py:169-171 — Stale docstring re. snapshot toons-list contract.
[NOTE] daydream/llm/safety.py:83 — `_CLOSE_TAG` constant dead after switch to `_CLOSE_TAG_RE`.
[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc.
[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s.
[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual catcher is `tests/drift/test_drift_constants.py`.
[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384.
[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.
[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.
[NOTE] README.md:82 and CLAUDE.md — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.
[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`.
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
- `/status/drift` endpoint is unauthenticated by design (`AccessMiddleware` is the gate). Same trust class as `/login` and `/cache/...`.
- v1 friend-scope on slot endpoints — any auth'd session can claim/kick any slot; per-session ownership lands with v2 multi-user-shared-world.
- `_ensure_session_id` stamps fresh UUIDs in tailscale mode even without `/api/login` (consistent with "tailnet membership IS the auth").
- Unbounded request body on `POST /api/slots/{slot}/create`. Accepted under documented friend-scope threat model; v2 may add explicit length caps.

---
*Prior review (2026-05-27, commit 89c14ad): light review of the docs-only `/goal` documentation (`GOAL.md` attempt-1 retrospective + attempt-2 plan, `README.md` "How this is built" section). 0 BLOCK / 0 WARN / 0 new NOTE; every internal reference and test-count claim verified.*

<!-- REVIEW_META: {"date":"2026-05-27","commit":"89697ad","reviewed_up_to":"89697adf8b03d1d68c156d47d9746c04c56ad694","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":1} -->
