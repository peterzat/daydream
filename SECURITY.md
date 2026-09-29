# SECURITY.md

## Security Review — 2026-09-29 (scope: paths)

**Summary:** Path-scoped review of 48 files: the code, tests and world
sources changed between the last scan (`4cef786`) and HEAD `43fba6b`. That
is the beta rehearsal's layer (letters and parcels through the post, handing
things between dreamers, who else is awake and where, traces of dreamers and
rosters, the while-you-were-away note, transient "thinking" frames, the
typed plant and a target on a no-target verb) and the dream
`dream-2026-09-28`, at WORLD_VERSION 1.9. No exploitable vulnerability. One
WARN: a player can file letters without limit, and every waiting letter is
loaded on every player's every command. Two new NOTEs: a parcel puts a
shared authored thing outside the rest-returns-things net and `account
delete` destroys it; the input log's metadata has a new audience (other
players) that the redeem card and the docs do not mention. The two prior
NOTEs are carried (0 BLOCK / 1 WARN / 4 NOTE).

### Scope and method

Each scoped file's diff from `4cef786` to HEAD was read in full (the four
new modules `post.py`, `absence.py`, `trace.py` and `live.py` whole), along
with the code it calls:

- **The post.** `write_letter`, `file_parcel`, `letters_waiting`,
  `arrival_notes`, `thread_lines`, `inbox`, `on_taken` and `_ring_for`;
  the `write` verb's allowlist; the parser's `write` and `give ... for`
  paths; how `private_to` gates scope (`objects.visible_to`,
  `contents_for`, `in_scope`), how `verbs_for` unions a letter's verbs, and
  what `take`, `give`, `send_home_things`, `world refresh` and `account
  delete` do with a private thing.
- **Between dreamers.** `_hand_to_player` and the carried check ahead of
  it, `dreaming_elsewhere`, `announce_wake`, `presence_changed`, the doze
  grace.
- **Traces.** `trace.last_seen`, `dreamers_today`, `report`,
  `roster_text`, `for_prompt`, and where each is shown (`ask`, `read`,
  `examine`, the dusk line, `{dreamers_today}`); `absence.take_note` and
  its merge into the slept leaf.
- **The model's inputs.** `dialogue.build_prompt`'s new OTHER DREAMERS
  and grounding sections, `TALK_SELECT_MAX_WORDS`, the plant fast path,
  the husk text that now carries the planter's phrase.
- **Page sinks.** Every changed one: the card path (`renderDetailInset`,
  `linkifyEntities`), `showThinking`, `renderDreaming`, the slept leaf,
  the keepsake card and glyph, and the How to Dream text.
- **Executor changes.** A rider target on a no-target verb, `use` on a
  toon becoming `give`, the carried key re-entering `execute_command`.
- **World sources.** `config.post`, the rosters, Quill's seed topic, the
  dream patch and its rehearsal record, the two walkthroughs (authored
  text and commands only); `tools/assemble_world.py --check` passes.

Two candidates were checked with a scratch script outside the repo (a
throwaway DB, the real functions): the cost of the waiting-letters scan as
letters pile up, and what `account delete` does to a filed parcel. Secrets
and instance values were compared without printing (below). The 260 tests
in the 12 scoped test files pass.

### Findings

[WARN] daydream/post.py:187-253 and :329-342; daydream/story.py:636-639;
daydream/api/ws.py:1185-1192 — A player can file letters without limit,
and every letter waiting for anyone is loaded on every player's every
command.
  Attack vector: An invited friend, or a runaway `bin/game play` loop, at
the post room repeats `write to <name>: x`. Nothing caps letters per
sender, per recipient or in all; the only brakes are the 500-character
line and the socket's token bucket (12 frames, then 3 a second;
ws.py:1091-1094), so one connection files about 10,000 letters an hour,
each a persisted thing at the post room that waits until the recipient
takes it. The recipient cannot refuse them and no operator verb clears
them. The cost lands on everyone: after each command the server recomputes
the acting player's threads (`_send_threads_if_changed`), which calls
`post.thread_lines`, then `letters_waiting`, then
`objects.contents_for(post room)`, which loads and JSON-parses every thing
at the post room and filters in Python. So each command by any player,
anywhere in the village, costs time proportional to all the letters
waiting for anyone. Every snapshot carries `threads` too, and the post
room's own scope and snapshot grow the same way.
  Evidence: Measured in the scratch repro: each `write_letter` takes about
1 ms and none is refused. With 1,000 letters waiting for someone else,
`story.threads_for` for a player with no post takes 6 ms (baseline
0.1 ms); with 5,000 it takes 31 ms, and `objects.in_scope` at the post
room the same. That is roughly 65 ms added to every player's every
command after an hour of it, and around 0.6 s after a night.
  Remediation: Cap in `write_letter`: a few letters waiting from one
sender to one recipient, and a few dozen per recipient, refused with an
authored line (Fen's pigeonhole is full). Have `letters_waiting` query
only the viewer's letters (location = the post room and
`json_extract(properties_json, '$.letter.to') = ?`), so the per-command
cost is the viewer's own post. Consider an admin verb that lists and
clears a sender's letters.

[NOTE] daydream/post.py:265-303; daydream/accounts_cli.py:155-157;
daydream/toons.py:440-452 — A parcel makes a shared authored thing
`private_to` one player, which puts it outside two safety nets written
before the post existed.
  Attack vector: Not an exploit; ordinary play. `give gear to Fen for Ada`
files any carried, non-private thing, the escapement gear or Pollen
included, as private to Ada at the post room. `rest_returns_things` sends
home only what a resting player carries (toons.py:450), and a filed parcel
is carried by no one, so it never goes home; `world refresh` keeps
`private_to` (refresh.py:49). If Ada never comes back, the thing is
invisible to everyone else for good. If the operator then deletes Ada's
account, `_forget_dreamer_state` deletes every `private_to` thing of hers
on the assumption that such things exist for her alone (finds, letters),
so the authored thing is destroyed. A later `world refresh` inserts a
missing authored object again at its home (refresh.py:198-206), which is
the recovery.
  Evidence: Scratch repro: filed the lantern for Ivo, rested the giver
(the lantern stayed at the post room, private), then ran
`_forget_dreamer_state` for Ivo: one record removed, and
`objects.get("i-lantern")` returned None.
  Remediation: In `_forget_dreamer_state`, a thing whose `letter.parcel`
is set, or that has a `home`, should be made public again and sent home
rather than deleted. Consider refusing to file a thing that has a `home`
(the world's own things), or sending an uncollected parcel home after
some days. DATA-LIFECYCLE.md's `account delete` section should also say
what stays: the letters and parcels the person left for others (their
typed words, now in the recipient's keeping) and the planter's phrase on a
spent seed's husk (growth.py:654-656).

[NOTE] daydream/trace.py:29-34, :153-170 and :212-241;
daydream/absence.py:39-48 — The raw input log has a second audience.
CLAUDE.md and DATA-LIFECYCLE.md describe it as private, read by the dream
digest. Now its metadata (who typed, when, in which room) reaches every
other player: `ask <resident> about <dreamer>` tells when and where they
were last seen and whether they are awake, dozing or resting; the ledger's
keepers roster lists every dreamer the same way; Bell's tally and the dusk
line name who came through today; a returning player reads who was here
while they rested. No typed text is shown, and this is the requested
household feature, so it is not a vulnerability. The redeem card's
disclosure ("the village keeps what players do and the operator reads
summaries of it") and the docs do not say that other dreamers see when you
were last here and where.
  Remediation: One sentence on the redeem card or in How to Dream, and in
DATA-LIFECYCLE.md's row for the input log. Optionally, a dreamer who has
rested for longer than some weeks drops off the roster.

[NOTE] daydream/accounts_cli.py:129-136 (carried unchanged) — `account
delete --yes` can leave a few records behind if the person is talking to
a resident at that moment: a reply still being generated is written after
the purge, with the `talk:`/`rel:` records. Still open: `account delete`
is not in `prodctl.STOP_FOR` (daydream/prodctl.py:211-213), and
`dialogue.talk` does not re-check the dreamer after the model call. The
remediation stands as written last time.

[NOTE] tests/test_config_edge.py:61 (outside these paths; carried
unchanged) — The non-loopback bind-host test still uses this box's real
tailnet IPv4 (it still matches `tailscale ip -4`; the value is not
reproduced here). Swap in `100.64.0.1` the next time the file is touched.

### Traced and cleared this run (not findings)

- **Letter privacy.** A letter is spawned at the post room with
  `private_to` the recipient. `objects.visible_to`, `contents_for` and
  `in_scope` honor it, so no other player sees, examines, takes or reads
  it, and the executor's scope gate rejects a guessed id. Its `verbs`
  union with the prototype's, so the recipient can take it; a dropped
  letter stays private; `_hand_to_player` and `file_parcel` refuse a
  private thing; only a parcel loses its privacy on take (`on_taken`).
  Letters never reach the model: the parser's `write` fast path returns
  the line whole and `write_letter` makes no call. The banlist is a tone
  check, not a control. `write` and `file_parcel` tell the writer whether
  a dreamer by that name exists, which the rosters already show.
- **Carried things only.** `_handle_give` requires the thing to be in the
  giver's hands before `_hand_to_player` or `file_parcel` run
  (verbs.py:818), so no fixture or room thing can be moved or made
  private. A gift to a dozing dreamer moves into their satchel by design;
  `send_home_things` returns world things when they rest.
- **Names.** A dreamer's name is bounded (`MAX_NAME_CHARS`) and
  printable, not otherwise restricted; every sink that shows it escapes
  or uses `textContent`. Names are not unique: a letter to a shared name
  goes to the lower slot (the carried accepted risk).
- **Page sinks.** The card path escapes before linking
  (`linkifyEntities`, main.js:1259) and the replacement escapes the id;
  `showThinking`, `renderDreaming`, the slept leaf and the keepsake card
  use `textContent`; `keepsakeGlyph` hashes the name only. A letter's
  newlines collapse in the card (cosmetic). No new client-to-server frame
  kind: `thinking` is server-to-client and carries a name or an engine
  line.
- **The model's inputs.** `trace.for_prompt` adds engine-composed lines
  (names, room titles, a state word) for dreamers the player named;
  `grounding` is authored topic text; `{dreamers_today}` is substituted
  only in authored narrations (the LLM data-skill path does not exist in
  this world). A letter's words reach a model only later, as part of the
  recipient's own journal, which is the existing `say` class.
- **Executor.** A rider target on a no-target verb is resolved in scope
  (verbs.py:442) or dropped; `use` on a toon becomes `give` with give's
  gates; the carried-key path re-enters `execute_command`, which
  re-validates, and cannot loop (a still-locked target falls through to
  the locked line).
- **Growth.** Refusals and the seed's question are the planter's alone;
  the husk keeps the planter's phrase (at most 120 characters, banlisted),
  read later through the escaped card path; the parent room's description
  names the planter.
- **`live` frames.** Registered per toon by the receive loop, unregistered
  only by the same sender (a takeover cannot unregister the new page),
  never persisted, and a failed send is ignored.
- **Presence.** `dreaming` lists other awake players and their room
  titles, never the viewer or a dozing dreamer; `presence_changed` carries
  an id the page never renders.
- **Delete's other paths.** Letters to the deleted person go
  (`private_to`); a letter they had taken is dropped by `delete_slot` and
  then deleted; letters they wrote stay with the recipient (the NOTE
  above).
- **Logs.** `post` logs dreamer and thing names and a length, never the
  text. No new route, no new dependency.
- **World data.** The assembled world byte-matches its sources; the dream
  patch is additive and its rehearsal ran every walkthrough with zero LLM
  calls; `config.post` is validated (room must exist, tellings must be
  strings); no URL, script or markup in any scoped data file.

### Secrets, PII and the instance

- **Credentials and addresses.** The values in
  `~/.config/daydream/cloudflare.env`, the box's addresses (`hostname -I`,
  `tailscale ip`), and the ids and hostnames in `instance/NOTES.md` were
  compared against every added line from `4cef786` to HEAD without
  printing. None appears. The box's hostname appears in the beta
  rehearsal's playtest docs (outside these paths); it is already in 122
  committed files (README, CLAUDE.md, `.env.example`), so that is not new.
- **Names.** Every account, display and invitee name in the dev accounts
  DB, and prod's (`prod account list`, `prod invite list`: only
  `cli-operator`, no open invites), were compared the same way. The only
  hits are `Peter`/`peter`: SECURITY.md's own carried text, and
  `worlds/lost-hours/dreams/dream-2026-09-28/rehearsal.json:9`, where
  `bin/game dream rehearse` recorded the pre-dream snapshot's absolute
  path under the operator's home. The Unix account name is already in the
  accepted-risk text and in five committed files (SPEC.md,
  docs/playtests/BRIEF.md, tests/test_ops_units.py, the previous dream's
  rehearsal record), so it is not flagged; a cheap tidy-up is for
  `rehearse` to record the path relative to the data dir. Wren, Vex and
  Halloran in the dream patch and walkthroughs are the beta rehearsal's
  agent personas (docs/playtests/2026-09-28-beta-rehearsal/SUMMARY.md),
  and the patch's toon ids are dev ids. No friend's name: prod holds no
  player account.
- **History.** The last three commits of the session-handling scoped
  files (`ws.py`, `slots.py`, `play.py`) hold no token-shaped string.
  `instance/` is still ignored. Players see the operator only as the
  Night Warden in every scoped file.

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
*Prior review (2026-09-28, paths, commit `4cef786`): 21 files covering the
codereview fix pass and the second playtest's fixes and lines. It found
0 BLOCK / 0 WARN / 2 NOTE: the prior WARN (account delete kept a player's
private lines) was confirmed fixed, and the two NOTEs (a delete during a
talk, the tailnet address in a test) are carried above. Full entry at
`git show 5db3142:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-29","commit":"43fba6bc6bc5f55dbc01004b265fdda924bd48c4","scope":"paths","scanned_files":["daydream/absence.py","daydream/api/slots.py","daydream/api/ws.py","daydream/collect.py","daydream/dialogue.py","daydream/drift.py","daydream/growth.py","daydream/live.py","daydream/llm/story_format.py","daydream/objects.py","daydream/parser.py","daydream/play.py","daydream/post.py","daydream/rules.py","daydream/skills/effects.py","daydream/story.py","daydream/toons.py","daydream/trace.py","daydream/verbs.py","daydream/version.py","tests/test_absence.py","tests/test_between_dreamers.py","tests/test_dialogue.py","tests/test_dozing.py","tests/test_growth.py","tests/test_linkify.py","tests/test_parser.py","tests/test_post.py","tests/test_story.py","tests/test_trace.py","tests/test_verbs.py","tests/test_ws_grow.py","web/assets/main.js","web/assets/style.css","web/index.html","worlds/lost-hours.json","worlds/lost-hours/arcs/00-prologue.json","worlds/lost-hours/arcs/07-letters.json","worlds/lost-hours/cast/bell-mott.json","worlds/lost-hours/cast/others.json","worlds/lost-hours/dreams/dream-2026-09-28/patch.json","worlds/lost-hours/dreams/dream-2026-09-28/rehearsal.json","worlds/lost-hours/regions/01-clocktower.json","worlds/lost-hours/regions/03-lane.json","worlds/lost-hours/regions/10-residents.json","worlds/lost-hours/walkthroughs/prologue-together.json","worlds/lost-hours/walkthroughs/quill-seed.json","worlds/lost-hours/world.json"],"block":0,"warn":1,"note":4} -->
