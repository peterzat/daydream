# SECURITY.md

## Security Review — 2026-09-30 (scope: paths)

**Summary:** Path-scoped review of the 22 files the caller named, read as
their change from the last scan (`d98b73f`) to HEAD `6981ba7`. That covers
the parser's whitespace fix (`922c122`), the agent-guard rework
(`aef3abd`), and the playtest turn on parts, the heard gate and reply
ranking (`c95f2a1` to `6981ba7`). The parser WARN is resolved. There are
three new WARNs. The guard's raw pass now deletes a quoted command
substitution inside a redirection target, so a gated verb there gets no
decision; six spellings that asked before `aef3abd` no longer do. A chain of
about 500 `eval`s makes the guard raise, and it still fails open (the
carried NOTE, now reachable with a short command). A click frame's ids reach
the dream digest as sent, and the player-text scan never reads them. The
register was 0 BLOCK / 3 WARN / 4 NOTE; /codereview fixed all three WARNs
in `bc0fb71` (see "Fixed after this scan" below), so it now reads 0 BLOCK /
0 WARN / 5 NOTE (the guard's nested-brace timeout added as a NOTE).

### Scope and method

- Each scoped file's diff from `d98b73f` to HEAD was read in full, and
  `tools/agent_guard.py` whole. So was the code the changes lean on:
  - `verbs._execute_resolved` and `_resolve_in_scope`, `objects.in_scope`
    and `visible_to`
  - the WS receive loop and `_handle_command`
  - `glimpse._best`, `answer` and `_local_line`; `heard.on_event`;
    `effects._apply_narrate`
  - `textscan.gather`, `dream.digest` and `render_digest`,
    `inputs.export_walkthrough`
- The six scoped test files pass (255 tests). `tools/assemble_world.py
  --check` confirms that the committed artifact matches its sources.
- A throwaway world (the canonical envelope, the suite's environment, a
  model client that raises) took crafted click frames and 500-character
  typed lines.
- The guard at `d98b73f` and at HEAD judged the same command payloads (as
  data, never run), and the real hook process ran under its 5 s timeout.
  Bash itself confirmed which substitutions run.

### Findings

[WARN] tools/agent_guard.py:110-112 (`_RAW_REDIRECTION`, applied at :366),
with :130-133 — Since `aef3abd`, the raw pass deletes each redirection and
its whole target before it looks for gated verbs. A target's double-quoted
part is deleted whole, `$( )` and backticks included. Bash runs a command
substitution inside a redirection target or a here-string, even when the
redirection then fails. The parsed pass keeps a double-quoted target as one
token and never reads inside it, and it takes the `;` that stands for an
unquoted backtick as the target. So a gated `bin/game prod` verb inside a
substitution in a target gets no decision from either pass. The raw pass
exists to catch a gated verb inside a quoted `$( )` (security WARN
2026-09-29); the docstring's "not modeled" line is about paths computed at
run time, not this.
  Attack vector: Player text that reaches the session (the dream digest,
`bin/game play`, letters) carries an instruction, and the agent runs a
command such as `echo x > "$(bin/game prod invite create --for Eve)"`. Bash
mints the invite while it works out the file name. The guard says nothing,
so only the harness's own rules stand, and they match command text by
prefix.
  Evidence (28 probes; G is a gated verb):
- HEAD gives no decision on 17 of them: `> "$(G)"`, `>"$(G)"`, `2>"$(G)"`,
  `&>"$(G)"`, `>> "$(G)"`, `exec 3>"$(G)"`, `cat < "$(G)"`,
  `cat <<< "$(G)"`, ``> "`G`"``, ``> `G` ``, ``echo '>"' "`G`"``, and six
  that asked at `d98b73f`: `> y"$(G)"`, `>| "$(G)"`, `> "a b $(G) c"`,
  `> "${HOME}$(G)"`, `> "$(echo; G)"` and `>"$(cd /tmp && G)"`.
- A bash run in the scratchpad created a marker file from inside a `>`, a
  `2>`, a `>|` and a `<<<` target.
  Remediation:
- End a raw-pass target at a substitution, and keep a variable in it: a
  backtick or `$(` ends the double-quoted alternative, and a backtick joins
  the unquoted class's exclusions. The pattern's second line becomes:

  ```python
  r"(?:-(?=[\s;&|()<>]|$)|\s*(?:\\.|\"(?:[^\"\\$`]|\\.|\$(?!\())*\"|'[^']*'|[^\s;&|()<>'\"\\`])+)?")
  ```

  A scratch copy with that line asked on all 28 probes, including a quoted
  `"/tmp/$x"` target inside a quoted substitution, and left all 116
  committed `cmd,want` cases in `tests/test_agent_guard.py` unchanged.
  Ending at every `$` instead missed three of the probes.
- In `_split_commands`, never take a separator as a redirection's target.
- Add the probes to `test_a_redirection_and_its_target_are_read_whole`.
- This is a guard edit, so it costs the operator one approval. Batch it
  with the next WARN and the guard NOTEs open in CODEREVIEW.md.

[WARN] tools/agent_guard.py:434-445 (`main`), with :182-183 (`eval` in
`_unwrap`) — The guard still fails open when `decide()` raises (the NOTE
carried from the last entry), and a short command now makes it raise.
`_unwrap` reads each `eval` by recursing, so a chain of about 500
(`eval eval ... cmd`, about 2.5 KB) passes Python's recursion limit. The
hook exits 1, which Claude Code treats as a non-blocking error: the command
runs with no decision from the guard. That drops any ask the raw pass
already found, and every deny that only the parsed pass makes: a credential
path spelled with a glob, a brace group, `..` or a backslash, or reached
through `cd`. Bash runs such a chain to its end.
  Attack vector: An instruction in player text leads the agent to put a long
`eval` chain before a gated verb or a glob-spelled credential read. The
guard crashes, and the harness's own rules decide.
  Evidence (the real hook process):
- `cat` of the SSH key's path spelled with a glob (`.s?h`) is denied. After
  1,000 `eval`s the hook exits 1 with a RecursionError and no decision. The
  shortest failing chain was about 497 `eval`s (2,485 characters).
- `bash -c` ran the inner command of a 1,000-`eval` chain.
- A second way to get no decision: `TOKEN_PRINTERS`' lazy run is still
  quadratic over one long line. `echo git` repeated 9,000 times (81 KB) took
  4.7 s of the hook's 5 s, so a longer line times out.
  Remediation:
- In `main`, wrap `decide` in `try/except Exception` (RecursionError
  included) and print an `ask` that names the failure.
- Ask when `eval` or shell nesting passes a small depth (16, say).
- Ask, before any regex runs, for a command above a set size (16 KB, say).
- Tests: a 1,000-`eval` chain asks or denies, and a 100 KB line decides
  within the timeout.

[WARN] daydream/api/ws.py:1241-1253 (`_handle_command`) — A click frame's
`dobj_id` and `iobj_id` are recorded in the input log as sent: any string up
to the 2,000-character frame. The dream digest prints them
(`dream.py:520`, `:596`; JSON-quoted, cut to 300 characters). The
player-text scan reads only a command row's verb and args
(`textscan.py:92-93`). So words a player puts in a click id reach the
session at dream time without passing the scan that CLAUDE.md requires
before every push. The new `dobj_name` is recorded too, in `resolved` only.
Nothing prints that field today (not the digest, the export or the scan),
so it is a gap in the scan but not yet a path to the session. The
concurrent codereview (2026-09-30c, preliminary) raised that half.
  Attack vector: An invited player sends a frame by hand,
`{"kind": "command", "verb": "examine", "dobj_id": "<instruction>"}`. The
command is refused as out of scope, but its row stays. The next dream digest
shows the text, and the scan reports nothing.
  Evidence: in the throwaway world, an instruction sent as a `dobj_id`
appeared in `render_digest()` and not in `textscan.gather()`.
  Remediation:
- Record only ids that resolve in the dreamer's scope (`clicked_in_scope`,
  :1051), and a fixed marker for the rest.
- Have `textscan.gather` read `dobj_id`, `iobj_id` and
  `resolved[].dobj_name` for command rows.
- A test: a frame with an unknown id records the marker, and the scan shows
  a clicked name.

Fixed after this scan (/codereview 2026-09-30c, cycle 2, `bc0fb71`;
re-reviewed, medium tier 2578 passed):

- The redirection-target WARN: a raw-pass target ends at `$(` or a
  backtick (the line above, verbatim), and `_split_commands` never takes a
  separator as a target. All 28 probes ask; every earlier `cmd,want` case
  answers as before. One new false ask: a quoted log path with a
  substitution in it (`> "/tmp/deploy-$(date +%s).log"`).
- The fail-open WARN: `main` turns any exception into an ask naming it;
  `eval`/shell nesting past 16 levels asks; a command over 16 KB skips the
  slow whole-line checks and asks, while the credential-name check and the
  parser still run (a deny still wins; the committed 96 KB `cd` line is
  still denied, in 0.66 s). A 1,000-`eval` chain asks through the real hook.
- The click-id WARN: `_handle_command` records an id only when it names
  something in the dreamer's scope (`(out of scope)` otherwise), and
  `textscan.gather` reads a command row's ids and `dobj_name`.

[NOTE] tools/agent_guard.py `_resolve` (brace expansion) — one word of
about 50,000 nested braces (100 KB) still takes 9.6 s, past the hook's 5 s
timeout, so that line gets no decision (18.9 s before). Asking on every
command over 16 KB would close it but turns the 96 KB `cd` test's deny into
an ask; a time limit inside `main`, or a single-pass brace expansion, would
close it without that. A guard edit, so it waits for the next guard batch.

Resolved since the last entry (verified this run):

- **[WARN] The chain-split patterns backtracked on whitespace runs**
  (daydream/parser.py). Fixed in `922c122`.
  - `parse_line` collapses every whitespace run to one space before it
    splits (:237), and `_segments` has no other caller.
  - 500-character lines parse in 0.2 to 2.8 ms (0.38 s before): spaces,
    tabs and newlines, no-break spaces, comma runs, `and then` runs,
    periods, `then` runs, and a mix.
  - The patterns that read the raw line first (`ws._WHAT_NOW_RE`,
    `ws._HELP_RE`, `meta.kind`) take under 2 ms on the same lines.
  - `test_a_long_whitespace_run_parses_fast` holds it.
- **The guard WARNs /codereview fixed in `aef3abd`** (backtracking in
  `TOKEN_PRINTERS` on a short padded line, `>|`, a `cd` that may not run,
  globs and brace groups) hold, and `tests/test_agent_guard.py` passes. The
  two new gaps in the same code are the WARNs above.
- **[NOTE] The guard fails open.** Now the second WARN above.

The findings below are carried forward. Their lines are unchanged, or
outside this scope.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py:200-207) — About
twenty pushes to a fork pull request from a branch named `main` fill the one
page of runs. A red main then reads "unknown" in `prod check` and
`prod plan`. Remediation: read main's head sha and that commit's runs, or
page until `limit` push runs are found.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's
description prints unmarked in `play`. So does a look that echoes a
sentence from a grown room or a grown thing. The server accepts control
characters in typed lines and appearance seeds. `glimpse.py` changed only
in parts, which are authored data, so nothing here has changed.
Remediation: carry a grown marker in the snapshot and on those narrate
lines, and refuse non-printable characters at the server.

[NOTE] daydream/skills/effects.py:347 — The placeholder expander still runs
over a letter's body and a dreamer's looks. It fills only
`{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:129-136 — Running `account delete --yes`
during a resident's reply leaves that reply and its `talk:`/`rel:` records
behind. The new draft ranking (`dialogue.unmet_names`) writes nothing for
a deleted dreamer, so the window is as before.

### Traced and cleared this run (not findings)

- **Parts on the click path** (`ws._handle_command`, `verbs.py:492-510`,
  `glimpse.part_host`).
  - A clicked name reaches what a typed name reaches (a part's forwarding,
    the absent answer, glimpses, "You don't see"), and each is told only to
    the actor. The part path makes no model call.
  - A part's thing comes from `glimpse._hosts`, which is `objects.in_scope`
    (another dreamer's private things are filtered out). It then passes
    `_resolve_in_scope` and the verb check, like a clicked id, and a verb
    its thing does not take is refused.
  - The name is cut to 60 characters, and the frame is capped and
    rate-limited as before.
  - The glimpse model line is keyed on the prose's own phrase. Its prompt
    carries a resolved verb name and the scene's words, never the typed
    text.
- **The page** (`web/assets/main.js`). `data-part` and the id are escaped,
  prose is escaped before it is linked, and the card's tab uses
  `textContent`. A part link sends its shown text back as `dobj_name`. An
  echoed name carrying markup reached only its sender and rendered as text.
- **Cards** (`effects.py:366-375`). The new `part` key passes the same
  all-strings filter.
- **Heard and dialogue.** `heard.on_event` now ignores `src: "local"` lines,
  so a model line can no longer turn a subject into a chip.
  `dialogue.unmet_names` only reorders drafts. It adds no model call, and
  the promise guard still reads the chosen draft.
- **The loader** (`glimpse.validate_glimpsed`, `format2.py:426-430`).
  `part` must be a boolean, only a thing has parts, and a part may not share
  its thing's names. Parts are authored data only: growth cannot write
  `glimpsed`, and `talk` cannot `set_property`.
- **The detail lint** (`prose_nouns.detail_aliases`) runs only in tests, on
  escaped patterns.
- **World data.** The new content is authored narration and one part.
  `assemble_world --check` matches, and WORLD_VERSION is 1.13 (MINOR).

### Player-text scan (CLAUDE.md "Player text is data")

- Prod and dev both ran in this review. Nothing was flagged, and there were
  no bursts. Prod had no new typed lines, and dev's were a test dreamer's.
  The counts, the verdict and the high-water marks are in the local
  instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped diff's 825 added lines hold no key, token, private-key block,
  email, box or tailnet address, home path, operator name or instance
  domain. The only long runs are test names. The last three commits of
  `tools/agent_guard.py`, its tests and `daydream/api/ws.py` hold no secret
  shape either.
- The only names are canon residents. `instance/` and
  `.claude/settings.local.json` are still ignored.

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
  the operator's user could point it at the tunnel token. Anyone who can do
  that already holds `docker`.
- **The pre-login surface is public** (the door, login, invite redemption,
  static assets). The app and the edge both throttle it.
- **Friends drive shared-world verbs on shared objects** (the co-op
  design).
- **What friends type reaches the local LLM.** Role separation, length
  caps, banlists and strict output validation stand between them.

Accepted in the 2026-09-29 codereview (CODEREVIEW.md):

- **A village thing handed to a dozing dreamer** (`verbs._hand_to_player`,
  the tuck-away branch) waits in their satchel until they rest. A page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. Refusing the hand-over broke the arc contract: walkthrough
  players never open a socket, so every walkthrough hand-over runs through
  the dozing branch. BACKLOG `dozing-handover-of-village-things`.

Carried register (from prior reviews; still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths. Neither path exists in the live Lost Hours world
  (planned for v2).
- Raw parser input is not role-separated. The output is re-grounded to a
  closed verb and an in-scope id. One reply may carry up to three commands,
  and each passes the same check. A target name the model gives reaches
  only glimpses and "not here", told to the actor.
- NPC dialogue and growth are exposed to prompt injection.
  - Input is wrapped, capped and banlisted, and output is validated before
    any mutation.
  - Refusal `reason` text is narrated without an output-banlist pass,
    through escaped sinks.
  - Every titled place, grown ones included, is in each resident's prompt.
  - A promise judge reads the drafts and the player's words. Its output is
    one enum verdict per draft and only chooses among the drafts or the
    authored deflection.
- World envelopes, archives and `bin/game` are trusted as the operator's
  own. That covers world load and reset content, `reset`'s `rm -rf`, dev
  `.env` sourcing, the dev `0.0.0.0` bind, and the deprecated
  `bootstrap_world`. None of these takes network input.
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
- Toon names are not unique, and lookalikes are not folded.
  - Moderation refuses an ambiguous key, and `/status/who` shows the id and
    the owner.
  - Since 2026-09-29, a new dreamer's name must be unique under case,
    spacing and compatibility folding.
  - Confusable alphabets are still not folded, and legacy duplicates stay.
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one.
  - `tools/agent_guard.py` has backed them since 2026-09-29. It is a
    pattern check, not a boundary: spellings through variables, `$'...'`,
    extglob, interpreter one-liners and the like remain (BACKLOG
    `agent-sessions-without-root`). Glob- and brace-spelled credential
    paths are modeled since `aef3abd`.
  - The two guard WARNs above are not unmodeled spellings: one is a
    regression of a modeled one, and the other is a crash.
- Player text reaches the agent's context through `bin/game play`: names,
  speech and move lines, and, marked since 2026-09-29, letters and looks.
  Gesture lines carry dreamer names the same way. The verbs an injected
  instruction would want stay behind ask rules.

---
*Prior review (2026-09-30, paths, commit `d98b73f`): 15 files covering the
review fixes in `4aeb1e9` and the agent-guard rework in `d98b73f`. It
closed the tea-cup and guard WARNs and two NOTEs, found the parser
whitespace WARN (fixed since in `922c122`) and the guard's fail-open NOTE,
and carried 0 BLOCK / 1 WARN / 5 NOTE. The full entry is at
`git show dadb9c0:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-30","commit":"6981ba7f4adb641fd8ffe491929062ff7cc64fb4","scope":"paths","scanned_files":["daydream/api/ws.py","daydream/dialogue.py","daydream/glimpse.py","daydream/heard.py","daydream/llm/format2.py","daydream/parser.py","daydream/prose_nouns.py","daydream/skills/effects.py","daydream/verbs.py","daydream/version.py","tests/baselines/whole_aliases.json","tests/test_agent_guard.py","tests/test_chains_guesses.py","tests/test_glimpse.py","tests/test_heard.py","tests/test_linkify.py","tests/test_prose_nouns.py","tools/agent_guard.py","web/assets/main.js","worlds/lost-hours.json","worlds/lost-hours/regions/01-clocktower.json","worlds/lost-hours/walkthroughs/keeper-welcome.json"],"block":0,"warn":0,"note":5} -->
