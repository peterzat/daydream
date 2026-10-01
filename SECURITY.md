# SECURITY.md

## Security Review — 2026-10-01 (scope: paths)

**Summary:** Path-scoped review of the nine files the caller named, read as
their change from the last scan (`068a34c`) to HEAD `677a903`. That covers
the /playthrough harness (`daydream/playthrough.py`, its tests, the
`bin/game playthrough` verb and the ignored `playthroughs/` folder) and the
review fixes in `story._tell`, `trace` and `model_eval`. One new WARN: the
blind player's sandbox does not hold. A file the player writes in its own
folder runs as the operator through the one command it is allowed. One new
NOTE: the player's environment is filtered by a denylist. The model-eval
NOTE is closed. Register: 0 BLOCK / 1 WARN / 9 NOTE (one new NOTE, eight
carried).

### Scope and method

- `daydream/playthrough.py` and `tests/test_playthrough.py` are new and were
  read in full. The other seven files were read as their diffs from
  `068a34c`, with `story._tell` and `model_eval.main` read in context.
- Also read, outside the scope but load-bearing:
  - `.claude/skills/playthrough/SKILL.md` and
    `docs/playtests/BROWSER-BRIEF.md`;
  - `claude --help` (2.1.286), for `--restricted`, `--tools`,
    `--allowedTools` and `dontAsk`;
  - the installed litellm's import-time `.env` load.
- The sandbox escape was reproduced in the scratchpad. The exact wrapper
  `setup()` writes, run as `./browser look` from a folder holding a planted
  `json.py`, ran that file as uid 1000. The same wrapper with `-I` ignored
  the file and still loaded the package through the editable install. No
  `claude -p` session was started.
- The three scoped test files pass (55 tests, the Chromium ones included).
- The player-text scan ran (below).

### Findings

[WARN] daydream/playthrough.py:193-200 (`wrapper_script`), with :407-416 (`player_argv`) and :437 (`run_player`) — The player's sandbox does not hold. `claude -p` runs with the player's folder as its working directory. It pre-approves bare `Write` and `Edit` there, and `Bash(./browser *)`. `./browser` is a shell script that runs `.venv/bin/python -m daydream.playthrough` from that same folder, and `python -m` puts the working directory first on `sys.path`. So a file the player writes there (`json.py`, or `daydream/__init__.py`) is imported before the real module. It runs as the operator, outside Claude Code, where dontAsk, restricted mode and the allow list never see it. The agent guard does not see it either: restricted mode ignores the user, project and local settings, where its hook is configured. The wrapper itself also sits in the writable folder. This run did not test whether a Write or Edit to it keeps the exec bit.
  Attack vector: Two pre-approved actions: Write `./json.py` with any code, then run `./browser look`. Reproduced: the planted file ran as uid 1000 through the exact wrapper `setup()` writes. Nothing outside reaches the player today. The village is fresh, the server listens on loopback, the SPA links nowhere off its origin, and the operator writes the persona. Exploiting it takes the player model itself, stuck or steered by on-screen text. The local model's improvised replies are the one source on that screen the project treats as untrusted. The reach would be the operator's whole user: the docker group, the prod sudoers entries, the Cloudflare token's folder, the gh login and the operator's Claude login. The docstring, the skill and `test_the_player_runs_sandboxed_to_its_browser_and_its_own_files` all promise that nothing runs but `./browser` and edits to the notes and report.
  Remediation: Run the wrapper's interpreter isolated: `exec {py} -I -m daydream.playthrough ...` (verified: the planted file is ignored and the package still loads). Narrow the writes to the two files the brief names: `--allowedTools "Bash(./browser *),Edit(./notes.md),Edit(./report.md)"` (Edit rules cover the Write tool). That also protects `./browser`. Check with one probe session that a Write to `./json.py` or `./browser` is refused. Pin both in the tests, and add the regression: run the generated wrapper from a folder holding a planted `json.py`, and assert the file never runs.

  Status (2026-10-01, /codereview fix cycle): fixed as remediated. `./browser` runs `python -I`; the allow list is `Bash(./browser *),Edit(./notes.md),Edit(./report.md)` and setup creates both files; `test_the_wrapper_never_runs_a_file_planted_beside_it` plants `json.py` and `daydream/__init__.py`. A live `claude -p` probe confirmed: notes.md and report.md writable, a Write to `./json.py` and an Edit to `./browser` denied, the player's own `--session-dir` refused.

[NOTE] daydream/playthrough.py:419-423 (`player_env`) — The player's environment drops only `DAYDREAM_*`, `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`. `bin/game` exports everything in the repo's `.env` and the per-host secrets file (`set -a`, bin/game:95-106). So `TYPESAFE_API_KEY`, which `jev/settings.py:35` accepts as the Jev key, reaches the player's `claude -p` and every `./browser` it runs. So does any other exported secret (checked with synthetic values). `test_the_player_inherits_no_keys_and_none_of_daydreams_settings` asserts that no `*_API_KEY` remains but seeds only `ANTHROPIC_API_KEY`. Today the player could read its environment through the WARN above. It could also expand a variable inside an allowed `./browser` argument, if Claude Code permits that (not tested). Remediation: build the environment from an allowlist (`PATH`, `HOME`, `USER`, `LANG`/`LC_*`, `TERM`, `TMPDIR`, and `XDG_RUNTIME_DIR`, which `sock_path` needs for the wrapper to find the daemon's socket). In the test, seed `TYPESAFE_API_KEY` and a token-shaped name.

  Status (2026-10-01): fixed. `player_env()` is an allowlist (`PLAYER_ENV_KEYS` plus `LC_*`); the test seeds `TYPESAFE_API_KEY`, a token-shaped name and a `CLAUDE_CODE_*` variable. The live probe signed in and played with this environment.

Carried from the last entry (still open):

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt. The guard reads code only for literal spellings, so a computed argv or path gets neither a prompt nor a decision. Narrower rules (`.venv/bin/python -m pytest *`) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). The template's allow list is unchanged.

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list. `cat .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`.

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling. Since `d09493d` the client pauses for a minute after a timeout, a network error, a 429 or a 5xx. That caps what an outage costs in time, not what a busy player spends. Remediation: a daily ceiling from the ledger, past which `enabled()` reads off.

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision. The code is unchanged and was not re-measured this run. A time limit inside `main`, or a single-pass brace expansion, would close it.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". Outside this scope; unchanged.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The server accepts control characters in typed lines and appearance seeds. Outside this scope; unchanged.

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). Outside this scope; unchanged.

### Closed since the last entry

- **model-eval and litellm's `.env` load.** This was the last entry's NOTE,
  raised to a WARN in codereview 2026-09-30f. Fixed in `fa2a7c0`:
  - `main()` sets `LITELLM_MODE=PRODUCTION` before it drops the Jev keys.
  - The installed litellm calls `load_dotenv()` in one place on its import
    path (`litellm/__init__.py:19-20`), and only when `LITELLM_MODE` is
    `DEV`. `main.py` and `utils.py` import dotenv but call nothing in it.
  - The test now clears `LITELLM_MODE` and asserts that `main()` sets it.

### Traced and cleared this run (not findings)

- **`story._tell`** (`a4d182e`) routes a line on its unfilled text, then
  fills `{dreamers_today}`. A dreamer's name can no longer narrow a room
  line to its actor, so the last entry's cleared note no longer applies. The
  clause says "you" only when the line is the actor's alone.
- **`trace.dreamers_today`** was removed and has no callers in daydream/,
  tests/, tools/ or web/.
- **The browser daemon.**
  - `open` joins the path to the session's base and refuses any other
    origin. The check compares Python's whole netloc after the join, so
    spellings with `//host`, `@`, a backslash, `javascript:`, `data:` or
    `file:` fail it.
  - `key` accepts only `[A-Za-z0-9+]{1,24}`, and a point must lie inside the
    1280x800 window.
  - The socket is 0600 in `$XDG_RUNTIME_DIR` (0700). No verb evaluates
    script the caller supplies; the page helpers are the module's own.
  - The wrapper passes `--as-player`, so `setup`, `teardown` and `_browser`
    are refused (tested). A second `--session-dir` from the player can reach
    only another playthrough daemon's socket.
  - The SPA and the door build no link off their origin, and every
    navigation goes to `document.baseURI`. A click cannot take the player to
    third-party content.
- **The throwaway server.**
  - It binds `127.0.0.1` with `DAYDREAM_ACCESS=tailscale` and the sign-in
    gate.
  - Its world, accounts, art cache and keep are the session's own. Only the
    GPU lock and the engines are shared, by design.
  - The made-up account skips the invite flow, in the session's own accounts
    DB only.
  - Its password (3 of 16 words plus two digits) is stored in three places:
    `session.json` (0600), the player's brief, and the action log entry for
    the `type` that signs in. It guards a throwaway village on loopback.
- **Jev in a playthrough.** `server_env` copies the environment, so with the
  dev key in `.env` the throwaway server runs with Jev on. TypeSafe then
  sees the blind player's typed lines and the judge's context about the
  made-up friend. All of it is agent-written, with no friend's text.
- **Teardown.**
  - Paths come from the session id, whose username part is reduced to
    `[a-z0-9]`.
  - Reports, notes, shots and the action log land in `/playthroughs/`, which
    `git check-ignore` confirms is ignored.
  - `copytree` follows a symlink in `shots/`, but Write and Edit make only
    regular files. Only the WARN's escape could plant one.
- **The persona** lands in the player's system prompt
  (`--append-system-prompt-file BRIEF.md`). An operator session steered into
  writing one gains nothing new, because the allow list already runs
  interpreters with no prompt (carried NOTE).

### Player-text scan (CLAUDE.md "Player text is data")

- Prod and dev both ran in this review. Nothing was flagged, and there were
  no bursts. Prod had no items since the clean start. Dev's items were the
  agents' probe dreamers and the operator's dev username, with no typed
  lines. The counts, the verdict and the high-water marks are in the local
  instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped diff, the skill and the brief hold no key, token, private-key
  block, email, box or tailnet address, home path, operator name or instance
  domain. Every pattern hit was a decorator. The invented names are stock
  first and last names, and the tests use "Robin Ash".
- The last three commits of `playthrough.py`, `bin/game`, `model_eval.py`
  and the playthrough tests hold no key-shaped value. No `.env` was ever
  committed, on any ref.
- `playthroughs/`, `instance/`, `.env` and `.claude/settings.local.json` are
  still ignored.

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
*Prior review (2026-09-30, paths, commit `068a34c`): 17 files covering the review fixes of `d09493d`, the private telling of `{dreamers_today}` and the Jev report's p95. It closed the four WARNs of the entry before it and found one new NOTE: model-eval's switch that keeps Jev off did not survive litellm's import of `.env`. Codereview 2026-09-30f raised it to a WARN and fixed it in `fa2a7c0`. The register stood at 0 BLOCK / 0 WARN / 9 NOTE. The full entry is at `git show ae79a94:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-01","commit":"677a90384462bf1b8d1073d86542257dc2c71eed","scope":"paths","scanned_files":[".gitignore","bin/game","daydream/model_eval.py","daydream/playthrough.py","daydream/story.py","daydream/trace.py","tests/test_model_eval.py","tests/test_playthrough.py","tests/test_trace.py"],"block":0,"warn":1,"note":9} -->
