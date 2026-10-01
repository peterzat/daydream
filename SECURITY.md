# SECURITY.md

## Security Review — 2026-10-01 (scope: paths)

**Summary:** Path-scoped review of the sixteen files the caller named, read
as their change from the last scan (`677a903`) to HEAD `6a934d1`. That
covers three commits:
- `abeeb5a`: the /codereview fixes to the playthrough sandbox.
- `0ced720`: playthrough fixes in the engine, the SPA and the village. A
  beat chip hides the topic it claims, `read` on an unwritten thing answers
  in the dream's terms, the columns name what lies below the fold, Tace
  knows you already talked with Bell, the dreamseed says how many words it
  holds, and `WORLD_VERSION` is 1.14.
- `6a934d1`: the playthrough's screen-only player, with pace, notes and
  budget gates.

No new findings. The last entry's WARN (the player's sandbox) and its new
NOTE (the player's environment) are fixed, and tests pin both. Register:
0 BLOCK / 0 WARN / 8 NOTE (all eight carried; their code is unchanged).

### Scope and method

- `daydream/playthrough.py` was read in full at HEAD. The other fifteen
  files were read as their diffs from `677a903`, with some code read in
  context: the refusal branch of `verbs._execute_resolved`,
  `story.available_topics`, and the prologue's other `wind` rules.
- Also read, outside the scope but load-bearing: `claude --help` (2.1.286)
  for `--restricted` and `dontAsk`. Restricted mode confines the file tools,
  Read included, to the working directory.
- The four scoped test files pass: 137 tests, none skipped. That includes
  the Chromium tests and the planted-file regression.
- `tools/assemble_world.py --check` passes: the committed
  `worlds/lost-hours.json` matches its sources.
- No `claude -p` session was started this run. The fix cycle's live probe
  is recorded under "Closed".
- The player-text scan ran (below).

### Findings

No new security issues identified in the reviewed scope.

Carried from the last entry (still open; none of their files changed since `677a903`):

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt. The guard reads code only for literal spellings, so a computed argv or path gets neither a prompt nor a decision. Narrower rules (`.venv/bin/python -m pytest *`) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). The template's allow list is unchanged.

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list. `cat .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`.

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling. Since `d09493d` the client pauses for a minute after a timeout, a network error, a 429 or a 5xx. That caps what an outage costs in time, not what a busy player spends. Remediation: a daily ceiling from the ledger, past which `enabled()` reads off.

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision. The code is unchanged and was not re-measured this run. A time limit inside `main`, or a single-pass brace expansion, would close it.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". Outside this scope; unchanged.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The server accepts control characters in typed lines and appearance seeds. Outside this scope; unchanged.

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). Outside this scope; unchanged.

### Closed since the last entry

- **The player's sandbox** (the WARN; fixed in `abeeb5a`).
  - `./browser` runs `python -I`, so nothing in the player's folder is
    importable (`playthrough.py:200-209`).
  - The allow list is `Bash(./browser *),Edit(./notes.md),Edit(./report.md)`
    (`:425`), and setup creates both files (`:400-401`). The player never
    needs to create a file and cannot edit `./browser`.
  - Option parsing stops at `--as-player` (`:1219-1224`), so a
    `--session-dir` from the player is an unknown command.
  - Three tests pin these fixes:
    `test_the_player_runs_sandboxed_to_its_browser_and_its_own_files`,
    `test_the_wrapper_reaches_the_player_verbs_and_nothing_else` and
    `test_the_wrapper_never_runs_a_file_planted_beside_it`. The last one
    runs the generated wrapper beside a planted `json.py` and
    `daydream/__init__.py`, and asserts that neither runs.
  - The fix cycle's live `claude -p` probe confirmed that notes.md and
    report.md are writable. It also confirmed that a Write to `./json.py`,
    an Edit to `./browser` and a second `--session-dir` are refused.
- **The player's environment** (the NOTE; fixed in `abeeb5a`).
  - `player_env()` is an allowlist: `PLAYER_ENV_KEYS` plus `LC_*`
    (`:433-444`).
  - The test seeds `TYPESAFE_API_KEY`, a token-shaped name and a
    `CLAUDE_CODE_*` variable, and asserts that none passes.
  - The proxy and CA variables pass so the player's own CLI can reach its
    API. A proxy URL can carry credentials, but none of these variables is
    set on this box.

### Traced and cleared this run (not findings)

- **The pace, notes and budget gates** (`Browser.gate`, `:1078-1096`) keep
  a playthrough honest. They are not a boundary.
  - They read only clocks, counters and the notes file's size and mtime.
  - A request marked `internal` skips the gates and the action log
    (`:1034`). Only setup sends one: the wrapper builds requests from fixed
    argparse keys (`player_request`, `:1169-1208`), and the player can run
    nothing else.
- **What the player reads** no longer carries the page's text.
  - `format_response` prints the screenshot's path, the address bar, the
    focused field and counts (`:1141-1166`). The `text` verb is gone.
  - Mark labels go only to the action log. A password field reads there as
    bullets (`fieldDesc`). The sign-in `type` was already logged (last
    entry).
- **`transcript_result`** counts Read calls on `/shots/` paths in the
  player's transcript. It opens nothing by those paths.
- **The SPA's fold tabs** (`main.js:1736` `updateProseIndex` and `:1823`
  `updateMarginIndex`) build every new element with `textContent`,
  `dataset` and an `onclick` property, and use `innerHTML` only to clear.
  The resident's name from `.topic-who` reaches only `textContent` and
  `data-region` (`:1874-1875`).
- **`verbs._unreadable_line`** (`verbs.py:564`, `:1321-1336`) answers `read`
  on a thing with no read verb, to the actor alone.
  - It runs after the same in-scope resolution as the refusal it replaces,
    and names the thing the same way.
  - Its regex is a plain alternation over the thing's name, aliases and
    seed, with no nested quantifiers.
- **`story.offered_topics`** (`story.py:542`) only filters chips by
  authored labels and aliases. Both kinds of topic always carry `aliases`.
- **The village data.**
  - The new `wind` rule repeats the existing rule's effects under one more
    condition: narrate, `set_pflag`, `set_property` on an `@dobj` that must
    carry `own_clock`, `adjust_rel` and `add_fact`.
  - The `SPOKE-BELL` rules (`00-prologue.json:77-80`) set a flag on the
    asking player only.
  - The spreading fact's `{actor}` comes from the existing rule. Dreamer
    names reaching resident prompts is an accepted risk.

### Player-text scan (CLAUDE.md "Player text is data")

- Prod and dev both ran in this review. Nothing was flagged, and there were
  no bursts. Prod had no items since the clean start. Dev's items were
  unchanged since the last scan: the agents' probe dreamers and the
  operator's dev username, with no typed lines. The counts, the verdict and
  the high-water marks are in the local instance notes, never here
  (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped diff holds none of these: a key, a token, a private-key block,
  an email, a box or tailnet address, a home path, the operator's name or
  the instance domain. The only pattern hits were pytest decorators.
- The tests' secrets are synthetic, and their names are the fixtures'
  (Robin Ash, Wren).
- The commits since `677a903` on the scoped files hold no key-shaped value.
- `playthroughs/`, `instance/`, `.env` and `.claude/settings.local.json`
  are still ignored, and git tracks nothing under `instance/` or
  `playthroughs/`.

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
*Prior review (2026-10-01, paths, commit `677a903`): nine files covering the new /playthrough harness and the review fixes in `story._tell`, `trace` and `model_eval`. It found one WARN: the blind player's sandbox did not hold, because a file the player wrote in its own folder ran as the operator through `./browser`. It also found one NOTE: the player's environment was filtered by a denylist. Both were fixed in `abeeb5a`, and the model-eval NOTE was closed. The register stood at 0 BLOCK / 1 WARN / 9 NOTE. The full entry is at `git show abeeb5a:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-01","commit":"6a934d10361102581de15fab0c17840a7645dee4","scope":"paths","scanned_files":["daydream/growth.py","daydream/playthrough.py","daydream/story.py","daydream/verbs.py","daydream/version.py","tests/test_browser_flow.py","tests/test_playthrough.py","tests/test_story.py","tests/test_verbs.py","web/assets/main.js","web/assets/style.css","web/index.html","worlds/lost-hours.json","worlds/lost-hours/arcs/00-prologue.json","worlds/lost-hours/walkthroughs/keeper-welcome.json","worlds/lost-hours/world.json"],"block":0,"warn":0,"note":8} -->
