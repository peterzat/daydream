## Review — 2026-04-23 (commit: 5de20c9)

**Summary:** Reviewed 2 unpushed commits (~2,200 lines): `cd0f7d3` (SPEC consume, docs only) and `5de20c9` (asset provenance v1+v2, unified `generate_image` API, `bin/game world {list,archive,restore,verify,delete}`, migrations 002+003). Tests are green at 208/208 after one codefix cycle (baseline was 207; +1 regression test for the BLOCK fix). The security scan found one BLOCK — tarfile path traversal in `cmd_restore` — which has been auto-fixed. Eight NOTEs cover documentation drift, a latent cache-key inconsistency on the unused override path, a non-atomic delete cascade, and three carry-forwards from the prior review.

**External reviewers:**
None reported findings (review-external.sh ran with empty output).

### Findings

[BLOCK] (RESOLVED) daydream/admin.py:297 — `cmd_restore` extracted tar archives without a path-safety filter (CVE-2007-4559 path traversal).
  Evidence: `t.extract(m, path=data_dir)` on Python 3.10 will write `m.name` like `../../../tmp/foo` outside `data_dir`. Verified at runtime: a crafted entry `../../../tmp/escaped-test-file.txt` extracted via the same call shape successfully wrote to `/tmp/escaped-test-file.txt`. The MANIFEST.json validation only inspected manifest contents, not member paths. CLAUDE.md explicitly designs archive/restore as "shipping a world to another box," so externally-produced archives are an intended workflow.
  Resolution: Added explicit pre-check rejecting any member whose name starts with `/` or contains `..`, and passed `filter='data'` (PEP 706) to `t.extract(...)` as the authoritative defense. New regression test `test_restore_rejects_path_traversal_member` builds a tampered archive with a `../../../tmp/...` entry and asserts the restore returns rc=2 and the file does NOT escape to /tmp.

[NOTE] daydream/images/client.py:152, 161 — `is_persistent_cached()` and `target_dedup_key()` use `load_workflow()` (no overrides applied), but `_generate_persistent` uses the override-applied `base_workflow` for `cache.cache_path`. If any caller ever passes `model=` or `lora=` overrides to `generate_image()` for a `PersistentTarget`, the WS layer's cache hit check and the in-flight dedup key would diverge from the actual cache file location. Currently latent: production WS path never passes overrides; CLI uses `EphemeralTarget`; smoke uses `EphemeralTarget`. Worth tightening before someone tries to add per-room LoRA variation.
  Suggested fix: Either reject overrides on the `PersistentTarget` path (simpler), or thread the override-applied workflow through `is_persistent_cached`/`target_dedup_key` so the WS helpers and the actual cache key always agree.

[NOTE] daydream/admin.py:410-420 — `cmd_delete` cascade is not transactional. The DB connection is in autocommit mode (`isolation_level=None` in `db.open_db`), so each `DELETE` statement commits independently. With `foreign_keys=ON`, a constraint violation midway through the cascade leaves the world in a partially-deleted state. Currently low-risk under the v0/v1 schema (single seeded room/toon/item per world; the documented delete order respects FK relationships), but operator-introduced data could trip it.
  Suggested fix: Wrap the cascade in an explicit transaction: `conn.execute("BEGIN")` ... `conn.execute("COMMIT")` with `ROLLBACK` on exception.

[NOTE] README.md:70 and CLAUDE.md:195 — Documentation references `~/data/daydream/images/test/` for image-test output, but the implementation writes to `~/data/daydream/images/ephemeral/` (per `daydream/images/client.py:179` and `daydream/images/cli.py:8`). The "Image generation API" section in CLAUDE.md was updated to reflect ephemeral, but the "Keeper images" convention block at line 195 wasn't.
  Suggested fix: Replace `images/test/` with `images/ephemeral/` in both files.

[NOTE] README.md:84 — Test count claims "153 passing as of this commit" but the actual current count is 208. Stale.
  Suggested fix: Update to 208 (or drop the count and let pytest/CI be the source of truth).

[NOTE] README.md:36 — `bin/game world` description lists "list / archive / delete" but the implemented subcommands also include `restore` and `verify`.
  Suggested fix: Mention restore and verify in the README one-liner, or simplify to `bin/game world help` for the full list.

[NOTE] daydream/events.py:117-122 — Unbounded subscriber queues (carried forward from prior review, unchanged).

[NOTE] daydream/api/ws.py:200 — `asyncio.wait` done-set tasks not `.exception()`-ed (carried forward from prior review, unchanged).

[NOTE] bin/game:78, bin/game:202-211 — `cmd_logs` accepts an unvalidated path component (carried forward from prior review, unchanged).

### Fixes Applied

[BLOCK] daydream/admin.py:297 — Added `filter='data'` to `t.extract(...)` plus a pre-check rejecting `..` or absolute-path members. Added regression test `tests/test_admin.py::test_restore_rejects_path_traversal_member`.

### Accepted Risks

The following are documented in SECURITY.md's Accepted Risks and not re-reported here: `https_only=False` cookie (LAN/Tailscale only), no CSRF token on `/api/login` and `/api/logout` (friend-scope phishing impact only), the 100.64.0.0/10 hardcoding for Tailscale CGNAT, and `AccessMiddleware` reading `scope["client"][0]` directly (secure default; documented operator caveat for reverse-proxy deployments).

---
*Prior review (2026-04-22, commit 54f84bc): reviewed the `DAYDREAM_ACCESS` toggle (new `AccessMiddleware`), port move 8080->54321, and internal services moving to 127.0.0.1. Tests were 153/153 green; security scan returned 0 findings; one NOTE on a bash/Python case-sensitivity gap in the UFW-reminder warning.*

<!-- REVIEW_META: {"date":"2026-04-23","commit":"5de20c9","reviewed_up_to":"5de20c9845edb22c4e71fc41cad5f0f4f37bd1ce","base":"origin/main","tier":"full","block":1,"warn":0,"note":8} -->
</content>
</invoke>