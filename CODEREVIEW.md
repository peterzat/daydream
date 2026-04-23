## Review — 2026-04-23 (commit: 50310c2)

**Summary:** Refresh review of 8 unpushed commits since the prior review (`db60c0f`): the data-skills-cli + safety-baseline-v1 increment (C1 safety primitives, C2 effects allowlist dispatcher, C3 DB-backed loader + registry merge + WS dispatch, C4 `bin/game world skill add` CLI, C5 forge showcase + WS E2E + bypass predicate gate), the post-close follow-up that extended the post-move snapshot re-push to `item_added` / `mood_set`, and the SPEC evolve + consume that adopted first-NPC as the next slice. Baseline 243/243 short + 321/321 medium; post-fix 247/247 short + 325/325 medium. Security scan of the seven code files returned 0 findings (scope refreshed; see SECURITY.md). External reviewer (OpenAI o3, ~$.14) flagged 1 BLOCK + 3 WARN/NOTE; review adjudicated to 2 WARN (case-variant break-out was WARN-level with defense-in-depth, not BLOCK; `json.dumps` crash rejected as false positive — dict came from `json.loads` and is guaranteed serializable; autocommit NOTE rejected as already a carry-forward from prior review). Independent review found a third WARN: the author-file `description` was REQUIRED by validation but never persisted — interpreter saw a hardcoded fallback. All 3 WARNs fixed via `/codefix` with paired tests; re-review verified the fixes are minimal, preserve backward compat, and do not regress any existing test.

**External reviewers:**
`[openai] o3 (high) -- 23973 in / 5986 out / 5760 reasoning -- ~$.1419`. 1 BLOCK (adjudicated to WARN, fixed), 1 WARN accepted (matched independent finding, fixed), 1 WARN rejected (false positive), 1 NOTE rejected (already carry-forward).

### Findings

No BLOCK or WARN findings remain against the diff. All three WARNs identified in this review round were fixed via /codefix; see "Fixes Applied" below.

### Fixes Applied

[WARN] (openai + independent) daydream/skills/data.py:189 — Extended the output-side banlist scan to include the `mood` field so `set_mood` effects cannot smuggle banned categories through `toons.mood` → SPA `${name} (${mood})` display. Added `test_banned_mood_value_drops_set_mood_effect` asserting that `{"effects": [{"kind": "set_mood", "mood": "grimdark"}]}` is dropped and the toon's mood stays at its prior value.

[WARN] (openai) daydream/llm/safety.py:99 — Replaced case-sensitive `str.replace(_CLOSE_TAG, ...)` with a case-insensitive + whitespace-tolerant regex `_CLOSE_TAG_RE = re.compile(r"</\s*player_input\s*>", re.IGNORECASE)` so case-variant (`</PLAYER_INPUT>`) and whitespace-padded (`</ player_input >`) close attempts are neutralized alongside the exact-lowercase form. Added `test_neutralizes_case_variant_closing_tag` and `test_neutralizes_whitespace_padded_closing_tag`.

[WARN] (independent) daydream/admin.py + daydream/skills/data.py — Author-file `description` field now persists end-to-end. New `migrations/005_skills_description.sql` adds a nullable `description TEXT` column; `cmd_skill_add`'s INSERT and ON CONFLICT DO UPDATE clauses carry the authored string; `_parse_pair` reads it and falls back to the prior generic `"A data skill: <name>."` string only when the column is NULL/empty (pre-005 rows). Added `test_skill_add_stores_authored_description` asserting the registry surfaces the authored text through to `spec.description`.

### Carry-forwards (unchanged vs prior entry)

The 11 NOTEs from the 2026-04-23 entry still apply unchanged:

[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc. One-line cleanup.

[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s. Comment-precision nit.

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual drift catcher is `tests/drift/test_drift_constants.py::test_whimsy_prompt_suffix_matches_code_constant`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384. Field currently dead (unread).

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.

[NOTE] README.md:70 and CLAUDE.md:218 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.

[NOTE] README.md:36 — `bin/game world` one-liner still lists "list / archive / delete"; missing `restore` and `verify`.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`. Latent today.

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode). Note: `cmd_skill_add` added this round is a single-statement INSERT-ON-CONFLICT and therefore atomic by itself; no new transactional concern introduced this round.

[NOTE] daydream/events.py:117-122, daydream/api/ws.py (subscriber queue), bin/game (`cmd_logs` unvalidated path component) — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.

### Accepted Risks

Unchanged from prior entry plus one new item documented in this round's SECURITY.md update:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- New this round (documented in this round's SECURITY.md update): LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). In-scope for the v1-allowlist-trusted baseline; v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.

### Note for next turn

Active SPEC (first NPC, 2026-04-23) calls for a `migrations/005_*.sql` file. This review round landed `migrations/005_skills_description.sql`. The next migration file should therefore be `006_first_npc.sql` (or the next available sequential number).

---
*Prior review (2026-04-23, commit db60c0f): multi-room nav C1-C4, Tailscale password bypass, /assets/* no-store, CLAUDE.md updates, SPEC consume. 0 BLOCK, 0 WARN; one external-reviewer BLOCK verified false; 11 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"50310c2","reviewed_up_to":"50310c211ad7c6fafa405c9355906f229fea7ec2","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":11} -->
