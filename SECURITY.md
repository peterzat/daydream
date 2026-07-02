## Security Review — 2026-07-02 (scope: paths)

**Summary:** Path-scoped audit of the Zork platform turn (v0.6.0) at commit
`3fdd91f` — 28 files / ~11K lines spanning the new declarative rule engine
(`rules.py`), world-state KV (`worldstate.py`), world clock (`clock.py`),
combat (`combat.py`), lighting (`lighting.py`), retell LLM layer
(`retell.py`), world verbs (`worldverbs.py`), pronoun memory
(`pronouns.py`), the format-2 keyless loader (`llm/format2.py`), the WS input
path + executor (`api/ws.py`, `verbs.py`, `parser.py`, `objects.py`,
`toons.py`, `skills/effects.py`), three additive migrations, admin/versioning
(`admin.py`, `version.py`), tooling (`assemble_world.py`, `ws_playthrough.py`,
`zork_oracle.py`, `bin/game`, `bin/zork-oracle-bootstrap`), and the SPA shell
(`web/index.html`, `web/assets/main.js`). The turn's central security
property holds under trace: the rule/effect engine keeps a **closed** condition
vocabulary and an **allowlisted** effect vocabulary, and the restricted kinds
(`RULE_ONLY_KINDS`: set_flag/adjust_score/kill_actor/teleport_actor/
start_fuse/… + world-shaping spawn_room/link_exit + rename_object) are
reachable ONLY through authored design-time paths — every LLM-facing dispatch
(talk dialogue, examine lazy-cache, retell) passes an allowlist that excludes
them, and `dispatch_effects` rejects an out-of-allowlist kind with no
mutation. All SQL is parameterized; LLM output is length/format/banlist
validated and HTML-escaped at every render sink; the tarfile restore keeps its
CVE-2007-4559 traversal guards. No secrets, no PII (git history of all 28
files scanned per commit). Net: **0 BLOCK / 0 WARN / 1 NOTE.**

### Findings

[NOTE] daydream/parser.py:175,491 (with daydream/api/ws.py:443) — one WS
`input` frame expands without a per-line cap. `_THEN_SPLIT` (splits on `.` /
`then`), `_AND_SPLIT` (splits on `,` / `and`), and TAKE/DROP/PUT ALL each turn
one typed line into an unbounded list of `Parse` commands; `_handle_input`
then runs `execute_command` per command, and every command ticks the world
clock (fuses, daemons, darkness) and appends broadcast events. A crafted line
("x and x and x and …" repeated, or a long `.`-chain) amplifies a single
frame into arbitrarily many synchronous clock ticks + event-log rows.
  Attack vector: an authenticated session (tailnet member in `tailscale`
  mode, or password-holder in `public`) sends one oversized `input` frame;
  the receive loop does the amplified work inline, growing the events table
  and momentarily loading the event loop.
  Evidence: `parser.py:175` (`segments = _THEN_SPLIT.split(text)`),
  `parser.py:491` (`for raw_name in _AND_SPLIT.split(part)`),
  `ws.py:443` (`for p in lp.commands: … await _dispatch_parsed`); no length
  or count bound on `text`, `segments`, or the expanded list.
  Remediation: cap typed-input length and the number of expanded
  commands/segments per line (reject or truncate past the cap). Defense in
  depth only — the sink is the already-accepted unbounded event-queue risk,
  the trust boundary is authenticated-only, and the impact is recoverable
  self-inflicted lag on a single-box deployment; no privilege gain.

Traced and cleared this run (not findings):

- **No LLM-facing path can emit a restricted effect kind.** `rules.dispatch`,
  the clock's fuse/daemon/darkness dispatches, and combat's `on_death` all
  pass `allowed=RULE_KINDS` over AUTHORED effect lists (design-time rule
  `do` blocks); the retell rephrase touches only a narrate effect's `text`,
  never its `kind`. The LLM-driven paths — `talk` (allowed = narrate/
  set_property/set_mood/spawn_object), examine lazy-cache (engine emits only
  set_property+narrate; the model supplies text), the parser (returns a
  closed verb + in-scope id, re-validated by `execute_command`) — cannot
  reach set_flag/adjust_score/kill_actor/teleport_actor/spawn_room/link_exit/
  rename_object. `effects.dispatch_effects` drops an out-of-allowlist kind
  with a narrate fallback and zero mutation (`effects.py:154-160`).
- **No PvP kill / privilege escalation via combat.** `attack` applies only to
  a dobj whose verb set includes `attack`; human toons spawn from `proto-npc`
  (verbs examine/talk), so a player is never attackable, and a toon with no
  authored `combat` block no-ops. `kill_actor`'s counterblow targets the
  attacker (self); `destroy_object` refuses rooms, prototypes, and
  human-controlled toons (`effects.py:530-533`).
- **Retell is injection-safe.** Its input is authored rule-narration text
  (never player free text — `say` emits a `say` event, `talk` runs the
  role-separated data-skill pipeline), its output is proper-noun/digit/
  length/banlist validated (`retell.py:100-124`) and HTML-escaped at render,
  and the whole call is `asyncio.wait_for`-bounded with an authored-text
  fallback on any exception, so a slow/hostile backend cannot hang a request.
- **No SQL injection.** `worldstate`/`objects`/`toons`/`admin` bind every
  value; `objects.things_where_property`/`by_slug` bind the json path
  operand; `toons._query`'s f-string interpolates only module-internal
  literal WHERE clauses (never request data).
- **Loaders + tooling are operator-trust, not request-controlled.**
  `format2.load_world2` / `bootstrap.load_world` validate fail-loud with
  zero writes and run at design time; `zork_oracle.py` spawns `dfrotz` via a
  pexpect ARG LIST (no shell) from an operator env var; `bin/zork-oracle-
  bootstrap` clones a fixed URL under `~/data/zork`; `assemble_world.py` is
  stdlib-only design-time assembly.
- **No new client-side XSS.** Every new render sink (`renderStatusRibbon`,
  detail insets, keepsakes, retold narration) uses `textContent` or routes
  through `linkifyEntities` → `escape()`; keepsake glyphs are a fixed SVG
  pool indexed by a name hash, never string-interpolated.

### Accepted Risks

Durable register carried forward; controls live largely outside this scope
and were not re-verified this pass.

- **LLM-emitted effects take an unscoped, LLM-chosen target id** on the
  `talk` dialogue path (bound to talk's non-restricted allowlist). The
  rule/growth/clock paths do NOT share this shape (engine- or author-
  constructed effects). v2 `skills-authoring-and-security`.
- **Shared-world mutation: any authed session may drive verbs on any in-scope
  shared object** (and authored daemons like the thief move/steal items
  between players). Intended single-shared-world / co-op design (fidelity
  relaxations R1/R4/R6); per-session ownership is v2. State-changing POSTs are
  CSRF-gated; `/ws` is Origin-gated + auth-gated.
- **Parser raw player input is not role-separated** before the grounding LLM
  call; output is strictly re-grounded to a closed verb + in-scope id, so a
  successful injection gains nothing a click could not already do.
- **Tailscale-mode auth is tailnet membership** (`auth.is_authed` True in
  `tailscale`; `AccessMiddleware` CGNAT `100.64.0.0/10` + loopback is the
  real gate). Cookie `https_only=False`; `/status/*` + `/cache/...`
  session-unauthenticated but AccessMiddleware-gated.
- **NPC dialogue / growth prompt-injection via player input**: role-separator
  wrapped, length-capped, input-banlist-checked; LLM output structured/
  validated and output-banlist-scanned before mutation. (Refusal `reason`
  is narrated without an output-banlist pass in `data.py`/`growth.py`;
  pre-existing, renders through escaped sinks.)
- **Operator-trust world envelopes + `bin/game`**: `world load`/`world reset`
  content (verbs/rules/fuses/daemons/growth), `reset`'s `rm -rf`,
  `.env`/`secrets.env` sourcing, `0.0.0.0` bind, the deprecated
  `bootstrap_world` LLM path reading `ANTHROPIC_API_KEY` (design-time admin
  tool, never runtime). None take network input.
- Unbounded slot-create body + event queues; liveness-gated claim takeover;
  missing CSP / `X-Content-Type-Options` on the SPA shell (XSS sinks are
  escaped).

---
*Prior review (2026-07-02, paths, commit `60001de`): path-scoped audit of
`tests/test_growth.py` (the Dreamseeds per-rule unit suite) — pytest-only code
with tmp-DB isolation, one static-string raw SQL, AsyncMock'd LLM, no secrets/
PII; 0 BLOCK / 0 WARN / 0 NOTE.*

<!-- SECURITY_META: {"date":"2026-07-02","commit":"3fdd91f911d4205e6c3674f59336a0341589fcd8","scope":"paths","scanned_files":["bin/game","bin/zork-oracle-bootstrap","daydream/admin.py","daydream/api/ws.py","daydream/clock.py","daydream/combat.py","daydream/events.py","daydream/lighting.py","daydream/llm/bootstrap.py","daydream/llm/format2.py","daydream/objects.py","daydream/parser.py","daydream/pronouns.py","daydream/retell.py","daydream/rules.py","daydream/skills/effects.py","daydream/toons.py","daydream/verbs.py","daydream/version.py","daydream/worldstate.py","daydream/worldverbs.py","migrations/013_world_state.sql","migrations/014_event_recipient.sql","migrations/015_put_verb.sql","tools/assemble_world.py","tools/ws_playthrough.py","tools/zork_oracle.py","web/assets/main.js","web/index.html"],"block":0,"warn":0,"note":1} -->
