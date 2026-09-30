# SECURITY.md

## Security Review — 2026-09-30 (scope: paths)

**Summary:** Path-scoped review of the 17 files the caller named, read as
their change from the last scan (`68125c8`) to HEAD `068a34c`: the review
fixes (`d09493d`), the private telling of `{dreamers_today}` (`e5863f9`),
the Jev report's p95 (`d69442e`), and docs. The four WARNs of the last
entry are closed. The three guard fixes have regression tests and are
installed live, and the operator accepted the judge's exact list. One new
NOTE: the switch that keeps Jev off during `bin/game model-eval` does not
survive litellm's import. Register: 0 BLOCK / 0 WARN / 9 NOTE (one new,
eight carried).

### Scope and method

- Each scoped file's diff from `68125c8` to HEAD was read. So were
  `tools/agent_guard.py`, `daydream/jev/client.py`, `daydream/jev/runtime.py`
  and `daydream/jev/settings.py` as they stand, and the code the changes
  lean on: `effects.second_person_recipient` and `tell_others`,
  `story.available_topics`, and the import-time `.env` load in litellm and
  python-dotenv (read from source; the `.env` itself was not read).
- The six scoped test files pass (416 tests).
- The guard: `bin/game guard status` reports that the installed copy
  matches the repo. The live settings run the hook as `/usr/bin/python3 -I`
  and hold the template's allow and ask rules exactly.
- The rewritten heredoc reader, the find check and the protected-write
  check were verified through their new regression tests and the install
  check only. This run did not probe them independently for new spellings.
  Their assurance rests on those tests and on the accepted risk that the
  guard is a pattern check, not a boundary.

### Findings

[NOTE] daydream/model_eval.py:1281-1288, with :170 (`_install_recorders`) — `main()` pops `DAYDREAM_JEV_API_KEY`, `TYPESAFE_API_KEY` and `DAYDREAM_EGRESS_URL` so that a run measures the local path (codereview 2026-09-30d). The run's first `import litellm` (:170) happens with `LITELLM_MODE` unset. Nothing on this path imports `daydream/llm/client.py`, which sets it, and neither `bin/game` nor `.env` sets it. litellm then calls `load_dotenv()`, which walks up from `.venv/.../litellm/` to the repo's `.env`. With `override=False` it restores any variable that is absent, so the popped key comes back. With the dev key in `.env` (the documented setup), Jev is on for the whole run.
  Attack vector: None. This is a control that does not hold. Each run sends TypeSafe the judge's context and drafts and the topic lines of the eval sets. Those are agent-authored (canon residents, invented dreamers), so no player text leaves. The cost is a small spend, and a local-model comparison that is partly Jev's, which the fix meant to prevent. The new test (`tests/test_model_eval.py:204`) replaces `_run` and runs under conftest's `LITELLM_MODE=PRODUCTION`, so it cannot see this.
  Remediation: In `main()`, set `os.environ["LITELLM_MODE"] = "PRODUCTION"` before the pops, or import `daydream.llm.client` first. In the test, `monkeypatch.delenv("LITELLM_MODE")` and assert that the patched `_run` sees it set.

Carried from the last entry (still open):

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt. The guard reads code only for literal spellings, so a computed argv or path gets neither a prompt nor a decision. Narrower rules (`.venv/bin/python -m pytest *`) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). The template's allow list is unchanged.

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list. `cat .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`.

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling. Since `d09493d` the client pauses for a minute after a timeout, a network error, a 429 or a 5xx. That caps what an outage costs in time, not what a busy player spends. Remediation: a daily ceiling from the ledger, past which `enabled()` reads off.

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision. The code is unchanged and was not re-measured this run. A time limit inside `main`, or a single-pass brace expansion, would close it.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". Outside this scope; unchanged.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The server accepts control characters in typed lines and appearance seeds. Outside this scope; unchanged.

[NOTE] daydream/skills/effects.py:356-357 (was :347) — The placeholder expander still runs over a letter's body and a dreamer's looks. Since `e5863f9` it fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). Outside this scope; unchanged.

### Closed since the last entry

- **Guard heredocs** (`_heredoc_spans`, `_heredoc_kind`): fixed in
  `d09493d`, with the cases `test_a_heredoc_hides_no_command` and
  `test_a_heredoc_is_found_as_the_shell_finds_it`. Installed.
- **Guard find listing** (`_finds_list_only`): fixed, with
  `test_a_find_lists_only_when_its_names_reach_only_text_filters`.
  Installed.
- **Guard protected writes** (`_protected_write`, `_find_runs`): fixed, with
  `test_every_way_to_write_a_protected_file_asks`. Installed.
- **The judge's data**: docs/EXTERNAL.md lists what `judge_view` sends, and
  the operator accepted that exact list (`1768691`). It moves to Accepted
  Risks. The stale `DAYDREAM_JEV` docstring in `daydream/jev/__init__.py`
  is corrected.
- **The hook's interpreter**: the template and the live settings run
  `/usr/bin/python3 -I`.

### Traced and cleared this run (not findings)

- **`trace.expand_placeholders`.**
  - `re.sub` with a function inserts dreamer names literally, so a name
    cannot inject a group reference.
  - `_SENTENCE_START` runs in time linear in the line.
  - The "you" form is used only when the event is private to the actor
    (effects.py:356, story.py:235); `tell_others` keeps every name.
  - In `story._tell`, a line with no recipient is still filled before
    routing. A dreamer's name read as second person can narrow such a room
    line to its actor. It never widens one (`second_person_recipient`
    returns only the actor), so there is no confidentiality impact.
- **`jev/runtime.topic`.** Jev's pick must still be one of `plain`
  (runtime.py:88). Topics that share a name with an open beat are now
  withheld from Jev. Every entry carries `aliases` (story.py:520-537).
- **`jev/client.ask`.** One deadline through `asyncio.wait_for`. The log
  lines and ledger rows are unchanged: purpose, outcome, status, time,
  tokens, cost, and an error's type name only.
- **`jev report`.** `ms` is sorted before the nearest-rank p95. Disagreements
  are still labelled as player text and JSON-escaped.
- **`model_eval`'s judge wrapper** passes `toon` through (the last review's
  BLOCK fix), covered by `test_a_guarded_talk_under_the_model_eval_judge_tag`.
- **`prodctl.plan`**: a comment change only.

### Player-text scan (CLAUDE.md "Player text is data")

- Prod and dev both ran in this review. Nothing was flagged, and there were
  no bursts. Prod had no new typed lines. Dev's only new input was the
  agent's own probe dreamer. The counts, the verdict and the high-water
  marks are in the local instance notes, never here (players' text stays
  off GitHub).

### Secrets, PII and the instance

- The scoped diff's 623 added lines hold no key, token, private-key block,
  email, box or tailnet address, home path, operator name or instance
  domain. Every pattern hit was a pytest decorator or a test name. Test
  fixtures use `test-key` and invented dreamers.
- The last three commits of `jev/client.py`, `jev/settings.py` and the Jev
  tests hold no key-shaped value. No `.env` was ever committed, on any ref.
- Outside the path scope, but in the outgoing push: `068a34c` adds
  REFLEXES.md's "Jev's first prod decision". It describes the operator's
  typed line without quoting it, as CLAUDE.md requires.
- `instance/`, `.env` and `.claude/settings.local.json` are still ignored.

### Accepted Risks

Accepted by the operator for going live (`docs/GOING-LIVE.md` section 9;
docs/ADMIN-ROOT.md "Security posture", 2026-09-28):

- **The engines run as `peter`.** vLLM (`:8000`) and ComfyUI (`:8188`)
  listen unauthenticated on loopback and run as `peter`, who is in the
  docker group. The prod service user can reach both. Planned fix: a
  separate engines user.
- **Local attackers are best-efforts only.** The box is single-user, and
  `peter` keeps the root-equivalent `docker` group, so a hostile process
  running as the operator is out of scope. The helper, the root-only
  secrets, and the validated and logged root actions are reasonable
  precautions, not a boundary against the operator's own user.
- **Known local-only residual (docs/ADMIN-ROOT.md).** systemd reads a
  release's `.release.env` as root, and releases belong to the operator. So
  the operator's user could point it at the tunnel token or at the
  gateway's key file. Anyone who can do that already holds `docker`.
- **The pre-login surface is public** (the door, login, invite redemption,
  static assets). The app and the edge both throttle it.
- **Friends drive shared-world verbs on shared objects** (the co-op
  design).
- **What friends type reaches the local LLM.** Role separation, length
  caps, banlists and strict output validation stand between them.

Accepted by the operator for Jev (docs/EXTERNAL.md, 2026-09-30; the exact
judge list confirmed in `1768691`):

- **While a key is set, TypeSafe receives** friends' typed lines to
  residents and the judge's context. That context includes other dreamers'
  names, whereabouts and deeds. TypeSafe states no retention, and the door
  does not say so.

Accepted in the 2026-09-29 codereview (CODEREVIEW.md):

- **A village thing handed to a dozing dreamer** (`verbs._hand_to_player`,
  the tuck-away branch) waits in their satchel until they rest. A page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. BACKLOG `dozing-handover-of-village-things`.

Carried register (from prior reviews; still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths. Neither path exists in the live Lost Hours world
  (planned for v2).
- Raw parser input is not role-separated. The output is re-grounded to a
  closed verb and an in-scope id. One reply may carry up to three commands,
  and each passes the same check.
- NPC dialogue and growth are exposed to prompt injection. Input is
  wrapped, capped and banlisted, and output is validated before any
  mutation. A promise judge (with Jev beside it when a key is set) only
  chooses among drafts or the authored deflection.
- World envelopes, archives, the installer and `bin/game` are trusted as
  the operator's own. That covers world load and reset content, `reset`'s
  `rm -rf`, dev `.env` sourcing, the dev `0.0.0.0` bind, and the deprecated
  `bootstrap_world`.
- Event queues are bounded (256, drop-oldest).
- DNS (127.0.0.53) and AF_UNIX leave the prod sandbox.
- Any local process can reach `127.0.0.1:54322` and set its own
  `X-Daydream-Client-IP`. That moves throttle keys only; the gate still
  applies.
- `gpu.lock` is writable by the service.
- Invite slugs are unsalted sha256 over about 983,000 phrases, so a copy of
  the accounts DB recovers open slugs.
- Strangers can keep invitations paused (a global cap); `invite unblock`
  reopens them.
- On the Workers Free plan, an anonymous client can exhaust the daily
  request quota. The one WAF rule covers the login and invite paths.
- The operator's Cloudflare token is account-wide: Workers Scripts edit
  cannot be scoped to one Worker.
- Toon names are not unique, and lookalikes are not folded. A new
  dreamer's name must be unique under case, spacing and compatibility
  folding; confusable alphabets and legacy duplicates remain.
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one.
  - `tools/agent_guard.py` has backed them since 2026-09-29, and since
    `8eb8107` the hook runs an installed copy that the operator promotes.
    It is a pattern check, not a boundary: spellings through variables,
    `$'...'`, extglob, interpreter one-liners, script files and the like
    remain (BACKLOG `agent-sessions-without-root`). The allow list runs
    interpreters with no prompt (NOTE above).
- Player text reaches the agent's context through `bin/game play` (names,
  speech, moves, gestures; letters and looks marked) and through
  `bin/game jev report --disagreements` (labelled as data). The verbs an
  injected instruction would want stay behind ask rules.

---
*Prior review (2026-09-30, paths, commit `68125c8`): 48 files covering the agent-guard rework and its installed copy, Jev and the egress gateway. It found four WARNs, three guard spellings that had stopped asking and the Jev judge sending other dreamers' data that EXTERNAL.md did not list, plus four new NOTEs. /codereview fixed the guard WARNs in `d09493d`, and the operator accepted the judge's exact list in `1768691`. The full entry is at `git show a3ce0ef:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-30","commit":"068a34ca19c71395c53e21cc3df66d7719661373","scope":"paths","scanned_files":["daydream/jev/__init__.py","daydream/jev/cli.py","daydream/jev/client.py","daydream/jev/runtime.py","daydream/model_eval.py","daydream/prodctl.py","daydream/skills/effects.py","daydream/story.py","daydream/trace.py","docs/claude-settings.local.example.json","tests/test_agent_guard.py","tests/test_jev.py","tests/test_jev_runtime.py","tests/test_model_eval.py","tests/test_promise_guard.py","tests/test_trace.py","tools/agent_guard.py"],"block":0,"warn":0,"note":9} -->
