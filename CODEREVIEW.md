## Review — 2026-04-23 (commit: 293a4a4)

**Summary:** Reviewed 6 unpushed commits since the prior review (5de20c9): `88e1763` (tar path-traversal fix already validated in the prior entry) + `4d606e6`..`293a4a4` (Test Architecture C1-C5: tier markers, `bin/game test` dispatcher, DAYDREAM_TARGET knob + engine liveness gates, drift probes with git-committed baselines, qpeek human-eval loop, TESTING.md). ~3,700 lines across 68 files, most of which are tier-marker adds (`pytestmark = pytest.mark.tier_short|medium|long`) plus new scaffolding under `tests/drift/`, `tests/baselines/`, `daydream/testing/`, and `bin/qpeek-bootstrap`. Tests are green at 220/220 (short=156, medium=211, +9 drift probes in long). Security scan re-ran over the 15 novel files and found zero issues — the prior BLOCK (tar path-traversal) remains fixed and is covered by `tests/test_admin.py::test_restore_rejects_path_traversal_member`. No BLOCK or WARN findings in this review; 9 NOTEs (4 new, 5 carried forward).

**External reviewers:**
None reported findings (review-external.sh ran with empty output).

### Findings

[NOTE] daydream/images/client.py:59 — Stale comment references `tests/test_whimsy_prompt_suffix.py` as "the drift catcher" but that file was removed in commit `ea02349` (Test architecture C3). The actual drift catcher is now `tests/drift/test_drift_constants.py::test_whimsy_prompt_suffix_matches_code_constant`.
  Suggested fix: Replace the file reference with `tests/drift/test_drift_constants.py`.

[NOTE] tests/drift/aesthetics/{cozy_room,forest_path,meadow_dusk}.json — Each corpus file declares `"expected_resolution": [1024, 1024]`, but the actual workflow at `daydream/images/workflows/painterly_room.json` produces 1024x384 (documented in the workflow's own `_meta` block: "Width/height default to 1024x384 to match the SPA's room-background slot"). The field is never read by any test (only mentioned in `tests/drift/conftest.py:246`'s docstring). If a future developer wires up `probe["expected_resolution"]` into `test_image_perceptual.py`, all three probes will fail immediately because the corpus value is wrong.
  Suggested fix: Either drop the dead field from all three JSONs, or correct the values to `[1024, 384]` so the field is ready for future use.

[NOTE] tests/drift/conftest.py:148 — `assert_within` docstring claims "Non-numeric fields fall back to exact match via compare_keys semantics" but the implementation only iterates over keys in the `within` dict (line 160). Consequence: `test_llm_json_adherence.py` records `observed_keys` and `model` in the baseline but never asserts them, so an LLM silently returning extra keys, or `DAYDREAM_LLM_MODEL` silently changing, would not trip drift detection. The primary schema-keys presence check at line 56-65 of `test_llm_json_adherence.py` is what actually catches the 7B/fp8-KV regression — so this is a doc/impl drift, not a detection gap for the advertised tripwire.
  Suggested fix: Either wire compare_keys into `assert_within` (belt-and-suspenders for silent model/key drift) or drop that sentence from the docstring.

[NOTE] tests/drift/conftest.py:59 — `img.getdata()` triggers a Pillow DeprecationWarning ("will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead"). Visible in every `bin/game test long` run against the three `test_image_aesthetic_probe` probes. `pyproject.toml` pins `Pillow>=10.0` with no upper bound, so a future `pip install -U Pillow` past 14 would break the dHash path.
  Suggested fix: Switch to `list(img.getdata())` → the Pillow 10+ API uses `list(img.tobytes())` or the documented replacement when Pillow ships it; for now, silencing the warning or pinning `Pillow<14` is fine.

[NOTE] README.md:70 and CLAUDE.md:201 — Documentation still references `~/data/daydream/images/test/` for image-test output, but the implementation writes to `~/data/daydream/images/ephemeral/` (per `daydream/images/cli.py:8` and `daydream/images/client.py:175`). Separately, `daydream/testing/human_eval.py:166` renders to `images/test/human-review/<date>/` — so `images/test/` IS a live path now, just not for the `bin/game image-test` CLI. The asset-file-layout section in CLAUDE.md (around line 157) does not document the human-review sub-path. Carry-forward from prior review (2026-04-23 entry); the prior review flagged only the drift, this review adds the human-review gap.
  Suggested fix: In README.md:70, change `images/test/` → `images/ephemeral/`. In CLAUDE.md:201's `pretty` convention, expand to cover `images/ephemeral/`, `images/cache/`, AND `images/test/human-review/`. In CLAUDE.md's file-layout block, add a row for `images/test/human-review/<date>/<name>.png`.

[NOTE] README.md:36 — `bin/game world` description still lists "list / archive / delete" but the implemented subcommands also include `restore` and `verify`. Carry-forward from prior review.
  Suggested fix: Mention restore and verify in the README one-liner.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use `load_workflow()` (no overrides applied), but `_generate_persistent` uses the override-applied `base_workflow` for `cache.cache_path`. Latent today — production WS path never passes overrides. Carry-forward from prior review.
  Suggested fix: Either reject overrides on the `PersistentTarget` path, or thread the override-applied workflow through the WS helpers.

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional. DB is in autocommit mode (`isolation_level=None`), so each `DELETE` commits independently. Carry-forward from prior review.
  Suggested fix: Wrap the cascade in an explicit transaction: `conn.execute("BEGIN")` ... `conn.execute("COMMIT")` with `ROLLBACK` on exception.

[NOTE] daydream/events.py:117-122, daydream/api/ws.py:200, bin/game:202-211 — Unbounded subscriber queues; `asyncio.wait` done-set tasks not `.exception()`-ed; `cmd_logs` accepts an unvalidated path component. Three distinct carry-forwards from prior reviews; unchanged.

### Fixes Applied

None. Only NOTE-level findings; no auto-fix by policy.

### Accepted Risks

The following are documented in SECURITY.md's Accepted Risks and not re-reported here: `https_only=False` cookie (LAN/Tailscale only), no CSRF token on `/api/login` and `/api/logout` (friend-scope phishing impact only), the 100.64.0.0/10 hardcoding for Tailscale CGNAT, `AccessMiddleware` reading `scope["client"][0]` directly (secure default; documented operator caveat for reverse-proxy deployments), `bin/game` sourcing `.env` + `secrets.env` as shell (operator-controlled gitignored files), and `bin/qpeek-bootstrap` cloning + installing from `github.com/peterzat/qpeek` (supply-chain trust on the project owner's own account).

---
*Prior review (2026-04-23, commit 5de20c9): found one BLOCK (tar path-traversal in `cmd_restore`, CVE-2007-4559) which was auto-fixed; 8 NOTEs covering documentation drift, a latent cache-key inconsistency on the unused override path, a non-atomic delete cascade, and carry-forwards.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"293a4a4","reviewed_up_to":"293a4a413374df2171282d29cc0b37e4f904fc89","base":"origin/main","tier":"full","block":0,"warn":0,"note":9} -->
