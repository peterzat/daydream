## Review — 2026-09-28h (commit: 18bcbd0)

**Summary:** Refresh review of the 20 unpushed commits over `origin/main` (`b6c7644`): the first friend's fix pass (docs/playtests/2026-09-28-first-friend.md). Every changed file is in the focus set and was read at full depth, with an independent adversarial pass by a subagent and a `/security` scan of the 30 code and data files. 0 BLOCK / 6 WARN / 3 NOTE; all six WARNs fixed in two /codefix cycles, each with a test; tests stable (medium 1980 passed before, 1987 after; long 2017 passed before the fixes; `ruff check .` green).

**External reviewers:**
None configured.

### Findings

[WARN] daydream/dream.py:387 — a dream patch's `threads` validate but are never installed
  Evidence: `threads` joined `_LIST_SECTIONS` and `_DEF_KEYS`, so `merge`/`check_patch` accept `add.threads`, but `apply_patch` writes only `for sec in ("rules", "storylets", "collectibles")`. Reproduced: a patch adding one thread checked clean and applied, and `story.threads_for` returned nothing; the rehearsal twin (built via `merge`) had it, so live and fresh diverge.
  Suggested fix: include `threads` in that loop (or iterate the list sections minus rooms/toons/things); add a test in tests/test_dream.py.

[WARN] web/assets/main.js:953 — your own echoed words clear "the dream stirs..." before the resident's reply
  Evidence: `verbs._handle_talk` now appends a private `say` before `dialogue.talk` awaits the model; `renderEvent`'s `say` branch falls through to `clearPending()`. A talk (or an unmatched ask, which becomes talk) shows the echo and loses the waiting cue for the ~2-3 s of the model call, or until the foggy line.
  Suggested fix: when the event is the player's own echo (`kind === "echo"`, or a `say` from `selfToonId` with `recipient_id === selfToonId`), insert it before the pending line and leave the pending line in place.

[WARN] daydream/api/ws.py:970 — the "went home while you rested" note is consumed on the server but lives only in the page
  Evidence: `take_went_home` clears the note when the first snapshot is built; web/assets/main.js:383 draws it from that snapshot with no `data-seq`, so any same-room re-snapshot (`chat.innerHTML = ""`: someone arrives, a take, a face painted) erases it, and a redeploy reload on entry (`triggerUpdateReload` returns early) loses it outright (unlike `while_you_slept`, which is stashed).
  Suggested fix: after the first snapshot is sent, append each note as a private narrate (`recipient_id` = the toon) so it lives in the log and replays; drop the snapshot field and its SPA rendering.

[WARN] daydream/parser.py:625 — `_GROUP` swallows "and" lists
  Evidence: `_GROUP` runs before the AND-list branch, so "take both the letter and the key" matches with noun "letter and the key" and answers "You don't see any letter and the key here.", taking nothing (before, the AND-list took each).
  Suggested fix: when the group's noun contains an AND-list separator, strip the quantifier and let the AND-list branch handle it.

[WARN] (security) daydream/verbs.py:1471 — account delete keeps what a player said to residents
  Evidence: the new private echo `say` rows (recipient = the speaker's toon) hold the player's words to residents; `accounts_cli._delete_account` / `_forget_dreamer_state` never touch the event log, while docs/DATA-LIFECYCLE.md promises the delete removes "what they said to each resident" and keeps only the shared history (what others saw). The older private chatter line quoting unparsed text (`ws.py` chatter) has the same shape.
  Suggested fix: when a dreamer is deleted, delete the event rows addressed only to it (`recipient_id = <toon id>`; nobody else saw them, seqs are never reused); test in tests/test_account_delete.py; name private lines in DATA-LIFECYCLE.md as something that goes.

[NOTE] daydream/dream.py:144 — the dream's envelope reconstruction keeps a fixed set of room keys, so a rehearsal copy drops a room's `at`; display-only (the arrival line), so a rehearsal is unaffected.

[NOTE] (security) tests/test_config_edge.py:61 — a real tailnet address in a test fixture (outside this diff; carried).

[WARN] tests/test_browser_playtest.py:5 — CI lint (`ruff check .`, .github/workflows) fails on the new browser test: 14 errors (I001 import order; F811 for each fixture imported from tests/test_browser_flow.py and then taken as a test parameter). CI's lint is already red on `origin/main` from 3 older errors (tests/test_layout_screens.py:199 F811, the same fixture pattern; tests/test_root_helper.py:439 and :655 B905 `zip()` without `strict=`), so the push would keep CI red.
  Suggested fix: make `ruff check .` pass: sort the import block; mark the imported fixtures as used by pytest without F811 (a per-file `# noqa: F811` on the parameters, or a `[tool.ruff.lint.per-file-ignores]` entry for these browser test modules); add `strict=True` to the two `zip()` calls (their lists are equal-length by construction, as the adjacent asserts show).

### Fixes Applied

Cycle 1 (/codefix): the five WARNs above the lint finding, each with a test verified to fail without its fix (tests/test_dream.py::test_a_dream_can_add_a_thread, tests/test_browser_flow.py::test_your_own_words_told_back_keep_the_waiting_line, tests/test_ws.py::test_what_went_home_is_a_private_line_that_a_re_snapshot_keeps, tests/test_parser.py::test_a_quantified_and_list_takes_each_named_thing, tests/test_account_delete.py::test_delete_removes_the_lines_only_the_dreamer_saw); CLAUDE.md and docs/DATA-LIFECYCLE.md follow. Re-reviewed: resolved. Remaining edge (NOTE): if a redeploy reload fires on the first snapshot of an entry, the went-home line is stored in the log but the reloaded page starts with an empty log and does not show it.

Cycle 2 (/codefix): the lint finding. `ruff check .` passes (which also clears CI's three older errors): the new test's import block sorted, `[tool.ruff.lint.per-file-ignores]` F811 for the two browser test modules that import fixtures, `strict=True` on the two zips. Re-reviewed: resolved. Committed as `18bcbd0`.

### Accepted Risks

Carried forward (the standing register lives in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc;
  `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust;
  CGNAT hardcoding in tailscale mode.
---
*Prior review (2026-09-28g, refresh, `44d8690`): comings and goings, the dreamer panel, Talk on the page, `prod plan` and the publish loop; 0 BLOCK / 3 WARN / 1 NOTE, all WARNs fixed.*

<!-- REVIEW_META: {"date":"2026-09-28","commit":"18bcbd0","reviewed_up_to":"18bcbd07d87419056b81191f956ebb194accf3ea","base":"origin/main","tier":"refresh","block":0,"warn":6,"note":3} -->
