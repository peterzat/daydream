## Review — 2026-05-07 (commit: 6daea43)

**Summary:** Light review (doc-only). Single commit `6daea43` updates `README.md` to fold the just-shipped NPC memory retrieval feature into the v0.1.0 release-notes section in preparation for tagging v0.1.0 at HEAD: adds the *NPC dialogue memory* bullet (per-world memories table, BGE-small CPU embedder, cosine + 24h recency-decay ranking, `<memory>...</memory>` role-separator wrapping, banlist-at-capture, fail-closed posture), bumps the Status + Tests + v0.1.0-intro tier counts to 290 short / 401 medium (the +1 medium is `test_delete_cascades_memories` from the prior turn's BLOCK fix), updates the Safety baseline bullet to mention the new `<memory>` role separator alongside `<player_input>`, updates the World admin bullet to call out memory rows in the cascade, and pivots "What's next" off NPC memory (now landed) onto LLM-driven drift, drift polish, and LanceDB-backed retrieval. No code, config, or test files touched; nothing else regressed.

Light-tier checks (factual accuracy, broken links, accidental secret leaks):
- Tier counts match HEAD: `bin/game test short` 290, `bin/game test medium` 401.
- Memory-section claims verified against HEAD code: 384-dim BGE-small (`daydream/memories.py:68`), `cosine_similarity * exp(-age_hours / DECAY_HOURS)` ranking (`memories.py:264-267`), `<memory>{{ m.text }}</memory>` template wrap (`skills/{rook,iris}.json:6`), banlist short-circuit at capture (`memories.py:195-198`), per-(npc, world) scoping (`memories.py:243-248`).
- Migration number 009 matches the file in tree.
- All bin/memory-bootstrap, BACKLOG.md, SPEC.md, CLAUDE.md, docs/gpu-and-models.md references resolve to existing files.
- No secret leaks; no link rot.

**External reviewers:**
Skipped (light review).

### Findings

[NOTE] README.md:149 — "What's next (per `BACKLOG.md`):" caption mismatches what BACKLOG.md actually contains. The three named items (LLM-driven drift, drift polish, LanceDB-backed retrieval) are forward-path proposals from SPEC.md's prior-turn `### Proposal` section, not standalone BACKLOG entries. BACKLOG.md has `npc-memory-retrieval (ACTIVE in spec 2026-05-07)` (now shipped, awaiting Backlog Sweep at next /spec evolve) but no `npc-llm-drift`, `drift-polish`, or `lancedb` entries.
  Evidence: `grep '^### ' BACKLOG.md` shows no entries with those names; the "LLM-driven drift" framing lives in the prior SPEC.md proposal.
  Suggested fix (low priority): drop the "(per `BACKLOG.md`):" qualifier — just say "What's next:" — OR add three small BACKLOG entries to back the references. Substantive content is accurate either way.

### Fixes Applied

None (light review skips the codefix loop).

### Carry-forwards (unchanged vs prior entry)

The `0acb46a` review's NOTE on the cosmetic capture-format stutter (`daydream/skills/data.py:366` writes "Rook said: Rook lifts...") is still present and carries forward at NOTE.

The 14 NOTEs from earlier reviews carry forward unchanged (none of their file patterns are in this turn's focus set):

[NOTE] tests/test_drift.py:61-70 — Dead `_open_db` helper.

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

Unchanged from prior entries:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`.
- `bin/vllm-bootstrap:91` and `bin/memory-bootstrap` interpolate `$MODEL` (sourced from `DAYDREAM_VLLM_MODEL` / `DAYDREAM_MEMORY_MODEL`) into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Same operator-trust class.

### Note for next turn

v0.1.0 tag candidate at HEAD (`6daea43`). Active SPEC closed at 7/7 (NPC memory retrieval); no `### Proposal` written yet (`/spec evolve` not run). Next /spec evolve cycle would generate the turn-close proposal AND propose deleting `npc-memory-retrieval (ACTIVE in spec 2026-05-07)` from BACKLOG.md.

---
*Prior review (2026-05-07, commit 0acb46a): refresh review of 3 unpushed commits (NPC memory retrieval v0 turn). 1 BLOCK auto-fixed (admin.py world-delete cascade missing memories DELETE), 2 WARNs auto-fixed (sentence-transformers moved to optional `memory` extra; banlist short-circuit at capture + `<memory>` role-separator wrapping). 1 new cosmetic NOTE; 14 prior NOTEs carried forward.*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"6daea43","reviewed_up_to":"6daea432d7e924f090b0bef7d3ed35daf618c7a6","base":"origin/main","tier":"light","block":0,"warn":0,"note":16} -->
