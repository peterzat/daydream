## Review — 2026-05-07 (commit: dd983fa)

**Summary:** Refresh review of one unpushed commit since `63e1ed0`. `dd983fa` is a bundled mega-commit covering three logical units: (1) world-bootstrap-opus closes 7/7 — `daydream/llm/bootstrap.py` (new, ~470 LOC) calls Claude Opus 4.7 via `litellm.acompletion`, validates a strict-JSON envelope (5 rooms with bidirectional exits + 4 toons in slot 1-5/100+ partition + items + 2 starter data skills), and INSERTs the bootstrapped content into a fresh `.db` under `world_id='w-bunny'` (canonical id retained so existing hardcoded references continue to work); 10 hermetic tests in `tests/test_bootstrap.py` mock `litellm.acompletion` at the module boundary; `daydream/admin.py` adds `cmd_world_bootstrap` + the `bootstrap` subparser. (2) SPEC.md consume to drift-bootstrapped-npcs (7 unchecked criteria; not in this commit's code surface). (3) BACKLOG sweep deletes the two ACTIVE-tagged shipped entries (`toon-slot-management`, `world-bootstrap-opus`). README rolls forward to 479 medium tests; new "world bootstrap" mention in the world-admin bullet.

**Review scope:** Refresh review. Focus: 5 file(s) changed since prior review (commit `63e1ed0`). 0 already-reviewed file(s). Tier counts at HEAD: 320 short / 479 medium green; no regression vs prior 320 / 469 (+10 from new bootstrap tests).

**External reviewers:**
None configured (review-external.sh on PATH but produced no output).

### Findings

[NOTE] daydream/llm/bootstrap.py:366-474 — `_write_db` is not transactional. `db.open_db` opens the connection in autocommit (`isolation_level=None`), so each DELETE/INSERT is its own implicit transaction. If any INSERT fails mid-pipeline (FK / CHECK violations from a future bug; the realistic skill-name UNIQUE path is now caught at the validator after this turn's WARN fix), the output DB is left half-populated — DELETEs of the seeded `w-bunny` content + some inserts succeeded, others didn't. Operator must manually delete the partial file. Same root issue as the carry-forward NOTE on `daydream/admin.py:410-420 cmd_delete`.
  Evidence: Lines 381-472 issue ~30 cur.execute() calls in autocommit mode with no BEGIN/COMMIT bracketing; the `try/finally` only ensures `conn.close()`, not rollback.
  Suggested fix: Bracket the DELETE+INSERT block with `cur.execute("BEGIN")` and `cur.execute("COMMIT")` (rollback in an except). The bootstrap path always runs against a fresh file (force=True unlinks first), so all-or-nothing semantics are clean. Low priority; the realistic failure mode goes away once the WARN above is addressed.

[NOTE] daydream/llm/bootstrap.py:340-343 — Skill `context_predicate.room_slug` is not cross-checked against the rooms list. Validator only confirms `context_predicate` is a dict; it does not require that `context_predicate.get("room_slug")`, when present, references a slug in `rooms[]`. A typo'd predicate yields a skill that never matches and is effectively dead, but inserts cleanly. Soft failure; operator notices when the skill never appears as a UI affordance.
  Evidence: Lines 340-343 only assert `isinstance(s.get("context_predicate"), dict)`. Compare to lines 300-303 which assert toons' `current_room_slug` is in `by_slug` and lines 324-327 which do the same for items.
  Suggested fix: After the dict check, if `"room_slug" in s["context_predicate"]`, verify `s["context_predicate"]["room_slug"] in by_slug` and raise BootstrapValidationError otherwise. Optional; the data-skills pipeline tolerates dead predicates today.

### Fixes Applied

- [WARN] daydream/llm/bootstrap.py:329-347 — Added `seen_skill_names` dedup pass in `_validate_envelope` mirroring the existing `seen_slugs` (rooms) and `seen_slots` (toons) patterns. Duplicate skill names now raise `BootstrapValidationError` (exit code 3) before reaching the DB layer, instead of bubbling out as `sqlite3.IntegrityError` from the `skills.name UNIQUE` constraint. No new test added for the new validator branch; a `test_bootstrap_rejects_duplicate_skill_name` would be a natural follow-up but was outside codefix's minimal-change scope.

### Carry-forwards (unchanged vs prior entry)

The 16 NOTEs from the prior entry carry forward unchanged. None of their file patterns were aggravated by this turn's focus set (admin.py changes are localized to the new `cmd_world_bootstrap` near the file end; the carry-forward NOTE on `cmd_delete` is at lines 410-420 and untouched):

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

### Note for next turn

The new SPEC.md (drift-bootstrapped-npcs, 0/7) is the next implementation target. The drift-loop's `_eligible_npcs` filters out any NPC missing from `_DRIFT_POOLS`, so bootstrapped NPCs (ids shaped `t-<slug>-<uuid>`) are silent in BOTH LLM-up and LLM-down configurations. Spec opens eligibility and adds a generic mood-bucketed canned pool with `{name}` interpolation. Implementation surface: `daydream/drift.py`, `tests/test_drift.py`, README tier counts.

---
*Prior review (2026-05-07, commit 63e1ed0): refresh review of `27534e9` (bin/game up-all bundled boot) and `63e1ed0` (toon-slot-management 8/8: 5-slot picker UI + slot endpoints + WS session-resolved controlled toon). 16 files reviewed. 0 BLOCK / 0 WARN / 1 NOTE (TOCTOU on slot create); 16 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"dd983fa","reviewed_up_to":"dd983fabf5f7ee8f3855f90e06d90d9b626e5099","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":2} -->
