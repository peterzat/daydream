# SECURITY.md

## Security Review — 2026-09-28 (scope: paths)

**Summary:** Path-scoped review of the 30 files in scope: the first friend's
playtest fix pass (`2b67900..f8d26c7`, 20 unpushed commits) plus `44d8690`,
measured from `600b1d5` (the tree the last review scanned, before its commit
was reworded). No code vulnerability found. One WARN: the new talk echo
writes what a player says to a resident into the event log as a private row
that `account delete` leaves behind, which breaks the deletion promise in
docs/DATA-LIFECYCLE.md. The prior NOTE (a tailnet address in a test outside
these paths) is still open, and the prior WARN is closed
(0 BLOCK / 1 WARN / 1 NOTE).

### Scope and method

Each scoped file's diff from `600b1d5` to HEAD `f8d26c7` was read in full,
along with the code it touches or calls:

- The WebSocket layer:
  - the broadcast loop's private-event filter, and the replay
    (`events.fetch_since(recipient_for=)`)
  - the new snapshot fields: `arrival_seq`, `threads`, `went_home` and
    `at`; toon `away` and `asked_topics`; object `keeps` and `detail`
  - "what now" and "help"
  - the greeting suppression's `fetch_since`
- The new event rows: the talk echo (`say` with a recipient), the ask echo
  (`echo`), the dozing note, and the echo guard's fallback. Also
  `effects._apply_narrate`'s `card`, traced back to `_sanitize_llm_effect`.
- The parser's trailing-phrase and group forms (`_TRAILING_PHRASE`,
  `_GROUP`, `_expand_group`, `_all_candidates`), timed against worst-case
  500-character inputs.
- The journal's wider window, story markers, time of day and pronouns
  (`fetch_for_toon`, `_event_lines`, `_user_prompt`).
- Threads: `story.threads_for`, the validator, dream patches, and the
  per-player `asked:` state.
- Things that go home: `home_of`, `send_home_things`, `take_went_home`.
- Every new or changed SPA sink:
  - the card renderer and `linkifyEntities`' person rule
  - the echo, chatter and went-home lines
  - the portrait inset and panel, and the takeover overlay
  - the scroll rail, the margin index and the threads list
  - keepsake tags
  - the attribute selectors built from object ids

Every `innerHTML` in main.js was swept, and the scoped Python diffs were
swept for SQL, subprocess and file sinks. The outgoing range
(`origin/main..HEAD`, every file and message) and the last three commits of
ws.py and journal.py were scanned for secrets and instance values. The 135
tests in the 8 scoped test files pass. The WARN was reproduced against a
temp data dir.

### Findings

[WARN] daydream/verbs.py:1470-1472 — Every line a player says to a resident
is now also written to the event log as a private `say` row, with the
speaker as both actor and recipient. `account delete` does not remove it.
  Attack vector: Not an exploit. The change breaks a privacy promise.
docs/DATA-LIFECYCLE.md (lines 104-110) says `account delete` removes "what
they said to each resident", and keeps only "the shared event history
(what others saw happen in the village)". These rows are addressed to the
speaker alone, so no one else ever saw them. Yet `_delete_account`
(daydream/accounts_cli.py:106) and `_forget_dreamer_state` (:139) never
touch `events`. The dialogue prompt is built to take in what a player says
about themself, so these rows can hold personal details. After a friend
asks to be forgotten, their words stay in the live DB. Every later backup,
local and offsite, copies them again, so they never age out.
  - No player can read them: the recipient toon is deleted, and a new toon
    gets a fresh random id.
  - Anyone with the DB or a backup can: the operator, and any tool that
    reads `events`.
  Evidence: `_handle_talk` appends `{"text": args.strip(), ...}` with
`recipient_id=actor.id` before any dialogue runs (verbs.py:1470-1472, added
in `8fa034f`). The repro: a player spoke a line to Hob in the story
fixture, then `_delete_account(..., confirmed=True)` ran. The dreamer's
`talk:` and other story records were deleted, but the `say` row holding the
words remained. A smaller form of the same gap predates this range:
  - The private chatter line quotes an unparsed typed line (ws.py:788,
    since `283aa22`).
  - Parser messages and model replies addressed to the player can carry
    fragments of what they typed.
  Remediation: When `account delete` removes a dreamer, delete or blank the
text of the event rows addressed only to it (`recipient_id = <toon id>`).
No one else saw those rows, so the shared history is unchanged. `seq` is
AUTOINCREMENT (migrations/001_initial.sql:89), so a deletion cannot free a
sequence number for reuse. Add a case to tests/test_account_delete.py:
talk to a resident, delete the account, and assert the words are gone.
Then add private lines to DATA-LIFECYCLE.md's list of what goes.

[NOTE] tests/test_config_edge.py:61 (outside these paths; carried unchanged
from the prior review) — The non-loopback bind-host test still uses this
box's real tailnet IPv4.
  Attack vector: Minimal. The address is in Tailscale's CGNAT range and
reachable only inside the operator's tailnet. It has been public since
`5f2bd3d`.
  Evidence: Still an exact match for `tailscale ip -4` (the value is not
reproduced here).
  Remediation: Swap in `100.64.0.1` the next time the file is touched. A
history rewrite is not warranted.

### Closed since the last review

- **The deleted test account's username in a commit message (prior
  WARN).** Reworded before the push (the commit is now `4a59178`). No
  message on `origin/main` and no tracked file at HEAD contains it.

### Traced and cleared this run (not findings)

- **New private rows stay private.**
  - These are all addressed to the actor: the ask echo, the talk echo, the
    dozing note, "what now", "help", the echo guard's fallback and the
    went-home note.
  - The broadcast loop drops any row addressed to someone else, whatever
    its kind, and every replay passes `recipient_for`.
  - `threads`, `went_home` and the journal ride only the controlled toon's
    snapshot. `asked_topics` is computed per viewer.
  - `take_went_home` and `send_home_things` write through
    `objects.set_property`, which emits no event.
- **Cards.** `_apply_narrate` keeps a card only when every value is a
  string, and it copies only four keys. `_sanitize_llm_effect` reduces an
  LLM-originated narrate to `text` and `to` before dispatch. So a card can
  come only from engine verbs, authored rules and dream patches. The page
  renders the card's label with `textContent`, and its body through
  `linkifyEntities`, which escapes first.
- **SPA sinks.**
  - Every new line uses `textContent` or `escape()`.
  - The person rule in `linkifyEntities` returns a slice of text that is
    already escaped.
  - Portrait URLs come from the server, go through `assetUrl`, and sit
    behind the sign-in gate.
  - The attribute selectors built from object ids take only ids the
    server mints (`o-` or `t-slot<n>-` plus hex) or the author writes. A
    card's `object_id` is the examined object's own id.
- **Parser.**
  - `_TRAILING_PHRASE` is quadratic at worst: about 10 ms for 500
    characters of whitespace. The frame cap (500 characters) and the
    per-connection rate (3 frames/s) bound it.
  - The group form runs only for take, drop and put. It draws on
    `_all_candidates`, which excludes another player's private finds.
  - Each expanded command still passes the executor's scope gate.
  - A "don't see any X" reply echoes the player's own noun back to them
    alone.
- **Dozing.** `away` and the dozing note tell players in the same room
  whether another player's page is open. They could already see that
  player's presence, and they get only a boolean: the session id stays on
  the server.
- **Journal.**
  - The window is wider (150 events, 48 lines of 260 characters) and now
    includes the player's own echoes.
  - Output validation is unchanged: refusal parse, 60 to 500 characters,
    and the banlist.
  - An entry is shown only to its owner.
  - Another player's words reach a journal only through rows addressed to
    its owner, as before.
- **Threads and dreams.**
  - Threads are authored and checked by `validate_story`. Dream patches
    pass `validate_envelope2`.
  - Per-player `asked:` state lives under `pq:<toon>:`, which
    `account delete` already forgets. It holds at most 200 entries per
    resident.
- **Takeover.** "Dream here instead" reconnects through the same account's
  session. The server still decides ownership (`_auto_enter`).
- **Nothing new at the edges.**
  - The outgoing range adds no routes and no dependencies.
  - `index.html` adds no inline script or handler.
  - The CSS adds no external URL.

### Secrets, PII and the instance

- **Credentials.** The values in `~/.config/daydream/` were compared
  without printing. They appear in:
  - no outgoing commit or message
  - none of the last three commits of ws.py and journal.py

  No token-shaped value, invite link or cookie value appears either.
- **Instance values.** None of these appears in the outgoing diff or its
  messages:
  - the zone id, the Zero Trust team, the AUD tag and the tunnel id
  - the invite ids and the box's public addresses
  - the deleted test account and the operator's name

  The KV id and the origin hostname appear only in their deliberately
  committed places.
- **Names.** Test fixtures and the playtest doc use fictional dreamer
  names. Of the names in the dev accounts DB, only the playtest's fictional
  dreamer appears. `instance/` is still gitignored.

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
*Prior review (2026-09-28, paths, commit `8c39d4a`, reworded to `600b1d5`):
37 files covering comings and goings, the dreamer panel and door note, Talk
on the input line, `prod plan`, and the codereview fix pass. It found
0 BLOCK / 1 WARN / 1 NOTE. The WARN (the deleted test account's username in
a commit message) was reworded before the push. The NOTE (a tailnet address
in an older test) is carried above. Full entry at
`git show b6c7644:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-28","commit":"f8d26c72a12781886e927a2a520d2b7026a8321c","scope":"paths","scanned_files":["daydream/api/ws.py","daydream/dialogue.py","daydream/dream.py","daydream/growth.py","daydream/journal.py","daydream/llm/story_format.py","daydream/parser.py","daydream/skills/effects.py","daydream/story.py","daydream/toons.py","daydream/verbs.py","daydream/version.py","daydream/walkthrough.py","tests/test_arrival.py","tests/test_browser_playtest.py","tests/test_dialogue.py","tests/test_dozing.py","tests/test_journal.py","tests/test_lost_hours_world.py","tests/test_parser.py","tests/test_story.py","tools/assemble_world.py","web/assets/main.js","web/assets/style.css","web/index.html","worlds/lost-hours/arcs/00-prologue.json","worlds/lost-hours/arcs/02-extra-hour.json","worlds/lost-hours/arcs/07-letters.json","worlds/lost-hours/regions/03-lane.json","worlds/lost-hours/world.json"],"block":0,"warn":1,"note":1} -->
