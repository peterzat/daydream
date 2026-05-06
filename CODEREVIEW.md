## Review — 2026-05-06 (commit: 2c3edb5)

**Summary:** Refresh review of the 12 unpushed commits since `1b045a6`. Eight commits ship the NPC dialogue + voice-bench + prompt-template-variety + tic-detection chain across three SPEC turns: `b00c884` (NPC dialogue: Rook speaks via the data-skill pipeline), `601cffa`+`12216e4` (voice-bench harness, corpus, AWQ baseline), `102d6aa`+`6013b6c` (Rook prompt-template variety pass + 2026-05-06 AWQ baseline showing 5/5 distinct openers), `c41d534` (tic-detection probe), `2c3edb5` (vLLM GGUF blocker for the active spec's RP-Ink leg). Four SPEC consume/evolve commits (`f41606a`, `4d2392f`, `cd68c22`, `1375232`) carry the meta state forward. Focus set = full set (12 paths): `bin/game` (voice-samples dispatch), `daydream/llm/client.py` (token-usage side channel), `daydream/voice_samples.py` (new harness), `skills/rook.json` (prompt template revised for opener variety), 5 corpus files at `tests/drift/voice/*.json`, and 3 test files (`tests/test_voice_baseline.py` new, `tests/test_voice_samples.py` new, `tests/test_ws_rook.py` new). 271/271 short + 360/360 medium green at HEAD. `/security` scanned the same 12 paths and returned 0 BLOCK/WARN/NOTE (SECURITY.md refreshed at `2c3edb5`; the new `_last_usage` side channel stores only token counts not prompt content; voice-samples harness is operator-only with proper env-var save/restore + tmpdir 0700 isolation; data-skill pipeline reuses `safety.wrap_player_input` + Jinja `SandboxedEnvironment`; corpus JSON is static + validated). External reviewers configured but no API keys active; `review-external.sh` exited silently (fail-open). Independent review: `voice_samples.py`'s tmp-DB lifecycle correctly restores `DAYDREAM_DATA_DIR` even on exception via try/finally; the LLM-client side channel clears at the top of each call so failed calls don't leak stale metrics; `_DIALOG_QUOTE_RE = (?<![A-Za-z])'` correctly skips apostrophes inside words ("Rook's", "today's") and matches dialog-opening single-quotes; the 04-24/05-06 parametrized regression-detection demo is a clean way to assert both the post-fix property AND the pre-fix counterexample; the C2 blocker is surfaced cleanly per the SPEC's "fails clean" language with a full traceback chain captured in commit body and SPEC.md `### Findings`. No new BLOCK, no new WARN, no new NOTE.

**External reviewers:**
Configured but no provider API keys active in `~/.config/claude-reviewers/.env`; script exited 0 with no output (fail-open).

### Findings

No BLOCK or WARN findings. No new NOTEs.

### Fixes Applied

None.

### Carry-forwards (unchanged vs prior entry)

All 12 NOTEs from the prior entry (`1b045a6`) still apply. None of their file patterns are in this round's focus set, but each remains present in the codebase:

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

### Note for next turn

Active SPEC (RP-Ink A/B + tic-detection probe, 2026-05-06) is at 2/5 with C2-C4 BLOCKED on a vLLM 0.19.1 + transformers 5.6.0 + gguf packaging-metadata bug. C1 (probe) and C5 (tests green) shipped. The blocker chain (`packages_distributions()` → `getattr(gguf, '__version__', 'N/A')` → `version.parse('N/A')`) and four resolution paths are durably documented in SPEC.md `### Findings (2026-05-06)` and BACKLOG.md `qwen-2.5-7b-rp-ink-trial` status note, so the next turn doesn't need conversation context to revisit. Operator decision required to unblock.

---
*Prior review (2026-04-24, commit 1b045a6): refresh review of the NPC presence narration chain (migration 006 seed Rook + `find_toon_in_room_by_name`, `core.examine` extends to toons, WS snapshot reflects NPC co-location, migration 007 adds `toons.presence_text`, broadcast loop emits presence narrates after controlled moves). 0 BLOCK / 0 WARN / 12 NOTEs (all carried forward).*

<!-- REVIEW_META: {"date":"2026-05-06","commit":"2c3edb5","reviewed_up_to":"2c3edb58b99385a0d8a3a4e0f015a2c62b383b41","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":12} -->
