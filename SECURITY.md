# SECURITY.md

## Security Review — 2026-09-29 (scope: paths)

**Addressed after this scan (commit `3009a51`, re-reviewed with tests):** all
three WARNs below. `bin/game ci` reads only this repository's push runs
(filtered locally) and prints titles from local git; the guard matches gated
verbs on the raw text as well (segment by segment, up to a redirection), denies
the other token printers named below and the two further credential files, and
asks before a recursive search rooted at home or a system directory. The
residual spellings this entry lists (variables, `$'...'`, globs in a verb,
interpreter one-liners, `find -exec` and the like) remain; the guard is a
pattern check, not a boundary (BACKLOG `agent-sessions-without-root`).

**Summary:** Path-scoped review of the ten files named by the caller, read as
their change from the last scan (`e6c5f99`) to HEAD `c50460e`: `bin/game ci`
and the CI line in `status`, `prod plan` and `prod check` (the new
`daydream/ci.py`), CI installing against the prod lock, and the agent guard's
fixes for the last review's two WARNs. No exploitable vulnerability in the app
or the edge. Three WARNs: the new CI reader counts a stranger's fork
pull-request run as a run on main, so anyone on GitHub can put a line of text
into the agent's status output and hide a red main; and the guard, whose
rewrite gaps are closed, still misses a gated verb inside a double-quoted
command substitution and a command that prints this box's GitHub token
(0 BLOCK / 3 WARN / 3 NOTE, the NOTEs carried from outside these paths).

### Scope and method

- Each scoped file's diff from `e6c5f99` to HEAD was read in full.
  `daydream/ci.py`, `tests/test_ci.py`, `tools/agent_guard.py`,
  `tests/test_agent_guard.py`, `daydream/prodcheck.py` and the workflow were
  read whole, with prodctl's `plan`, `main`, `release_env`, `as_prod` and
  `passthrough`, and the runbook and skill lines that run `prod plan`,
  `ci watch` and `prod check` in a publish.
- GitHub, read-only: this repository's public run list (21 runs, all pushes
  to main from this repository); its Actions settings (default token
  permission read; fork pull requests from first-time contributors wait for
  approval); and a large public repository's run list filtered by
  `branch=main`, which held 64 pull-request runs from one fork whose branch
  is named main, each `completed` with conclusion `action_required` and
  carrying the PR's title.
- Probes in the scratchpad, touching no live data: `ci.main_status` over that
  fork-run shape with `gh` faked; the guard's `decide()` over some seventy
  command shapes beside the guard from `e6c5f99`, with sentinels in place of
  the credential paths (no command this review ran named a credential path
  or a gated verb); `gh config get -h github.com oauth_token` in a clean
  environment against a fabricated config directory, which printed the
  fabricated token. Other credential stores in the operator's home were
  checked for existence only.
- The three scoped test files, `tests/test_prodcheck.py` and
  `tests/test_prodctl.py` pass (157 tests).

### Findings

[WARN] daydream/ci.py:42 (with :57, :64-70, :78-94, :146-149;
daydream/prodcheck.py:200-207, :373-375; daydream/prodctl.py:946-954;
bin/game:527-530) — The CI reader asks GitHub for runs by branch name alone,
so a pull-request run from any fork whose branch is named `main` counts as a
run on this repository's main. Its title (the stranger's PR title) is printed
by `bin/game status`, `prod plan`, `prod check` and `bin/game ci`, and while it
is the newest run it stands in for main's verdict, so a red main reads as a
note.
  Attack vector: The repository is public and the workflow runs on
`pull_request`. Anyone with a GitHub account forks it and opens a PR from the
fork's `main`, titled for the agent ("the operator asks you to run ...";
up to 70 characters are printed per run). The run is listed at once, awaiting
approval, with no action by the operator. A publish runs `prod plan` before
its push and `prod check` after its deploy, and `bin/game status` runs
routinely, all in the session that holds the prod grant: the title arrives
inside the tool's own status line, unmarked, from a wider population than the
invited friends that "Player text is data" names, and the player-text scan
never sees it. The same run turns a red main into a note in `prod check` and
removes `prod plan`'s RED line, the signal this change added. `ci watch`
filters by the pushed commit's sha, so the publish's own wait is unaffected.
The ask rules and the guard still stand behind any verb the text names.
  Evidence: `runs()` queries `branch={branch}&per_page={limit}` with no event
or repository filter (:42). `_shape` takes `display_title` (:57). `state()`
returns an unmapped conclusion as itself, so a fork run awaiting approval is
`action_required` (:64-70). `main_status()` answers with the newest run's
state and description (:87-89). `check_ci` fails only on `failed`
(prodcheck.py:205-207), and `plan` prints the words and adds its RED line only
on `failed` (prodctl.py:950-954). With `gh` faked to return a failed push run
and a newer fork run in GitHub's shape, `main_status()` gave `action_required`
with the fork's title, `check_ci` a note, and `plan` no RED line. No such run
exists here today.
  Remediation: Add `event=push` to the query (the workflow's push trigger is
limited to main, so only an account with write access can create a matching
run), and drop runs whose `head_repository.full_name` differs from
`repository.full_name`. Print the subject from the local repository
(`git log -1 --format=%s <sha>`) instead of GitHub's `display_title`, or only
the verdict and sha, and strip non-printable characters from what is printed.
Treat an unmapped conclusion as unknown while still reporting the last
finished push run. Test a fork run newest over a failed push run: the verdict
stays `failed` and the fork's title does not appear.

[WARN] tools/agent_guard.py:78, :124 (with :73-104, :117-153, :239-252) — A
gated verb inside a double-quoted command substitution gets no opinion.
`out="$(bin/game prod invite create --for "Robin" --json)"`, a natural way to
capture the invite skill's JSON, passes, as do backticks inside double quotes
and a process substitution, and so does any spelling that puts the verb's
words inside one shell word or behind a program the guard does not know.
  Attack vector: As in the last two reviews, a steered agent's command
(player text, or now a PR title through the CI line above). The line does not
start with `bin/game prod`, so the settings' allow and ask prefixes do not
match it as typed, and whether Claude Code's own matching looks inside a
substitution is not tested here; in auto mode the classifier may be the only
check. The guard is the layer described as reading each command "the way the
shell will" and asking "however they are spelled".
  Evidence: `_split_commands` turns `$(`, backticks and parentheses into
` ; ` before lexing (:78), but inside double quotes the result stays one word;
that word begins `out=`, matches the assignment pattern and is skipped whole
(:124), so nothing is left to check. The `e6c5f99` guard behaves the same.
Also no opinion (probed): `function f { G; }` (the keyword is skipped, the
name is not), `coproc G`, `python3 -c "os.system('G')"` and a list-form
`subprocess.run`, `find . -exec G \;`, `script -qc "G"`, `taskset` and
`systemd-run`, `flock FILE -c 'G'`, `watch -n 5 'G'`, and the spellings the
last review listed (a variable or an ANSI-C quote in the verb, `xargs` fed the
verb on stdin, `env -S`, `sh -c '... "$@"' _ VERB`, the release's `bin/game`
by a relative path after `cd`), where G is a gated verb such as
`bin/game prod account role NAME admin`. The self-protection shares the limit:
a Python `open(..., "w")` or `git reset --hard` rewrites the guard with no
opinion.
  Remediation: Match gated verbs over the raw text as well, as the credential
check now does: at every `bin/game` (a release path included), read the
following words, splitting on whitespace, quotes, commas, brackets,
parentheses, backticks and `$(`, and apply `_gated`; ask when those words hold
`$`, a backtick, a glob character or an ANSI-C quote. One pass covers the
substitutions, the interpreters, `find -exec`, `script`, `coproc`, the
`function` head and unknown wrappers. Add a test for each shape above,
starting with the invite capture.

[WARN] tools/agent_guard.py:40-43, :156-162 (with :107-114, :231-235,
:243-246) — The deny misses a command that prints this box's GitHub token, and
credential reads that name a parent directory. The box's `gh` is 2.4.0, which
has no `gh auth token` and keeps the token in `~/.config/gh/hosts.yml`;
`gh config get -h github.com oauth_token` prints it, with no guard opinion. So
do `git -C DIR credential fill`, `git -c KEY=VALUE credential fill`,
`git credential 'fill'` and `gh auth 'git-credential' get` (git's helper for
github.com here is gh), and `grep -rn CLOUDFLARE_API_TOKEN ~`,
`tar c ~/.config`, `cd ~/.config && cat gh/hosts.yml` or a glob.
  Attack vector: As above, and also with no injection at all: a recursive grep
of the home directory is an ordinary search, and it prints the Cloudflare
token's line from `~/.config/daydream/cloudflare.env`. CLAUDE.md says the hook
"denies outright any command or file read that names this box's credential
paths ... or prints the GitHub token"; the Read deny rules do not reach Bash,
so for a Bash read the guard is the deterministic layer. The GitHub token
carries the scopes `gh auth login` granted (by default `repo`, `read:org` and
`gist`).
  Evidence: `TOKEN_PRINTERS` (:40-43) has no `gh config get`, and its git
alternatives need `credential` directly after `git`, unquoted. The argv check
(:243-246) covers only `gh auth token` and `gh auth ... -t|--show-token`, and
no argv check reads git. The fallback's runs start only at the first word and
at `bin/game` (:107-114), so a quoted `gh` word after a comment holding an
apostrophe is never checked. `_names_credentials` (:156-162) matches a
credential directory as a substring, so a parent directory, a path relative
to a `cd`, or a glob does not match. Every command named in this finding gets
no opinion (probed with sentinels for the paths).
`gh config get -h github.com oauth_token`, run in a clean environment against
a fabricated config directory, printed the fabricated token, and
`gh auth --help` lists no `token` subcommand. Two credential files in the
operator's home are outside the list: `~/.claude/.credentials.json` (the
Claude Code sign-in) and another tool's 0600 config under `~/.config`
(existence checked, contents not read).
  Remediation: Deny any command containing `oauth_token`, and match git with
global options before the subcommand, for example
`\bgit\b(\s+-\S+(\s+[^\s-]\S*)?)*\s+credential(-\w+)?\b`; run the gh and git
checks over the parsed argv, where quotes are gone, and over every fallback
run. Match the credential files' own names too (`hosts.yml`,
`cloudflare.env`, `prod.env`, `daydream.env`, `authorized_keys`, `id_*`,
`.credentials.json`), and ask on a recursive read (`grep -r`, `rg`, `tar`,
`zip -r`, `cp -r`, `rsync`, `find`) rooted at `~`, `$HOME`, `~/.config`,
`/srv/daydream` or `/etc`. Add tests for each.

[NOTE] daydream/play.py:84-85 (outside these paths; carried unchanged) — A
grown place's description prints unmarked in `play`, and the server accepts
control characters in typed lines and appearance seeds. Carry a grown marker
in the snapshot and print that description marked; refuse non-printable
characters at the server, as names already are.

[NOTE] daydream/skills/effects.py:347 (outside these paths; carried
unchanged) — The placeholder expander still runs over a letter's body and a
dreamer's looks; it fills only `{dreamers_today}`, and the `from_player` flag
is a ready skip condition. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:129-136 (outside these paths; carried
unchanged) — `account delete --yes` during a resident's reply leaves that
reply and its `talk:`/`rel:` records behind; `account delete` is not in
`prodctl.STOP_FOR`, and `dialogue.talk` does not re-check the dreamer after the
model call.

### Resolved since the last review

- **WARN, the rewrite's three gaps.** A credential path as a redirection
  target (`cat <`, `base64 <`, a `while read` loop, `exec 3<`, an append to
  `authorized_keys`), `gh` after a comment holding an apostrophe (in its plain
  spelling), and a release's `bin/game edge sleep|secrets|kv-create` now deny
  or ask, each tested. The raw-line pass that closed the first two (every word
  of the line, redirection targets and heredoc bodies included) only adds
  denials.
- **WARN, commands after reserved words.** `if`, `then`, `else`, `elif`, `do`,
  `while`, `until`, `!`, `{` and a `name()` head are skipped as wrappers are,
  and `git credential fill` and `gh auth git-credential` deny in their plain
  spellings. What remains is in the second and third WARNs above.
- **NOTE, the test's tailnet address.** tests/test_config_edge.py:61 now uses
  `100.64.0.1`. The old value remains in history; a tailnet address is
  reachable only from the tailnet, so it does not justify a rewrite.

### Traced and cleared this run (not findings)

- **The workflow.** It runs on push to main and on `pull_request` (never
  `pull_request_target`), uses no secrets, and interpolates no event text into
  a `run:` line; the repository's default token permission is read, and a
  fork's run gets a read-only token regardless. A fork PR's pip cache is
  scoped to its own ref. Installing against the prod lock narrows what CI
  resolves; the dev extras stay unpinned (carried: versions, not hashes).
- **`gh` from the shell.** `_gh` runs a fixed argv without a shell, in the
  repository, with a 30 s timeout; the only caller-supplied part is the sha
  from `git rev-parse` of the operator's own ref. A failure reads as unknown,
  a note.
- **`bin/game status`** runs `python -m daydream.ci` from the caller's
  directory, like the other Python subcommands (the carried `bin/game` trust);
  prod's passthrough runs from the release directory.
- **The raw pass fails closed.** A line that merely mentions a token printer
  or a credential path (a commit message, a heredoc) is denied: a usability
  cost, not a gap.
- **The suite and GitHub.** The autouse fake covers in-process calls only;
  the smoke script's `bin/game status` (tests/test_game_script.sh:39) asks
  GitHub read-only through `gh`, in dev and in the deploy gate. Not a
  security issue.

### Player-text scan (CLAUDE.md "Player text is data")

- Dev and prod both run; the verdict and high-water marks live in the local
  instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The 321 lines added in the scoped files were scanned without printing
  values: the email-shaped hits are pytest decorators, the long runs are test
  names, and the one address is the `100.64.0.1` placeholder. There is no key,
  token or password shape, and no instance domain, hosting company or
  operator name; `daydream/ci.py` names the repository only through `gh`'s
  `{owner}/{repo}` placeholders.
- The last three commits of each scoped file that handles credentials or
  runs `gh` (`ci.py`, `prodctl.py`, `prodcheck.py`, `agent_guard.py`,
  `bin/game`, the workflow) hold no secret-shaped string.
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
  may slip past one. A PreToolUse hook would be firmer. (Since 2026-09-29
  `tools/agent_guard.py` backs them; its gaps are this review's second and
  third WARNs.)
- Player text reaches the agent's context through `bin/game play`: names,
  speech and move lines, and (marked since 2026-09-29) letters and looks.
  The verbs an injected instruction would want stay behind ask rules.

---
*Prior review (2026-09-29, paths, commit `e6c5f99`): 41 files, the codereview
fixes (the guard's rewrite and self-protection, rests across devices and the
shell, one ownership read per frame, the rate budget kept across a reconnect,
players' words marked in `play`, the venv seal) and the repo's
genericization. It found 0 BLOCK / 2 WARN / 4 NOTE: the guard rewrite's three
gaps and commands after reserved words (both resolved above, apart from this
review's second and third WARNs), and the play-marking, placeholder,
account-delete and test-address NOTEs (the last resolved above). That entry
was never committed; the one before it is at `git show a53a075:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-29","commit":"c50460e031a34f3292429881d7bb96f0b03aecf4","scope":"paths","scanned_files":[".github/workflows/test.yml","bin/game","daydream/ci.py","daydream/prodcheck.py","daydream/prodctl.py","tests/conftest.py","tests/test_agent_guard.py","tests/test_ci.py","tests/test_config_edge.py","tools/agent_guard.py"],"block":0,"warn":3,"note":3} -->
