# SECURITY.md

## Security Review — 2026-10-03 (scope: paths)

**Summary:** Path-scoped review of the 15 paths the caller named, read in
full and as their change from the last scan (`d03a48a`) to HEAD `968da2b`.
Two commits touch them:
- `62d77ef`: the last review's fixes. `public_status()` also catches
  `http.client.HTTPException`, which closes the truncated-read traceback the
  last scan noted, and the card follows only a png/jpg door.
- `968da2b` (unpushed): a link shared while the village sleeps unfurls like
  the door. The keepsakes sync carries the door's preview words, card and
  icons to KV (`door`, `asset:<path>`). While asleep, the Worker puts the
  same tags on its page, serves the card and icons from KV, and answers a
  link-preview user agent with a 200 instead of the 503. `prod check` gains
  a "link preview" check.

No new finding. The tags are escaped. The images are the release's public
assets, named by a validated path. The 200 changes only the status. A
hostile export gains nothing the service user does not already have while
awake. Register: 0 BLOCK / 0 WARN / 9 NOTE, all carried; their files are
unchanged.

**Post-fix re-check** (`edge/src/worker.js`, `edge/test/preview.test.js`;
the uncommitted fix of CODEREVIEW's WARN). The Worker now reads the door
preview before it decides, and a link-preview fetcher gets the 200 only when
a preview is synced. With nothing synced, or a malformed record, it gets the
503 as before, and the test now asserts that status. The fix adds no
finding. It adds one KV read to the asleep JSON answers (see "KV reads while
asleep"). Re-reading the whole Worker found one older issue, a NOTE: the
uptime watch erases its outage history when a read of it fails (`watch`,
shaped in `03a5b08`). Register: 0 BLOCK / 0 WARN / 10 NOTE.

### Findings

No new security issue in the range's changes or in the post-fix change. The
post-fix re-read of the whole Worker found one older issue:

[NOTE] edge/src/worker.js:45-54 and :85 (`watch`) — A failed read of the `uptime` record is taken as an empty record and written back. The recorded outages are erased, and while reads keep failing no unplanned outage can open. It predates this range (the record's shape is from `03a5b08`, 2026-09-28).
  Attack vector: An anonymous client floods the asleep pages (two to four KV reads a request) until the Workers Free plan's 100,000 daily KV reads run out. Friends' tabs left on the asleep note get there too: about a dozen through a whole day of sleep since the fix (three reads per 30 s cycle), about seventeen before. Until the quota resets, each five-minute run (`*/5` cron) reads the flag as awake (`:45`, fail-open by design). The probe fails because the tunnel is down, the `uptime` read fails (`:46-51`), and the run writes `{suspect_since, outages: []}` (`:85`). The history is gone for good, and the "watch:" part of `prod status` (`daydream/edge.py:175-182`) reads "up; no unplanned outage recorded" through a real outage. One transient read error during an outage erases the history the same way.
  Evidence: a local probe of `watch` over a record holding two outages, in three stores: reads that throw (flag asleep), an `uptime` read that throws (origin down), and reads that return null. Every run returned "down"; the record kept 0 outages and never set `down_since`. Mitigation: `prod status` leads with the live public status, which still says the village does not answer.
  Confidence: high for the mechanism. How Cloudflare signals an exhausted read quota (an error or an empty read) is unverified. Both erase; skipping on a thrown read fixes only the first.
  Remediation: when the `uptime` read throws, skip the run and write nothing (return "unknown"), and reset only a value that parses badly. Optionally read the flag strictly in `watch`, so an unreadable flag skips the run instead of probing as awake. Add a throwing-`get` case to `edge/test/worker.test.js`.

Carried (still open; their files are outside this scope and unchanged since `d03a48a`):

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

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". (carried from the 2026-09-29 scan, not re-checked) Its prodcheck half is in this scope and was re-read: `check_ci` (prodcheck.py:227-234) and its call (:446) are unchanged; `968da2b` added only the link-preview check.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The `read` reply on written prose (`glimpse.py:471`) names a noun from the same prose. The server accepts control characters in typed lines and appearance seeds. (carried from the 2026-09-29 scan, not re-checked)

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`. (carried from the 2026-09-29 scan, not re-checked)

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). (carried from the 2026-09-28 scan, not re-checked)

### Traced and cleared this run (not findings)

- **The 200 for a link-preview fetcher** (`worker.js:319-328`, `:347-348`).
  It keys on the User-Agent, which anyone can send, but it changes only the
  status. The body is the page a person gets with a 503: `no-store`,
  `noindex`, the same CSP. API paths, `/cache/`, `/status/` and `/assets/`
  keep the 503 JSON. The keepsakes block appears only for a request that
  carries a live pass cookie. A server-side fetcher carries none, and the
  preview tags lead the page either way. Since the post-fix change it also
  needs a synced door preview. With none, an unparseable record, or one
  with no usable title (blank, a number, an array, a string), the fetcher
  gets the 503 for `*/*` and for `text/html` (probed). HEAD and POST keep
  the 503 JSON.
- **The preview tags** (`worker.js:388-429`). The KV words are trimmed to
  200 characters and escaped. Attribute names and link rels are constants.
  Each image URL is the configured host and base plus a path the record
  lists and `ASSET_PATH` matches. A probe with a hostile record (markup,
  quote breaks, a `javascript:` card, an unknown rel, traversal and
  upper-case paths) came out escaped or dropped. Markers inside the door's
  words are not expanded, since `{{PREVIEW}}` is filled last. An invite
  path previews as "An invitation to" the title and never echoes the slug.
  The same hostile record, re-probed through the post-fix gate, came out
  the same (the `stylesheet` link on the page is the template's own).
- **Markers inside player text** (`worker.js:334-346`). The asleep page
  fills its markers in sequence, so a keepsakes line or a dreamer's name
  that says `{{PREVIEW}}` expands into the Worker's own preview markup.
  A dreamer's name may be any 24 printable characters, and the chronicle
  can carry a planter's name. `{{BASE}}`, `{{PLACE}}` and `{{place}}`
  already expanded the same way. Every marker's value is escaped and fixed
  in shape, and player text sits in text context, so nothing a player
  writes becomes markup (probed). A single-pass fill would make the page
  exact. The operator's note sits in an attribute, and a note that says
  `{{PREVIEW}}` breaks that attribute harmlessly. Notes are operator-only.
- **Images served from the edge** (`worker.js:315-318`, `:362`,
  `:372-384`). Only `^/assets/[a-z0-9_-]+\.(?:png|jpg)$` on the normalized
  path qualifies (an encoded slash is refused before this), read from an
  `asset:`-prefixed key, so no other KV key is reachable. Responses are
  `image/png` or `image/jpeg` with `nosniff` and `no-store`. Query
  strings, dot segments, `%2e%2e`, case and `%0a` variants were probed.
  They are the same public files the origin serves under `/assets/`.
- **The sync's trust boundary** (`keepsakes.py:99-118`,
  `edge.py:258-293`). The export runs as the service user, and the
  operator pushes what it prints. `_door()` reads the release's read-only
  `web/` (no symlinks are committed there) by a validated instance path or
  the fixed icon paths, each at most 1 MiB. A hostile export could now also
  set the door's words and image bytes. The Worker escapes the words and
  serves the bytes only as images, and the same user already controls the
  whole door page while awake, so nothing escalates. The manifest removes
  `door` and `asset:` keys a later export leaves out. Two small edges, no
  security effect: `DOOR_ASSET` uses `$`, which admits a trailing newline,
  so a hostile export could write an `asset:` key the Worker never serves
  (`fullmatch` would tidy it); and a malformed `door` ends the sync with a
  traceback before any write.
- **KV reads while asleep.** An anonymous page render now reads two keys
  (`state`, `door`), and an image request one or two. A flood reaches the
  free plan's daily KV read quota at about half the requests it took
  before. On exhaustion every read fails soft: the flag reads awake, the
  origin probe still shows the asleep page, without its note, keepsakes or
  preview. This is the accepted daily-quota risk below, reached sooner.
  Post-fix, the JSON answers read `door` too: two keys, or three at a path
  shaped like an image the edge lacks. The most one anonymous request costs
  is unchanged at four (such a path as a page, with a session cookie). A
  friend's tab on the asleep note now costs three reads per 30 s cycle
  instead of two (the refused WebSocket, then the `api/me` probe), so the
  read quota now binds before the request quota for that traffic. Reading
  `door` only when the page renders or a fetcher could unfurl would keep
  the JSON answers at one read. On exhaustion every path still fails soft
  (probed: a 503, no exception, no note, no preview). The lasting effect is
  the `watch` NOTE above.
- **`prod check`'s link preview** (`prodcheck.py:108-127`, `:363-370`). It
  fetches the card only when `og:image` starts with the configured public
  root, follows no redirect, caps the body at 200 KB and sends no cookie.
  Not an SSRF.
- **The door page** (`server.py:217-249`, `door.html:13-25`). The new
  `{{card_alt}}` is escaped and built from instance.json's validated place.
  The preview words now come from one function (`instance.preview()`) and
  are unchanged in substance. The invite page still never reads its slug.
- **`62d77ef`** changes exception handling, the card fallback and a
  docstring: no security effect. `tools/make_link_card.py` reads the
  operator's painting and writes local files; nothing it handles is player
  input.

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 3 items: a dreamer name, its look and a
    username, with no typed lines (the operator's own, per the instance
    notes).
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username. They are the agents' probe dreamers and the operator's dev
    username, unchanged since the last scan.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- Re-run in the post-fix pass: prod `--since 0` (3 items) and dev
  `--since 548` (63 items), both unchanged, nothing flagged, no bursts.
  Verdict unchanged.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- These hold none of a key, a token, a private-key block, an account id,
  an email, a box or tailnet address, a home path, the operator's name, a
  friend's name, an invite slug or the instance domain:
  - the last three commits of each scoped module and template
    (`git log -p --follow -3`);
  - the unpushed range `origin/main..968da2b` (one commit, every text file)
    and its commit message. Its added lines use `example.com` only.
- The test fixtures are fake: `example.com` and `example.org` hosts, RFC
  5737 addresses in `test_auth.py`, placeholder invitee names, and the
  documented example slug `amber-thimble`.
- `edge/wrangler.toml`'s instance values are committed by design (CLAUDE.md)
  and unchanged in this range. `instance/` is still ignored.

### Coverage

- All dimensions were reviewed for the 15 paths.
  - Read in full: `daydream/edge.py`, `instance.py`, `keepsakes.py`,
    `prodcheck.py`, `server.py`, `edge/src/worker.js`, the asleep template,
    `web/door.html`, `tools/make_link_card.py` and
    `edge/test/preview.test.js`.
  - The five Python test files were read as their diffs and
    pattern-scanned in full for secrets, PII and addresses.
  - Tests ran: the Worker's suite (48 passed) and the five Python files
    (89 passed).
- Probes, all deterministic and local: a Node harness over the Worker's
  `handle` with hostile KV records, markers in keepsakes text and path
  variants; `edge.desired_keys` over malformed exports. No model call, no
  render, no network beyond the two text scans.
- Post-fix pass: `edge/src/worker.js` and `edge/test/preview.test.js` were
  re-read in full and as the uncommitted diff, and the Worker's suite ran
  (48 passed). A local harness compared HEAD's `handle` with the fixed one:
  - KV reads per request class;
  - nothing-synced and malformed records under both `accept` values;
  - HEAD, POST, `/api/`, `/cache/`, `/status/`, `/assets/` and an invite
    path with a door present;
  - every KV read throwing, and the hostile record.
  A second probe drove `watch` over failing reads. Both files' git history
  was re-checked (`git log -p --follow -3`). The diff adds no secret,
  address, name or instance fact.
- Read in context, outside scope: `config.WEB_DIR`, `public_origin` and
  `public_base`; `prodctl.run_release_python` and the read-only release
  build; `edge/wrangler.toml`; `asleep.js` (textContent only); the dreamer
  name check in `api/slots.py`.
- No dependency manifest is in scope; `edge/package*.json` is unchanged in
  the range.
- Outside the named paths, the range also changes `docs/GOING-LIVE.md`,
  `docs/INSTANCES.md`, `docs/runbooks/sleep-and-wake.md`,
  `docs/runbooks/verify.md`, `CODEREVIEW.md` and `SECURITY.md`. They were
  pattern-scanned for secrets and instance facts only.
- Git history checked for secrets: `daydream/edge.py` (the Cloudflare
  token), `daydream/keepsakes.py` (the pass list), `daydream/prodcheck.py`
  (the CLI's cookie), `edge/src/worker.js` (the Access service token, by
  binding), and the other scoped modules and templates, as above.

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
*Prior review (2026-10-01, paths, commit `d03a48a`): sixteen paths over two commits after `2a8d93b`: `prod status`'s edge line read from the Worker's public status with "not run since boot" for timer jobs, and the door's Open Graph tags with a link card, icons and the `card_image` instance word. No new finding; the register stood at 0 BLOCK / 0 WARN / 9 NOTE, all carried. The full entry is at `git show 114cd38:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-03","commit":"968da2b5ca90848daa4df44122fe93f73e265dc8","scope":"paths","scanned_files":["daydream/edge.py","daydream/instance.py","daydream/keepsakes.py","daydream/prodcheck.py","daydream/server.py","edge/public/daydream/_edge/asleep.html","edge/src/worker.js","edge/test/preview.test.js","tests/test_auth.py","tests/test_edge_ctl.py","tests/test_instances.py","tests/test_keepsakes.py","tests/test_prodcheck.py","tools/make_link_card.py","web/door.html"],"block":0,"warn":0,"note":10} -->
