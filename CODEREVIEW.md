## Review — 2026-05-07 (commit: 0acb46a)

**Summary:** Refresh review of the 3 unpushed commits since `c94a16e` (NPC memory retrieval v0). Focus set: 11 paths — `daydream/memories.py` (NEW; capture/retrieve with pure-Python cosine + recency decay, struct-packed BLOB embeddings, lazy CPU embedder, fail-closed everywhere), `daydream/skills/data.py` (`_resolve_npc_and_world` helper + retrieve-before-render + capture-after-narrate-dispatch wiring), `migrations/009_memories.sql` (NEW; per-world memories table; FK on `world_id`), `bin/memory-bootstrap` (NEW; CPU-torch wheel install + BGE-small pre-cache), `skills/rook.json` + `skills/iris.json` (Jinja `{% if memories %}` block before player_input section), `tests/conftest.py` (DAYDREAM_MEMORY_ENABLED=0 default), `tests/test_memories.py` (NEW; 22 tests), `tests/test_ws_rook.py` (+2 integration tests), `pyproject.toml` (sentence-transformers added as runtime dep), `.gitignore` (ORIGINAL-PROMPT.md). 290/290 short + 400/400 medium green at HEAD (was 277/376; +13/+24 from new memory tests). `/security` returned 1 WARN (stored prompt-injection via captured memory text — defense-in-depth, see SECURITY.md). External reviewers configured but no API keys active; `review-external.sh` exited silently.

Independent review: SQL is parameterized at `memories.py:201-205,243-248`; `_get_embedder` lazy-loads from a module global so import is cheap and tests bypass via `_embed` mock; the `_cosine` pure-Python implementation handles dimension mismatch + zero-norm safely; the score-then-(-score, age) sort correctly breaks ties on recency; the data-skill pipeline's capture phase only fires when narration is non-empty AND not on refusal/banlist/empty-effects paths (early returns short-circuit before line 358). The `_resolve_npc_and_world` per-world scoping check at line 213 correctly excludes a toon row whose world_id mismatches the conversation's room. Test isolation is consistent with the `DAYDREAM_DRIFT_ENABLED=0` pattern — the conftest opt-out leaves existing 16 Rook/Iris tests stable.

One BLOCK: the world-delete admin cascade at `daydream/admin.py:421-432` does not include `DELETE FROM memories WHERE world_id = ?`, which violates the new FK from `memories(world_id)` to `worlds(id)` (PRAGMA foreign_keys = ON since `db.py:22`). Reproduced experimentally: insert one memory row, run the admin cascade, get `sqlite3.IntegrityError: FOREIGN KEY constraint failed`. Tests don't catch this because conftest sets `DAYDREAM_MEMORY_ENABLED=0`, so the test path never inserts memories rows.

Two WARNs: (1) `pyproject.toml` lists `sentence-transformers>=3.0` as a runtime dep, which causes `pip install -e '.[dev]'` to pull torch via the default GPU index (~2 GB), defeating `bin/memory-bootstrap`'s CPU-only wheel install (~200 MB) and contradicting the README's CPU-savings claim. (2) Stored prompt-injection via captured memory text — captured `args` and narration are rendered into future prompts WITHOUT role-separator wrapping or banlist re-scan, breaking the `<player_input>` containment for any retrieved memory.

**External reviewers:**
Configured but no provider API keys active in `~/.config/claude-reviewers/.env`; script exited 0 with no output (fail-open).

### Findings

[BLOCK] daydream/admin.py:421-432 — `cmd_delete` cascade missing `DELETE FROM memories WHERE world_id = ?`. After migration 009 lands and any memory has been captured for an NPC in the target world, the world-delete operator command fails with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` because `memories.world_id` REFERENCES `worlds(id)` and the cascade tries to delete the world row before clearing memory rows.
  Evidence: `migrations/009_memories.sql:31` declares `world_id TEXT NOT NULL REFERENCES worlds(id)`; `daydream/db.py:22` enforces `PRAGMA foreign_keys = ON`; manual repro shows FK violation when running the existing cascade against a DB with one captured memory row.
  Suggested fix: add `conn.execute("DELETE FROM memories WHERE world_id = ?", (world_id,))` BEFORE `DELETE FROM toons` at line 430 (memories references world_id only, so order is just before the worlds delete; placing it next to the other child deletes reads cleanly). Add a regression test in `tests/test_admin.py` that inserts a memory row, runs `delete --yes`, and asserts both the world is gone and `SELECT count(*) FROM memories WHERE world_id = ?` returns 0.

[WARN] pyproject.toml:22 + bin/memory-bootstrap:35-43 — Two install paths for `sentence-transformers` conflict. The pyproject runtime dep pulls torch via the default GPU index when `pip install -e '.[dev]'` runs; the bootstrap's `--extra-index-url https://download.pytorch.org/whl/cpu` install path then short-circuits because the package is already present. The README's NPC memory section claims CPU-wheel savings ("avoids the ~1.5 GB CUDA libs we never use") but real users get the heavy install regardless of order.
  Evidence: `pyproject.toml:22` declares `sentence-transformers>=3.0` in `[project] dependencies`; `bin/memory-bootstrap:35-43` does `if "$VENV_PY" -c "import sentence_transformers" 2>/dev/null; then echo "already installed"`; `README.md:94` claims the bootstrap installs via the CPU index.
  Suggested fix: move `sentence-transformers>=3.0` from `[project] dependencies` to `[project.optional-dependencies]` under a new `memory` extra (or just leave it un-declared since `bin/memory-bootstrap` is the canonical install path). Then the bootstrap is the sole install path → CPU wheels guaranteed → README accurate. Spec criterion 2's "new runtime dependency" wording deviates slightly with this fix; the spirit of "memory is opt-in via bootstrap" is preserved.

[WARN] daydream/skills/data.py:362,366 + skills/{rook,iris}.json:6 — Stored prompt-injection via captured memory text (security finding; see SECURITY.md). Captured `args` and narrate text are stored raw and rendered into future prompts at the memory-block position BEFORE the `<player_input>` envelope, with no role-separator and no banlist re-scan. A turn-1 input that passes the WHIMSY tone banlist (which only filters tone, not prompt-injection patterns) would bypass `wrap_player_input` containment on every later turn that retrieves it. v0 impact ceiling is mild voice/tone deviation (output banlist + effect allowlist still backstop); does not enable auth bypass / RCE / data exfiltration. Defense-in-depth gap consistent with friend-scope deployment posture.
  Evidence: `daydream/skills/data.py:362` `f"the visitor said: {args}"` (raw `args` from player); `:366` `f"{speaker} said: {narration}"`; `skills/rook.json:6` `{% for m in memories %}- {{ m.text }}\n{% endfor %}` is plain Jinja text-emit with no enclosing role tag.
  Suggested fix: lightest mitigation is to wrap memory-block rendering in `<memory>` role-separator tags (`{% for m in memories %}<memory>{{ m.text }}</memory>\n{% endfor %}` — analogous to `<player_input>` containment) AND have `memories.capture` short-circuit on `safety.first_banned(text)` hits before INSERT. Heavier (v2) fix lives in BACKLOG `skills-authoring-and-security`.

[NOTE] daydream/skills/data.py:366 — Capture format stutters. Memories are captured as `f"{speaker} said: {narration}"` where `speaker` is "Rook" or "Iris" and `narration` already starts with the same name in third person ("Rook lifts a forearm and brushes soot..."). Result: stored memory reads "Rook said: Rook lifts a forearm...". Cosmetic; the LLM tolerates it. Optional fix would store `narration` verbatim without the speaker wrapping, since the narration itself already names the speaker.

### Fixes Applied

- [BLOCK fixed] `daydream/admin.py:429` — added `DELETE FROM memories WHERE world_id = ?` to the cmd_delete cascade, ordered next to the other child deletes (before items/toons/rooms/worlds). New regression test `tests/test_admin.py:375 test_delete_cascades_memories` inserts a memory row, runs `delete --yes`, and asserts both the world is gone and the memory rows are too — exercises the cascade against an active FK.
- [WARN fixed] `pyproject.toml` — moved `sentence-transformers>=3.0` from `[project] dependencies` to a new `[project.optional-dependencies] memory` extra. `pip install -e '.[dev]'` no longer pulls torch via the default GPU index; `bin/memory-bootstrap` is now the canonical install path → CPU wheels guaranteed → README claim accurate.
- [WARN fixed] `daydream/memories.py:189-198 + skills/{rook,iris}.json:6` — wrapped each rendered memory in `<memory>{{ m.text }}</memory>` role-separator tags (analogous to the existing `<player_input>` containment) AND added a `safety.first_banned(text)` short-circuit at the top of `memories.capture` that returns `None` and logs a warning before any embedding or DB write. Defense-in-depth: stored prompt-injection now needs to bypass the WHIMSY input-banlist AT capture time, not just at the original turn's input gate. `daydream.llm.safety` import added at `memories.py:52`.

### Carry-forwards (unchanged vs prior entries)

The NOTE from `c94a16e` on the dead `_open_db` test helper is still present (test file untouched this round) and carries forward at NOTE severity:

[NOTE] tests/test_drift.py:61-70 — Dead `_open_db` helper. Defined but never called.

The NOTE from `b6a2551` on `tests/test_ws_iris.py` docstring drift carries forward. The 12 NOTEs from `2c3edb5` carry forward unchanged (none of their file patterns are in this round's focus set):

[NOTE] tests/test_ws_iris.py:169-171 — Stale docstring re. snapshot toons-list contract.

[NOTE] daydream/llm/safety.py:83 — `_CLOSE_TAG` constant dead after switch to `_CLOSE_TAG_RE`.

[NOTE] web/assets/style.css:183-184 — `footer a` / `footer a:hover` rules dead after 881a6dc.

[NOTE] bin/game — `cmd_up` readiness-poll comment says "~3s" but worst-case is ~13s.

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py`; actual catcher is `tests/drift/test_drift_constants.py`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each declares `"expected_resolution": [1024, 1024]` but the workflow produces 1024x384.

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims compare-keys semantics the implementation does not provide.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers Pillow DeprecationWarning.

[NOTE] README.md:70 and CLAUDE.md:218 — Docs reference `~/data/daydream/images/test/` for image-test output but the code writes to `~/data/daydream/images/ephemeral/`.

[NOTE] README.md:36 — `bin/game world` one-liner missing `restore` and `verify`.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use override-unaware `load_workflow()`, while `_generate_persistent` uses the override-applied `base_workflow`.

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional (DB in autocommit mode).

[NOTE] daydream/events.py:117-122, daydream/api/ws.py, bin/game (`cmd_logs`) — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component.

### Accepted Risks

Unchanged from prior entry:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.
- `bin/vllm-bootstrap:91` and `bin/memory-bootstrap` interpolate `$MODEL` (sourced from `DAYDREAM_VLLM_MODEL` / `DAYDREAM_MEMORY_MODEL`) into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Same operator-trust class.

### Note for next turn

Active SPEC closed at 7/7 (NPC memory retrieval). No turn-close `### Proposal` written yet (`/spec evolve` not run this turn). Backlog Sweep would propose deleting `npc-memory-retrieval (ACTIVE in spec 2026-05-07)` once the spec is formally evolved.

---
*Prior review (2026-05-07, commit c94a16e): refresh review of NPC drift loop turn (3 commits since b6a2551). 0 BLOCK / 0 WARN / 1 new NOTE (dead `_open_db` test helper); 13 prior NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"0acb46a","reviewed_up_to":"0acb46af5a7449ad9a1e4ec6de70d23bbfd8a730","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":15} -->
