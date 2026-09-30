# SECURITY.md

## Security Review — 2026-09-30 (scope: paths)

**Summary:** Path-scoped review of the 48 files the caller named, read as
their change from the last scan (`6981ba7`) to HEAD `68125c8`: the review
fixes (`836ebe1`, `bc0fb71`), the agent-guard rework and its installed copy
(`8eb8107`, `cda0d2a`), Jev (`fd04015`), the egress gateway and the root
helper's egress verbs (`c87981d`, `443c93b`), and docs. The gateway, its
unit, the root helper's key handling and the Jev client hold. There are four
new WARNs. Three are places where `8eb8107` stopped asking on spellings the
guard asked on before: a heredoc run by a shell behind `timeout`, a `find`
whose listing is consumed, and sed's other in-place forms on the protected
files. The fourth: the Jev judge sends TypeSafe other dreamers' names,
whereabouts and deeds, which docs/EXTERNAL.md does not list and the operator
has not accepted. Register: 0 BLOCK / 4 WARN / 9 NOTE (four new NOTEs, five
carried).

**Status after /codereview 2026-09-30d:** all four WARNs are fixed in the
commit that follows `68125c8`. The guard's heredoc reader was rewritten to
find heredocs as the shell does (the whole delimiter word, any program
unwrapped as the argv pass does, text only for a short list of text readers,
anything unfollowed read as commands); a `find` lists only when its output
reaches nothing but text filters; the protected-write check reads every
in-place spelling, sed's `w`, `sort -o`, `--output`, `uniq`'s output operand
and `find -exec`; and EXTERNAL.md now lists exactly what `judge_view` sends,
for the operator to accept before a prod key is set. The guard fixes are
live only after `! bin/game guard install`. The hook-interpreter NOTE is
addressed in the template (the hook runs `/usr/bin/python3 -I`); the live
settings follow in the same approval as the guard install. Open: 0 BLOCK /
0 WARN / 8 NOTE.

### Scope and method

- Each scoped file's diff from `6981ba7` to HEAD was read. New files were
  read whole: `daydream/egress.py`, `daydream/jev/*`,
  `ops/systemd/daydream-egress.service`, and `tools/agent_guard.py` as it
  stands. So was the code the changes lean on:
  - `dialogue.build_prompt`'s sections and `judge_view`,
    `trace.dreamer_line`, `knowledge.known_facts`
  - `verbs._handle_talk` with `story.available_topics`
  - `prodctl.release_env`, `as_prod` and `root`; `admin.cmd_backup`
  - the root helper's unit validator, file writer and env parser
- The 13 scoped test files pass (623 tests).
- Probes, all on data (nothing a payload names was run):
  - The guard at `6981ba7`, at `604671b` (the last pushed commit) and at
    HEAD judged the same payloads.
  - The gateway ran on an ephemeral loopback port with its upstream replaced
    by a recorder and a dummy key.
  - A copy of the guard ran under a scratch user site holding a `.pth` file.
  - A harmless `timeout 5 bash <<'EOF'` ran from this review's session with
    no prompt.

### Findings

[WARN] tools/agent_guard.py:165-184 (`_heredoc_kind`), with :232-266 (`_read_heredocs`) — A heredoc is read as commands only when the program it feeds is a shell, `eval`, `source` or `ssh`, and as text otherwise; text is dropped from every pass. The program is found by skipping wrapper names and words that start with `-` (:176), not the way `_unwrap` skips a wrapper's value (`WRAPPER_VALUE_OPTS`, `WRAPPER_FIRST_WORD`). So in `timeout 60 bash <<'EOF'` the program is `60`, and the body gets no decision: a gated verb there no longer asks, and a read of a credential file there is no longer denied. Both were caught at `6981ba7` and `604671b`, which read a heredoc's lines as commands.
  Attack vector: Player text that reaches the session (the dream digest, `bin/game play`, letters, `bin/game jev report --disagreements`) carries an instruction, and the agent runs a gated `bin/game prod` verb or a credential read inside `timeout 60 bash <<'EOF'`. `Bash(timeout *)` is on the allow list (template :13, and the live settings), so nothing prompts, and the guard reads the body as text.
  Evidence (each asked or denied at both earlier commits; no decision at HEAD):
- `timeout 60 bash <<'EOF'` with a gated verb in the body; the same with a `cat` of the Cloudflare token's file (was a deny).
- `timeout 5 sh -s <<'EOF'`, `nice -n 5 bash <<'EOF'`, `flock /tmp/l bash <<'EOF'`, `ionice -c 3 bash <<'EOF'`, `cat <<'EOF' | timeout 60 bash`, and `timeout 60 bash -c "$(cat <<'EOF' ... EOF)"`.
- `timeout 60 python3 <<'EOF'` with a `subprocess.run([...])` of a gated verb, or with an `open()` of the token's file (was a deny).
- Code heredocs (:260) keep only the lines that run a program, so a gated command held in a string on one line and run on the next (`cmd = "bin/game prod invite create ...".split()`, then `subprocess.run(cmd)`; the same in `node`) no longer asks. `python3 *` and `node *` are allowlisted.
- Pre-existing, no decision in all three: a here-string fed to a shell (`bash <<< "<gated verb>"`, `timeout 60 bash <<< "..."`). The raw pass deletes the here-string's word as a redirection target.
  Remediation:
- In `_heredoc_kind`, find the program as `_unwrap` does (skip each wrapper's value, `sudo -u USER` included), for the command before the heredoc and each command piped after it.
- Read a heredoc as text only for programs known to consume text (`cat`, `tee`, `git`, `gh`, or a command whose output is redirected to a file); read any other program's heredoc as commands, as before `8eb8107`.
- In a code heredoc, when any line runs a program, read every line for gated verbs (a heredoc that only prints stays quiet).
- Read a here-string fed to a shell, `eval` or `source` as commands.
- Add these probes to the heredoc tests. The fix goes live with the operator's `! bin/game guard install`.

[WARN] tools/agent_guard.py:668-669 (`lists_only`), with :566 (`_FIND_PIPED`) — Since `8eb8107`, a `find` rooted above a credential folder (`~`, `~/.config`) asks only when its output is piped straight into `xargs`, `while read` or `parallel`. Every other way of consuming the listing reads as a names-only find, so the ask that stood at `6981ba7` and `604671b` is gone.
  Attack vector: As above: an injected instruction leads the agent to a `find` over `~/.config` whose listing feeds a reader, and the token file's contents are printed. `find *`, `cat *`, `grep *`, `sed *` and `timeout *` are all allowlisted.
  Evidence (each asked at both earlier commits; no decision at HEAD), with `find ~/.config -name 'cloud*'` as F:
- `F | timeout 5 xargs cat`, `F -print0 | timeout 5 xargs -0 cat`, and `F | head -1 | timeout 5 xargs cat`.
- `F | while IFS= read -r f; do cat "$f"; done` (the pattern wants `while read` with nothing between).
- `cat $(F)` and `for f in $(F); do cat "$f"; done`.
- `F | grep -v zzz | xargs cat`, `F | sed 's/^/cat /' | timeout 5 sh`, and `F | tar -cf - -T - | tar -xOf -`.
  Remediation: Count a find as names-only only when its listing reaches the terminal: nothing piped after it, and not inside `$( )`, backticks or a `for ... in`. Add the probes above as `ask` cases.

[WARN] tools/agent_guard.py:499-543 (`_protected_write`), :524-525 — The guard's own protection (the permission settings and, since `8eb8107`, the installed guard) now asks on a `sed` or `perl` write only when an argument starts with `-i` or `-pi`. The old check matched `sed ... -i` anywhere in the line. So sed's other in-place spellings, which asked on the settings at `6981ba7` and `604671b`, get no decision, on the settings and on the installed guard alike. Several other writers that name the protected file were never modeled, and the new allow list lets them run with no prompt.
  Attack vector: An injected instruction's first move is to loosen the guard or the settings (codereview 2026-09-29c). `sed *`, `sort *`, `uniq *`, `find *`, `git log*`, `git diff*` and `git commit *` are allowlisted. A rewritten settings file can drop the hook and the ask rules, and a rewritten installed guard takes effect on the next command.
  Evidence (settings and installed guard):
- Asked on the settings at both earlier commits, no decision at HEAD: `sed --in-place '...' FILE`, `sed --in-place=.bak`, a short-option cluster (`sed -Ei`, `sed -ni`), and `find FILE -exec sed -i '...' {} +`.
- No decision in all three, reachable with no prompt only since the allow list grew: sed's `w FILE` command and `s///w FILE` flag, `sort -o FILE`, `uniq IN FILE`, `find ... -fprint FILE`, and `git log -1 --format=%B --output=FILE` (with an allowlisted `git commit` to carry the text).
  Remediation:
- Model sed's in-place forms (`--in-place[=SUF]`, any short-option cluster that contains `i`) and a protected path anywhere in sed's script.
- Add `sort -o/--output`, `uniq`'s second operand, `find -fprint*`, `find -exec/-execdir` (read the command it runs as its own argv) and `git log|diff|show --output`.
- A simpler fail-closed rule would also do: any argument naming a protected path asks, unless the program is on a short read-only list (`cat`, `head`, `tail`, `grep`, `rg`, `diff`, `cmp`, `sha256sum`, `stat`, `ls`, `wc`, and `git add|commit|diff|log|show` without `--output`). That keeps reading, testing and committing quiet.
- Tests for each spelling. Live after `! bin/game guard install`.

[WARN] daydream/dialogue.py:523-532 (`_JUDGE_SECTIONS`, `judge_view`), sent by daydream/jev/runtime.py:36 and daydream/jev/surfaces.py:141-156 — The judge hands Jev the whole `judge_view` as its state. That view carries other dreamers' data that docs/EXTERNAL.md's "What leaves the box" does not list. Rule 6 of that document makes the list what the operator accepts.
- Sent, but not listed:
  - `WHO IS HERE` (dialogue.py:237): every dreamer in the room, by name.
  - `OTHER DREAMERS` (:253-255): a dreamer the player names, with when and where they were last seen and whether they are awake, dozing or resting (`trace.dreamer_line`).
  - Inside `WHAT <resident> KNOWS`: other players' deeds, by name (`knowledge.known_facts` puts them after the speaker's own). The document says "what they know", which a reader would not take to mean other people's names and deeds.
- Listed, but not sent: the recent exchange with that dreamer (that section starts with the resident's name and is not kept).
  Attack vector: Not an exploit, but a data flow past its consent. Once a key is set at the gateway, every judged reply sends these to TypeSafe, which states no retention. A friend who never spoke to a resident has their dreamer name, whereabouts, state and deeds sent whenever someone else talks near them or asks about them. The acceptance on record (2026-09-30) covers the speaker's own typed lines. Dev sends only test dreamers today.
  Remediation:
- Before the prod key is set, choose one of two:
  - Replace other dreamers' names with a neutral token in Jev's copy of the context and drafts, and drop `OTHER DREAMERS` from that copy (the local judge keeps the full view).
  - Or list these in EXTERNAL.md and have the operator accept them.
- Test: Jev's state for a reply names no dreamer but the speaker.
- Correct `daydream/jev/__init__.py`'s docstring. It still describes a `DAYDREAM_JEV` switch that is "off (the default)", but Jev is on whenever a key is reachable (`settings.enabled`).

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list now includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`. Interpreter code runs with no prompt, and the guard, which reads code only for literal spellings, is the only check on it. A computed argv (`'bin/' + 'game'`) runs a gated verb, and a computed path lists a credential folder, with neither a prompt nor a guard decision (probed). The Accepted Risks entry on the guard ("interpreter one-liners ... remain") dates from when those commands prompted. Narrower rules (`.venv/bin/python -m pytest *` rather than any interpreter) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). Re-confirm the acceptance with this premise.

[NOTE] docs/claude-settings.local.example.json:106 — The hook runs `python3` from PATH, not isolated. A `.pth` file in the user site (enabled for the system python) or a `python3` earlier on PATH (a user's `~/.local/bin` often comes first) runs before the guard. It can exit 0 with no output, which the `|| echo ask` fallback does not catch. Neither write names a protected path, so the guard does not ask. With a copy of the guard and a scratch user site, both a deny and an ask payload got no decision; `/usr/bin/python3 -I` restored both. Remediation: `/usr/bin/python3 -I "$HOME/.local/share/daydream/guard/agent_guard.py"` in the template and the live settings (one settings edit).

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:59-60 — The dev Jev key lives in the repo's `.env`, which the guard's credential list does not cover. `cat .env`, `grep JEV .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`. Either way, EXTERNAL.md's `grep ... .env | bin/game prod root egress set ...` becomes the operator's own `!` command.

[NOTE] daydream/verbs.py:1811-1821, with daydream/dialogue.py:761-762 — Every free line to a resident asks Jev once (the topic), and every improvised reply asks once more (the judge), with no budget. An invited player at the WebSocket rate limit spends the prepaid balance down. When it is empty, the client pauses and the local path serves, so the cost is money, not the game. Remediation: a daily ceiling from the ledger (spend since midnight), past which `enabled()` reads off.

Carried from the last entry (their lines are unchanged or outside this scope):

[NOTE] tools/agent_guard.py `_resolve` (brace expansion) — A `cd` into one word of about 50,000 nested braces (97 KB) still takes 9.6 s at HEAD, past the hook's 5 s timeout, so it gets no decision. `cat`, `find`, `ls` and `grep -r` with the same word now answer in 0.2 s. A time limit inside `main`, or a single-pass brace expansion, would close it.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". Read main's head sha and that commit's runs, or page until `limit` push runs are found.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The server accepts control characters in typed lines and appearance seeds. Carry a grown marker in the snapshot and on those lines, and refuse non-printable characters at the server.

[NOTE] daydream/skills/effects.py:347 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply and its `talk:`/`rel:` records behind. It now also leaves the reply's Jev decision row, if a key is set: the purge runs before the in-flight reply records it. That row is pruned after 30 days.

### Traced and cleared this run (not findings)

- **The egress gateway**, on an ephemeral loopback port with a recording
  upstream:
  - A caller's `Authorization` is replaced by the route's key.
  - Only the route's exact method and path pairs are forwarded. A query
    string, `//`, `..`, a percent-encoded path, an absolute-form target and
    an unknown route get 404; a negative or oversized length gets 413.
  - One request per connection, so a chunked body is never parsed as a
    second request. Upstream `Set-Cookie` is dropped, and TLS verifies the
    host.
  - It refuses a non-loopback listen address and logs route, path, status,
    bytes and time, never a body or a key.
  - A local client that declares a body and stalls holds one thread
    (TasksMax 64), a local nuisance only. Any local process can use the key
    through it, which is the design and inside the local-attacker
    acceptance.
- **Its unit and the root helper.**
  - The validator pins `ExecStart` to the root-installed code under
    `python3 -I`, and requires `DynamicUser`, the address denies and the
    hidden paths.
  - It refuses any key outside the unit's allowlist (`IPAddressAllow`,
    `Environment`, `BindPaths`, `ExecStartPre`, `User`,
    `SupplementaryGroups`, writable paths), and a second `IPAddressDeny`.
    New tests cover most of these; this run probed the rest.
  - `egress set` takes one stdin line of 8 to 512 printable characters with
    no whitespace, quotes, `\`, `$`, backticks or `#`, so no new line
    reaches the env file.
  - It writes root 0600 through the no-symlink writer, and logs the key's
    name only. `show` and `doctor` print set or not set.
- **Jev in the game.**
  - `client._headers` sends the key only on direct (dev) calls. Through the
    gateway it sends none.
  - Logs carry purpose, outcome, status, time, tokens and cost. The ledger's
    calls hold no text.
  - Decisions hold the speaker's words and the drafts. They stay under the
    data dir for 30 days, are not in backups (`cmd_backup` copies the two
    DBs and the provenance only), and `account delete` purges them by
    dreamer (both surfaces pass `toon`).
  - A topic Jev picks is one of `story.available_topics` for that player,
    which `ask` reaches anyway. The judge only chooses among drafts that
    passed the deterministic name and commitment checks, and the reply is
    the asker's alone. Jev writes no text.
- **Prod plumbing.**
  - `prod jev` runs as the service user under `env -i`, so the operator's
    `.env` never reaches it. `jev eval` refuses through the gateway.
  - `jev report --disagreements` labels player text as data and
    JSON-escapes it, control characters included.
  - `prod check` probes through the gateway (no key sent). `prod plan`
    probes with this checkout's key, directly.
  - `conftest` clears every Jev variable and fails any test that reaches
    Jev's network. `LITELLM_MODE=PRODUCTION` stops litellm reloading `.env`.
- **The review fixes** (`836ebe1`, `bc0fb71`):
  - A click frame's ids are logged only when they are in scope
    (`(out of scope)` otherwise), and the text scan reads ids and
    `dobj_name`.
  - The parser's part grounding goes through `glimpse.part_host` and then
    the executor's scope check. `play click` sends a part's name, as the
    page does.
- **The guard's other changes hold.**
  - A subagent's ask becomes a deny, and `bin/game guard install` asks.
  - A write to the installed copy by `cp`, `>`, `tee`, `sed -i`, or a
    Python heredoc with a literal path, asks.
  - A command over 16 KB, nesting past 16 levels, and an exception all ask.
  - The install test uses a scratch `DAYDREAM_GUARD_HOME`.

### Player-text scan (CLAUDE.md "Player text is data")

- Prod and dev both ran in this review. Nothing was flagged. The one burst
  in dev was the Jev spike's scripted battery, and prod had no new typed
  lines. The counts, the verdict and the high-water marks are in the local
  instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped diff's 4,661 added lines hold no key, token, private-key block,
  email, box or tailnet address, home path, operator name or instance
  domain. The TypeSafe key's shape appears only as a test pattern and a
  fixture made of `0123...`.
- No `.env` was ever committed, on any ref. The last three commits of
  `egress.py`, `jev/settings.py`, `jev/client.py` and the root helper hold
  no key-shaped value.
- The eval sets and the talk battery are agent-authored: canon residents,
  invented lines. The seven outgoing commit messages hold no player text or
  PII. The operator's game commands that `68125c8` stops quoting were pushed
  earlier; they are game commands, not personal data.
- `instance/` and `.claude/settings.local.json` are still ignored.

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
  the operator's user could point it at the tunnel token, or now at the
  gateway's key file. Anyone who can do that already holds `docker`.
- **The pre-login surface is public** (the door, login, invite redemption,
  static assets). The app and the edge both throttle it.
- **Friends drive shared-world verbs on shared objects** (the co-op
  design).
- **What friends type reaches the local LLM.** Role separation, length
  caps, banlists and strict output validation stand between them.

Accepted by the operator for Jev (docs/EXTERNAL.md, 2026-09-30):

- **Friends' typed lines to residents reach TypeSafe while a key is set**,
  with no stated retention, and the door does not say so. Other dreamers'
  data in the judge's context is the WARN above, not part of this
  acceptance.

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
  mutation. A promise judge (now with Jev beside it when a key is set) only
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
    remain (BACKLOG `agent-sessions-without-root`). The allow list now runs
    interpreters with no prompt (NOTE above).
  - The three guard WARNs above are not unmodeled spellings: each asked
    before `8eb8107`.
- Player text reaches the agent's context through `bin/game play` (names,
  speech, moves, gestures; letters and looks marked) and, since this turn,
  through `bin/game jev report --disagreements` (labelled as data). The
  verbs an injected instruction would want stay behind ask rules.

---
*Prior review (2026-09-30, paths, commit `6981ba7`): 22 files covering the parser whitespace fix, the agent-guard rework in `aef3abd` and the parts playtest turn. It found three WARNs: the guard deleting a quoted substitution inside a redirection target, the guard failing open on a long `eval` chain, and click-frame ids reaching the dream digest unscanned. /codereview fixed all three in `bc0fb71`, leaving 0 BLOCK / 0 WARN / 5 NOTE. The full entry is at `git show 604671b:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-30","commit":"68125c8cdb13345ff60923882f7027b4be63dc5d","warn_fixed_by":"codereview-2026-09-30d","scope":"paths","scanned_files":["bin/game","bin/install-hooks","daydream/accounts_cli.py","daydream/api/ws.py","daydream/config.py","daydream/dialogue.py","daydream/egress.py","daydream/jev/__init__.py","daydream/jev/cli.py","daydream/jev/client.py","daydream/jev/evals.py","daydream/jev/ledger.py","daydream/jev/runtime.py","daydream/jev/seam.py","daydream/jev/settings.py","daydream/jev/surfaces.py","daydream/llm/client.py","daydream/parser.py","daydream/play.py","daydream/prodcheck.py","daydream/prodctl.py","daydream/textscan.py","daydream/verbs.py","docs/claude-settings.local.example.json","docs/playtests/2026-09-30-jev-talk.battery.json","ops/install-prod.sh","ops/root/daydream-root","ops/systemd/daydream-egress.service","tests/conftest.py","tests/model_eval/judge_adversarial.json","tests/model_eval/judge_labeled.json","tests/model_eval/parser_heldout.json","tests/model_eval/topics_heldout.json","tests/model_eval/topics_labeled.json","tests/test_agent_guard.py","tests/test_egress.py","tests/test_glimpse.py","tests/test_guard_install.py","tests/test_jev.py","tests/test_jev_runtime.py","tests/test_no_cloud_keys.py","tests/test_play_bridge.py","tests/test_prodcheck.py","tests/test_prodctl.py","tests/test_root_helper.py","tests/test_runbooks.py","tests/test_textscan.py","tools/agent_guard.py"],"block":0,"warn":4,"note":9} -->
