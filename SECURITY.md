# SECURITY.md

## Security Review — 2026-10-03 (scope: paths)

**Summary:** Path-scoped review of the four paths the caller named, read in
full and as their change from the last scan (`968da2b`) to HEAD `97a1f4e`.
Two commits touch them:
- `7efca17`: the last review's WARN fix, now committed. The Worker reads the
  door preview first and gives a link-preview fetcher the 200 only when one
  is synced. It is the change the last entry's post-fix pass checked.
- `97a1f4e` (unpushed): main's CI verdict is its tip's own run.
  `main_status` reads the branch tip from GitHub's ref API. When the list's
  newest run belongs to another commit, it asks for the tip's runs by
  commit, and with none listed it says "unknown".

No new finding. The tip must be a 40-hex commit id before it reaches a
query, and the new words carry only our own run's state, a short sha and
the local commit subject. Both NOTEs in these files are still present: the
uptime watch erases its history on a failed read, and a fork's runs can
still fill the one page of runs (the new tip read is not reached when that
page filters to empty). Register: 0 BLOCK / 0 WARN / 10 NOTE, 2 re-checked
and 8 carried.

**Post-fix re-check** (`/codereview` Step 7, uncommitted over `97a1f4e`):
`daydream/ci.py` and `tests/test_ci.py` after `/codefix`'s change for the
code review's WARN. When GitHub cannot name main's tip, a listed "passed"
now reads "unknown" (a note in `prod check`) instead of standing as main's.
A failed, running or other newest run still speaks. The tests that read a
verdict now answer the tip read themselves. Nothing resolved and nothing
new: the change only turns a green into a note, makes no extra `gh` call,
and its words carry only our own run's state, short sha and local subject.
The fork-flood NOTE is still present (probed again). Register unchanged:
0 BLOCK / 0 WARN / 10 NOTE.

### Findings

No new security issue in the range. Two older NOTEs in the scoped files
were re-checked and are still present:

[NOTE] edge/src/worker.js:45-54 and :85 (`watch`) — A failed read of the `uptime` record is taken as an empty record and written back. The recorded outages are erased, and while reads keep failing no unplanned outage can open. It predates this range (the record's shape is from `03a5b08`, 2026-09-28).
  Attack vector: An anonymous client floods the asleep pages (two to four KV reads a request) until the Workers Free plan's 100,000 daily KV reads run out. Friends' tabs left on the asleep note get there too: about a dozen through a whole day of sleep since the fix (three reads per 30 s cycle), about seventeen before. Until the quota resets, each five-minute run (`*/5` cron) reads the flag as awake (`:45`, fail-open by design). The probe fails because the tunnel is down, the `uptime` read fails (`:46-51`), and the run writes `{suspect_since, outages: []}` (`:85`). The history is gone for good, and the "watch:" part of `prod status` (`daydream/edge.py:175-182`) reads "up; no unplanned outage recorded" through a real outage. One transient read error during an outage erases the history the same way.
  Evidence: a local probe of `watch` over a record holding two outages, in three stores: reads that throw (flag asleep), an `uptime` read that throws (origin down), and reads that return null. Every run returned "down"; the record kept 0 outages and never set `down_since`. Mitigation: `prod status` leads with the live public status, which still says the village does not answer.
  Confidence: high for the mechanism. How Cloudflare signals an exhausted read quota (an error or an empty read) is unverified. Both erase; skipping on a thrown read fixes only the first.
  Remediation: when the `uptime` read throws, skip the run and write nothing (return "unknown"), and reset only a value that parses badly. Optionally read the flag strictly in `watch`, so an unreadable flag skips the run instead of probing as awake. Add a throwing-`get` case to `edge/test/worker.test.js`.
  Re-checked this run: `watch` is unchanged since `165c5df` (2026-09-29). A local probe on HEAD, over a throwing `uptime` read with the origin down, again returned "down", kept 0 of 2 outages and set no `down_since`.

[NOTE] daydream/ci.py:49-61 and :122-126 (with daydream/prodcheck.py:227-234) — A run of a pull request from a fork's branch named `main` is listed under `branch=main`. About twenty of them fill the one page `runs()` reads, the push-only, same-repository filter leaves it empty, and `main_status` returns "unknown" ("no runs on main") before it reads the tip. `prod check` then passes a red main with a note. First found in the 2026-09-29 scan; re-checked this run.
  Attack vector: A stranger forks the public repo and pushes about twenty times to a pull request from their `main`. Each push lists a `pull_request` run, one waiting for approval included (as the 2026-09-29 scan found). Until our next push, `prod check`, `prod plan`, `bin/game ci` and `bin/game status` read main as "unknown" instead of red. `bin/game ci watch`, the publish's gate, asks by commit and still sees the red run.
  Evidence: a local probe of `main_status` with GitHub's paging honored (newest first, `per_page`, and the `branch` and `head_sha` filters). 19 fork runs over a red tip read "failed". 20 and 40 read "unknown" ("no runs on main"), while `runs(sha=<tip>)` alone returned the red run. The tip read of `97a1f4e` is never reached in that case, because `:125-126` returns first.
  Confidence: high for the mechanism; medium that every push of an unapproved first-time contributor lists a run.
  Remediation: read the tip before giving up on an empty list, and ask by commit (`runs(branch, sha=head)`) whenever the filtered list is empty or its newest is not the tip. A fork's runs carry their own head commits, so they cannot fill that page.
  Re-checked post-fix: the `/codefix` change sits after the empty-list return, so a full page of fork runs still reads "unknown" before the tip is read (probed again: 20 and 40 fork runs over a red tip, one `gh` call each; 19 still read "failed"). With the page only partly filled, an old green of ours and the tip unreadable, the verdict is now "unknown" where it was "passed"; with the tip readable it was and is "failed".

Carried (still open; their files are outside this scope and unchanged since `968da2b`):

[NOTE] daydream/llm/safety.py:57-59 (with daydream/api/slots.py:201, daydream/growth.py:286 and :364-381, and node "4" of daydream/images/workflows/painterly_room.json and painterly_portrait.json) — The content banlist is per word, and the two paths that put a friend's words into SDXL (a dreamer's portrait and a grown room's painting) have nothing else between them and a synonym. (carried from the 2026-10-01 scan, not re-checked)
  Attack vector: An invited friend makes a dreamer whose look is "a bare-breasted bather" or "a sexy dreamer in lingerie". `_toon_request` (slots.py:164-203) passes it, and the portrait shows on the dreamer's card to everyone in the room and stays in the art keep. On the growth path, "a sleeper in her nakedness" passes the gate (growth.py:550), and if the gardener keeps the word, `art_seed` weights it at 1.4.
  Evidence: the 2026-10-01 entry's deterministic calls. `first_banned` returns None for sex, sexy, porn, nakedness, nudist, undressing, disrobed, bare-breasted, breasts and lingerie (and for blood, severed, decapitated and entrails). Node 4 of both workflows names style terms only. Mitigations: accounts are invited, and a player makes at most six dreamers a day.
  Confidence: high that these words reach the prompt. How explicitly SDXL draws them is unmeasured.
  Remediation:
  - Add content terms to node 4 of both workflows (nsfw, nudity, nude, naked, sexual, lingerie, gore, blood, corpse). It changes every cache key, so batch it with the next workflow change.
  - Extend the sexual category with whole words safe in this world. Avoid stems that catch village words ("nudge", "sextant", "sexton", "chimney breast").
  - In `art_seed`, weight only runs of two or more consecutive phrase words, and strip `()[]:` from the `room_seed` part.

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt. The guard reads code only for literal spellings, so a computed argv or path gets neither a prompt nor a decision. Narrower rules (`.venv/bin/python -m pytest *`) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). (carried from the 2026-09-30 scan, not re-checked)

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list. `cat .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`. (carried from the 2026-09-30 scan, not re-checked)

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling. Since `d09493d` the client pauses for a minute after a timeout, a network error, a 429 or a 5xx. That caps what an outage costs in time, not what a busy player spends. The parser change of `b2b112d` sends more lines to residents (`<name>, <words>`), and so, with a key set, to Jev. Remediation: a daily ceiling from the ledger, past which `enabled()` reads off. (carried from the 2026-09-30 scan, not re-checked)

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision. A time limit inside `main`, or a single-pass brace expansion, would close it. (carried from the 2026-09-30 scan, not re-checked)

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The `read` reply on written prose (`glimpse.py:471`) names a noun from the same prose. The server accepts control characters in typed lines and appearance seeds. (carried from the 2026-09-29 scan, not re-checked)

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`. (carried from the 2026-09-29 scan, not re-checked)

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). (carried from the 2026-09-28 scan, not re-checked)

### Traced and cleared this run (not findings)

- **The tip read** (`ci.py:100-111`). Every caller passes the default
  branch, `main`, so nothing variable reaches the ref path. The reply must
  be an object whose `object.sha` is 40 lowercase hex characters. A list, a
  null object, upper case, a leading dash, 64 hex characters, or a reply
  that is not JSON each read as an unreadable tip (below; probed, and
  again post-fix with an empty reply too: over a stale green, each reads
  "unknown"). `_SHA` uses `^...$`, which also admits a trailing newline.
  GitHub never sends one, and such a sha would only make the next query
  fail and read "unknown". `fullmatch` would be exact.
- **The query by commit** (`ci.py:49`, `:131-136` post-fix). Only the
  validated tip reaches `head_sha=`, so the query string holds nothing but
  hex. What comes back passes the same push-only and same-repository
  filters (probed: a tip with only a fork's run listed reads "unknown").
  The merge puts the tip's runs first, and a run in progress over a failed
  one still says both.
- **The new words** (`ci.py:134-135` post-fix, and the fix's own at
  `:129-130`). The branch is a constant, the tip is hex, and `describe`
  prints our own run's state, seven characters of its sha and the local
  git subject. Nothing a stranger writes reaches the operator's terminal or
  the agent's context through them.
- **An unreadable tip** (`ci.py:127-130` post-fix). At `97a1f4e` the list
  spoke, so a stale green list could stand over a red main while GitHub
  refused the ref call. Since the post-fix change a listed "passed" reads
  "unknown"; a failed, running or other newest still speaks, and none of
  those reads as green (probed: a stale green, a red, a run over a red, a
  run over a green, a cancelled). A stranger cannot cause an unreadable tip:
  the call runs on the operator's own `gh` credentials and rate budget.
- **Older code in `ci.py`, unchanged and unreachable** (noted for
  completeness):
  - `runs()` returns a list-shaped reply as it is (`:57-58`, for the tests'
    fakes), past the push-only, same-repository and control-character
    filters. GitHub's list-runs endpoint always answers an object. Moving
    the adapter into the tests would make it exact.
  - `_subject()` hands a run's `head_sha` to `git log` as a positional
    argument (`:73-74`), where a value starting with `-` would be read as an
    option (`--output=<file>` writes a file). GitHub's `head_sha` is always
    a 40-hex commit id, and only our own push runs reach `_shape`. Checking
    it with `_SHA` in `_shape`, or passing `--end-of-options`, would close
    it.
- **The Worker** (`7efca17`). The committed change is the one the last
  entry's post-fix pass checked, and its line references hold. Re-read in
  full:
  - The 200 needs a synced door preview, a GET, a link-preview user agent,
    and a path outside the API and `/assets/`.
  - The door's words are escaped and filled last, so markers in them stay
    literal text.
  - Markers in keepsakes text expand only into the Worker's own values: the
    base, the place, and the fixed-shape preview markup (probed again, with
    a hostile door record and a pass).
  - Images are served only for `ASSET_PATH`, from `asset:` keys.
  - The extra `door` read on each asleep JSON answer is as the last entry
    traced it: the accepted daily-quota risk, reached sooner.

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 3 items: a dreamer name, its look and a
    username, with no typed lines (the operator's own, per the instance
    notes).
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username, unchanged since the last scan.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- Re-run for the post-fix pass: both unchanged (prod 3 items, dev 63),
  nothing flagged, no bursts, the same high-water marks. Verdict: nobody
  steering.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- These hold none of a key, a token, a private-key block, an account id, an
  email, a box or tailnet address, a home path, the operator's name, a
  friend's name or an invite slug:
  - the four files as they stand, and the last three commits of each
    (`git log -p --follow -3`);
  - the range `968da2b..97a1f4e` (every text file) and its two commit
    messages, the unpushed `97a1f4e` included;
  - the post-fix diff of the two files and of `docs/runbooks/verify.md`'s
    CI row.
- One removed line in that history (`5a40e58`, in `worker.js`) names the
  instance's domain: that commit took it out of a comment. The domain is
  committed by design in `edge/wrangler.toml` (CLAUDE.md), so this is not a
  leak.
- The fixtures are fake: `example.com` hosts, GitHub repositories named
  `x/y`, `me/daydream` and `stranger/daydream`, the documented example slug
  `amber-thimble`, and the operator's public title.
- `instance/` is still ignored.

### Coverage

- All dimensions were reviewed for the four paths, read in full and as
  their diff from `968da2b`.
- Tests ran: the Worker's suite (48 passed) and `tests/test_ci.py` (11
  passed).
- Probes, all deterministic and local:
  - a Python harness over `ci.main_status` with fake GitHub replies: paging
    honored, fork floods of 19, 20 and 40 runs, odd ref replies, a tip with
    only a fork's run, a red tip behind a stale green list, and an
    unreadable tip;
  - a Node harness over the Worker's `watch` with a throwing `uptime` read,
    and over the asleep page with a hostile door record and markers in a
    pass's keepsakes.
- No `gh` call reached GitHub, and nothing else used the network beyond the
  two text scans.
- Read in context, outside scope: `prodcheck.check_ci` and its call,
  `prod plan`'s CI line, `bin/game status`'s CI line, the conftest fixture
  that keeps the suite off GitHub, the CI workflow's triggers (`push` to
  main and `pull_request`; no `pull_request_target`, no schedule), and the
  asleep template.
- No dependency manifest is in scope.
- Outside the named paths, the range also changes `docs/runbooks/verify.md`,
  `CODEREVIEW.md` and `SECURITY.md`. They were pattern-scanned for secrets
  and instance facts only.
- Git history checked for secrets: `edge/src/worker.js` (the Access service
  token, by binding, and session cookies, hashed), `daydream/ci.py` (the
  operator's `gh` credentials, which the module never reads), and the two
  test files.
- Post-fix pass: `daydream/ci.py` and `tests/test_ci.py` re-read in full
  with `/codefix`'s diff, all dimensions. `tests/test_ci.py`: 11 passed. The
  `main_status` harness ran again over the fixed code, with GitHub's paging
  honored: unreadable tips under a stale green, a red, a run over a red or
  a green and a cancelled run; seven odd ref replies; fork floods of 19, 20
  and 40; a partial flood with the tip readable and unreadable. Every case
  read as expected except the open fork-flood NOTE's two. No `gh` call
  reached GitHub (the suite's conftest blanks `ci._gh`). The diff's
  `docs/runbooks/verify.md` row (a doc, outside scope) was read and
  pattern-scanned for secrets and instance facts only. Git history of
  both files re-checked with `git log -p --follow -3`; HEAD is unchanged,
  and the fix is uncommitted.

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
*Prior review (2026-10-03, paths, commit `968da2b`, with a post-fix pass over the fix later committed as `7efca17`): fifteen paths over `62d77ef` and `968da2b`, the asleep page's link preview (the door's words, card and icons synced to KV, and a 200 for a link-preview fetcher once a preview is synced). No new finding in the range; the post-fix re-read of the Worker found the uptime watch NOTE. The register stood at 0 BLOCK / 0 WARN / 10 NOTE. The full entry is at `git show 7efca17:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-03","commit":"97a1f4e26bc3a08d32527bb73513d20b1b796010","scope":"paths","scanned_files":["daydream/ci.py","edge/src/worker.js","edge/test/preview.test.js","tests/test_ci.py"],"block":0,"warn":0,"note":10} -->
