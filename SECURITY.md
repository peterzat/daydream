# SECURITY.md

## Security Review — 2026-10-01 (scope: paths)

**Summary:** Path-scoped review of the 16 paths the caller named, read in
full and as their change from the last scan (`2a8d93b`) to HEAD `d03a48a`.
Two unpushed commits touch them:
- `113b1df`: `prod status` leads its edge line with what friends see (the
  Worker's public status), then the flag; a timer job with no run since
  boot reads "not run since boot".
- `d03a48a`: the door carries Open Graph and Twitter tags filled by the
  server, a 1200x630 link card and two icons (made by the new
  `tools/make_link_card.py`), and a new `card_image` instance word.

No new finding. Every value the new tags carry is escaped and comes from
instance.json or the environment, never the request; the invite preview is
the same page for any slug; the new images carry no metadata. Register:
0 BLOCK / 0 WARN / 9 NOTE, all carried; their files are unchanged.

### Findings

No new security issues identified in the reviewed paths.

Carried from the last entry (still open; none of their files changed since `2a8d93b`):

[NOTE] daydream/llm/safety.py:57-59 (with daydream/api/slots.py:201, daydream/growth.py:286 and :364-381, and node "4" of daydream/images/workflows/painterly_room.json and painterly_portrait.json) — The content banlist is per word, and the two paths that put a friend's words into SDXL (a dreamer's portrait and a grown room's painting) have nothing else between them and a synonym. Unchanged since the last entry, which narrowed it.
  Attack vector: An invited friend makes a dreamer whose look is "a bare-breasted bather" or "a sexy dreamer in lingerie". `_toon_request` (slots.py:164-203) passes it, and the portrait shows on the dreamer's card to everyone in the room and stays in the art keep. On the growth path, "a sleeper in her nakedness" passes the gate (growth.py:550), and if the gardener keeps the word, `art_seed` weights it at 1.4.
  Evidence: the last entry's deterministic calls. `first_banned` returns None for sex, sexy, porn, nakedness, nudist, undressing, disrobed, bare-breasted, breasts and lingerie (and for blood, severed, decapitated and entrails). Node 4 of both workflows names style terms only. Mitigations: accounts are invited, and a player makes at most six dreamers a day.
  Confidence: high that these words reach the prompt. How explicitly SDXL draws them is unmeasured.
  Remediation:
  - Add content terms to node 4 of both workflows (nsfw, nudity, nude, naked, sexual, lingerie, gore, blood, corpse). It changes every cache key, so batch it with the next workflow change.
  - Extend the sexual category with whole words safe in this world. Avoid stems that catch village words ("nudge", "sextant", "sexton", "chimney breast").
  - In `art_seed`, weight only runs of two or more consecutive phrase words, and strip `()[]:` from the `room_seed` part.

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt. The guard reads code only for literal spellings, so a computed argv or path gets neither a prompt nor a decision. Narrower rules (`.venv/bin/python -m pytest *`) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). The template's allow list is unchanged.

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list. `cat .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`.

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling. Since `d09493d` the client pauses for a minute after a timeout, a network error, a 429 or a 5xx. That caps what an outage costs in time, not what a busy player spends. The parser change of `b2b112d` sends more lines to residents (`<name>, <words>`), and so, with a key set, to Jev. Remediation: a daily ceiling from the ledger, past which `enabled()` reads off.

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision. The code is unchanged and was not re-measured this run. A time limit inside `main`, or a single-pass brace expansion, would close it.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". `ci.py` is outside this scope and unchanged; `prodcheck.check_ci` is unchanged (`113b1df` touched only `check_timer`'s message).

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The `read` reply on written prose (`glimpse.py:471`) names a noun from the same prose. The server accepts control characters in typed lines and appearance seeds. `play.py` is unchanged.

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). Outside this scope; unchanged.

### Traced and cleared this run (not findings)

- **The door's new tags** (`server.py:217-247`, `door.html:13-25`,
  `index.html:8-9`). Every marker is replaced with `html_escape(...,
  quote=True)`. The values come from instance.json (validated: a string,
  printable, at most 200 characters; `card_image` only
  `assets/<name>.png|jpg`) or from `DAYDREAM_PUBLIC_ORIGIN` and
  `DAYDREAM_PUBLIC_BASE`, never from the request. Probes in scratch data
  dirs:
  - a Host and an X-Forwarded-Host of another domain appear nowhere in the
    page. Dev's og:image is base-absolute; prod's is the configured origin;
  - instance words carrying `"><script>` and a quote-breaking attribute
    come out escaped in every tag.
- **Invite slugs.** `invite_page` never reads its slug. Six hostile slugs
  (markup, template markers, 5,000 characters, percent-encoded text) and a
  plain one return a byte-identical 3,920-byte page; one with an encoded
  slash 404s at routing (and the Worker refuses `%2f` before that). The
  preview reads "An invitation to" the instance's title for any slug, so it
  is no oracle for a good slug and names no one. Peek, which does name the
  invitee, still runs only from door.js's POST. An unfurler that ran script
  would reach it with or without these tags, and a page with an og:image is
  less likely to be previewed by screenshot.
- **Marker order.** `_page` replaces markers in sequence, so a marker
  inside an earlier value expands (a lede that says `{{card_url}}` renders
  the card's URL). The values are the operator's instance.json, and the
  output is still escaped.
- **The new images.** The card JPEG holds a JFIF header and no EXIF,
  comment, ICC profile or trailing bytes. Both icons hold only IHDR, IDAT
  and IEND. They show the door painting, already public, and the
  "daydream" wordmark, and they are public under `/assets/` like it. The
  door painting itself (unchanged, outside scope) carries a ComfyUI
  `prompt` text chunk: the committed workflow's model names and prompt, no
  paths or names.
- **Icons and referrers.** The icon links are same-origin in prod (the
  Worker 301s every other host to `PUBLIC_HOST`), so CSP `img-src 'self'`
  holds. `Referrer-Policy: same-origin` keeps an invite path's referrer on
  the origin that already serves it, as style.css and door.js did before.
- **The card fallback** (`instance.py:81-82`). An instance with a door and
  no card previews with its door. A `.webp` door passes into `card_image`
  outside the card's own shape (png or jpg). It is still an `assets/` name:
  a preview quirk, not a security issue.
- **The edge line** (`edge.describe_public`, `prodctl.edge_line`). It
  prints the Worker's public `/edge/status` JSON to the operator's
  terminal. Its `note` comes only from the operator's KV flag, and
  `describe_state` and `edge status` already printed it. One robustness
  gap, not a security issue: a truncated body raises
  `http.client.IncompleteRead` from `public_status()` (probed on loopback),
  which neither `public_status` nor `edge_line` catches, so `prod status`
  would end in a traceback. A codereview item.
- `tools/make_link_card.py` reads the operator's own painting and writes
  local files; nothing it handles is player input. `prodcheck.check_timer`
  changes a message only.

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 3 items: a dreamer name, its look and a
    username, with no typed lines (the operator's own, per the instance
    notes).
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username. They are the agents' probe dreamers and the operator's dev
    username, unchanged since the last scan.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- These hold none of a key, a token, a private-key block, an account id,
  an email, a box or tailnet address, a home path, the operator's name or
  the instance domain:
  - the last three commits of each scoped module
    (`git log -p --follow -3`);
  - the unpushed range `origin/main..d03a48a` (two commits, every text
    file) and both commit messages. Its added lines use `example.com` only.
- The test fixtures are fake: the token and account id in
  `test_edge_ctl.py`, the password in `test_prodctl.py`, the SSH keys
  whose comment is the box's username (`test_prodctl.py:229-232`, since
  `6f15505`; the username already appears in the accepted risks below),
  and RFC 5737 documentation addresses in `test_auth.py`.
- `instance/` is still ignored.

### Coverage

- All dimensions were reviewed for the 16 paths.
  - Read in full: `daydream/edge.py`, `instance.py`, `prodcheck.py`,
    `prodctl.py`, `server.py`, `tools/make_link_card.py`, `web/door.html`
    and `web/index.html`.
  - The three images were inspected byte by byte and by eye.
  - The five test files were read as their diffs and pattern-scanned in
    full for secrets, PII and addresses. They ran: 122 passed.
- Read in context, outside scope: `config.public_origin`, `public_base`
  and `boot_problems`; `api/headers.py` (CSP, referrer policy);
  `api/nocache.py`; `api/gate.py` (the public allowlist); the invite peek
  endpoint; `web/assets/door.js` (peek on load); `edge/src/worker.js`
  (host redirect, status body, response rewrite).
- No dependency manifest is in scope. Pillow, imported by the new tool and
  the new test, is a dev and test dependency; the tool decodes only the
  operator's painting.
- Every probe was deterministic and local: TestClient in scratch data
  dirs, a loopback socket and Pillow over the committed assets. No model
  call, no render, and nothing written outside the scratchpad except this
  file and the local instance notes.
- Outside the named paths, the range also changes `docs/INSTANCES.md`,
  `docs/runbooks/sleep-and-wake.md`, `CODEREVIEW.md` and `SECURITY.md`.
  They were pattern-scanned for secrets and instance facts only.
- Git history checked for secrets: `daydream/edge.py` and
  `daydream/prodctl.py` (they handle the Cloudflare token, the CLI's
  cookie and the age recipients) and the other four modules, as above.

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
*Prior review (2026-10-01, paths, commit `2a8d93b`): five paths over three commits after `d57fbe3`: teardown's scrub of every file it lands (resolving that entry's playthrough NOTE), screenshots re-encoded at 960 px with `playthrough purge`, and nudity words in the content banlist. No BLOCK or WARN. The art NOTE was narrowed: synonyms still reach SDXL on two paths, and the workflows' negative prompts name no content. The register stood at 0 BLOCK / 0 WARN / 9 NOTE. The full entry is at `git show 9339e60:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-01","commit":"d03a48ab7a905eb4e189d09eb64a214566266317","scope":"paths","scanned_files":["daydream/edge.py","daydream/instance.py","daydream/prodcheck.py","daydream/prodctl.py","daydream/server.py","tests/test_auth.py","tests/test_edge_ctl.py","tests/test_instances.py","tests/test_prodcheck.py","tests/test_prodctl.py","tools/make_link_card.py","web/assets/card-village.jpg","web/assets/icon-180.png","web/assets/icon-32.png","web/door.html","web/index.html"],"block":0,"warn":0,"note":9} -->
