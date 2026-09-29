# SECURITY.md

## Security Review — 2026-09-29 (scope: paths)

**Summary:** Path-scoped review of the eleven files named by the caller, read
as their change from the last scan (`c50460e`) to HEAD `d2f7538`: the fixes
for that scan's three WARNs (`daydream/ci.py` and `tools/agent_guard.py`, with
their tests), the server closing a socket whose page has sent nothing for
150 s, and the page riding out a brief socket drop and naming the satchel and
the book under "you carry". There is no exploitable vulnerability in the app
or the edge, and the CI reader no longer relays a stranger's text. One WARN:
the guard's new search check misses the directories the credential files sit
in. `grep -rn CLOUDFLARE ~/.config` still prints the Cloudflare token's line
with no opinion, and `gh auth status -th github.com` prints the GitHub token
(0 BLOCK / 1 WARN / 5 NOTE; three of the NOTEs are carried unchanged from
outside these paths).

### Scope and method

- Each scoped file's diff from `c50460e` to HEAD was read in full.
  `daydream/ci.py`, `tools/agent_guard.py` and `tests/test_agent_guard.py`
  were read whole. So were `ws_endpoint`, `_receive_loop`, `_busy` and
  `_session_watch` in `daydream/api/ws.py`, `prodcheck.check_ci`, every
  `innerHTML` sink in `web/assets/main.js` with its escaping helpers, and
  `server._page`, which fills `web/index.html`'s placeholders.
- Probes ran in the scratchpad and touched no live data. The guard's
  `decide()` was run over about forty command shapes, beside the guard from
  `c50460e`. Credential paths were built from parts, so no command this
  review ran named a credential path or a gated verb. `ci.main_status()` and
  `check_ci` were run with `gh` faked to serve one page of fork runs over a
  red push run. The installed `gh` (2.4.0) was given `auth status -th` in a
  clean environment, against a fabricated config for a fake host.
- The scoped tests pass. That is 175 in `test_agent_guard`, `test_ci`,
  `test_ws_limits` and `test_frontend`, and 19 in headless Chromium
  (`test_browser_flow`).

### Findings

[WARN] tools/agent_guard.py:36-38, :267 (with :47, :163-169, :264-266) — The
second scan's fix asks before a recursive search rooted at home, but not
before one rooted at the directories the credential files sit in. A
clustered short flag also still prints the GitHub token. None of these gets
an opinion:
- `grep -rn CLOUDFLARE ~/.config`, which prints the `CLOUDFLARE_API_TOKEN=`
  line of `~/.config/daydream/cloudflare.env`.
- `grep -rn oauth_token ~/.config`, which prints the GitHub token from
  `~/.config/gh/hosts.yml`.
- The same search with `rg`, with `$HOME/.config`, or with a trailing slash.
- `find ~/.config -name '*.env' -exec cat {} +`.
- A search under `~/.claude`, which reaches Claude Code's sign-in file.
- `gh auth status -th github.com`.
  Attack vector: This is the last WARN's own path, and it needs no
injection. Searching for a config value one directory below `~` is as
ordinary as searching `~` itself. It prints a live credential into the
session's context and its saved transcript. A steered command (player text,
per CLAUDE.md) gets the same result. CLAUDE.md says the hook denies any
command that names the credential paths or prints the GitHub token. For a
Bash read, the hook is the deterministic layer.
  Evidence: `BROAD_ROOTS` (:36-38) holds `~`, `$HOME`, `/`, `/root`, `/home`,
`/etc`, `/srv`, `/srv/daydream` and the home path, and :267 asks only when an
argument equals one of them exactly. `_names_credentials` (:163-169) matches
a credential directory as a substring, so a parent directory never matches.
`gh` 2.4.0 lists `-t, --show-token` and `-h, --hostname`. Given
`-th example.invalid`, it checked that host alone with no flag error, while
`-tz` failed on the `z`. So `-th github.com` is `-t -h github.com`, which the
guard denies. But the token pattern needs `-t\b` (:47), and the argv check
needs a literal `-t` (:264-266). Every command above was probed and got no
opinion. So did `tar c ~/.config | tar xO`, which the last entry named.
  Remediation:
- Expand `~`, `$HOME` and `${HOME}` in each argument of a searcher (and of
  `tar`, `zip -r`, `cp -r` and `rsync`), and normalize it. Ask when the
  result is an ancestor of a credential directory (compare with
  `os.path.commonpath`).
- After `gh auth status`, treat any short-flag cluster that holds `t` as
  `--show-token`.
- Deny any command that contains `oauth_token`, as the last remediation
  proposed.
- Add a test for each shape above.

[NOTE] tools/agent_guard.py:246-255 (with :256-274) — The raw gated-verb pass
(the fix for the last scan's second WARN) leaves three gaps.
- It cuts each segment at its first redirection. So
  `out="$(bin/game prod 2>/dev/null invite create --for Robin --json)"`, or
  one with `2>&1` before `prod`, again gets no opinion.
- List-form `subprocess.run(['bin/game','prod',...])` is still not read,
  because commas and brackets are not split.
- The pass returns `ask` before the parsed pass's credential denials run. A
  quote-broken credential read (`~/.con''fig/...`) next to any gated verb now
  asks in either order. The guard at `c50460e` denied it when the read came
  first.
All three need a crafted spelling. That is the class the operator accepted as
"a pattern check, not a boundary", and the prompt shows the whole command.
Remediation: drop a redirection word and its target instead of cutting there.
Add `,[]` to the split. Run every check and let a deny win over an ask.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py:200-207) — The
fork-run filter works on one page of `limit * 4` runs. Each push to a fork
pull request from a branch named `main` lists a run awaiting approval under
`branch=main`. So a stranger who pushes to one about twenty times fills that
page. Then `main_status()` reads `unknown`, "no runs on main". `prod check`
passes that as a note, and `prod plan` prints no RED line while main is red.
This was probed with a faked `gh`. No stranger's text reaches the output now.
`ci watch`, which a publish runs for its own push, filters by the commit and
is unaffected. Remediation: read main's head sha
(`gh api repos/{owner}/{repo}/branches/main`) and that commit's runs, as
`watch` does. Or page until `limit` push runs are found. Either way, say so
when a full page held none.

[NOTE] daydream/play.py:84-85 (outside these paths; carried unchanged) — A
grown place's description prints unmarked in `play`, and the server accepts
control characters in typed lines and appearance seeds. Carry a grown marker
in the snapshot and print that description marked. Refuse non-printable
characters at the server, as names already are.

[NOTE] daydream/skills/effects.py:347 (outside these paths; carried
unchanged) — The placeholder expander still runs over a letter's body and a
dreamer's looks. It fills only `{dreamers_today}`, and the `from_player` flag
is a ready skip condition. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:129-136 (outside these paths; carried
unchanged) — `account delete --yes` during a resident's reply leaves that
reply and its `talk:`/`rel:` records behind. `account delete` is not in
`prodctl.STOP_FOR`, and `dialogue.talk` does not re-check the dreamer after
the model call.

(The three carried files are unchanged since `c50460e` and were not re-read.)

### Resolved since the last review

- **WARN, the CI reader.** `runs()` keeps only this repository's push runs
  (it checks `event`, and compares `head_repository` with `repository`).
  Titles come from local git with control characters stripped. A fork run
  no longer answers for main. This is tested with a fork run newer than a
  red push run. The page-size residual is the second NOTE.
- **WARN, a gated verb in a quoted substitution.** The invite capture asks,
  and a test covers it. The shapes that remain are the first NOTE.
- **WARN, token printers and credential reads.** These now deny or ask, each
  tested: `gh config get ... oauth_token`, `git -C|-c ... credential fill`, a
  quoted `gh auth 'git-credential'`, the two further credential files, and
  searches rooted at `~`, `$HOME`, `/`, `/etc` and `/srv`. What remains is
  the WARN above.

### Traced and cleared this run (not findings)

- **The quiet close** (`ws.py:1141`, `:1249-1250`, `:1319-1366`). Its state
  is per connection, and any frame refreshes it. A busy handler defers only
  the quiet close, never the session re-read, so a revoked account's socket
  still closes within 30 s even mid-command. The close runs the same
  `finally` (unmark, unregister, unsubscribe). It ends a ghost the edge kept
  open, which had gone on hearing its room. The new log line carries only
  the username and a number of seconds. Pings still ride the per-frame
  session check and the shared rate bucket.
- **The page.** New text goes through `textContent`. `chipTarget`
  (`main.js:906-916`) builds its selector with `CSS.escape`, and the command
  it sends carries a snapshot object id that the server re-checks for scope
  and verb. Every `innerHTML` sink escapes `& < > "` first (`main.js:1857`)
  and quotes its one attribute with `"`. `server._page` HTML-escapes
  `web/index.html`'s placeholders (`server.py:240`), and the new markup is
  static SVG. `style.css` loads only a self-hosted font and data URIs.
- **The CI reader's git call.** `ci._subject` runs git with an argv (no
  shell) on a sha from one of this repository's push runs. Only a forged API
  response could turn that sha into an option (hardening:
  `--end-of-options`). The list-shaped shortcut in `runs()` serves only the
  tests' fakes, since the endpoint returns an object.

### Player-text scan (CLAUDE.md "Player text is data")

- Dev and prod both ran in this review, and nothing was flagged. Counts,
  the verdict and the high-water marks are in the local instance notes,
  never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped files, and the last three commits of `tools/agent_guard.py`,
  `daydream/ci.py`, `daydream/api/ws.py` and their tests, hold no key, token
  or password shape. They name no instance domain, hosting company, operator
  name or email. The only addresses are the browser test's loopback bind.
- `instance/` and `.claude/settings.local.json` are still ignored, and the
  guard is wired in the local settings.

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
  the tuck-away branch) waits in their satchel until they rest; a page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. Refusing it broke the arc contract (walkthrough players never
  open a socket, so every walkthrough hand-over runs through the dozing
  branch). BACKLOG `dozing-handover-of-village-things`.

Carried register (from prior reviews; still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths. Neither path exists in the live Lost Hours world
  (planned for v2).
- Raw parser input is not role-separated. The output is re-grounded to a
  closed verb and an in-scope id.
- NPC dialogue and growth are exposed to prompt injection.
  - Input is wrapped, capped and banlisted, and output is validated before
    any mutation.
  - Refusal `reason` text is narrated without an output-banlist pass,
    through escaped sinks.
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
- Toon names are not unique, and lookalikes are not folded. Moderation
  refuses an ambiguous key, and `/status/who` shows the id and the owner.
  (Since 2026-09-29 a new dreamer's name must be unique under case, spacing
  and compatibility folding; confusable alphabets are still not folded, and
  legacy duplicates stay.)
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one. `tools/agent_guard.py` backs them (since 2026-09-29).
  It is a pattern check, not a boundary: spellings through variables,
  `$'...'`, globs in a verb, interpreter one-liners and the like remain
  (BACKLOG `agent-sessions-without-root`). Its gaps this run are the WARN
  and the first NOTE.
- Player text reaches the agent's context through `bin/game play`: names,
  speech and move lines, and (marked since 2026-09-29) letters and looks.
  The verbs an injected instruction would want stay behind ask rules.

---
*Prior review (2026-09-29, paths, commit `c50460e`): ten files, covering
`bin/game ci` and the CI line in `status`, `prod plan` and `prod check`, CI
installing against the prod lock, and the guard's fixes for the review
before. It found 0 BLOCK / 3 WARN / 3 NOTE. The three WARNs were these. A
stranger's fork pull request from a branch named `main` put its title into
the agent's status output and hid a red main. The guard missed a gated verb
inside a double-quoted substitution. And the guard missed commands that
print the GitHub token, as well as recursive reads of home. All three were
fixed in `3009a51`; what remains is this entry's WARN and its first two
NOTEs. The full entry is at `git show 560a837:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-29","commit":"d2f753829bad66be183720fd6d989df33e8c533a","scope":"paths","scanned_files":["daydream/api/ws.py","daydream/ci.py","tests/test_agent_guard.py","tests/test_browser_flow.py","tests/test_ci.py","tests/test_frontend.py","tests/test_ws_limits.py","tools/agent_guard.py","web/assets/main.js","web/assets/style.css","web/index.html"],"block":0,"warn":1,"note":5} -->
