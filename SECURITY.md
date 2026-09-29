# SECURITY.md

## Security Review — 2026-09-29 (scope: paths)

**Summary:** Path-scoped review of the 22 files named by the caller, read as
their change from the last scan (`43fba6b`) to HEAD `69760f7`: the codereview
fix pass over the beta rehearsal's household layer (the post's caps and its
narrower query, a parcel refused for a village thing, `set_property` declared
on `give`, one turn per `open`, the placeholder filled on every telling path,
the away note kept for the leaver's return, world-scoped presence), the
onboarding words, and the door's disclosure. No exploitable vulnerability. The
prior WARN (uncapped letters read on every command) is fixed and re-measured,
and both prior data NOTEs are addressed. Two new NOTEs: the placeholder
expander now runs over a player's letter body, and a leave-and-claim loop
re-snapshots every connected player from two unthrottled endpoints. The two
carried NOTEs stand (0 BLOCK / 0 WARN / 4 NOTE).

### Scope and method

- Each scoped file's diff from `43fba6b` to HEAD was read in full; `post.py`,
  `absence.py`, `trace.py`, `live.py` and `door.js` were re-read whole.
- The code each change calls was read wherever the change could widen a trust
  boundary: `objects.things_where_property` (the new letter query),
  `verbs._execute_resolved` (the executor `open` now re-enters),
  `_handle_give`, `_hand_to_player` and `file_parcel` (everything dispatched
  under `give`'s widened allowlist), `_handle_read` and
  `effects._apply_narrate` / `tell_others` (what text reaches the new
  `expand_placeholders`), the WS event filter and re-snapshot trigger
  (`ws.py:1240-1290`), `_auto_enter` and `claim_slot` (when `announce_wake`
  fires), `server.py`'s `{{place}}` fill, and the dreamer-name rule
  (`slots.py:131`).
- Three scratch scripts against throwaway DBs under the scratchpad (nothing
  under `~/data/daydream`): the cost of `letters_waiting` / `threads_for` with
  1,000 and 5,000 letters waiting for someone else, an end-to-end letter
  carrying `{dreamers_today}` read by its recipient, and the cost of one
  `_state_snapshot`.
- `tools/assemble_world.py --check` passes; the six scoped test files pass
  (126 tests).

### Findings

[NOTE] daydream/skills/effects.py:347 (and :309), daydream/trace.py:185-193,
daydream/post.py:94-112 and :257, daydream/verbs.py:1152-1156 — The
placeholder expander now runs over every narrated text, a player's own words
included.
  Attack vector: Not an exploit today; a template applied to untrusted text.
A letter's stored `text` is the authored `read_text` with the writer's body
substituted in (post.py:257); `read` narrates it (verbs.py:1152-1156)
through `_apply_narrate`, which since this fix pass calls
`trace.expand_placeholders` on every text (effects.py:347). So a writer who
types `{dreamers_today}` has it replaced, in the recipient's reading, with the
names of the dreamers who typed today. A dreamer may also be named
`{dreamers_today}` (16 printable characters; slots.py:131 allows any printable
name up to 24), which would expand in every line that names them. The only
placeholder is that one, and what it reveals is what Bell's tally and the dusk
line already tell every player, so there is no confidentiality impact; the
class matters if a later placeholder ever carries something a player should
not read.
  Evidence: Scratch repro: `write to Ivo: today {dreamers_today}; also
{actor} {to} {text}` stored the body verbatim; Ivo's `read` narrated "today
one dreamer, Wren, came through today; also {actor} {to} {text}" (only the
new placeholder expands; `{actor}` is replaced only in `others` lines).
  Remediation: Expand placeholders on authored strings only: substitute
player-supplied fields after expansion, or have `post._line` neutralise `{`
in the letter body and in dreamer names (`{text}`, `{from}`, `{to}`), and
refuse a dreamer name containing braces at slots.py:131.

[NOTE] daydream/api/slots.py:311-312 and :317-337 (leave), daydream/toons.py:121
with daydream/api/slots.py:235-272 (claim), daydream/api/ws.py:93 and
:1272-1285 — A world-scoped `presence_changed` re-snapshots every connected
player, and the two endpoints that emit it are not throttled.
  Attack vector: A signed-in friend, or a misbehaving `bin/game play` script
(the gate and the CSRF check keep strangers and other origins out), loops
`POST /api/session/leave` then `POST /api/slots/<own slot>/claim`. Each leave
emits a world-scoped `presence_changed` (slots.py:311, `room_id=None` since
this fix pass), and each claim after a rest calls `announce_wake`, which emits
another (toons.py:121). The kind is in `_EFFECT_MUTATION_KINDS` (ws.py:93) and
the event has no room, so every connection's loop builds and sends a fresh
`_state_snapshot` (ws.py:1272-1285): two full snapshots per connected player
per cycle, and a journal task per leave. Neither endpoint has a per-session
rate (the only throttle in slots.py is `DREAMERS_PER_DAY` on create, :164),
and the WS token bucket does not cover HTTP. Before this pass the fan-out
reached only the leaver's room. Transient, and `account disable` ends it, so
a rate-limiting note rather than a WARN.
  Evidence: One `_state_snapshot` measured 0.74 ms in a two-toon room of the
seed world (a fuller village room costs more); with twelve connected players
a cycle is roughly 20 ms of event-loop time plus the leave's own work, so a
loop at ten cycles a second takes a fifth or more of the single loop for
everyone.
  Remediation: A small per-session throttle on leave and claim (a few a
minute is generous for a person), or deliver the world-scoped presence event
to viewers in other rooms as a light `dreaming` refresh rather than a full
re-snapshot.

[NOTE] daydream/accounts_cli.py:129-136 (outside these paths; carried
unchanged) — `account delete --yes` during a resident's reply leaves that
reply and its `talk:`/`rel:` records behind; `account delete` is not in
`prodctl.STOP_FOR`, and `dialogue.talk` does not re-check the dreamer after
the model call. The remediation stands as written.

[NOTE] tests/test_config_edge.py:61 (outside these paths; carried unchanged)
— The non-loopback bind-host test still uses this box's tailnet IPv4 (one
line; the value is not reproduced here). Swap in `100.64.0.1` the next time
the file is touched.

### Resolved since the last review

- **WARN, uncapped letters read on every command.** Fixed: `write_letter`
  refuses past five waiting from one hand or twenty for one dreamer
  (post.py:50-51, :233-238) in authored words (`too_many_text`), and
  `letters_waiting` reads only the viewer's own letters by `letter.to`
  (post.py:349-361, through `objects.things_where_property`: a parameterised
  `json_extract` whose key is a code constant). Re-measured in the same
  scratch shape as last time: with 5,000 letters waiting for someone else,
  `letters_waiting` for another player takes 0.62 ms (was 31 ms) and
  `threads_for` 0.63 ms; with 1,000, 0.14 ms (was 6 ms). The scans that still
  grow with the post room's contents (`in_scope` there, and the recipient's
  own `letters_waiting`, about 6 ms per 1,000) are now bounded by the caps.
  Parcels are uncapped, but each needs a carried keepsake with no home, a
  supply the world's content bounds.
- **NOTE, a parcel of an authored thing destroyed by `account delete`.**
  Fixed: `file_parcel` refuses a thing whose `toons.home_of` is set
  (post.py:305-310, authored `belongs_text`), so a village thing is never
  made private to one dreamer, and DATA-LIFECYCLE.md now says what a delete
  keeps of the post. A gift to a dozing dreamer is the accepted risk below.
- **NOTE, the input log's second audience.** The redeem card now says other
  dreamers can see when you were last here and where (door.js:82-85), and
  DATA-LIFECYCLE.md describes what other dreamers see of a dreamer and that
  typed text stays private.

### Traced and cleared this run (not findings)

- **`give` declares `set_property`.** Everything dispatched under it is
  engine-composed: `_handle_give` (a move, the authored `gives_mood` and
  `gives` reward, a narrate), `_hand_to_player` (a move, a narrate) and
  `file_parcel` (a move, `private_to`, `letter`, a narrate). Authored `give`
  rules run under `effects.RULE_KINDS`, not the verb's set, and no model
  output reaches `dispatch_effects` with `give`'s allowlist. The call-site
  widening is gone.
- **`open` with the key in hand.** `_execute_resolved(VERBS["use"], key,
  target)` re-resolves both objects in scope, requires `use` among the key's
  verbs and a thing as the target, and runs the authored `use` rule as if
  typed; the recursion is bounded (the second `_handle_open` sees a state
  other than `locked`, or falls through to the locked line).
- **World-scoped `presence_changed` with `except`.** The WS filter checks
  `except` before the room filter (ws.py:1244), so the leaver's own open page
  skips it and cannot consume the away note; `take_note` also refuses to
  clear the stamp for a toon no longer human-controlled. The payload is a
  toon id the page never renders.
- **Beats select at any length.** A long line naming an open beat now
  advances it deterministically, and `topic_text` returns None for beats, so
  a beat's payoff is never grounding for the model: less model exposure, not
  more.
- **The index page's new `{{place}}` uses.** Filled by `server.py:236-240`
  with `html.escape(..., quote=True)` from `instance.json`, the operator's
  own file.
- **`config.post.keeper`** is validated against the world's toon ids at load;
  the assembled world byte-matches its sources; the two new authored strings
  carry no markup or URL.
- **Page.** `showThinking` and `renderSnapshot` only clear transient lines;
  door.js's new sentence is `textContent`; `.dreamer-note` is style only.
- **Tests and logs.** The six scoped test files use fictional names; `post`
  logs names and a length, never the text.

### Secrets, PII and the instance

- Every added line from `43fba6b` to HEAD was compared, without printing,
  against the values in `~/.config/daydream/cloudflare.env`, the box's
  addresses (`hostname -I`, `tailscale ip`) and its hostname: no credential
  value and no address. The hostname matched only SECURITY.md's own carried
  accepted-risk text (it is the operator's Unix account name, already in 110
  committed files), as the prior version did.
- Added lines were scanned for email addresses, IPv4 and CGNAT addresses and
  the operator's names: the only hits are SECURITY.md's prior text.
- The last three commits of `slots.py`, `post.py`, `trace.py`, `absence.py`
  and `door.js` hold no token-shaped string (the only keyword hits are
  door.js's "set password" button label).
- `instance/` is still ignored; the working tree was clean at the start of
  the review; players see the operator only as the Night Warden in every
  scoped file.

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

Accepted in the 2026-09-29 codereview (CODEREVIEW.md):

- **A village thing handed to a dozing dreamer** (`verbs._hand_to_player`,
  the tuck-away branch) waits in their satchel until they rest; a page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. Refusing it broke the arc contract (walkthrough players never
  open a socket, so every walkthrough hand-over runs through the dozing
  branch). BACKLOG `dozing-handover-of-village-things`.

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
*Prior review (2026-09-29, paths, commit `43fba6b`): 48 files, the beta
rehearsal's household layer (letters and parcels, hand-overs, who else is
awake, traces and rosters, the away note, thinking frames, the typed plant)
and the dream `dream-2026-09-28`, at WORLD_VERSION 1.9. It found 0 BLOCK /
1 WARN / 4 NOTE: the WARN (uncapped letters read on every command) and two
NOTEs (a parcel of an authored thing under `account delete`; the input log's
second audience undisclosed) are resolved above, and the other two NOTEs are
carried. Full entry at `git show 69760f7:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-29","commit":"69760f7baca60dce17002d0d843efd0b572f610a","scope":"paths","scanned_files":["daydream/absence.py","daydream/api/slots.py","daydream/live.py","daydream/llm/story_format.py","daydream/post.py","daydream/skills/effects.py","daydream/story.py","daydream/toons.py","daydream/trace.py","daydream/verbs.py","tests/test_absence.py","tests/test_dozing.py","tests/test_post.py","tests/test_story.py","tests/test_trace.py","tests/test_verbs.py","web/assets/door.js","web/assets/main.js","web/assets/style.css","web/index.html","worlds/lost-hours.json","worlds/lost-hours/world.json"],"block":0,"warn":0,"note":4} -->
