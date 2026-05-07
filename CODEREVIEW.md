## Review — 2026-05-07 (commit: 541d6c7)

**Summary:** Light review (docs-only). Single commit `541d6c7` cuts v0.2.0: README.md "Latest stable cut" → v0.2.0 plus a new "v0.2.0 — second inhabited dream" release-notes section above v0.1.0 capturing the deltas (LLM-driven drift narrates with mood-aware canned fallback, drift polish — per-NPC weights + room-occupancy suppression + mood-affecting drift, drift instrumentation — voice-bench harness + outcome counters + `/status/drift` endpoint, tooling — `bin/install-hooks` + memory salience drift probe). v0.1.0's stale "What's next" line removed. TESTING.md tier-count annotations rolled forward from v0.1.0 (290/401/411) to v0.2.0 (320/451/460) at lines 58, 117, 125, 133, 267. SPEC.md closed 6/6. Local annotated tag `v0.2.0` created at this commit (not pushed). No code, config, or test files touched.

Light-tier checks (factual accuracy, broken links, accidental secret leaks):
- Tier counts match HEAD: `bin/game test short` 320, `bin/game test medium` 451, all-tier collect 460.
- Release-notes claims verified against HEAD code: `_NPC_DRIFT_WEIGHT` + `DAYDREAM_DRIFT_SUPPRESS_OCCUPIED` + `DAYDREAM_DRIFT_LLM_ENABLED` + `_DEFAULT_MOOD_DRIFT_PROB = 0.2` all present in `daydream/drift.py`; 5 corpus files in `tests/drift/drift-voice/`; `bin/install-hooks`, `daydream/drift_samples.py`, `tests/drift/test_memory_ranking.py`, `tests/baselines/memory_ranking.golden.json` all exist; `/status/drift` endpoint at `daydream/server.py:60`; `bin/game drift-samples` subcommand at `bin/game:374`.
- `git tag -l` shows both `v0.1.0` and `v0.2.0`; v0.2.0 annotated, dated 2026-05-07, points to `541d6c7`.
- TESTING.md count refresh internally consistent: short (320) + medium-only (131) = medium total (451); medium (451) + drift probes (9) = long (460).
- All bin/install-hooks, BACKLOG.md, SPEC.md, CLAUDE.md, docs/gpu-and-models.md references resolve to existing files.
- No secret leaks; no link rot.

**External reviewers:**
Skipped (light review).

### Findings

No issues found.

### Fixes Applied

None (light review skips the codefix loop).

### Carry-forwards (unchanged vs prior entry)

The 15 NOTEs from earlier reviews carry forward unchanged (none of their file patterns are in this turn's focus set):

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

Unchanged vs prior entry:

- Existing: cookie `https_only=False`, no CSRF token on `/api/login` or `/api/logout`, the 100.64.0.0/10 Tailscale CGNAT hardcoding, `AccessMiddleware` reading `scope["client"][0]` directly, the intentionally-unauthenticated `/cache/...` static route, `bin/game` sourcing `.env` + `secrets.env`, `bin/qpeek-bootstrap` cloning from `github.com/peterzat/qpeek`, and `bin/game cmd_logs` unvalidated path component.
- Tailscale-mode login short-circuit (`daydream/api/auth.py:32-34` and `is_authed` bypass).
- LLM-controllable `toon_id` in `set_mood` effects (effects.py:128-151). v2's per-effect jsonschema + target authorization lands under BACKLOG `skills-authoring-and-security`. `daydream/toons.py:set_mood` is the underlying parameterized helper — it inherits the same authorization concern at its data-skill caller, not at the helper itself.
- `bin/vllm-bootstrap` and `bin/memory-bootstrap` interpolate `$MODEL` into an unquoted heredoc to invoke `huggingface_hub.snapshot_download`. Operator-trust class.
- Stored prompt-injection via captured memory text (defense-in-depth gap surfaced in SECURITY.md WARN at `daydream/skills/data.py:361-367` + `skills/{rook,iris}.json:6`). The LLM-driven drift path inherits the same gap class via `<memory>{{ m.text }}</memory>` rendering in `_render_drift_prompt`. Backstops are sound.
- `/status/drift` endpoint is unauthenticated by design (`AccessMiddleware` is the gate; loopback / tailnet only). Exposes three integer counters since process boot. Same trust class as `/login` and `/cache/...`.

### Note for next turn

v0.2.0 tag exists locally at `541d6c7` but is NOT pushed. Pushing the tag (`git push origin v0.2.0`) is a separate operator action. The branch (`main`) push is also pending. Active SPEC.md is closed 6/6 (v0.2.0 cut); next /spec evolve cycle generates the turn-close proposal.

---
*Prior review (2026-05-07, commit c8f66d4): refresh review of one bundled commit covering drift polish round two + drift instrumentation. 0 BLOCK / 0 WARN / 0 new NOTE; 15 NOTEs carry forward. Tier counts 320 short / 451 medium green; no regression. /security path-scoped over 5 paths with new code surface; 0/0/0 with one new accepted risk recorded (`/status/drift` AccessMiddleware-gated).*

<!-- REVIEW_META: {"date":"2026-05-07","commit":"541d6c7","reviewed_up_to":"541d6c7c12ff6498332e64dc5a1f0f8b14e7e3c7","base":"origin/main","tier":"light","block":0,"warn":0,"note":15} -->
