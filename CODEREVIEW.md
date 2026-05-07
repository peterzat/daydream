## Review — 2026-05-07 (commit: cfcd5f1)

**Summary:** Refresh review of 4 unpushed commits since `6daea43` covering the LLM-driven drift turn and two adjacent landings: `2f9f825` adds `tests/baselines/memory_ranking.golden.json` + `tests/drift/test_memory_ranking.py` (tier_short salience-formula drift probe pinning the `cosine_similarity * exp(-age_hours/24)` ordering and per-item scores against a 5-memory crafted corpus); `f52a424` adds `bin/install-hooks` (idempotent pre-commit + pre-push installer with `--uninstall`, marker-aware so user-written hooks aren't clobbered, refuses to overwrite non-marker hooks); `220d4fc` rewrites `daydream/drift.py` to a two-path tick (LLM-composed when `DAYDREAM_DRIFT_LLM_ENABLED=1` with `memories.retrieve(query=npc.seed)` + Jinja-rendered prompt + `safety.first_banned` output check + canned-pool fallback on any failure; mood-bucketed canned pool keyed by NPC then mood with 8 distinct lines per NPC across content/thoughtful/default), restructures `_DRIFT_POOLS`, makes `_tick` async, adds `DAYDREAM_DRIFT_LLM_ENABLED=0` default in `tests/conftest.py`, replaces `tests/test_drift.py` with 19 tests (5 carry-forwards + 14 new); `cfcd5f1` rolls forward README test counts (290→297 short, 401→413 medium) at status + tests sections, refreshes the drift bullet, drops shipped items from "What's next." Tier counts: 297 short / 413 medium, both 100% green; no regression vs prior review's 290/401.

**Review scope:** Refresh review. Focus: 8 file(s) changed since prior review (commit `6daea43`). 0 already-reviewed file(s) (focus set equals full set since upstream).

**External reviewers:**
None configured (review-external.sh on PATH but no provider config produced output).

### Findings

No new BLOCK or WARN findings.

The prior review's [NOTE] `tests/test_drift.py:61-70 — Dead _open_db helper` is resolved by this turn's full rewrite of test_drift.py.

### Fixes Applied

None this run (no BLOCK/WARN to fix).

### Carry-forwards (unchanged vs prior entry)

The 15 NOTEs from earlier reviews carry forward unchanged (none of their file patterns are in this turn's focus set, except the README path NOTE which wasn't touched by this turn's README edits):

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

### Accepted Risks

Unchanged from prior entries:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.
- `bin/vllm-bootstrap:91` and `bin/memory-bootstrap` interpolate `$MODEL` into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Operator-trust class.
- Stored prompt-injection via captured memory text (defense-in-depth gap surfaced in SECURITY.md WARN at `daydream/skills/data.py:361-367` + `skills/{rook,iris}.json:6`). The new LLM-driven drift path at `drift.py:244-293` inherits the same gap class (memory text rendered as `<memory>{{ m.text }}</memory>` in the drift prompt without literal `</memory>` neutralization). Backstops are sound: capture-side banlist (`memories.py:195-198`), drift output-side banlist (`drift.py:288-292`), and unconditional canned-pool fallback. Drift's smaller output shape (`{"narrate": "..."}`, no `effects` parsing) gives it a strictly smaller blast radius than the dialogue path. Per-skill-instructions, accepted risks are not re-flagged in /security; this entry documents the parallel.

### Note for next turn

Active SPEC at HEAD (`cfcd5f1`) is closed at 7/7 (LLM-driven drift narrates with mood-aware canned fallback). The `### Proposal (2026-05-07)` is written and pending consume — five direction candidates: code review (this turn), drift polish round two (per-NPC cadence, room-occupancy suppression, mood-affecting drift), drift voice-bench harness, v0.2.0 cut, drift LLM observability. The user signaled drift polish round two as the next spec direction.

---
*Prior review (2026-05-07, commit 6daea43): light review (doc-only). Single commit landed README v0.1.0 polish folding NPC memory into release notes; no code/config/test files touched. 1 NOTE on README.md:149 "What's next (per BACKLOG.md)" caption mismatch (now obsolete — this turn's README rewrite drops the "(per BACKLOG.md)" qualifier). 14 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"cfcd5f1","reviewed_up_to":"cfcd5f12e91c85cd6d87ae9184a0fe49162fdbd1","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":15} -->
