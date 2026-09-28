# SECURITY.md

## Security Review — 2026-09-28 (scope: paths)

**Summary:** Path-scoped review of 21 files: the code, tests and world
sources changed between the last scan (`f8d26c7`) and HEAD `4cef786`. That
covers the codereview fix pass (`18bcbd0`) and the second playtest's fixes
and lines (`8ff847b`, `94121c5`). No vulnerability found, and the prior WARN
is fixed: `account delete` now removes the rows addressed only to the
person's dreamers. One new NOTE records a narrow gap in that fix: a reply
that is still being generated when the account is deleted gets written
after the purge. The prior NOTE is carried (0 BLOCK / 0 WARN / 2 NOTE).

### Scope and method

Each scoped file's diff from `f8d26c7` to HEAD was read in full, along with
the code it calls:

- **Account delete.** `events.forget_private` and its caller in
  `_delete_account`, the connection's autocommit mode, and the broadcast
  and replay rules that decide who ever sees a row with a recipient.
- **The went-home note.** It is now a private narrate appended after the
  first snapshot. Checked where its text comes from
  (`toons.send_home_things`, `take_went_home`) and where the page renders
  it (the narrate path).
- **The `threads` frame.** `story.threads_for`, the `carried_filter`
  condition the new thread uses, and the per-frame checks that run before
  the frame is sent.
- **Dream threads.** A dream patch's threads are now installed
  (`dream.apply_patch`). Checked their validation (`check_patch`).
- **The parser.** The quantified AND-list branch (`_expand_multi`).
- **Page sinks.** Every changed one: the own-echo insertion, `setThreads`
  and `renderThreads`, the `linkifyEntities` regex, and the margin index
  reset.
- **World sources.** The Pim thread split, the gear seed and Tock's
  greeting (authored text only).

The prior WARN's fix was checked two ways: with its new test, and with a
scratch repro outside the repo that also covered a reply still being
generated. Secrets were checked without printing any value:

- The outgoing range (`origin/main..HEAD`) and every commit message since
  `f8d26c7` were compared against the instance's credentials, ids,
  addresses and names.
- Every two-word phrase was hashed and compared against the stored invite
  slugs.
- The last three commits of each of the four credential-handling files in
  scope were scanned.

The 286 tests in the 9 scoped test files pass.

### Findings

[NOTE] daydream/accounts_cli.py:129-136 — `account delete --yes` can leave a
few records behind if the person is talking to a resident at that moment.
It purges the dreamer's private rows and story records, but a reply that is
still being generated gets written after the purge.
  Attack vector: Not an exploit. It happens only if the operator deletes
someone while they are talking to a resident.
  - In prod, the delete runs while the service is up: `account delete` is
    not in `prodctl.STOP_FOR` (daydream/prodctl.py:211-213).
  - `dialogue.talk` waits several seconds for the model (daydream/dialogue.py:426:
    a 15 s timeout per call, plus any wait for the GPU).
  - When the reply comes back, it is appended addressed to the dreamer
    (:482), and the exchange is stored under `talk:<npc>:<toon>` (:488).
    Nothing checks first that the dreamer still exists.
  - The account's session stays valid until the last step (:136), so a
    frame that arrives meanwhile is still accepted. Untested: in that
    window the same session could also create a new dreamer, which the
    delete would miss.
  Evidence: Reproduced with a scratch test (not committed). It holds the
model call open, runs `_delete_account(..., confirmed=True)`, then lets
the reply finish.
  - Control (delete after the talk ends): nothing is left.
  - Delete during the model call: one reply row addressed to the deleted
    dreamer is left, and so are `rel:`, `relday:` and `talk:t-hob:<toon>`,
    all written after the purge. The `talk:` record holds the player's
    words verbatim.
  No player can read these rows: they are keyed to a toon id that no one
holds. The DB and later backups still keep them, though, which falls
short of what docs/DATA-LIFECYCLE.md promises.
  Remediation: Two options.
  - Simplest: have `prodctl` stop the service around
    `account delete --yes`, as it does for the other verbs that change
    prod data. Add the verb to `STOP_FOR`, gated on `--yes` the way
    `NEEDS_YES` gates the destructive world verbs.
  - In code: revoke the account's sessions before touching its dreamers.
    Then have `dialogue.talk` return without writing if
    `objects.get(actor.id)` is gone after the model call.

  Either way, turn the scratch repro into a test in
tests/test_account_delete.py.

[NOTE] tests/test_config_edge.py:61 (outside these paths; carried unchanged)
— The non-loopback bind-host test still uses this box's real tailnet IPv4.
  Attack vector: Minimal. The address is in Tailscale's CGNAT range and
reachable only inside the operator's tailnet. It has been public since
`5f2bd3d`.
  Evidence: It still matches `tailscale ip -4` exactly (the value is not
reproduced here). This range does not touch the file.
  Remediation: Swap in `100.64.0.1` the next time the file is touched. A
history rewrite is not warranted.

### Closed since the last review

- **Account delete kept what a player said to residents (prior WARN).**
  Fixed in `18bcbd0`:
  - `events.forget_private` (daydream/events.py:191-197) deletes every row
    addressed to the dreamer. `_delete_account` calls it for each dreamer
    (daydream/accounts_cli.py:132).
  - The connection is autocommit (`isolation_level=None`,
    daydream/db.py:20), so the delete takes effect at once.
  - A row with a recipient reaches only that recipient. The broadcast loop
    drops it for everyone else, including the player who caused it
    (daydream/api/ws.py:1181-1183), and replay filters the same way. So
    the delete removes only lines no one else saw, and the shared history
    stays.
  - `seq` is AUTOINCREMENT, so no sequence number is reused. The SQL is
    parameterized.

  The new test covers the fix, and so did the control case in the repro.
  The remaining gap is the first NOTE above.

### Traced and cleared this run (not findings)

- **The went-home note** (daydream/api/ws.py:973-977).
  - It is a narrate addressed to the dreamer, appended after the first
    snapshot.
  - Its text holds a thing's name and a room title, both written by the
    server (`toons.send_home_things`).
  - The page renders it through `linkifyEntities`, which escapes first.
  - `take_went_home` keeps only entries that have a name. If sending the
    first snapshot fails, the note stays unread for the next connection.
  - The note has a recipient, so it goes with the account.
- **The `threads` frame** (daydream/api/ws.py:1125-1132).
  - It is sent only for the connection's own dreamer, and only after the
    incoming frame passes the session check, the ownership check and the
    rate limit.
  - `threads_for` evaluates authored conditions for that dreamer. The new
    `carried_filter` thread looks only at what the player is carrying
    (daydream/rules.py:254-261).
  - The page renders threads with `textContent`.
  - The work per frame is bounded by the number of authored threads and
    by the 3-frames-per-second limit.
- **Dream threads.**
  - `apply_patch` now installs them like rules and storylets.
  - The operator directs every patch, and `check_patch` validates it.
  - A callback thread gated on `{"actor": <toon id>}` shows only to that
    player.
  - The dream runbook keeps the raw digest out of the public repo and
    treats it as untrusted.
- **Parser.**
  - The quantified AND-list branch only strips the quantifier and passes
    the text to the existing AND-list path. A player could already reach
    that path by typing the list without "both".
  - Every expanded command still passes the executor's scope gate.
  - The regexes (`_AND_SPLIT`, `_GROUP`) are unchanged. At worst they are
    quadratic within the 500-character limit.
- **Page sinks.**
  - The own-echo branch inserts a line that was already built with
    `escape()` or `textContent`. It matches on `actor_id` and
    `recipient_id`, which the server sets.
  - The new `linkifyEntities` lookbehind only narrows matches.
    - It still runs over escaped text, and the replacement escapes the id.
    - An alias can match inside an escape sequence (`amp` in `&amp;`) and
      split it. The result is a visible glitch, never markup, the same as
      with the old `\b`.
  - The margin index reset clears with `innerHTML = ""`, and its tabs use
    `textContent`.
  - `index.html` adds help text only: no script, no handler and no URL.
- **Nothing new at the edges.**
  - No new route and no new frame kind from the client.
  - No new dependency: `pyproject.toml` adds only lint settings.
  - No log line with content. The delete's printed summary carries counts
    only.
- **World sources.** The Pim threads, the gear seed and Tock's greeting
  are authored text, rendered through the existing escaped sinks.
  WORLD_VERSION 1.7 is a MINOR bump with no schema change.

### Secrets, PII and the instance

- **Credentials.** The values in `~/.config/daydream/` were compared
  without printing. They appear in no added line and no message from
  `f8d26c7` to HEAD. They also appear in none of the last three commits
  of `accounts_cli.py`, `ws.py`, `test_root_helper.py` or
  `test_account_delete.py`. No token-shaped value appears: the long
  strings are commit SHAs and test names.
- **Instance values.** These were compared without printing:
  - the ids and addresses in `instance/NOTES.md`
  - the box's public addresses
  - every username, display name and invitee name in the prod accounts
    DBs

  There were only two hits, both in SECURITY.md's carried text:
  `127.0.0.1`, and `peter` as the Unix account in the accepted risks. No
  two-word phrase in the range hashes to a stored invite slug.
  `instance/` is still gitignored.
- **Names.** Test fixtures use fictional names. The playtest doc's "Hazel"
  (outside these paths) is an agent persona: it appears only in the dev
  accounts DB, and in no prod accounts DB or backup.

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
- A shell rest does not reach an open socket; `account disable` is the
  stop.
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one. A PreToolUse hook would be firmer.
- Player text reaches the agent's context through `bin/game play`: names,
  speech and move lines. The verbs an injected instruction would want stay
  behind ask rules.

---
*Prior review (2026-09-28, paths, commit `f8d26c7`): 30 files covering the
first friend's playtest fix pass. It found 0 BLOCK / 1 WARN / 1 NOTE. The
WARN (account delete kept a player's private lines) was fixed in `18bcbd0`
and is closed above. The NOTE is carried. Full entry at
`git show 63e15c3:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"4cef78698ac0731c329de0859e047e2ee78e661c","scope":"paths","scanned_files":["daydream/accounts_cli.py","daydream/api/ws.py","daydream/dream.py","daydream/events.py","daydream/parser.py","daydream/version.py","pyproject.toml","tests/test_account_delete.py","tests/test_browser_flow.py","tests/test_browser_playtest.py","tests/test_dozing.py","tests/test_dream.py","tests/test_linkify.py","tests/test_parser.py","tests/test_root_helper.py","tests/test_ws.py","web/assets/main.js","web/index.html","worlds/lost-hours/arcs/01-pim.json","worlds/lost-hours/regions/02-square.json","worlds/lost-hours/regions/10-residents.json"],"block":0,"warn":0,"note":2} -->
