## Security Review — 2026-04-23 (scope: paths)

**Summary:** One BLOCK in the new `bin/game world restore` path: tarfile extraction without a safety filter is vulnerable to CVE-2007-4559 (path traversal). A maliciously crafted archive can write arbitrary files outside `data_dir` on Python 3.10, including `~/.ssh/authorized_keys`, shell rc files, and `~/.config/cron`-style entries — yielding code execution as the user running the restore. The threat model documented in CLAUDE.md ("shipping a world to another box") explicitly involves archives received from external sources, so reachability is real. All other dimensions are clean: SQL queries are parameterized; the `serve_cached_image` route validates path components; the asset/cache module's hashes are well-isolated; admin command argument validation against the DB blocks malicious world_id values from reaching destructive ops.

### Findings

[BLOCK] daydream/admin.py:297 — Tar extraction without a safety filter allows path traversal (CVE-2007-4559).
  Attack vector: An attacker (or a careless peer) crafts a `.tar.gz` archive containing entries with `../` traversal or absolute paths, sends it to the operator (e.g. via the documented "ship a world to another box" workflow), and the operator runs `bin/game world restore <archive.tar.gz> --yes`. The code at admin.py:297 calls `t.extract(m, path=data_dir)` with no `filter='data'` argument; on Python 3.10 (this project's pinned version per `pyproject.toml`), `tarfile.extract` happily writes to `../../../etc/...` or absolute paths. POC: building a tar entry named `../../../tmp/evidence` and extracting it via the same code path successfully wrote outside the target directory in this environment. The MANIFEST.json validation only inspects the manifest's content, not the path safety of payload members. Realistic exploit chains: write to `~/.ssh/authorized_keys`, `~/.bashrc`, `~/.config/systemd/user/*.service` for code execution as the operator.
  Evidence: `daydream/admin.py:293-297`:
  ```
  with tarfile.open(archive_path, "r:gz") as t:
      for m in t.getmembers():
          if m.name == "MANIFEST.json":
              continue
          t.extract(m, path=data_dir)
  ```
  Remediation: Pass `filter='data'` to `extract()` (or `extractall()`), e.g. `t.extract(m, path=data_dir, filter='data')`. The `'data'` filter (PEP 706, available in 3.10.12+) blocks absolute paths, parent-traversal, links pointing outside the destination, special files, and ownership/permission funny business. Belt-and-suspenders: also reject any member whose `m.name` starts with `/` or contains `..`, before calling extract. After applying the filter, the existing `test_restore_round_trip` test will continue to pass; add a test that crafts a `../escape` tar entry and asserts `extract` raises.

### Accepted Risks

- Cookie `https_only=False` in `daydream/server.py:37` is documented inline ("friend-scope; box is on a private LAN/Tailscale only").
- No CSRF token on `/api/login` and `/api/logout`. Worst-case impact under the documented threat model is forced-logout from a phishing page; consistent with friend-scope posture.
- The 100.64.0.0/10 hardcoding in `daydream/api/access.py:25` is correct because Tailscale's CGNAT range is fixed by their design. A self-hosted Headscale with a custom range would need that constant updated. Documented in CLAUDE.md.
- `AccessMiddleware` reads `scope["client"][0]` directly rather than honoring forwarded-for headers. This is the secure default given uvicorn is not started with `--proxy-headers`. Operators who later put the app behind a reverse proxy must add `--forwarded-allow-ips` themselves AND audit that the proxy strips inbound `X-Forwarded-For`.

---
*Prior review (2026-04-22): no findings; `AccessMiddleware`, port hygiene, and test scaffolding were the focus.*

<!-- SECURITY_META: {"date":"2026-04-23","commit":"5de20c9845edb22c4e71fc41cad5f0f4f37bd1ce","scope":"paths","block":1,"warn":0,"note":0,"scanned_files":["bin/game","daydream/admin.py","daydream/api/ws.py","daydream/assets.py","daydream/images/cache.py","daydream/images/cli.py","daydream/images/client.py","daydream/rooms.py","daydream/server.py","migrations/002_generated_assets.sql","migrations/003_assets_world_and_pin.sql","tests/conftest.py","tests/test_admin.py","tests/test_assets.py","tests/test_db.py","tests/test_image_cache.py","tests/test_image_client.py","tests/test_image_test_cli.py","tests/test_ws_images.py","tools/arbiter-smoke.py"]} -->
