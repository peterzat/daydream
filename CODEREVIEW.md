## Review — 2026-10-01 (commit: 677a903)

**Summary:** Full-depth review of `origin/main..677a903`, the /playthrough skill: `daydream/playthrough.py` (fresh village, made-up account, loopback server, headless Chromium daemon, the sandboxed `claude -p` player, teardown), `docs/playtests/BROWSER-BRIEF.md`, `.claude/skills/playthrough/SKILL.md`, `tests/test_playthrough.py`, and the `bin/game` / `.gitignore` / CLAUDE.md wiring. Tests before: short+medium 2763 passed; after one /codefix cycle: 2764 passed. Security (/security, paths): 0 BLOCK / 1 WARN / 9 NOTE; the WARN is the first finding below, fixed.

**External reviewers:**
None configured.

### Findings

[WARN] daydream/playthrough.py:193 — the player can run arbitrary code outside its sandbox: `./browser` runs `python -m daydream.playthrough` with the player's folder as cwd, `python -m` puts the cwd first on `sys.path`, and the player may Write/Edit any file in that folder (`--allowedTools "Bash(./browser *),Write,Edit"`, :414). A planted `json.py` (or `daydream/__init__.py`, or an edited `./browser`) runs as the operator's user on the next `./browser` call, outside Claude Code's permission checks and the agent guard. (security, reproduced with a harmless `json.py`)
  Evidence: `wrapper_script` writes `exec {py} -m daydream.playthrough --session-dir ... --as-player "$@"`; `player_argv` allows `Write,Edit` unscoped; `run_player` sets `cwd=p["player"]`.
  Suggested fix: run the wrapper's Python isolated (`exec {py} -I -m daydream.playthrough ...`), and allow edits only to the two files the brief names (`Bash(./browser *),Edit(./notes.md),Edit(./report.md)`; setup creates both, report.md empty, so the player never needs to create a file). Update `test_the_player_runs_sandboxed_to_its_browser_and_its_own_files` and add a regression test that runs the generated wrapper with a planted `json.py` beside it and asserts the planted file never runs.

[WARN] daydream/playthrough.py:1181 — options after `--as-player` are still parsed, so the player's own arguments can retarget the session: `./browser --session-dir /other look` sets `sdir_arg` to `/other` (the loop keeps consuming `--session-dir` after the wrapper's `--as-player`). The wrapper's contract is "player verbs only" for this session.
  Evidence: `while argv and argv[0] in ("--session-dir", "--as-player")` runs over the wrapper's fixed prefix and then over the player's arguments; checked: `--session-dir /a --as-player --session-dir /b look` resolves to `/b`.
  Suggested fix: stop option parsing at `--as-player` (everything after it is the player's verb and its arguments); test that `--as-player --session-dir X look` is refused as an unknown verb.

[WARN] daydream/playthrough.py:419 — `player_env()` hands the sandboxed player the operator's whole environment minus `DAYDREAM_*` and two API keys. `bin/game` exports everything in the project `.env` and the per-host secrets file (`set -a`), so any other secret there (e.g. `TYPESAFE_API_KEY`, which Jev accepts, per /security) and this session's own `CLAUDE_CODE_*` variables reach the player's shell, where `./browser type "$VAR"` would expand them into the game's input log and its Jev egress. (also a /security NOTE)
  Evidence: `{k: v for k, v in os.environ.items() if not k.startswith("DAYDREAM_") and k not in (...)}`; bin/game:95-106 sources both files with `set -a`.
  Suggested fix: an explicit allowlist (PATH, HOME, USER, LOGNAME, SHELL, LANG, LC_*, TERM, TMPDIR, XDG_RUNTIME_DIR (the wrapper finds its socket there), and the proxy/CA variables if set); extend the test to plant a non-DAYDREAM secret and a `CLAUDE_CODE_*` variable and assert neither passes.

[NOTE] daydream/playthrough.py:430 — `run_player` launches a long `claude -p` run without checking that the session's browser and server answer; a dead browser makes every move fail for the whole run. A ping before launching would fail fast.

[NOTE] daydream/playthrough.py:267 — the playthrough server inherits bin/game's environment, including the dev Jev key from `.env`, so a playthrough's typed lines reach Jev the way dev's do (small spend; an agent's text, not a friend's). Consistent with dev's accepted egress (docs/EXTERNAL.md); worth knowing.

### Fixes Applied

- [WARN] daydream/playthrough.py:193 — `./browser` runs `python -I` (nothing in the player's folder is importable); the player's allowed tools are `Bash(./browser *),Edit(./notes.md),Edit(./report.md)`, and setup creates an empty report.md. Regression test `test_the_wrapper_never_runs_a_file_planted_beside_it` (a planted `json.py` and `daydream/__init__.py` never run). Confirmed in a live `claude -p` probe: report.md and notes.md writable, a Write to `./json.py` and an Edit to `./browser` denied.
- [WARN] daydream/playthrough.py:1181 — option parsing stops at `--as-player`; the player's `--session-dir` is refused as an unknown command (tested, and refused in the live probe).
- [WARN] daydream/playthrough.py:419 — `player_env()` is an allowlist (PATH, HOME, USER, LOGNAME, SHELL, LANG, LC_*, TERM, XDG_RUNTIME_DIR, temp dirs, proxy and CA variables); the test plants a non-DAYDREAM secret and a `CLAUDE_CODE_*` variable. The live probe signed in and played with this environment.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-09-30f, refresh, `068a34c`): Bell's "who came through today" and `jev report`; 3 WARN fixed in one /codefix cycle (a "You" line routed before filling, a caller-less wrapper removed, model-eval's Jev-off made real), 0 BLOCK.*

<!-- REVIEW_META: {"date":"2026-10-01","commit":"677a903","reviewed_up_to":"677a90384462bf1b8d1073d86542257dc2c71eed","base":"origin/main","tier":"full","block":0,"warn":3,"note":2} -->
