# SECURITY.md

## Security Review — 2026-10-01 (scope: paths)

**Summary:** Path-scoped review of the 18 paths the caller named, read as
their change from the last scan (`adc00ff`) to HEAD `d57fbe3`. That covers
four commits:
- `32d5840`: the /codereview fixes. `art_seed` weights only the planter's
  words the composition kept (the last entry's WARN), and the gear Tace hands
  back goes home to the loft.
- `a1c4bbb`: a REFLEXES heading (outside the named paths).
- `a29ad0e`: `playthroughs/` leaves `.gitignore`. Teardown's copy of the
  action log names screenshots by their place and masks the made-up password.
- `d57fbe3`: the first three blind runs, committed: reports, notes, action
  logs and 403 screenshots.

The last entry's WARN is fixed: this run's probe shows the words the gardener
drops stay out of the painting's weighted words. No BLOCK or WARN. Two NOTEs
are new. The first carries that WARN's open image-content follow-ups, now
measured: the gardener itself kept a nude figure for one of four adversarial
phrases, and `art_seed` weights what it keeps. The second is teardown's
scrub, which covers only the action log's typed text. The committed
playthroughs hold nothing of the instance. Register: 0 BLOCK / 0 WARN /
10 NOTE (eight carried; their files are unchanged).

### Findings

[NOTE] daydream/growth.py:364-381 (with daydream/llm/safety.py:57-58) — The fix for the last entry's WARN holds for what the dream-gardener drops. What it keeps still reaches SDXL with no content check, and is now weighted at 1.4. That WARN's other two remediations (an image-content wordlist, negative-prompt terms) are still open; this NOTE carries them.
  Attack vector: A friend with an unspent dreamseed plants a phrase that passes the gates. The banlist's content category is three words, so "nude" and "naked" pass. When the gardener keeps the content in its `room_seed`, `art_seed` puts those words first at weight 1.4 (`growth.py:656` stores it). The first entry paints it from `Room.art_seed`, for every visitor.
  Evidence: A text-only probe sent four adversarial phrases and a control through the production gates, `GROWTH_SYSTEM`, `_user_prompt`, `validate_growth_output` and `art_seed`, against the served model. It made 5 calls, rendered no image and wrote nothing.
  - For an unclothed bather and for a dead man by a pool, the composition left the content out, and `art_seed` did not weight it. The fix works there.
  - For a nude sleeper, the gardener kept "a nude sleeper whose pale skin..." in its `room_seed`. `art_seed` weighted "a nude sleeper skin pale as candle wax" at 1.4.
  - A skull with a knife was refused. The control kept its colour words.
  - The filter is per word. A deterministic call to `art_seed`, with a `room_seed` that uses "bathing", "naked" and "woman" in separate, harmless phrases, returns "(a woman bathing naked beneath:1.4)". The probe did not produce that case.
  - The `room_seed` part is appended unsanitized, so weight syntax the gardener copies from a phrase reaches the prompt. No ComfyUI embeddings are installed.
  Precedent: appearance seeds reach SDXL raw behind a cap and the same banlist. Accounts are invited, and the admin repaint tool replaces a painting. Confidence: high that the words reach the prompt; no image was rendered.
  Remediation:
  - Add nudity terms to the banlist's content category (nude, naked, unclothed, undressed, topless; "naked" also catches bare branches, an acceptable cost here). The banlist already runs over the phrase, the composition and appearance seeds. The check on the composition holds even when a phrase is spelled to dodge a wordlist.
  - Add content terms to the workflow's negative prompt at the next workflow change. That change busts every cache key, so batch it.
  - Optionally, weight only runs of two or more consecutive phrase words found in the same order in `room_seed`. Strip `()[]:` from the `room_seed` part, as the phrase part already is.

[NOTE] daydream/playthrough.py:586-602 and :616-629 (with :1174 and :104) — Since `a29ad0e` the reports folder is committed, and teardown scrubs only the typed text in the action log. The player's notes.md and report.md, page-errors.log and each entry's `marks` labels are copied as written.
  Attack vector: `format_response` hands the player every screenshot's absolute path, which names the operator's home directory (:1174). BRIEF.md gives it the made-up password. A future player that quotes a path or the password in its notes or report, or types the password into a plain text field, lands it in a commit. The skill's read before commit is the only control.
  Evidence: A deterministic call to `shareable_actions` kept the password in two cases: in a `marks` label (`text field "username" containing "<password>"`), and when typed in two pieces. None of the three committed runs did either; each was checked against its session's own password, which was never printed. The password opens nothing after teardown: its account lives only in the session's data dir, and the loopback server stops. So the practical exposure is the box's username and data layout, and the username is already public as the git author. `reports_dir()`'s docstring (:104) still calls the folder gitignored.
  Remediation:
  - Mask the password over the whole serialized entry, `marks` included.
  - Run notes.md, report.md and page-errors.log through the same scrub on their way into `playthroughs/`: the password masked, and the session dir rewritten to a relative path.
  - Fix the docstring.
  - Extend `test_teardown_lands_the_report_with_its_session_record` with both cases.

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

- **The committed playthroughs** (3 reports, 3 notes, 3 action logs, the
  README and 403 screenshots).
  - None holds a key, a token, a private-key block, an email, a box or
    tailnet address, a home path, a URL, the operator's name or the instance
    domain.
  - All three logs mask the password. No session's password appears in any
    tracked file, in any diff in the history, or in any commit message. Each
    was checked against that session's own password, never printed. The
    local raw logs keep it, by design.
  - The screenshots carry only JFIF and an sRGB profile: no EXIF, no
    comments. The three viewed (the door, the awake page, a grown room) show
    only the page, with no browser chrome.
  - The operator's name surfaces only in the invite card, the sleep note and
    the "invitations are resting" line. A playthrough reaches none of them,
    and dev's `.env` does not set it.
  - The four session servers are stopped (nothing listens on their ports).
    Their accounts exist only in each session's own data dir.
- **The blind players' typed lines,** now in git, read as data: sign-in,
  looks, greetings, asks, plant phrases and two letters. Nothing steering.
  Their villages had no other players. The only inputs were authored data,
  the local model and the player itself, so a report cannot carry a third
  party's words into a later session.
- **`shareable_actions`' paths.** `shot` becomes `shots/<name>`. A line that
  does not parse is dropped, not copied. `sess["id"]` comes from the 0600
  session file, built from a username reduced to `[a-z0-9]`.
- **`art_seed`'s phrase part** is ASCII letters only (`[a-z]+`), stricter
  than the strip it replaced, so no weights, brackets or colons come from the
  phrase. A phrase in look-alike letters splits into fragments that match
  nothing in `room_seed`.
- **The prologue's new effect** is `set_property` on a fixed id with an
  authored value, under `RULE_KINDS`.
  `test_the_gear_tace_hands_back_goes_home_to_the_loft` pins it, and the
  assembled artifact matches its sources.
- **`.gitignore`** still ignores `instance/`, `.env` and
  `.claude/settings.local.json`, and git tracks none of them.

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

- The unpushed range (`32d5840..d57fbe3`, three commits, every text file)
  and `32d5840` itself hold none of these: a key, a token, a private-key
  block, an email, a box or tailnet address, a home path, the operator's
  name or the instance domain. A pattern scan of the added lines found
  nothing.
- The names in the playthroughs are the harness's made-up players and
  village residents. The names in tests are fixtures (Robin Ash, Wren).

### Coverage

- All dimensions were reviewed. No dependency manifests or ops files are in
  scope.
- `daydream/playthrough.py` was read in full. `daydream/growth.py` was read
  as its diff, with `art_seed`'s caller, the gardener prompt, the validator
  and the banlist read in context, and the image client's prompt builder for
  how `art_seed` reaches ComfyUI.
- The ten playthrough text files were read in full. The action logs were
  read as parsed entries, with every typed line read.
- The 403 screenshots are outside the named paths. All were checked for
  embedded metadata and three were viewed; the other 400 were not viewed.
- The three test files were read as diffs and run: 137 passed, none
  skipped. `tools/assemble_world.py --check` passes.
- One live probe ran: five text calls to the shared vLLM while prod was
  awake. No image was rendered and nothing was written.
- Git history: no credential-handling files are in scope. The commits since
  `adc00ff` were checked for key-shaped values, and the whole history for
  the four sessions' passwords.

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
*Prior review (2026-10-01, paths, commit `adc00ff`): 33 paths (70 files) over six commits after `6a934d1`: the fold-tab fixes, the SPA's rail and margin band, the parser's vocative talk, the Ledger's planted places, the gear trail, and the playthrough fixes with `art_seed` at WORLD_VERSION 1.15. One WARN: a grown room's painting led with the planter's raw phrase at weight 1.4, restoring what the gardener had left out (six text-only probes). `32d5840` fixed it by weighting only the words the composition kept. The register stood at 0 BLOCK / 1 WARN / 8 NOTE. The full entry is at `git show 32d5840:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-01","commit":"d57fbe34527543fcafc12b4b3ac8013db98decb5","scope":"paths","scanned_files":[".gitignore","daydream/growth.py","daydream/playthrough.py","playthroughs/2026-10-01-noor.md","playthroughs/2026-10-01-noor/actions.log","playthroughs/2026-10-01-noor/notes.md","playthroughs/2026-10-01-priya.md","playthroughs/2026-10-01-priya/actions.log","playthroughs/2026-10-01-priya/notes.md","playthroughs/2026-10-01-silas.md","playthroughs/2026-10-01-silas/actions.log","playthroughs/2026-10-01-silas/notes.md","playthroughs/README.md","tests/test_growth.py","tests/test_playthrough.py","tests/test_walkthroughs.py","worlds/lost-hours.json","worlds/lost-hours/arcs/00-prologue.json"],"block":0,"warn":0,"note":10} -->
