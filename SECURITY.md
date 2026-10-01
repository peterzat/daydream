# SECURITY.md

## Security Review — 2026-10-01 (scope: paths)

**Summary:** Path-scoped review of the five paths the caller named, read as
their change from the last scan (`d57fbe3`) to HEAD `2a8d93b`. That covers
three commits:
- `4b69ea6`: teardown scrubs every file it lands in the reports folder (the
  made-up password, and the session's absolute folder), and the
  `reports_dir()` docstring is fixed. This was the last entry's playthrough
  NOTE, now resolved.
- `9c9bad0`: the reports folder's screenshots are re-encoded at 960 px, and
  `bin/game playthrough purge` deletes finished sessions' villages.
- `2a8d93b`: nudity words join the banlist's content category, the first
  half of the last entry's art NOTE.

No BLOCK or WARN. The art NOTE is carried, narrowed: the case the last entry
measured is closed, but synonyms and inflections still reach SDXL on two
paths (a grown room's painting and a dreamer's portrait), and the negative
prompts are unchanged. Register: 0 BLOCK / 0 WARN / 9 NOTE (eight carried;
their files are unchanged).

### Findings

[NOTE] daydream/llm/safety.py:57-59 (with daydream/api/slots.py:201, daydream/growth.py:286 and :364-381, and node "4" of daydream/images/workflows/painterly_room.json and painterly_portrait.json) — `2a8d93b` closes the case the last entry measured. A phrase or a dreamer's look that says nude or naked is now refused before any call, and a composition that keeps one is rejected with the seed kept. The list is per word, though, and the two paths that put a friend's words into SDXL have nothing else between them and a synonym. The workflows' negative prompts still name no content (the other half of the last entry's remediation), and `art_seed` still builds a weighted run from words scattered through the `room_seed`.
  Attack vector: An invited friend makes a dreamer whose look is "a bare-breasted bather" or "a sexy dreamer in lingerie". `_toon_request` (slots.py:164-203) checks a 300-character cap and `first_banned`, and both pass. The portrait is painted from those words (`portrait_target`, images/client.py:313), shown on the dreamer's card to every player in the same room, and kept in the art keep with its prompt. An admin repaint replaces the cache file, not the kept copy. On the growth path, the phrase "a sleeper in her nakedness" passes the gate (growth.py:550). If the gardener keeps the word, the composition passes (growth.py:286) and `art_seed` weights it at 1.4.
  Evidence: deterministic calls only (no model call, no render):
  - `first_banned` returns None for sex, sexy, porn, nakedness, nudist, undressing, disrobed, bare-breasted, breasts, lingerie and "nothing but moonlight". On the gore side it returns None for blood, severed, decapitated and entrails.
  - `validate_growth_output` now rejects a `room_seed` that says "naked" anywhere, so the last entry's "(a woman bathing naked beneath:1.4)" can no longer form. It accepts one that says "nakedness", and `art_seed` then returns "(a sleeper in her nakedness:1.4)".
  - The combination still forms with a word the list lacks. The phrase "a woman bathing bare beneath the willow" passes the gate, a `room_seed` of "a woman's shawl on bare branches, and birds bathing beneath a willow by the pool" passes the validator, and `art_seed` returns "(a woman bathing bare beneath the willow:1.4)".
  - Node 4 of both workflows lists style terms only (harsh edges, pixel art, neon, ..., deformed, low quality).
  - Mitigations: accounts are invited, and a player makes at most six dreamers a day (`DREAMERS_PER_DAY`). None of the seven new words appears in `worlds/`, so nothing authored is newly dropped.
  Confidence: high that these words reach the prompt. No image was rendered, so how explicitly SDXL draws them under the portrait framing and the watercolor LoRA is unmeasured.
  Remediation:
  - Add content terms to node 4 of both workflows (for example nsfw, nudity, nude, naked, sexual, lingerie, gore, blood, corpse). The model then resists the synonyms no wordlist will hold. It changes every cache key, so batch it with the next workflow change, as the last entry said.
  - Extend the sexual category with whole words that are safe in this world: sexy, porn, pornographic, nakedness, nudist, nudism, undressing, disrobed, lingerie, bare-breasted. Avoid stems that catch village words: `nud\w*` takes "nudge", `sex\w*` takes "sextant" and "sexton", and "breast" takes "chimney breast".
  - In `art_seed`, weight only runs of two or more consecutive phrase words found in the same order in the `room_seed`, and strip `()[]:` from the `room_seed` part (unchanged from the last entry).

Carried from the last entry (still open; none of their files changed since `adc00ff`):

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt. The guard reads code only for literal spellings, so a computed argv or path gets neither a prompt nor a decision. Narrower rules (`.venv/bin/python -m pytest *`) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). The template's allow list is unchanged.

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list. `cat .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`.

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling. Since `d09493d` the client pauses for a minute after a timeout, a network error, a 429 or a 5xx. That caps what an outage costs in time, not what a busy player spends. The parser change of `b2b112d` sends more lines to residents (`<name>, <words>`), and so, with a key set, to Jev. Remediation: a daily ceiling from the ledger, past which `enabled()` reads off.

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision. The code is unchanged and was not re-measured this run. A time limit inside `main`, or a single-pass brace expansion, would close it.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". Outside this scope; unchanged.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The `read` reply on written prose (`glimpse.py:471`) names a noun from the same prose. The server accepts control characters in typed lines and appearance seeds. `play.py` is unchanged.

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). Outside this scope; unchanged.

### Traced and cleared this run (not findings)

- **Teardown's scrub (`4b69ea6`) resolves the last entry's playthrough
  NOTE.** All four remediations landed:
  - each action-log line is scrubbed whole after its shot is made
    relative, mark labels included;
  - notes, page errors and the report with its session record pass through
    the same scrub, which masks the password and turns the session's folder
    and its `player/` folder (as written and resolved) into the run's id;
  - the docstring is fixed;
  - the test plants both cases and passes.

  A probe in a scratch data dir showed the residuals: a password typed in
  two pieces, or written in another case, is not masked. From the code, a
  password cut short by a mark label's 72-character limit would leave its
  prefix, and a screenshot shows whatever was typed in plain view. None of
  this matters. The password belongs to an account that exists only in the
  session's own data dir, whose server stops at teardown and which `purge`
  now deletes. A path outside the session folder (the sessions root, the
  home directory) is also kept. It adds nothing: the box's home and data
  layout already appear in four tracked files (`docs/playtests/BRIEF.md`,
  `tests/test_ops_units.py` and two dreams' `rehearsal.json`).
- **`share_shot` (`9c9bad0`).** Its input is the harness's own Chromium
  screenshots. The player can write only notes.md and report.md, so nothing
  it controls reaches Pillow. The re-encode drops EXIF and ICC profiles. A
  JPEG comment would survive (Pillow carries `info["comment"]` through
  `convert` and `save`, checked), but Chromium's screenshots carry none. A
  file that will not open is copied as it is, as the earlier `copytree` did.
- **`purge_finished` (`9c9bad0`).** It deletes only a directory under the
  sessions root that holds `session.json`, has a landed report of the same
  name, is not the current session, and whose recorded server and browser
  are not live harness processes. `shutil.rmtree` refuses a symlinked entry
  and does not follow links inside one. The player cannot reach it:
  `./browser purge` exits 2 (checked), like every verb outside the eight
  player verbs. Purging also removes the raw action log and transcript that
  hold the unmasked password.
- **The banlist change** is additive. `first_banned` is a fixed
  alternation with word boundaries, so it has no backtracking risk, and
  "nudes" matches once "nude" fails its boundary. The new words appear
  nowhere in `worlds/`, `docs/canon/` or WHIMSY.md. Every other caller
  (letters, dreamer names, dialogue drafts, journals, drift, glimpses,
  memories) refuses or falls back on a hit, so a false positive fails
  closed.

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 0 items (the fresh 1.15 village).
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username. They are the agents' probe dreamers and the operator's dev
    username, with no typed lines, unchanged since the last scan.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The five files' last three commits each (`git log -p --follow -3`) and
  the unpushed range (`4b69ea6..2a8d93b`, two commits, every text file)
  hold none of these: a key, a token, a private-key block, an email, a box
  or tailnet address, a home path, the operator's name or the instance
  domain.
- The names in the tests are fixtures (Robin Ash, Wren, Ada, Bo, Cy, Di),
  and so is the password they use.

### Coverage

- All dimensions were reviewed. No dependency manifests or ops files are in
  scope. Pillow, newly imported by `playthrough.py`, is a dev and test
  dependency (12.2.0 in the dev venv, not in the prod lock), and it decodes
  only harness-made screenshots.
- `daydream/llm/safety.py`, `daydream/playthrough.py`,
  `tests/test_playthrough.py` and `tests/test_safety.py` were read in full.
  `tests/test_growth.py` was read as its diff, its test list and its
  fixtures.
- Read in context for the banlist's reach: growth's validator, `art_seed`
  and phrase gate; `slots._toon_request`; `portrait_target`; both
  workflows' negative prompts; the art keep's header.
- The three test files ran: 124 passed, none skipped (the medium tier drove
  Chromium).
- Every probe was deterministic and local: teardown on a fake session in a
  scratch data dir, `share_shot` on a JPEG carrying EXIF, ICC and a
  comment, and the banlist, the validator and `art_seed` on chosen strings.
  No model call, no render, and nothing written outside the scratchpad.
- Outside the named paths, the unpushed range also changes
  `.claude/skills/playthrough/SKILL.md`, `CLAUDE.md` and
  `playthroughs/README.md`. They were pattern-scanned for secrets and
  instance facts only, not reviewed.
- Git history: no credential-handling files are in scope (`playthrough.py`
  handles only the made-up password, stored 0600). The five files' recent
  history was checked as above.

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
*Prior review (2026-10-01, paths, commit `d57fbe3`): 18 paths over four commits after `adc00ff`: the `art_seed` fix, the gear's home, and the first three blind playthroughs committed with their reports, notes, action logs and 403 screenshots. The last entry's WARN was fixed. Two NOTEs were new: the gardener kept a nude figure for one of four adversarial phrases and `art_seed` weighted it, and teardown scrubbed only the action log's typed text. The register stood at 0 BLOCK / 0 WARN / 10 NOTE. The full entry is at `git show 4b69ea6:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-01","commit":"2a8d93babc2eca7c4235b9684e97c7a83d8bddf7","scope":"paths","scanned_files":["daydream/llm/safety.py","daydream/playthrough.py","tests/test_growth.py","tests/test_playthrough.py","tests/test_safety.py"],"block":0,"warn":0,"note":9} -->
