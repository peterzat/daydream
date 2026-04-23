## Review — 2026-04-23 (commit: 1a92aaa)

**Summary:** Refresh review of the 2 commits landed since the prior review (`50310c2`): `c33fdaa` applied the three WARN fixes the prior review demanded (narrative-text scan covers `mood`, `wrap_player_input` uses case-insensitive + whitespace-tolerant regex, `skills.description` persists via migration 005), and `1a92aaa` refreshed CODEREVIEW.md + SECURITY.md to record those fixes. Focus set was 7 code/test files; the 7 files previously reviewed (daydream/api/ws.py, daydream/skills/effects.py, daydream/skills/registry.py, skills/forge.json, tests/test_effects.py, tests/test_ws_forge.py, BACKLOG.md) were unchanged since 50310c2, so interaction checks were not needed. 247/247 short + 325/325 medium green. `/security` re-scanned the 7 touched files (3 of which were in the prior scanned_files, 4 of which are new) and returned 0 findings (SECURITY.md refreshed). External reviewer (OpenAI o3, ~$.19) returned "No issues found." Independent review surfaced one NOTE: the `_CLOSE_TAG = "</player_input>"` string constant in `daydream/llm/safety.py:83` is now dead after the switch to `_CLOSE_TAG_RE`. 0 BLOCK / 0 WARN.

**External reviewers:**
`[openai] o3 (high) -- 25348 in / 8505 out / 8448 reasoning -- ~$.1863`. 0 findings.

### Findings

No BLOCK or WARN findings.

[NOTE] daydream/llm/safety.py:83 — `_CLOSE_TAG = "</player_input>"` is defined but no longer referenced after the switch to `_CLOSE_TAG_RE` in commit c33fdaa. One-line cleanup: delete it, or use it as a source fragment for the regex (`r"</\s*" + re.escape("player_input") + r"\s*>"`). No behavior change either way.

### Fixes Applied

None. The only new finding is NOTE-level; NOTEs are not auto-fixed.

### Carry-forwards (unchanged vs prior entry)

All 11 NOTEs from the prior entry still apply unchanged — none of their referenced code changed in this review's focus set:

[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc. One-line cleanup.

[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s. Comment-precision nit.

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual drift catcher is `tests/drift/test_drift_constants.py::test_whimsy_prompt_suffix_matches_code_constant`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384. Field currently dead (unread).

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.

[NOTE] README.md:70 and CLAUDE.md:218 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.

[NOTE] README.md:36 — `bin/game world` one-liner still lists "list / archive / delete"; missing `restore` and `verify`.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`. Latent today.

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode). Note: `cmd_skill_add` added in the data-skills round is a single-statement INSERT-ON-CONFLICT and therefore atomic by itself; no new transactional concern introduced this round.

[NOTE] daydream/events.py:117-122, daydream/api/ws.py (subscriber queue), bin/game (`cmd_logs` unvalidated path component) — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.

### Accepted Risks

Unchanged from prior entry:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). In-scope for the v1-allowlist-trusted baseline; v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.

### Note for next turn

Active SPEC (first NPC, 2026-04-23) calls for a `migrations/006_first_npc.sql` file — 005 is now held by the `skills.description` column. Unchanged from prior entry.

---
*Prior review (2026-04-23, commit 50310c2): refresh of data-skills-cli + safety-baseline-v1 increment (C1 safety, C2 effects, C3 loader, C4 CLI, C5 forge showcase) plus SPEC evolve + consume. Started 0/3/0 (BLOCK/WARN/NOTE net of carry-forwards); all 3 WARNs fixed via /codefix (landed as c33fdaa). 11 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"1a92aaa","reviewed_up_to":"1a92aaa066c604cc7c73d66382c7bc5be994a2f7","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":12} -->
