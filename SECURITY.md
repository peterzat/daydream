# SECURITY.md

## Security Review — 2026-09-29 (scope: paths)

**Summary:** Path-scoped review of the 50 files named by the caller, read as
their change from the last scan (`69760f7`) to HEAD `6129d7a`: the fixes from
the day's red-team review (the Worker's https redirect and encoded-slash
refusal; socket, session, presence and journal limits; unique dreamer names;
private things inside containers; the session cap; the Access header strip;
the venv seal; the prod side-door refusals; ComfyUI without API nodes), the
agent-side defenses (the player-text scan, the PreToolUse guard and its
settings template, `play`'s marking), and "what the page offers"
(`heard.py`, place-aware card verbs, world content at WORLD_VERSION 1.10). No
exploitable vulnerability in the app or the edge. One WARN: the new agent
guard misses a gated verb or a credential read on a later line of a command,
or after a `#` inside a word. Three new NOTEs. Of the prior NOTEs, the
presence fan-out is resolved and the placeholder one is half resolved; the
two carried NOTEs stand (0 BLOCK / 1 WARN / 6 NOTE).

### Scope and method

- Each scoped file's diff from `69760f7` to HEAD was read in full;
  `heard.py`, `textscan.py`, `tools/agent_guard.py` and `edge/src/worker.js`
  were read whole.
- The code each change calls was read wherever it could widen a trust
  boundary: `objects.in_scope`, `visible_to` and the snapshot's entity
  sidecar (private things); `events.fetch_since` and the events table's
  timestamp default (the replay window); `_auto_enter`, `announce_wake`,
  `toons.kick_slot` and every `presence_changed` emitter (the presence
  budget); the post and trace name lookups (unique names);
  `prodctl.passthrough`, `needs_stop`, `build_release` and bin/game's
  `world patch` parsing (side doors, the seal); the prod unit's sandbox
  directives.
- Probes, all in the scratchpad and touching no live data: the guard's
  `decide()` over multi-line, `#`, `bash -lc` and path spellings (with a
  sentinel in place of the real credential paths; the guard is wired in this
  session and refused a probe that named one); the per-session rate bucket
  across a reconnect; a read-only look at how the venv seal treats an existing venv.
- The eleven scoped test files pass (205 tests), the Worker's 33 unit tests
  pass, and `tools/assemble_world.py --check` matches.

### Findings

[WARN] tools/agent_guard.py:52-71 (with :74-94, :110, :133) — The guard's
command splitter does not split on newlines and treats a `#` inside a word
as a comment, so a gated verb or a credential read on a later line, or after
`x#;`, gets no opinion.
  Attack vector: Player text reaches this session (the text-scan,
`bin/game play`, the digest, letters), and the guard is the deterministic
layer meant to catch a steered agent's command however it is spelled. shlex
keeps the newline in `whitespace`, which it checks before
`punctuation_chars`, so a multi-line command (the usual shape of an agent's
Bash call) becomes one argv whose first word is line one's command. shlex's
default `commenters = "#"` drops the rest of the line at a mid-word `#`,
which bash reads as a literal character. Combined with a spelling the
template's prefix rules do not match (an absolute path to `bin/game`),
nothing deterministic stands between an obeyed injection and
`prod account role <x> admin` or `prod invite create`. For a Bash `cat` of
the Cloudflare token or a second-line `gh auth token`, the guard is the
layer meant to deny it. The permission mode (auto mode's classifier) is
then the last check.
  Evidence: `decide()` returns ask for `bin/game prod invite create --for M`,
for its absolute-path form and for a `;` chain, but None for
`echo ok\nbin/game prod invite create --for M` (`\n` a newline),
`cd <repo>\n<repo>/bin/game prod account role m admin`,
`echo a#; bin/game prod invite create --for M` and `true\ngh auth token`.
With a sentinel standing in for a credential path, `cat SENTINEL/x` is
denied but `echo x#; cat SENTINEL/x` is not. `_split_commands` returns one
argv starting `echo` for the newline case and `[['echo', 'a']]` for the `#`
case; bash runs both second commands. Also unread: `bash -lc '...'` (only a
bare `-c` is unwrapped), `bin//game`, a heredoc into `bash`, globs or
variables in the path or the verb. An Edit or Write of the guard itself or
of `.claude/settings.local.json` gets no opinion. tests/test_agent_guard.py
has no newline or `#` case.
  Remediation: Drop the newline from `lex.whitespace` (or turn newlines into
` ; ` before lexing) and set `lex.commenters = ""`; unwrap any shell option
cluster containing `c`; `os.path.normpath` the executable; ask on what it
cannot read (`eval`, `source`, a shell reading stdin or a heredoc, `$` or
glob characters in the executable or verb position, `git credential`); ask
on an Edit or Write of `tools/agent_guard.py` and `.claude/settings*.json`;
add newline and `#` cases to the tests. Keep describing the guard as a speed
bump behind the policy and the ask rules, not a boundary.

[NOTE] daydream/play.py:118-119 and :304, daydream/textscan.py:79-123,
daydream/api/ws.py:742-748, daydream/api/slots.py:190 — The player-text
defenses cover other dreamers' `say` lines and typed input; other channels
of player words reach the agent unmarked, and control characters pass
through.
  Attack vector: A friend writes a letter to an agent's dreamer, or sets an
appearance (300 characters, narrated to anyone who examines them,
verbs.py:709-719), holding instructions. When the operator's agent later
plays (`bin/game prod play`, approved per call, or dev `play` after
`prod pull`) and reads the letter or examines the dreamer, the words print as
plain narration: `play` marks only other dreamers' `say` lines, and prints
its banner (whose own text says "a letter you read is too") only when a
marked line is present. The text-scan gathers typed lines, command words,
dreamer names, grown places and usernames, but not appearance seeds. Typed
lines and appearance seeds keep control characters (only names are
`isprintable`-checked, slots.py:171), and `play` prints narration raw, so a
human running `play` in a terminal receives any escape sequences they carry
(the `say` path and the scan's output are JSON-escaped). The agent's policy
is the barrier; this is its labeling.
  Evidence: play.py:118-119 returns `p["text"]` unmarked for every narrate;
:126-134 mark `say` from others; :304 gates the banner on a marked line. The
post's `read_text` is `To {to}, from {from}:\n\n{text}`, so a letter's body
is bare. `textscan.gather` has no appearance source. ws.py:742 only strips a
typed line; slots.py:190 only strips an appearance.
  Remediation: Tag the narrations that carry player words (a letter read, a
dreamer examined, a grown place) with a payload marker and have `play` mark
them; print the banner whenever one appears; pass every printed line through
a control-character filter; refuse non-printable characters in typed lines
and appearance seeds at the server, as names already are; add players'
appearance seeds to the scan.

[NOTE] daydream/api/ws.py:937-955 — A session's shared rate budget is
dropped with its last socket, so closing and reopening refills the burst.
  Attack vector: A signed-in friend's script (the gate, the Origin check and
the three-socket cap keep others out and concurrency bounded) closes its
socket and reopens it to get twelve fresh frames each time, instead of three
a second; each cheap frame (a take, a drop) re-snapshots everyone in the
room. Before this change the budget was per socket, so this is an
unfinished edge of the fix, not a regression.
  Evidence: Scratch probe of the module: twelve frames taken and the
thirteenth refused; `_unregister_socket` then `_register_socket` for the
same session; `_bucket_for` returns a new bucket and twelve more frames pass
at once.
  Remediation: Keep a session's bucket past its last socket and prune
entries idle longer than a full refill (RATE_BURST / RATE_PER_SECOND, four
seconds), or key the bucket by account.

[NOTE] daydream/prodctl.py:459-472 with :450 — The venv seal checks
ownership only, so a change made to a venv while it was still
group-writable would survive the first sealed deploy.
  Attack vector: Needs code running as `daydream` outside the systemd
sandbox (inside it `/srv` is read-only: ProtectSystem=strict,
ReadWritePaths=/srv/daydream/data; the operator's own pass-throughs are the
only such processes today). Such a process can rewrite an operator-owned,
group-writable file in the venv, for example its
`distutils-precedence.pth`. The seal's `chmod -R go-w` succeeds on it, the
ownership walk passes it, and `build_release` then runs the venv's python as
the operator without `-S` (:450), so `site` executes the `.pth`: the
escalation the seal was written to stop.
  Evidence: `_seal_venv` compares `st_uid` only, and a venv built before
the seal landed was group-writable by `daydream` from the day it was built
(the setgid parent and a 0002 umask), `.pth` files included, with every
entry owned by the operator.
  Remediation: Rebuild the venv once (move it aside; the next deploy builds
and seals a fresh one), and run the operator-side compile without `site`
(`python -I -S -m compileall`), so no venv `.pth` ever runs as the operator.

[NOTE] daydream/skills/effects.py:347, daydream/post.py:257 (outside these
paths; carried, half resolved) — The placeholder expander still runs over a
letter's body. A new dreamer's name may no longer hold braces
(slots.py:177). BACKLOG `placeholders-over-player-text`.

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

- **NOTE, world-scoped presence re-snapshots from unthrottled endpoints.**
  Fixed: leave, claim and kick share a per-account budget of ten a minute
  (slots.py:91-104, a 429 past it). Every path that rests or wakes a dreamer
  passes one of them: a rest needs leave, kick or the shell, and auto-enter
  wakes a resting dreamer only for a session that has not left, which a
  fresh sign-in reaches only after a leave. A recap runs one at a time per
  dreamer and takes the arbiter's background slot.
- **NOTE, placeholders over player text (half).** Dreamer names refuse
  braces; letter bodies remain (the carried NOTE above).

### Traced and cleared this run (not findings)

- **heard.py.** Keys come only from the world's vocabulary (topics, beats,
  mentions), so `pq:<toon>:met` cannot grow with player text. A chip is a
  subset of the available topics, which typing reaches anyway, so it
  discloses nothing new. The audience mirrors the socket filter (the
  recipient, or the room less `except`); a dark room names nothing; private
  things are skipped. Writes are single autocommit statements, and a failure
  in the hook is logged, never raised into `events.append`.
- **Private things in containers.** `visible_contents(o, viewer)`,
  `_container_glance` and `look` now filter by viewer; `in_scope` and the
  entity sidecar already did; toon cards carry no inventory.
- **Unique names.** The fold (NFKC, casefold, whitespace) is looser than the
  post and trace lookups (`.lower()` equality), so two dreamers cannot
  collide there. Legacy duplicates are not renamed (prod has none since this
  morning's clean start).
- **The replay window.** `within_s` compares `datetime('now', ...)` with the
  events table's `CURRENT_TIMESTAMP` default, the same format.
- **Sockets.** A command frame's words and verb are capped; past three
  sockets the oldest is told `elsewhere`; a rested page closes on its next
  frame or event; `close_session_sockets` acts on the caller's own session.
- **Sessions and headers.** `create_session` keeps the newest ten. The Access
  middleware strips `cf-access-client-id` and `cf-access-client-secret`
  before the mode check, for HTTP and WebSocket scopes.
- **The Worker.** The https redirect precedes everything else. `%2f|%5c` is
  refused on the parsed path (backslashes are already normalised to `/`, and
  `%252f` decodes once at the origin into no route). The probes use
  `redirect: "manual"`.
- **prodctl.** `_refuse_side_doors` matches bin/game's own rule (any
  `--check` makes `world patch` check-only), so the refusal and the guard
  agree; `text-scan` is not in `STOP_FOR`. `edge tail` prints errors only;
  its pretty form still shows an errored request's URL, so an errored
  `/invite/<slug>` view would show that slug, a far smaller surface than
  before.
- **The text-scan's output** is ASCII-escaped JSON under a banner, cut at 300
  characters with the flags taken over the whole text; it writes nothing.
- **ComfyUI** in this checkout supports `--disable-api-nodes`
  (comfy/cli_args.py:183).
- **Page.** The new notes are set with `textContent`; a selector built from
  an object id can at worst throw.

### Player-text scan (CLAUDE.md "Player text is data")

- Run per the policy; the verdict and high-water mark live in the local
  instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The 2,249 added lines from `69760f7` to HEAD were scanned without printing
  values. The email-shaped hits are pytest decorators; the one IPv4 is
  `100.64.0.1` (the CGNAT base); no address of this box appears (compared
  with `hostname -I` and `tailscale ip`); the hostname, a short common word,
  matches only inside ordinary words; the token-shaped runs are a commit SHA, a base64
  test fixture, and test and backlog names.
- The last three commits of each credential-handling file in scope
  (`edge.py`, `prodctl.py`, `accounts.py`, `access.py`, `textscan.py`,
  `bin/game`, the settings template, `worker.js`, `agent_guard.py`) hold no
  secret-shaped string.
- The scoped tests use fictional names and loopback addresses. `instance/`
  is still ignored; the working tree was clean at the start; players see the
  operator only as the Night Warden.

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
  (Since 2026-09-29 a new dreamer's name must be unique under case, spacing
  and compatibility folding; confusable alphabets are still not folded, and
  legacy duplicates stay.)
- A shell rest does not reach an open socket; `account disable` is the
  stop. (Since 2026-09-29 the socket closes on its next frame or event, but
  the page's reconnect wakes the dreamer again, since a shell rest does not
  mark the session as left.)
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one. A PreToolUse hook would be firmer. (Since 2026-09-29
  `tools/agent_guard.py` backs them; its gaps are this review's WARN.)
- Player text reaches the agent's context through `bin/game play`: names,
  speech and move lines. The verbs an injected instruction would want stay
  behind ask rules.

---
*Prior review (2026-09-29, paths, commit `69760f7`): 22 files, the
codereview fix pass over the beta rehearsal's household layer, the
onboarding words and the door's disclosure. It found 0 BLOCK / 0 WARN / 4
NOTE: the placeholder expander over player text (half resolved above), the
unthrottled world-scoped presence re-snapshot (resolved above), and the two
carried NOTEs. Full entry at `git show 8b606df:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-29","commit":"6129d7a0ff50d0f9438ef21d50283e6503591e0e","scope":"paths","scanned_files":["bin/game","daydream/accounts.py","daydream/api/access.py","daydream/api/slots.py","daydream/api/ws.py","daydream/edge.py","daydream/events.py","daydream/heard.py","daydream/journal.py","daydream/llm/story_format.py","daydream/objects.py","daydream/play.py","daydream/prodctl.py","daydream/story.py","daydream/textscan.py","daydream/verbs.py","daydream/version.py","daydream/walkthrough.py","docs/claude-settings.local.example.json","edge/src/worker.js","edge/test/worker.test.js","tests/conftest.py","tests/test_abuse_limits.py","tests/test_access_middleware.py","tests/test_agent_guard.py","tests/test_dozing.py","tests/test_heard.py","tests/test_logs.py","tests/test_prodctl.py","tests/test_slots.py","tests/test_textscan.py","tests/test_ws.py","tests/test_ws_grow.py","tools/agent_guard.py","web/assets/main.js","web/assets/style.css","worlds/lost-hours.json","worlds/lost-hours/arcs/01-pim.json","worlds/lost-hours/arcs/02-extra-hour.json","worlds/lost-hours/arcs/03-rain-wait.json","worlds/lost-hours/arcs/04-summer.json","worlds/lost-hours/arcs/05-margin.json","worlds/lost-hours/arcs/06-nell-evening.json","worlds/lost-hours/arcs/07-letters.json","worlds/lost-hours/arcs/08-tace-hour.json","worlds/lost-hours/arcs/09-bell-dawn.json","worlds/lost-hours/arcs/10-mott-minute.json","worlds/lost-hours/cast/bell-mott.json","worlds/lost-hours/cast/others.json","worlds/lost-hours/cast/tace.json"],"block":0,"warn":1,"note":6} -->
