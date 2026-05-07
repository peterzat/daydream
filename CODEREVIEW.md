## Review — 2026-05-07 (commit: c94a16e)

**Summary:** Refresh review of the 3 unpushed commits since `b6a2551`. One SPEC turn landed: NPC drift loop v0 (`cc30a20` SPEC consume + `8a3ade4` C1-C5 close + `c94a16e` SPEC evolve + turn-close proposal). Focus set = 5 code paths: `daydream/drift.py` (NEW; asyncio.Task drift loop with FastAPI lifespan integration; constant-dict per-NPC pool of 4 lines each for Rook + Iris; `_compute_next_interval` reads `DAYDREAM_DRIFT_IDLE_SECONDS=300` / `BUSY_SECONDS=1800` defaults at each wake-up; `_tick` randomly picks an NPC, draws a line, emits `system`/None/`narrate` event; cancellation re-raises `CancelledError` cleanly), `daydream/events.py` (3-line `subscriber_count() -> int` accessor), `daydream/server.py` (lifespan import + symmetric drift start/stop wrapped in try/finally so `db.close_db()` runs even on exception during yield — strictly more robust than the prior `yield; close_db()` pattern), `tests/conftest.py` (sets `DAYDREAM_DRIFT_ENABLED=0` at module import so the asyncio.Task isn't spawned for every TestClient lifespan), `tests/test_drift.py` (NEW; 8 tests covering cadence pure-function, tick DB-interaction, empty-world no-op, pool quality, cancellation cleanup, disabled-mode no-task). 277/277 short + 376/376 medium green at HEAD (was 271/368; +6/+8 from new drift tests). `/security` scanned the same 5 code paths and returned 0 BLOCK/WARN/NOTE (drift is purely system-authored, no operator/player input flows in, asyncio single-thread rules out subscriber-list race, env-var trust posture unchanged). External reviewers configured but no API keys active; `review-external.sh` exited silently. Independent review: `_tick`'s SQLite read happens on the same event loop as FastAPI handlers (no thread-safety concern; asyncio multiplexes cooperatively), the `random.choice(eligible)` selection correctly handles the empty-pool-skip case via the `eligible` filter, the `try/except` around `asyncio.sleep` re-raises `CancelledError` so cancellation during sleep propagates, and the lifespan's `try/finally` survives a startup-time exception during `start_drift_loop` because `drift_handle` is initialized before `try`. Test for cancellation gives the loop one event-loop tick (`await asyncio.sleep(0.01)`) to start sleeping before cancelling, exercising the in-sleep cancellation path. One new NOTE on dead test helper; no BLOCK, no WARN.

**External reviewers:**
Configured but no provider API keys active in `~/.config/claude-reviewers/.env`; script exited 0 with no output (fail-open).

### Findings

[NOTE] tests/test_drift.py:61-70 — Dead `_open_db` helper. Function is defined at module scope but never called by any test; its body uses an `if False` placeholder for path resolution. Tests at lines 73 and 112 call `db.init_live(migrations_dir=config.MIGRATIONS_DIR)` directly without going through this helper.
  Evidence: `_open_db()` at lines 61-70; no callers found in the file (`grep _open_db tests/test_drift.py` returns only the definition).
  Suggested fix: delete the function entirely. The tests call `db.init_live(migrations_dir=config.MIGRATIONS_DIR)` inline, which is what the helper would have done after stripping its `if False` placeholder.

### Fixes Applied

None.

### Carry-forwards (unchanged vs prior entries)

The new NOTE from prior review (`b6a2551`) on the docstring drift in `tests/test_ws_iris.py` is still present (the file wasn't touched this round) and carries forward at NOTE severity:

[NOTE] tests/test_ws_iris.py:169-171 — Test docstring is stale; says "iris appears in the room's toons list with appearance + presence_text populated" but the body asserts only `id == "t-iris"` and `mood == "thoughtful"` (per the snapshot's actual `id/name/mood` contract). The inline comment at lines 190-193 already explains the right contract.

All 12 NOTEs from the earlier entry (`2c3edb5`) still apply. None of their file patterns are in this round's focus set, but each remains present in the codebase:

[NOTE] daydream/llm/safety.py:83 — `_CLOSE_TAG = "</player_input>"` dead after the switch to `_CLOSE_TAG_RE`.

[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc.

[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s.

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual drift catcher is `tests/drift/test_drift_constants.py::test_whimsy_prompt_suffix_matches_code_constant`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384. Field currently dead (unread).

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.

[NOTE] README.md:70 and CLAUDE.md:218 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.

[NOTE] README.md:36 — `bin/game world` one-liner still lists "list / archive / delete"; missing `restore` and `verify`.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`. Latent today.

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode).

[NOTE] daydream/events.py:117-122, daydream/api/ws.py (subscriber queue), bin/game (`cmd_logs` unvalidated path component) — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.

### Accepted Risks

Unchanged from prior entry:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). In-scope for the v1-allowlist-trusted baseline; v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.
- `bin/vllm-bootstrap:91` interpolates `$MODEL` (sourced from `DAYDREAM_VLLM_MODEL`) into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Same operator-trust class as `bin/game` env-sourcing.

### Note for next turn

Active SPEC closed at 5/5 (NPC drift loop). Next-turn proposal in SPEC.md `### Proposal (2026-05-07)` recommends BACKLOG `npc-memory-retrieval` (newly-eligible: `npc-drift-loop landed` gate now satisfied this turn). Backlog Sweep proposes deleting the just-shipped `npc-drift-loop (ACTIVE in spec 2026-05-07)` entry. `watercolor-lora-ab` surfaced for the 6th time and is becoming a stale revisit-candidate; worth either a status-note refresh or a revisit-criteria sharpening before the 7th surfacing.

---
*Prior review (2026-05-07, commit b6a2551): refresh review of 13 commits across 3 SPEC turns (RP-Ink + tic-probe close, voice-bench cleanup hygiene round, second NPC Iris). 0 BLOCK / 0 WARN / 1 new NOTE (test_ws_iris docstring drift); 12 prior NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"c94a16e","reviewed_up_to":"c94a16e4a8d56efa02ae0f3592532d600d119a08","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":14} -->
