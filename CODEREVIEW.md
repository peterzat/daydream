## Review — 2026-04-24 (commit: 1b045a6)

**Summary:** Refresh review of the 5 code-bearing commits landed since the prior review (`1a92aaa`): `6f014d0` (migration 006 seeds Rook + `find_toon_in_room_by_name`), `93ab08e` (core.examine extends to toons with toon-wins-on-collision), `f6ddf66` (WS snapshot reflects NPC co-location), `f32037a` (migration 007 adds `toons.presence_text`), `2a93236` (broadcast loop emits presence narrates after controlled moves). Two SPEC turn-close + consume commits landed alongside. Focus set matches full set (9 files): `daydream/api/ws.py`, `daydream/skills/core.py`, `daydream/toons.py`, `migrations/006_first_npc.sql`, `migrations/007_npc_presence.sql`, plus 4 test files. 253/253 short + 335/335 medium green. `/security` scanned the same 9 files and returned 0 findings (SECURITY.md refreshed; Rook/Wren are fictional, `presence_text` lands in `narrate` payloads not LLM prompts, SQL is parameterized, migrations are static DDL/DML). External reviewers configured but no API keys active, so `review-external.sh` exited silently. Independent review: examine-on-toon branches (lookup order, article-stripping, case-insensitivity, room scoping) are correct; the new `_emit_npc_presence_narrates` correctly sits inside the controlled-move branch with `snapshot_seq = events.max_seq()` captured BEFORE the narrate emission so the narrates pass the snapshot-duplicate filter, narrate events thread through the per-queue broadcast back to the client with the room filter correctly dropping narrates whose player has already left the room; `presence_text` is loaded defensively on pre-007 rows; migration 006's `INSERT OR IGNORE` + migration 007's add-column-with-NULL-default are both idempotent under the `_migrations`-table guard. No new BLOCK, no new WARN, no new NOTE.

**External reviewers:**
Configured but all provider API keys are commented out in `~/.config/claude-reviewers/.env`; script exited 0 with no output (fail-open).

### Findings

No BLOCK or WARN findings. No new NOTEs.

### Fixes Applied

None.

### Carry-forwards (unchanged vs prior entry)

All 12 NOTEs from the prior entry still apply. The only one whose file is in this round's focus set is the subscriber-queue / unbounded-queue NOTE on `daydream/api/ws.py`; the new `_emit_npc_presence_narrates` calls `events.append` which enqueues to the same unbounded subscriber queues, so the concern is unchanged. Other NOTEs:

[NOTE] daydream/llm/safety.py:83 — `_CLOSE_TAG = "</player_input>"` dead after the switch to `_CLOSE_TAG_RE`. Unchanged.

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

Active SPEC (NPC dialogue — Rook speaks, 2026-04-24) calls for `skills/rook.json` + a new `tests/test_ws_rook.py`. The NPC-presence-narrate machinery this review covered is a prerequisite feature (Rook feels present in the room) and lands cleanly; the dialogue pipeline re-uses the existing data-skill executor so the next increment is largely content + tests.

---
*Prior review (2026-04-23, commit 1a92aaa): refresh review of `c33fdaa` (three WARN fixes from the prior round: narrative-text mood coverage, case-insensitive close-tag regex, `skills.description` persistence) + `1a92aaa` (docs refresh). 0 BLOCK / 0 WARN; one new NOTE (dead `_CLOSE_TAG` constant); 11 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-04-24","commit":"1b045a6","reviewed_up_to":"1b045a66576e4c55f214ec51d1d390bc737c784a","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":12} -->
