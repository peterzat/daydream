## Review — 2026-09-28b (commit: f3f46dc) — full

**Summary:** Pre-push review of the operating turn against origin/main
(`fdf4077`): 5 commits, 34 files, +1,774 / -90 (`bin/game prod check`, the
prodctl NOTE fixes, the review-NOTE fixes in accounts/auth/admin/SPA/Worker,
a headless-browser test, ops and runbook tests, and the playbooks in
docs/runbooks/). Two fresh reviewers read it in parallel: one for the code
(all new tests confirmed to fail when their fix is reverted), one
fact-checking every playbook and doc claim against the code. Each finding
below was re-checked against the code before inclusion. Baseline: medium
tier 1685 passed, Worker tests 27/27, browser tests 2/2 with Chromium; after
two fix passes 1701 passed, Worker 27/27, ruff clean. A /security scan of the
code changed since its last run found 0 BLOCK / 0 WARN / 2 NOTE (the
`/status/who` spoof, fixed here, and the timer units awaiting the operator's
`sudo ops/install-prod.sh`).

**External reviewers:** None configured.

### Findings

No BLOCK findings.

**WARN**

[WARN] daydream/server.py:177 — `/status/who` prints player-chosen names inside its own `name [id], ` layout, so a toon name can fake another toon's id entry and steer moderation onto the wrong friend.
  Evidence: names allow `[`, `]` and `,` (printable, at most 24 characters). A toon named `B [t-slot2-9f4f6ed2], A` makes the line read as if a second toon carried Mira's id; docs/runbooks/friends.md tells the operator to take the id from this output, and `delete-toon <id>` then deletes the real Mira (the name isn't equal to the key, so the ambiguity refusal never fires).
  Suggested fix (the code reviewer and the /security scan agree): (1) one toon per line, id first, name JSON-quoted (`json.dumps(name, ensure_ascii=False)`), then the owner's username and `(away)` when not live, e.g. `playing:\n  t-slot5-aaaa1111  "B [t-…], A"  owner robin  (away)`; keep `playing: no one`. (2) Refuse `[`, `]` and any substring shaped like a toon id (`t-slot\d+-[0-9a-f]{8}`, and any existing toon id) in toon names at create (daydream/api/slots.py). (3) `_find_toons` also counts a toon whose NAME contains the key as a match, so an id quoted inside another name is ambiguous. Update tests/test_admin_surfaces.py; add tests that a bracketed, id-bearing name is refused at create and cannot produce a line starting with another toon's id. `prodctl.status()` prints the body as is.

[WARN] daydream/prodcheck.py:169-205, 290 — one probe's network error aborts the whole check with no per-check output, in the verifier docs/runbooks/incident.md says to run first.
  Evidence: `http_request`, `ws_session` and `run` catch nothing, and `report()` runs only after every probe. A DNS/TLS failure or a WebSocket `open_timeout` reaches `prodctl.main` as a bare "error: timed out"; `websockets.exceptions.InvalidMessage` and `http.client.IncompleteRead` are not OSError subclasses and end in a traceback.
  Suggested fix: wrap each probe so an exception becomes a failing `Check(name, False, f"{type(e).__name__}: {e}")`, and always reach `report()` (timer checks included). Test: a `request` that raises for one URL yields one failing check and the rest still run.

[WARN] daydream/prodcheck.py:147-155 — a timer job that is not installed, or whose timer is not enabled, reads "ok (not run yet)" forever.
  Evidence: `systemctl show nonexistent.service -p Result -p ExecMainExitTimestamp` prints `Result=success`, `ExecMainExitTimestamp=n/a` (verified on the box, `LoadState=not-found`).
  Suggested fix: also read `LoadState` of the service (fail unless `loaded`) and `ActiveState` of the matching `.timer` (fail unless `active`); `check_timer` takes both. Tests for not-found and an inactive timer.

[WARN] daydream/prodcheck.py:288 with docs/runbooks/verify.md:20 — an awake box behind an asleep flag passes `prod check`, and verify.md says it fails.
  Evidence: `expect` is derived from the flag itself (`"awake" if (awake and flag != "asleep") else "asleep"`), so after a `prod wake` that could not flip the flag (the case incident.md and sleep-and-wake.md describe) every check passes with "edge status: asleep" while friends cannot get in.
  Suggested fix: when the service is active and the flag is `asleep`, add a failing check ("the flag says asleep while the service runs: friends see the asleep page; `bin/game edge wake` unless that is intended"). Update verify.md's row: a stale awake flag on an asleep box is harmless (the Worker reads an unreachable origin as asleep), so it is not a failure. Test both.

[WARN] daydream/dream.py:842 and :780 — in prod, `dream rehearse` crashes copying its report into the read-only release, and `dream install` is gated only by the rehearsal committed from dev.
  Evidence: rehearse writes `data/dreams/<id>/rehearsal.json`, then `shutil.copyfile(... , pdir / "rehearsal.json")`; a release is `chmod -R a-w` (prodctl.py:385) and the process runs as the service user, so it raises PermissionError. `install_ready(patch, pdir)` reads only `pdir/rehearsal.json`. docs/runbooks/content.md steps 4-5 therefore fail, and a prod install is gated on a rehearsal against dev's world.
  Suggested fix: in rehearse, skip the copy (say where the report is) when `pdir` is not writable; make install-check/install accept a passing rehearsal of exactly this patch from `config.data_dir() / "dreams" / <id> / "rehearsal.json"` first, then `pdir`. Tests: a read-only patch dir rehearses and installs from the data-dir report.

[WARN] docs/runbooks/content.md:38-39 — "Undo a bad dream by restoring the pre-dream snapshot it printed": no prod verb can (`world snapshot-restore` refuses while a live DB exists, admin.py:599-605, and only the service user can move it).
  Suggested fix: take `bin/game prod backup` immediately before `dream install`, and undo with `bin/game prod world restore-backup /srv/daydream/data/backups/<that ts>` (which also rolls the accounts DB back to that moment).

[WARN] docs/runbooks/friends.md:27 — "closing it there ... takes it back": after a 4409 close the tab stops retrying (`dreamingElsewhere`), so closing the other tab does not bring this one back.
  Suggested fix: "reload this tab, or press enter in 'your dreamer' here, to take it back."

[WARN] docs/runbooks/backups.md:41-47 — "restore from any machine holding one of the SSH keys" is followed by `bin/game prod offsite-restore`, which decrypts only with the box's own key and needs cloudflare.env and wrangler (prodctl.py:695).
  Suggested fix: prove the round trip on the box with `prod offsite-restore`; from another machine, fetch the object from R2 and `age -d -i <your ssh key>`.

[WARN] .claude/skills/village/SKILL.md:43-46 — the numbered `sleep` steps are out of order (the code: warn and wait, flag asleep, stop tunnel and service, rest everyone and write journals, sync keepsakes, stop the engines; prodctl.py:567-605).
  Suggested fix: list them in that order, as sleep-and-wake.md does.

[WARN] daydream/edge.py:44 — `PUBLIC_STATUS` hardcodes `https://www.eidolon.com/daydream/edge/status`, so a fork's `bin/game edge status` probes this instance, contradicting "a fork changes the few committed instance values" (README, GOING-LIVE, CLOUDFLARE-SETUP's list).
  Suggested fix: derive it from edge/wrangler.toml's `PUBLIC_HOST` and `BASE` vars (edge.py already reads that file for the KV id). Test with a synthetic wrangler.toml.

[WARN] daydream/accounts.py `commit_password_change` — the password change is split around an await, so a reset redeemed in that window could be overwritten by a change still in flight from a session the reset just ended (recorded by the /security scan as a non-finding; the fix is two lines).
  Suggested fix: `prepare_password_change` returns the hash it verified against; `commit_password_change` updates `WHERE id = ? AND password_hash = <that hash>` and, if no row changed (or the kept session no longer exists), raises AccountError("your password changed meanwhile; sign in again"). Test: a hash change between prepare and commit is refused.

**WARN (reclassified from NOTE: cheap, and each is a playbook inaccuracy an agent would act on or a small invariant gap)**

[WARN] daydream/keepsakes.py:122 with accounts.py:442 — the 180-day cap is applied when passes sync, but the Worker trusts the published `expires` (the 30-day sliding expiry), so a session crossing 180 days during a sleep keeps its keepsakes until that expiry. Publish `min(expires_at, created_at + SESSION_MAX_DAYS)`.

[WARN] .claude/settings.local.json (local) with docs/runbooks/README.md, CLAUDE.md, README.md — `prod account cli-cookie` (prints an admin session cookie) and `prod world load ... --force` (overwrites the live world) are not among the prompting verbs the docs list. The ask rules were added locally outside the fix pass; the fix pass adds both verbs to the documented lists (docs/runbooks/README.md, CLAUDE.md "Agent policy for prod" and "This repo and this instance", README.md).

[WARN] docs/runbooks/content.md:43 — "Prod never renders room or resident art": a target missing from the copy is painted lazily by prod on first entry; `prebake --from-cache` lists such targets as `missing`.

[WARN] docs/runbooks/deploy.md:21 — "~1650 tests"; the tiers collect ~1690.

[WARN] docs/GOING-LIVE.md:243 — lists "prod listens only on loopback" among what `prod check` verifies; no check looks at the bind address.

[WARN] docs/GOING-LIVE.md:261 — the browser test runs "in CI's tier and in the deploy gate"; CI skips it (no browser).

**Re-review of the first fix pass (cycle 2)**

[WARN] daydream/api/slots.py `_mimics_a_toon_id` — a new name is refused if it contains ANY existing toon id, residents included (`t-bell`, `t-fen`, `t-mott`, ...), so ordinary names are refused: "Matt-Fenwick" contains "t-fen", "Kat-bell" contains "t-bell".
  Evidence: `any(t.id.lower() in low for t in toons._query("world_id = ?", ...))` scans every toon in the world. Moderation (`_find_toons`, `rest-toon`/`delete-toon`) acts only on player toons, slots 1-99.
  Suggested fix: scan only player toons (`"world_id = ? AND slot BETWEEN 1 AND 99"`), keep the bracket and `t-slot…` shape rules. Test: "Matt-Fenwick" is accepted in the Lost Hours world (whose resident ids include `t-fen`), and a name containing a player toon's id is still refused.

### Fixes Applied

All 18 WARNs, in `f3f46dc` (two /codefix passes, each re-reviewed here against the
code): the `/status/who` layout, name rules and substring-aware moderation;
`prod check`'s per-probe isolation, timer install/active checks and the
asleep-flag-over-a-running-service check; prod dream rehearse and
install-check reading the data dir; the password change's compare-and-swap;
the 180-day cap on published pass expiry; `edge status` deriving its URL from
wrangler.toml; the playbook and doc corrections; and (cycle 2) the name rule
narrowed to player toons so residents' short ids don't refuse ordinary names.
The two local ask rules (`prod account cli-cookie`, `prod world load`) were
added outside the fix pass.

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.

---
*Prior review (2026-09-28, refresh, `3df294b`): the going-live push; 3 BLOCK (the Worker's Access-cookie leak on WebSocket answers, the front door's empty credentials, "rest" re-entering) and 9 of 10 WARNs fixed before it was pushed as `fdf4077`; the tenth (the /village deploy wording) was fixed by the operator's direction in this turn.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"f3f46dc","reviewed_up_to":"f3f46dc9505542ed84cf56b8c6bdc659535723e2","base":"origin/main","tier":"full","block":0,"warn":18,"note":0,"fixed":18} -->
