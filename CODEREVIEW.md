## Review — 2026-09-28e (commit: 03a5b08) — full

**Summary:** Pre-push review of the second half of the first prod evening's turn against origin/main (`b0377a1`): 20 commits, 62 files, +4,900 lines. The art keep and data lifecycle, `account delete`, instances (several games behind one door) with the prod swap and the edge's words, the root helper (daydream-root) and its validator, the uptime watch, the dreamer cap, and the fork path (docs/FORKING.md). Three fresh reviewers (the root helper; instances and the swap; the keep, delete and docs) plus /security of every changed code file; each finding below was re-checked against the code. Baseline: medium 1928 passed, Worker 33/33; after one /codefix pass 1949 passed, Worker 35/35.

**External reviewers:**
None configured.

### Findings

No BLOCK findings. The root reviewer found no escalation path in the helper (argument smuggling, root execution of release code, symlink races and 17 further hostile unit directives were all refused); the separation check found no person's name or private instance detail in the outgoing diff (after the history rewrite in this turn).

**WARN**

[WARN] ops/root/daydream-root:272,320,335 (parse_unit) — (/security) the parser strips Unicode whitespace where systemd strips only ASCII: `ProtectHome<U+00A0>=yes` validates clean, but systemd (v249, verified on this box) reads an unknown key and drops the directive, leaving a weaker sandbox than validated; the NBSP is invisible in the diff `units` prints for the human's --apply approval.
  Suggested fix: refuse any non-ASCII character in unit text before parsing (as it already refuses control characters); add the hostile variant to tests/test_root_helper.py.

[WARN] ops/install-prod.sh:32 — `OPERATOR="${SUDO_USER:-peter}"` falls back to this instance's username when run as root without sudo: on a fork it grants sudoers and writes root.conf and the operator units for a user that may not exist. Reclassified from NOTE (a fork footgun, cheap).
  Suggested fix: refuse to run when SUDO_USER is unset or is root ("run it with sudo as the operator"); test it in tests/test_ops_units.py.

[WARN] edge/src/worker.js (watch) with daydream/edge.py (describe_uptime) — the uptime watch never closes an outage once the flag says asleep (it returns before reading uptime), so a failure followed by `prod sleep` stays "DOWN since ..." for the whole sleep and records one long outage on wake; and planned stops with the flag awake (`instance use`, `instance migrate`, `deploy`, the stop-for passthroughs, the KV-propagation minute after `sleep` flags asleep) are recorded as unplanned.
  Suggested fix: (1) when the flag is asleep and down_since is set, close it at that tick (record `{from, to, ended: "asleep"}`); (2) open an outage only on the second consecutive failed probe (store `suspect_since` on the first failure, clear it on success; writes still happen only on a change), so a planned window shorter than the cron interval never counts; (3) describe_uptime says "(unplanned)" without claiming the flag's state. Node tests for each: failure then sleep closes; one failed tick then up records nothing; two failed ticks open.

[WARN] daydream/prodctl.py:1028,975 (instance_use, instance_create) — a world-less instance can be attached: `use` refuses only on preflight rc 3, preflight prints "live_world: missing" with rc 0, the server boots an empty data dir on the seeded legacy world and answers as the target, so the swap "succeeds" and friends land in the wrong world. `instance create` with a bad envelope leaves the dir behind and a retry fails with File exists.
  Suggested fix: `use` refuses unless preflight returns 0 and reports a live world; `create` removes the new dir when the load fails (a `daydream.instance discard NAME` run as the service user that refuses a dir holding a world), or resumes into an existing world-less dir. Tests.

[WARN] daydream/prodctl.py:1095-1107 (--instance) — `--instance` is accepted on every verb and silently retargets half of the work of verbs that act on the attached instance: `sleep --instance zork` announces, rests and journals zork and publishes its passes while the village is the one going down; `deploy --instance zork` backs up zork and migrates the village; `keepsakes` swaps KV; `instance use X --instance Y` rests Y.
  Suggested fix: accept `--instance` only on the instance-scoped verbs (the passthroughs and `backup`), refuse it elsewhere with a clear message. Tests.

[WARN] daydream/prodctl.py:228 (passthrough needs_stop) — a stop-for verb on a detached instance (`world refresh --instance zork`, `prebake`, `dream install`) stops the attached service for nothing. Reclassified from NOTE.
  Suggested fix: skip the stop when INSTANCE is set and is not the attached instance. Test.

[WARN] daydream/instance.py:95,183 — identity comes from instance.json's optional `name`, not the directory: a nameless instance.json under instances/zork gets the shared cookie `dd_session_prod`, `/status/build` says "-", every `use` fails its served check and rolls back, and `prod check` fails permanently; `migrate` keeps an existing nameless file. Reclassified from NOTE.
  Suggested fix: for a data dir under `instances/`, the name is the dir's (refuse a different `name` in the file); `migrate` writes the name into an existing file. Tests.

[WARN] daydream/prodctl.py:1003,1068 — `instance use` and `migrate` write the flag with note "" and erase an asleep note ("back Sunday"). Reclassified from NOTE.
  Suggested fix: keep the flag's note unless `--note` is given (`edge.set_state(note=None)` keeps it). Test.

[WARN] daydream/admin.py:324 (cmd_restore) with daydream/images/keep.py:75, daydream/prebake.py:98 — `world restore` extracts over an existing cache file in place ("wb"), and since the keep hard-links cache files, it overwrites a kept painting through the shared inode (reproduced: the file named for sha B then held A's bytes), breaking the keep's content addressing.
  Suggested fix: in cmd_restore, replace existing files instead of writing into them (extract to a temp name and os.replace, or unlink a regular file first); as defense in depth, make each kept inode read-only (chmod 0444 in `_store`) so any in-place open fails loudly while renames still work (check the repaint's .prev copy still works). Tests: restore over a kept painting leaves the keep intact.

[WARN] daydream/accounts_cli.py:106-134, daydream/accounts.py:290-304 — `account delete` leaves private data the docs promise to remove: `talk:<npc>:<toon>` (the player's own typed sentences), `pq:<toon>:*` (the Book), `rel:`/`relday:`/`greeted:`/`bystander:` keys naming the toon, `private_to` things (their finds), and the `dreamer-create:<account>` throttle row (reproduced: the talk log kept "my real name is ... and I live on ...").
  Suggested fix: delete the world_state keys that name the toon (the `pq:<id>:` prefix and keys ending in `:<id>` or equal to `greeted:<id>`, per the key shapes in story.py/collect.py/dialogue.py), delete things whose `private_to` is the toon, and add the `dreamer-create:` key to delete_account; assert each in tests/test_account_delete.py.

[WARN] daydream/prebake.py:51 with daydream/images/client.py (_generate_persistent) — `prebake --from-keep` selects toons with is_human_controlled = 0 only, so after a restore the portraits of players who closed a tab without resting are not restored and get repainted on the GPU; `_generate_persistent` never consults the keep on a cache miss. Reclassified from NOTE (player portraits are what the first reset lost).
  Suggested fix: on a cache miss, `_generate_persistent` restores the kept painting for that cache key (link, record, keep a "restored" line) before rendering; from-keep mode includes every toon with an appearance seed. Tests.

[WARN] daydream/images/keep.py:88-89 (records) — a torn non-ASCII line in provenance.jsonl (a full disk mid-append) raises UnicodeDecodeError outside the try, so keep-sync fails and `world reset`/`world delete` refuse. Reclassified from NOTE.
  Suggested fix: read bytes and decode each line inside the try (skip what fails). Test with a torn multi-byte line.

[WARN] daydream/prebake.py:102-104 (_adopt_from_keep) — a restored painting records the canonical prompt even when the kept image was an experimental repaint ("prompt not retained"), so the provenance is wrong. Reclassified from NOTE.
  Suggested fix: carry the found record's prompt (and a `restored_from` sha pointer) into the new record and the generated_assets row. Test.

[WARN] daydream/admin.py:805 (cmd_keep_sync) — a corrupt or unmigratable live DB makes keep-sync fail, so `world reset` (the escape hatch) refuses with a misleading "the art keep could not be written". Reclassified from NOTE.
  Suggested fix: when the DB cannot be opened, still keep every cache file (as "found", no DB needed), say the DB error plainly, and succeed if the files were kept, so a reset of a broken world still proceeds after keeping the art. Test.

[WARN] docs — (a) docs/CLOUDFLARE-SETUP.md:87 `install -m 600 /dev/null ~/.config/daydream/cloudflare.env` fails when the dir is missing (use `install -D -m 600`); (b) :96-97 the step-1 check cannot catch a bad token (no authenticated call when the KV id is unset): give a real token check (the Cloudflare token-verify endpoint); (c) backups.md:5,29-30, reset.md:17,57-58, content.md:40 name the flat `/srv/daydream/data/backups/<ts>`, wrong on a box with instances (`/srv/daydream/data/instances/<name>/backups/<ts>`; `prod backup` prints it); (d) DATA-LIFECYCLE.md:94 "`bin/game backup`" is not a verb (`bin/game world backup`, `bin/game prod backup`). Reclassified from NOTE.

**NOTE**

[NOTE] ops/systemd keepsakes/offsite (installed copies) — carried from SECURITY.md: the installed units still set NoNewPrivileges; the next `sudo ops/install-prod.sh` (which also installs the helper) carries the fix.

### Fixes Applied

All 15 WARNs in `03a5b08` (one /codefix pass), re-reviewed here against the code; four fixes ran past codefix's usual size and were read line by line (the watch, the swap and create guards, the restore and read-only keep, restore-on-cache-miss, which now runs on the live render path and falls back to a render on any error). The root helper refuses non-ASCII units and the installer refuses a missing SUDO_USER; the watch debounces and closes on sleep; instances refuse a world-less attach, clean up a failed create, scope `--instance`, skip a needless stop, name themselves by their dir and keep the flag's note; the keep survives a restore, a torn line and a broken DB, restores before rendering, and records the true prompt; `account delete` removes the dreamer's remaining private records; four doc fixes.

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
---
*Prior review (2026-09-28d, light, `26ae2da`): the reset playbook; no findings. Before it (2026-09-28c, full, `cca5c50`): the first prod evening's first half, 12 WARN all fixed.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"03a5b08","reviewed_up_to":"03a5b08e4f963369241d852ed07367eedb1c76e5","base":"origin/main","tier":"full","block":0,"warn":15,"note":1,"fixed":15} -->
