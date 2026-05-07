## Review — 2026-05-07 (commit: 63e1ed0)

**Summary:** Refresh review of two unpushed commits since `541d6c7`. (1) `27534e9` adds `bin/game up-all` — a bundled boot that starts FastAPI synchronously, then kicks off vLLM + ComfyUI in the background via the existing `nohup-fork-and-return` pattern; engine startup failures are skipped via `|| echo` so an unbootstrapped engine doesn't abort the whole call. CLAUDE.md Lifecycle section + the engines-don't-auto-start paragraph both name `up-all`; smoke check in `tests/test_game_script.sh` asserts it's in the usage line. (2) `63e1ed0` lands toon-slot-management — `daydream/api/slots.py` (new) with four endpoints (`GET /api/slots`, `POST /api/slots/{N}/{create,claim,kick}`); `daydream/api/auth.py` adds `_ensure_session_id` stamping a UUID into the session on login; `daydream/api/ws.py` replaces the `HUMAN_TOON_ID = "t-wren"` constant with `_resolve_controlled_toon_id(session_id)` + `LEGACY_TOON_ID` fallback, threaded through `_state_snapshot`/`_handle_input`/`_broadcast_loop`/`_receive_loop`; `daydream/toons.py` gains `HUMAN_SLOT_RANGE` + 5 new helpers (`get_toon_by_session`, `get_human_slots`, `_slot_occupied`, `create_toon_in_slot`, `claim_slot`, `kick_slot`); `daydream/server.py` mounts the slots router; `web/{index.html,assets/main.js,assets/style.css}` add a "switch toon" footer button + slots panel with create/claim/kick affordances. 18 new tests across `tests/test_slots.py` (13), `tests/test_ws.py` (2), `tests/test_frontend.py` (3). README counts rolled forward; SPEC closed 8/8. BACKLOG `toon-slot-management` annotated ACTIVE.

**Review scope:** Refresh review. Focus: 16 file(s) changed since prior review (commit `541d6c7`). 0 already-reviewed file(s). Tier counts at HEAD: 320 short / 469 medium green; no regression vs prior 320 / 451.

**External reviewers:**
None configured (review-external.sh on PATH but produced no output).

### Findings

[NOTE] daydream/toons.py:create_toon_in_slot (lines ~165-185) — TOCTOU between `_slot_occupied` SELECT and the subsequent `INSERT`. Two simultaneous POSTs to `/api/slots/{N}/create` could both pass the SELECT-occupancy check; the second `INSERT` would then trip the schema's `UNIQUE (world_id, slot)` constraint (migration 001) and raise `sqlite3.IntegrityError`, surfacing as a 500 to the second caller instead of the SPEC-stated 409. Non-exploitable in practice — daydream is one async-single-thread FastAPI process with sync SQLite calls, so the SELECT and INSERT serialize via the GIL + asyncio cooperative model with no `await` between them — but the spec contract ("two simultaneous POSTs against the same slot result in one 200 and one 409") technically allows a 500 today.
  Evidence: `daydream/toons.py:165-185` shows SELECT-then-INSERT with no `try/except sqlite3.IntegrityError`. The unique constraint at `migrations/001_initial.sql:50` enforces row-level atomicity but the API surface doesn't translate the IntegrityError into 409.
  Suggested fix (low priority): wrap the `INSERT` in `try/except sqlite3.IntegrityError` and return `None` on hit; the existing `slots.py:create_slot` mapping of `None → 409` then handles it correctly. v2 multi-user-shared-world with multiple WS-fanout processes would actually exercise this race; v1 single-process doesn't.

### Fixes Applied

None this run (no BLOCK/WARN to fix).

### Carry-forwards (unchanged vs prior entry)

The 15 NOTEs from earlier reviews carry forward unchanged (none of their file patterns were aggravated by this turn's focus set):

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

Unchanged vs prior entry, plus three recorded by this turn's `/security`:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`. `daydream/toons.py:set_mood` is the parameterized helper; same trust class.
- `bin/vllm-bootstrap` and `bin/memory-bootstrap` interpolate `$MODEL` into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Operator-trust class.
- Stored prompt-injection via captured memory text (defense-in-depth gap surfaced earlier).
- `/status/drift` endpoint is unauthenticated by design (`AccessMiddleware` is the gate). Same trust class as `/login` and `/cache/...`.
- **NEW:** v1 friend-scope on slot endpoints — any auth'd session can claim/kick any slot; per-session ownership lands with v2 multi-user-shared-world.
- **NEW:** `_ensure_session_id` stamps fresh UUIDs in tailscale mode even without `/api/login` (consistent with "tailnet membership IS the auth").
- **NEW:** Unbounded request body on `POST /api/slots/{slot}/create`. Accepted under documented friend-scope threat model; v2 may add explicit length caps.

### Note for next turn

Active SPEC.md is closed 8/8 (toon-slot-management). Next /spec evolve cycle generates the turn-close proposal. The user noted the next direction (this conversation): world-bootstrap-opus from BACKLOG (Opus 4.7 authors a fresh world's rooms + toons + skills). The session-resolved WS path means a bootstrapped world's toons can immediately be claimed via the picker without any further auth work.

---
*Prior review (2026-05-07, commit 541d6c7): light review (docs-only) for the v0.2.0 cut. README's "Latest stable cut" rolled to v0.2.0; new "second inhabited dream" release-notes section added; TESTING.md tier counts refreshed (290/401/411 → 320/451/460); local annotated tag `v0.2.0`. 0/0/0; 15 NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"63e1ed0","reviewed_up_to":"63e1ed07da0510e6d3a9ad96ff3570371848a585","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":16} -->
