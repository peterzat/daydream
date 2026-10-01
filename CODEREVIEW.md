## Review — 2026-10-01d (commit: d57fbe3)

**Summary:** Refresh review of `origin/main..d57fbe3` (all files in focus): the REFLEXES heading; `playthroughs/` leaves .gitignore behind a spoiler README, README "Blind playthroughs" explains /playthrough and links it, teardown's action-log copy names screenshots relative to `shots/` and masks the made-up password, and the skill commits each run; the first three runs (reports, notes, action logs, 403 screenshots, 33 MB). Separation check: no instance facts in the committed text; screenshots spot-checked (page only, no URL bar, password field never shows its value). Tests before: short+medium 2785 passed; after one /codefix cycle: 2785 passed (the extended test is the same test). Security (/security, paths): 0 BLOCK / 0 WARN / 10 NOTE; its teardown NOTE is folded into the WARN below.

**External reviewers:**
None configured.

### Findings

[WARN] daydream/playthrough.py:616 — teardown masks the made-up password only in the action log's `args.text`, but the folder is now committed as teardown leaves it, and the password reaches the player in its brief (`playthrough.py:188`). A player that writes it into notes.md or report.md (or types it into a text field, whose value a mark label echoes unmasked, `playthrough.py:718`) lands it in git. The three committed runs hold none of their passwords (checked); the gap is for the next run. (confidence: high that the path exists; impact low, a stopped throwaway village's account)
  Evidence: `for key in ("notes", "page_errors"): shutil.copy2(...)`; `report.write_text(body + ...)` from the player's report.md; `shareable_actions` replaces the password only inside `args["text"]`.
  Also (security, confirmed by a direct test): the player sees each screenshot's absolute path under the operator's home (`.../player/shots/NNN.jpg`), so notes or a report citing one carry the box's username and data layout; and the `reports_dir()` docstring (`playthrough.py:104`) still calls the folder gitignored.
  Suggested fix: one scrub applied to every text file teardown writes into the reports folder (each action-log line as a whole after relativizing `shot`, the copied notes and page errors, and the report body): the password masked, and the session dir's absolute path (and its player/ folder) replaced with the run's relative folder. Fix the `reports_dir()` docstring. Extend `test_teardown_lands_the_report_with_its_session_record` with the password and an absolute shot path in the fake notes, report, page errors and a mark label.

[NOTE] playthroughs/README.md:5 — says each report was written after the player "played the game in a browser by sight"; the first run (`2026-10-01-priya`) had the old text aid and opened few screenshots, which its session record shows. (low)

[NOTE] playthroughs/ — each run adds about 11 MB of JPEGs to history for good. Consider downscaling or re-encoding shots at teardown, or committing only the shots a report cites, before many more runs land. (medium)

### Fixes Applied

- [WARN] daydream/playthrough.py:616 — `scrub(text, password, sdir, sid)` masks the password and replaces the session's absolute folder (and its `player/` folder, both as written and resolved, longest first) with the run's id; teardown applies it to the copied notes and page errors, the report with its session record, and each action-log line as a whole after the shot is made relative (mark labels included). The `reports_dir()` docstring no longer says gitignored. `test_teardown_lands_the_report_with_its_session_record` now plants the password and an absolute shot path in the report, notes, page errors and a mark label, and asserts neither lands (it fails with the fix reverted). A password typed in two pieces is not caught (security NOTE; the account dies with the village).

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-01c, refresh, `adc00ff`): the second and third playthroughs' fixes and WORLD_VERSION 1.15; 2 WARN fixed in one /codefix cycle (a grown room's painting weights only the words the gardener kept; the handed-back gear's home is the loft), 0 BLOCK.*

<!-- REVIEW_META: {"date":"2026-10-01","commit":"d57fbe3","reviewed_up_to":"d57fbe3","base":"origin/main","tier":"refresh","block":0,"warn":1,"note":2} -->
