## Review — 2026-05-07 (commit: c8f66d4)

**Summary:** Refresh review of one bundled commit (`c8f66d4`) covering two SPEC turns: (1) drift polish round two — per-NPC selection weights via `_NPC_DRIFT_WEIGHT` + `_pick_npc(eligible, rng)` (defaults equal), room-occupancy suppression via `_occupied_room_ids()` + `_eligible_npcs` filter (toggle `DAYDREAM_DRIFT_SUPPRESS_OCCUPIED`, default 1), and probabilistic mood transitions via `_maybe_transition_mood` (toggles `DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED` + `_PROB`; persists via new `daydream/toons.py:set_mood` parameterized helper); (2) drift instrumentation — extracted `_render_drift_prompt(npc, memories)` pure helper from `_llm_narrate`, added module-level `_TICK_COUNTS: dict[str, int]` (`llm_emit` / `canned_fallback` / `noop`) + `tick_counts()` accessor + `reset_tick_counts()` test helper, added `daydream/drift_samples.py` voice-bench harness mirroring `voice_samples.py` (hermetic, no DB, synthetic memories from corpus), added `/status/drift` plain-text endpoint to `daydream/server.py` (empty body when zero-state, one-line summary otherwise; loopback/tailnet-only via existing `AccessMiddleware`), extended `bin/game` with `drift-samples` subcommand + `cmd_status` drift-line printout, added 5 corpus prompts under `tests/drift/drift-voice/` covering Rook/Iris × content/thoughtful × empty/with-memories + a non-bucketed mood. 30 new tests across `tests/test_drift.py` (+28: weights x5, occupancy x4, mood-drift x4, composed x1, counters x6, render x3, status endpoint x2, others) + `tests/test_toons.py` (+3 new file) + `tests/test_drift_samples.py` (+9 new file). Tier counts: 297 → 320 short / 413 → 451 medium; both 100% green.

**Review scope:** Refresh review. Focus: 15 file(s) changed since prior review (commit `cfcd5f1`). 0 already-reviewed file(s).

**External reviewers:**
None configured (review-external.sh on PATH but no provider config produced output).

### Findings

No new BLOCK or WARN findings. No new NOTEs.

### Fixes Applied

None this run (no BLOCK/WARN to fix).

### Carry-forwards (unchanged vs prior entry)

The 15 NOTEs from earlier reviews carry forward unchanged (none of their file patterns are aggravated by this turn's focus set):

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

Unchanged from prior entries, plus one new entry from this turn's `/security`:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`. `daydream/toons.py:set_mood` is the underlying parameterized helper — it inherits the same authorization concern at its data-skill caller, not at the helper itself.
- `bin/vllm-bootstrap` and `bin/memory-bootstrap` interpolate `$MODEL` into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Operator-trust class.
- Stored prompt-injection via captured memory text (defense-in-depth gap surfaced in SECURITY.md WARN at `daydream/skills/data.py:361-367` + `skills/{rook,iris}.json:6`). The LLM-driven drift path at `drift.py:_llm_narrate` and the new `_render_drift_prompt` helper inherit the same gap class (memory text rendered as `<memory>{{ m.text }}</memory>` in the drift prompt without literal `</memory>` neutralization). Backstops are sound: capture-side banlist (`memories.py:195-198`), drift output-side banlist (`drift.py:288-292`), and unconditional canned-pool fallback. Drift's smaller output shape gives it strictly smaller blast radius than the dialogue path.
- **NEW:** `/status/drift` endpoint is unauthenticated by design (`AccessMiddleware` is the gate; loopback / tailnet only). Exposes three integer counters since process boot. Same trust class as `/login` (unauthenticated, AccessMiddleware-gated) and the intentionally-unauthenticated `/cache/{world}/...` static route. No PII, no secrets, counters reset on every `bin/game up`.

### Note for next turn

Active SPEC at HEAD (`c8f66d4`) is closed at 7/7 (drift instrumentation: voice-bench harness + outcome observability). The bundled commit message names both turns explicitly. Next /spec evolve cycle would generate the turn-close proposal.

---
*Prior review (2026-05-07, commit cfcd5f1): refresh review of 4 unpushed commits since 6daea43 covering the LLM-driven drift turn + memory_ranking probe + bin/install-hooks. 0 BLOCK / 0 WARN / 0 new NOTE; prior tests/test_drift.py:61-70 dead `_open_db` helper NOTE resolved by that turn's full rewrite. 15 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"c8f66d4","reviewed_up_to":"c8f66d4c901aa875bce440cdd2ff12714ca69a18","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":15} -->
