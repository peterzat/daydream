## Review — 2026-09-30d (commit: d09493d)

**Summary:** Full-depth review of `origin/main..68125c8` (53 files, +5,100/-123): the agent guard's prompt reduction (heredocs read as what they feed, protected files ask only on a real write, the installed copy), Jev beside the promise judge and topic choice, the egress gateway and its root-helper verbs, and the docs. Three fresh reviewers (the Jev runtime, the gateway and root helper, the guard) plus `/security` on the changed paths, with probes against the guard at origin/main and HEAD. Tests: medium 2678 before, 2745 after one /codefix cycle (67 new: 62 in the guard's suite); short 2053; `ruff check .` clean. All 2 BLOCK and 7 WARN fixed in `d09493d`; the re-review found no new BLOCK or WARN.

**External reviewers:**
None configured.

### Findings

[BLOCK] tools/agent_guard.py:149-184 (`_HEREDOC`, `_heredoc_kind`), with `_read_heredocs`/`_skeleton`/`_code_bodies` — a heredoc fed to a program the guard does not recognize is read as text and dropped, and so is everything after a delimiter the regex cuts short; gated verbs hidden this way got an ask at origin/main and get no decision now (also /security WARN 1, which shows a credential-file read losing its deny the same way).
  Evidence (strings fed to both guards, nothing run; G = `bin/game prod invite create --for Eve`):
  `cat <<X-Y >/dev/null\nhello\nX-Y\nG` new=None old=ask (the regex takes `X` as the delimiter, never finds it, and swallows the rest as text; `END.1` the same);
  `sudo -u daydream bash <<EOF\nG\nEOF` new=None old=ask (`daydream` taken as the program);
  `nice -n 5 bash <<EOF ...` and `timeout 30 bash <<EOF ...` new=None old=ask (`5`, `30`);
  `while read -r l; do eval "$l"; done <<EOF\nG\nEOF` new=None old=ask (`done`);
  `cat <<EOF | sudo -u daydream bash\nG\nEOF` new=None old=ask.
  Suggested fix: (a) the delimiter is the whole shell word after `<<`/`<<-` (quotes stripped), not an identifier prefix; (b) a heredoc whose closing line is never found keeps its body, read as commands; (c) find each program the heredoc feeds (the command it belongs to, and every command it is piped into) with the same unwrapping the argv pass uses (`_unwrap`, `WRAPPER_VALUE_OPTS`, positional values such as `timeout N` and `nice -n N`), and read the body as "text" only when every such program is in a short allowlist of text consumers (`cat`, `tee`, `git`, `gh`, `head`, `tail`, `wc`, `grep`, `sort`, `diff`, `jq`), "code" when one is an interpreter, and "shell" for anything else, a shell keyword (`done`, `fi`, `}`, `)`) included; (d) tests: every probe above asks, and the text cases the change was made for (`cat > f <<EOF` with prose, `git commit -F - <<EOF`) stay quiet.

[BLOCK] daydream/model_eval.py:389 (`_install_judge_tag`) — its wrapper is `async def tagged(context, drafts)`, but `dialogue.talk` now calls `judge(..., toon=actor.id)`, so every guarded talk under `bin/game model-eval` raises TypeError, key or no key; the dialogue and promise suites (the gate CLAUDE.md requires before any model or flag change) fail.
  Evidence: a probe installs the tag, turns the guard on, runs `verbs.execute_command(me, "talk", "t-tace", None, "who taught you everything you know?")`: `TypeError: tagged() got an unexpected keyword argument 'toon'`.
  Suggested fix: `async def tagged(context, drafts, toon=None)` passing `toon=toon` to `real`; a tier_short test that runs one guarded talk with the tag installed.

[WARN] daydream/jev/runtime.py:65 (`topic`) — with Jev on, a paraphrase can take an open story beat's line away: authors make a beat win over overlapping plain topics by listing those topics' names as the beat's aliases (`mott-minute/mott-confides` aliases "the folded thing", "the tin", which are also Mott's plain labels), and the word match honours that, but Jev is offered the plain topics whose names are an open beat's aliases, so a paraphrase naming no alias gets the canned plain answer and `dialogue.talk` (whose `advance` would have fired the beat) never runs.
  Evidence: probe on the canonical world, the beat open, the dialogue mock advancing it, Jev answering "the folded thing" at 0.9: Jev off, beat done True; Jev on, beat done False.
  Suggested fix: in `topic`, drop from `plain` every topic whose label or aliases (normalized) match an open beat's label or aliases from the same `available_topics` list.

[WARN] daydream/model_eval.py `main` — `bin/game` loads `.env`, so with the dev key present Jev is on during `bin/game model-eval`: the promise suite's verdicts become the combined rule, topic routing becomes Jev's, runs spend and write text-bearing ledger rows, and a local-model comparison is partly Jev.
  Suggested fix: at the start of `main`, remove `DAYDREAM_JEV_API_KEY`, `TYPESAFE_API_KEY` and `DAYDREAM_EGRESS_URL` from `os.environ` and call `daydream.jev.settings.forget()`, with a comment saying model-eval measures the local path.

[WARN] daydream/jev/client.py:103-106 (`ask`) — `timeout_s()` is httpx's per-phase timeout (connect, write, read each), and only 402/401/403 pause calls, so during an upstream outage every free line to a resident waits the full timeout, several phases' worth, on every call; docs/EXTERNAL.md says "at most the 3 s timeout".
  Suggested fix: bound the call with `asyncio.wait_for(..., settings.timeout_s())` (a total deadline), and after a timeout, a transport error, a 5xx or a 429, pause calls for 60 s (`PAUSE_S["unreachable"]`), recorded like the other pauses; tests with the mock transport.

[WARN] daydream/jev/__init__.py:1-25 and daydream/prodctl.py:996-998 — stale descriptions: the package docstring still says Jev is a spike on `spike/jev` with `DAYDREAM_JEV` / `DAYDREAM_JEV_<SURFACE>` off/shadow/on modes and `_MIN` thresholds (none exist; an operator setting `DAYDREAM_JEV=off` to stop sending text gets no effect), and `plan`'s comment says "Prod itself runs Jev off: prod.env holds no key, and the service may reach loopback only".
  Suggested fix: rewrite both to match `settings.py` (on exactly when a key is reachable: `.env` in dev, the egress gateway's key in prod; off by removing it; `TYPESAFE_API_KEY` also read).

[WARN] (security) tools/agent_guard.py:668-669 (`lists_only`) — a `find` over `~` or `~/.config` asks only when piped straight into `xargs`, `while read` or `parallel`; `| timeout 5 xargs cat`, `while IFS= read`, `cat $(find ...)` and `| grep x | xargs cat` asked at origin/main and get no decision now.
  Suggested fix: a find lists only when its output reaches no other program except a short set of text filters (`head`, `tail`, `wc`, `sort`, `uniq`, `grep`, `cut`), with every later command in its pipeline checked through `_unwrap`, and never inside `$( )` or backticks.

[WARN] (security) tools/agent_guard.py:524-525 (`_protected_write`) — writes to the settings or the installed guard by `sed --in-place`, `sed -Ei`/`-ni`, or `find ... -exec sed -i` asked at origin/main and get no decision now; `sed`'s `w` command, `sort -o`, `uniq IN OUT` and `git ... --output` were never caught and are now on the allowlist.
  Suggested fix: `sed`/`perl` naming a protected path is a write when any short-option cluster contains `i`, or `--in-place`, or the script has a `w`/`W` command; `sort -o/--output`, `uniq`'s second operand, and any `--output`/`--output=` naming a protected path are writes; the argv after `find -exec/-execdir/-ok/-okdir` is checked as a command of its own. Tests for each.

[WARN] (security) daydream/dialogue.py:523-532 (`judge_view`) with docs/EXTERNAL.md "What leaves the box" — Jev's judge also receives other dreamers' data the doc does not list: the names of everyone in the room, a named dreamer's last-seen place, time and state, and other players' deeds by name.
  Suggested fix: list these precisely under "What leaves the box" (the operator accepted "the resident's context" for the judge, JEV-SPIKE.md open item 2; the publish report surfaces the exact list to the operator before a prod key is set).

[NOTE] daydream/jev/settings.py:68-80 — in prod, `enabled()` does a synchronous urllib GET to the gateway's `/routes` (1 s timeout) at most once a minute on the event loop; instant when the gateway is up or absent, up to 1 s for everyone if it hangs.
[NOTE] tests/conftest.py `_no_jev` does not stub `settings._gateway_has_key`: a future test under `DAYDREAM_ENV=prod` reaching a talk surface would ask the real 127.0.0.1:54323.
[NOTE] daydream/accounts_cli.py:133-137 — `account delete` purges Jev decisions only for dreamers in the current world; ones from before a reset age out at 30 days.
[NOTE] daydream/egress.py:165-166 — a lowercase upstream `content-type` plus the `setdefault("Content-Type")` yields two content-type headers.
[NOTE] daydream/egress.py Handler — no socket timeout: a stalled local caller holds a thread; about 62 exhaust `TasksMax=64` (Jev then falls back to local).
[NOTE] ops/root/daydream-root `_egress_doctor` — prints "matches release X" when the release has no `daydream/egress.py` to compare (or none is deployed).
[NOTE] (security) The dev allowlist now covers `python3 *`, `node *`, `.venv/bin/python *` and `timeout *`: the accepted risk on interpreter one-liners was written when those prompted; the operator re-confirms it.
[NOTE] (security) The dev Jev key is in the repo's `.env`, which the guard does not deny reading; Jev has no daily spend ceiling.
[NOTE] tools/agent_guard.py (after the fix) — five prompts HEAD did not give, all conservative: `find /` with escaped `\( \)` grouping reads as a group, and an interpreter heredoc the reader stops on reads whole (a docstring naming a gated verb then asks).
[NOTE] tools/agent_guard.py (after the fix, not caught at origin/main either) — variable flow (`x=$(cat <<EOF ...)` then `eval "$x"`), `xargs bin/game <<EOF`, `git apply`/`patch` heredocs that edit the settings, and `curl -o` onto a protected file.
[NOTE] tools/agent_guard.py `_RUNS` — interpreter code that builds a gated command from variables across lines is not read (a list on one line, `subprocess.run(["bin/game"] + args)` on another): code can always assemble a command the guard does not see.

### Fixes Applied

All in `d09493d` (one /codefix cycle, then the re-review):

- [BLOCK] tools/agent_guard.py — a new heredoc reader (`_heredoc_spans`) finds heredocs as bash does (the whole delimiter word, operators outside quotes, `${ }` and comments, the body from the first unquoted newline to an exact closing line); a body is text only when every program it feeds (unwrapped as the argv pass unwraps, across pipes, both sides of the operator and any enclosing `$( )`) is in `TEXT_READERS`, code when the rest are interpreters, and commands otherwise; a body never closed, and every body of a command the reader does not follow (arithmetic, ANSI-C quoting, a stray parenthesis, more than 32 heredocs), is commands. Every probe above asks; `cat > f <<EOF`, `git commit -F -` and `git commit -m "$(cat <<'EOF' ...)"` stay quiet.
- [BLOCK] daydream/model_eval.py — `tagged(context, drafts, toon=None)` passes `toon` on; a tier_short test runs a guarded talk with the tag installed.
- [WARN] daydream/jev/runtime.py — plain topics that share a normalized name with an open beat are not offered to Jev; a test on Mott's beat.
- [WARN] daydream/model_eval.py `main` — removes the Jev keys and `DAYDREAM_EGRESS_URL` and forgets the cached gateway answer; a test.
- [WARN] daydream/jev/client.py — one total deadline (`asyncio.wait_for`); a timeout, transport error, 429 or 5xx pauses calls for 60 s (`unreachable`); tests; EXTERNAL.md says so.
- [WARN] daydream/jev/__init__.py, daydream/prodctl.py — both describe the key-presence switch.
- [WARN] (security) tools/agent_guard.py `lists_only` — a find lists only with no substitution, subshell or group involved, no file written, and every later stage in head/tail/wc/sort/uniq/grep/cut.
- [WARN] (security) tools/agent_guard.py `_protected_write` — `-i` in any short-option cluster, `--in-place`, sed's `w`/`W`, `sort -o`, `--output(=)`, `uniq`'s output operand, and the command a `find -exec` runs; words now split on `=` (which also makes the old `dd of=` check work).
- [WARN] (security) docs/EXTERNAL.md — "What leaves the box" lists exactly what `judge_view` sends (not the recent exchange, which it never sent).
- [NOTE, applied] docs/claude-settings.local.example.json — the hook runs `/usr/bin/python3 -I` (the live settings follow with the guard install, one approval).

Re-review: every earlier probe asks, and each protected-write probe asks or reads as it should. A replay of all 14,039 recorded Bash/Read/Edit/Write calls through HEAD's guard and the fixed one differs by five prompts, all on the safe side: four `find /` commands with escaped `\( \)` grouping, and one interpreter heredoc whose docstring names `bin/game prod sleep`. Pathological inputs (a 530 KB heredoc, 40 heredocs, 5,000 `<<`, 2,000 nested substitutions) decide in under 0.05 s. The guard fixes are live only after `! bin/game guard install`.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-09-30c, refresh, `bc0fb71`): the playtest turn (the heard gate, reply ranking, glimpse parts, refusals by the typed name); 1 BLOCK and 8 WARN (three from /security) fixed over two /codefix cycles; five NOTEs left open.*

<!-- REVIEW_META: {"date":"2026-09-30","commit":"d09493d","reviewed_up_to":"d09493d46a6440524be925e413f32b2cd2748050","base":"origin/main","tier":"full","block":0,"warn":0,"note":11} -->
