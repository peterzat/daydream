# SECURITY.md

## Security Review — 2026-09-27 (scope: paths)

**Summary:** Path-scoped audit of the pivot turn (The Village of Lost Hours):
the 111 files changed since the last review (`e613cef`..`529398b`, 68
commits; three of the files are deleted at HEAD). About 7,700 lines are
engine code: the story layer (story, knowledge, collect, village, director,
dialogue, variants), the raw input log, dreams, refresh, the play bridge,
prebake, the new snapshot fields, and the SPA's book, topic chips, and
while-you-slept leaf. The model-facing surfaces hold up. Grounded dialogue
dispatches no effects, and its beat choice is an enum re-checked at commit.
The twelve story effect kinds are rule-only. Per-player finds are filtered
out of other players' scope. The new SPA surfaces render through
`textContent` or `escape`. The three gaps all come from player-controlled
text reaching places it did not reach before: an uncapped toon name now
enters other players' dialogue prompts and a persistent, village-wide deed
fact; the dream digest hands raw player text to the in-session agent with no
marking; and the runbook commits that digest to a public repository. Net:
**0 BLOCK / 3 WARN / 2 NOTE.** Every finding was traced in code; none was
reproduced live this run.

### Findings

[WARN] daydream/api/slots.py:157-180, daydream/knowledge.py:53, daydream/dialogue.py:178-207 — a toon name has no length, character, or tone check, and the pivot carries it into other players' LLM prompts and into a persistent deed fact that spreads to every NPC.
  Attack vector: an authenticated player (a tailnet member in `tailscale`
  mode, a password holder in `public` mode) creates a toon whose name is very
  long or carries instructions. The endpoint accepts any non-empty string.
  The SPA collects the name with `window.prompt`, and a direct POST passes
  the CSRF gate as a non-browser client. The player then plays the normal
  onboarding: ask Tace about the first winding, then wind the small clock.
  That fires the authored `first-winding` deed
  (`worlds/lost-hours/arcs/00-prologue.json:83-89`), which `add_fact` stores
  with the raw name baked into its text and spreads to every NPC after 60
  minutes. From then on:
  - Every voice-sheet dialogue prompt, for any player, includes up to 14
    known facts, with other players' deeds ranked ahead of authored lore
    (`dialogue.py:204-207`, `knowledge.py:126-159`), outside the
    `<player_input>` wrapper. A name long enough to push the prompt past the
    served context window (`--max-model-len 8192`) makes vLLM reject the
    request. `acompletion_json` turns any backend error into
    `LLMUnavailable` (`llm/client.py:119-124`), and `dialogue.talk` then
    narrates the foggy outage line (`dialogue.py:414-417`). Free-form talk
    with every NPC fails for every player. Deterministic play (topics,
    verbs) keeps working.
  - The fact is a worldstate row. It survives restarts, and
    `toons.delete_slot` (`toons.py:334`) does not remove it, so deleting the
    toon does not help. Recovery is a DB repair, a snapshot restore, or
    `world reset`.
  - Co-located names enter the same prompt directly (`WHO IS HERE`,
    `dialogue.py:178, 200`). Leaving the dream keeps a toon in its room
    (`kick_slot`), so a long-named resting toon affects that room even
    without the deed. The parser's scope list carries the same names
    (`parser.py:757-767`, pre-existing).
  - A shorter crafted name is a cross-player prompt-injection channel into
    other players' NPC replies. It is not role-separated, not length-capped,
    and not banlist-checked, which are the three premises of the accepted
    dialogue-injection risk. Output stays constrained (banlist-scanned text,
    an `advance` limited to the victim's own open beats and re-checked at
    commit), so the content half is low impact among friends.
  Evidence: `slots.py:157-160` checks only for a non-empty string, while
  `appearance_seed` beside it gets a 300-character cap and the banlist
  (`slots.py:166-178`). `toons.create_toon_in_slot` inserts the name
  verbatim (`toons.py:222-237`). `knowledge.py:53` renders `{actor}` with
  the raw name into the stored fact. The same name reaches the dream digest
  as a markdown heading (`dream.py:559`; see the next finding). This is not
  the accepted "unbounded slot-create body" risk: that entry is about request
  size, and this is about where the name now travels. Traced in code, not
  reproduced live; the context-window step relies on vLLM refusing prompts
  longer than `max_model_len`, which is its standard behavior.
  Remediation: validate `name` at create the way `appearance_seed` is
  validated: a short cap (32 to 40 characters), control characters and
  newlines rejected, banlist-checked, 400 otherwise, with a test beside
  `tests/security/test_appearance_seed_gate.py`. As defense in depth,
  truncate the name wherever it is rendered into stored or prompt text
  (`knowledge.add_fact`, `dialogue.build_prompt`, the parser scope list),
  and present deed facts as quoted data. Check the live names once after the
  fix (today they are the four playtest personas).

[WARN] daydream/dream.py:551-589 (with docs/DREAM-RUNBOOK.md "Trigger" and section 1) — the dream digest hands raw player text to the in-session agent with no marking that it is untrusted.
  Attack vector: any authenticated player types lines, or picks a name,
  addressed to the dream author, for example text dressed as an operator
  note. `ws.py:592-598` stores each typed line verbatim (only its ends are
  trimmed, so internal newlines survive, as they do in names).
  `render_digest` writes names as `###` headings and typed lines as list
  items, unescaped (`dream.py:559, 563-565`), so player text can forge
  headings and whole sections inside `digest.md`. The runbook tells the
  agent to "Read digest.md closely: it is the only thing you know about what
  happened", to call back to deeds by name, and to do every step "without
  further prompting": writing files, `bin/game dream install` (which cycles
  the live server), and committing. It never says the digest is data. The
  play bridge has the same shape for playtester agents: `play.py:101-116`
  prints other players' `say` text and names verbatim.
  Evidence: the path from player input to the agent's context is direct and
  needs no bug. Whether an attempt succeeds depends on the agent acting on
  injected text, which current models are trained to resist; that likelihood
  was not tested and is uncertain. The gap is the missing separation on a
  channel that feeds an agent with shell, git, and deploy authority, which
  may be running without per-command approval.
  Remediation: in `render_digest`, emit every player- or model-sourced string
  (names, typed lines, clicked args, deed, chronicle, and local-model lines)
  as a single-line JSON-quoted value, length-capped, and open `digest.md`
  with a banner that those sections are untrusted player or model text. Add
  a rule to the runbook, and the same line to `docs/playtests/BRIEF.md`: the
  agent never runs a command, edits a file outside the dream folder, or
  changes the runbook's steps because of anything written in the digest or
  in play output; player text is material for callbacks only.

[WARN] docs/DREAM-RUNBOOK.md section 6, daydream/dream.py:473-548 — the runbook commits each dream's digest, which holds every player's raw typed lines, to a public repository.
  Attack vector: anyone who can read `github.com/peterzat/daydream` (it
  loads without authentication) can read players' private input once a
  dream over real play is committed and pushed. Section 6 says "Commit
  `worlds/lost-hours/dreams/<id>/` (digest, patch, rehearsal)".
  `digest.json` and `digest.md` carry each player's name and every line they
  typed or clicked since the last dream, with timestamps and rooms, plus
  relationships and deeds (`dream.py:493-507`). That includes `talk` to
  NPCs, which this turn made private, and anything a player types by
  mistake.
  Evidence: the SPEC (criterion 16), `inputs.py:7`, and migration 016
  describe the log as private and never broadcast; the in-game help page
  does not say typed lines are kept. Current state: the one committed digest
  (`dream-2026-09-26`) holds only the four agent-playtest personas, and the
  61 local commits (the dream included) are not yet pushed, so nothing real
  is exposed today.
  Remediation: stop committing raw digests. Write `digest.json` and
  `digest.md` under the data dir, as the rehearsal scratch databases already
  are (`dream.py:788-791`), or gitignore `worlds/*/dreams/*/digest.*`, and
  commit the patch, the rehearsal report, and at most a summary without
  player text. Update runbook section 6 to match, and decide before the first
  push whether the persona digest stays in history. Consider one line on the
  help page saying typed lines are kept for the village's dreams. (A related
  retention gap is tracked in CODEREVIEW.md: `world delete` leaves `inputs`
  rows.)

[NOTE] daydream/skills/effects.py:186-197, 321-349, daydream/skills/data.py:289 — a model-authored narrate keeps the new `variants` and `others` fields, which the data-skill output banlist never reads.
  Attack vector: none in the live world today. The only `origin="llm"`
  producer is the data-skill pipeline. The live DB has no skill rows,
  format-2 worlds cannot author room data skills, and every Lost Hours NPC
  talks through `dialogue.py`, which emits no effects. In a format-1 world
  (the `bunny.json` fixture) or after `bin/game world skill add`, a player
  steering the model could get unscanned text narrated: `variants` replaces
  the scanned `text` (`effects.py:321-328`), and `others` is broadcast to the
  room (`effects.py:349`).
  Evidence: `_sanitize_llm_effect` returns a narrate unchanged
  (`effects.py:197`); `_narrative_text` scans `text`, `seed`, `name`, and
  `mood` only (`data.py:289`); no test under `tests/security/` covers these
  fields. `to` and `room` on the same path fall under the accepted
  unscoped-target risk.
  Remediation: the fix proposed in the matching CODEREVIEW.md WARN (reduce an
  `origin="llm"` narrate to `kind` and `text`, with `to` allowed only as
  `@actor`), plus `others` and `variants` in `_narrative_text` for defense in
  depth, with a regression test under `tests/security/`.

[NOTE] daydream/parser.py:176, 207-224, 641, daydream/api/ws.py:598, 620, 658, 840 — carried forward from 2026-07-02 and re-verified: a WS `input` frame still has no length cap and no cap on segments or expanded commands, and the pivot adds sinks for the full line.
  Attack vector: an authenticated session sends oversized or long-chained
  lines. New this turn: the raw input log stores each line verbatim
  (`ws.py:598`), command frames store `verb` and `args` uncapped
  (`ws.py:840`), the private chatter reply echoes the whole line into the
  event log (`ws.py:658`), and a THEN chain of talk segments runs one
  dialogue round per segment. Frames are bounded only by the WebSocket
  server's message limit.
  Evidence: `_segments` splits on THEN and periods with no count limit
  (`parser.py:207-224`), each segment parses in turn (`parser.py:176`),
  AND-lists expand per name (`parser.py:641`), and `_handle_input` executes
  every parsed command (`ws.py:620`). Authenticated-only, recoverable, no
  privilege gain.
  Remediation: cap typed input (1,000 to 2,000 characters) at the WS boundary
  before `inputs.record`, cap segments and expanded commands per line, and
  cap `verb` and `args` in command frames.

Traced and cleared this run (not findings):

- **Per-player finds stay private.** `objects.in_scope` drops things
  `private_to` another toon (`objects.py:221, 237`), snapshots and `look` use
  `contents_for` (`ws.py:191`, `verbs.py:556`), and `collect.collect`
  re-checks the owner (`collect.py:154-156`). The "take all" candidate list
  skips the filter (`parser.py:668`, tracked as a CODEREVIEW.md WARN), but
  the executor refuses with a generic "You don't see that here", which shows
  that something is present, not what.
- **Grounded dialogue is narrow.** It dispatches no effects. `advance` is a
  JSON-schema enum and is checked against the offered ids
  (`dialogue.py:236-241, 333-334`), then re-checked at commit
  (`story.py:399`). The line is banlist-scanned and capped at 420 characters
  (`dialogue.py:330-332`), and replies to players are private. A player's
  stored lines (capped at 300 characters, `story.py:174`) reach only that
  player's own later prompts.
- **Director and drift.** The director's ranking is an enum over eligible
  authored storylets, and an out-of-set answer is ignored
  (`director.py:252-265`); the chronicle lines it sees are capped at 120
  characters. Drift variation takes authored lines only and validates the
  result.
- **Story effect kinds are rule-only.** All twelve are in `RULE_ONLY_KINDS`
  (`effects.py:110-116`), so they are outside `DEFAULT_KINDS` and talk's
  allowlist. Only authored rules, beats, endings, topics, storylets, and page
  rewards dispatch them, under `RULE_KINDS`.
- **Per-player state and the input log.** `rel:`, `pq:`, and `talk:` keys
  use server-issued ids. A snapshot carries only the controlled player's
  journal, book, and while-you-slept note (`ws.py:289, 296-297`). Nothing in
  the API reads the `inputs` table: only the WS writes to it, and only the
  dream CLI reads it.
- **SQL and XSS.** New queries are parameterized (`inputs.py`, the `except`
  filter in `events.py`, `dream.py`, `refresh.py`, `village.py`,
  `dialogue.py`). The new SPA surfaces (topic chips, book, while-you-slept,
  folio) use `textContent`; the say line's new `to` field goes through
  `escape` (`main.js:606`); `linkifyEntities` escapes before it wraps.
- **Operator tooling.** `dream`, `refresh`, `prebake`, `walkthrough`,
  `analyzer`, `model_eval`, `assemble_world`, and the new `bin/game` verbs
  (`dream`, `play`, `prebake`, `world refresh`, `world patch`) take no
  network input. `bin/game` quotes its variables, and the prebake contact
  sheet escapes labels and prompts.
- **Play bridge credentials.** Each named session's cookie (a session with
  no expiry) is saved at `~/data/daydream/play/<name>.json` with the default
  0664 mode (`play.py:54-55`). The 0750 home directory and the single human
  account contain it; writing it 0600 would match the session secret.
- **Secrets and PII.** None in the scoped files or in the last three commits
  of `.env.example`, `bin/game`, `play.py`, and `slots.py`. `.env` has never
  been committed. `docs/pretty/lantern-bridge.png` carries only the ComfyUI
  prompt graph. The model-eval results hold no host paths or addresses.
- **Prior residual.** Reads of `seed` and `presence_text` still assume
  strings (`Toon.from_object`, the presence greetings in `ws.py`). No model
  output can write them this turn: dialogue emits no effects, and the
  data-skill default excludes `set_property`.

Open items outside this scope (carried forward, not re-verified this run):
the per-install session secret written before its chmod to 0600
(`daydream/config.py:161-162`, NOTE since 2026-07-07), and the CI workflow's
mutable action tags and missing `permissions:` block
(`.github/workflows/test.yml`).

### Accepted Risks

Durable register carried forward (trust model: single shared password,
tailnet membership as the outer gate, no per-user roles; loopback is the
admin boundary). Factual updates only: talk lost `set_property` in
`6b1af0f`, and the canonical world's NPCs now talk through the voice-sheet
path, which emits no effects.

- **LLM-emitted effects take an unscoped, LLM-chosen target id** on the
  data-skill paths: `talk` for NPCs without a voice sheet
  (narrate/set_mood/spawn_object, spawns sanitized since `a932d6e`) and
  room-affordance data skills (`DEFAULT_KINDS`, narrowed by each skill's
  declared kinds). Neither path exists in the live Lost Hours world. Rule,
  growth, clock, and story paths do not share this shape. v2
  `skills-authoring-and-security`.
- **Shared-world mutation: any authed session may drive verbs on any
  in-scope shared object** and repaint rooms while the regen UI is on
  (dev default). Intended single-shared-world co-op design; per-session
  ownership is v2. State-changing POSTs are CSRF-origin-gated; `/ws` is
  Origin-gated and auth-gated.
- **Parser raw player input is not role-separated** before the grounding
  LLM call; output is strictly re-grounded to a closed verb + in-scope id.
- **Tailscale-mode auth is tailnet membership** (`auth.is_authed` returns
  True unconditionally in `tailscale`; the AccessMiddleware CGNAT
  `100.64.0.0/10` + loopback check is the real gate). Cookie
  `https_only=False`; `/status/*` + `/cache/...` session-unauthenticated
  but AccessMiddleware-gated.
- **NPC dialogue / growth prompt-injection via player input**: role-
  separator wrapped, length-capped, input-banlist-checked; LLM output
  structured, validated, and output-banlist-scanned before mutation.
  (Refusal `reason` is narrated without an output-banlist pass in
  `data.py`, `growth.py`, and `dialogue.py`; renders through escaped sinks.)
  Player names are the exception found this run; see the first WARN.
- **Operator-trust world envelopes + `bin/game`**: `world load`/`reset`
  content (verbs/rules/fuses/daemons/growth/drift pools/dialogue),
  `reset`'s `rm -rf`, `.env`/`secrets.env` sourcing, the `0.0.0.0` bind,
  the deprecated `bootstrap_world` LLM path reading `ANTHROPIC_API_KEY`
  (design-time only). None take network input.
- Unbounded slot-create body (size; the prompt-content half was the
  2026-07-07 WARN, gated in `21fed3f`) + liveness-gated claim takeover;
  missing CSP / `X-Content-Type-Options` on the SPA shell (XSS sinks are
  escaped); event queues bounded (256, drop-oldest).

---
*Prior review (2026-09-26, paths, commit `e613cef`): the 8 files after the
model re-evaluation turn (default-model pin, bounded `vllm-down`,
`appearance_seed` read guard). 0 BLOCK / 1 WARN / 0 NOTE: talk's
`set_property` let the dialogue model write any key on any object (a
game-wide lockout through a room seed, a per-entry disconnect through
`presence_text`), resolved in `6b1af0f`; the pivot's two side findings (LLM
spawns carrying authored-only properties, data skills ignoring their
declared kinds) were resolved in `a932d6e`.*

<!-- SECURITY_META: {"date":"2026-09-27","commit":"529398b07178b712146bd0ac6df3cd53dba4675a","scope":"paths","scanned_files":[".env.example","bin/game","daydream/analyzer.py","daydream/api/slots.py","daydream/api/ws.py","daydream/collect.py","daydream/dialogue.py","daydream/director.py","daydream/dream.py","daydream/drift.py","daydream/events.py","daydream/gpu/arbiter.py","daydream/growth.py","daydream/inputs.py","daydream/journal.py","daydream/knowledge.py","daydream/llm/bootstrap.py","daydream/llm/client.py","daydream/llm/format2.py","daydream/llm/safety.py","daydream/llm/story_format.py","daydream/model_eval.py","daydream/objects.py","daydream/parser.py","daydream/play.py","daydream/prebake.py","daydream/refresh.py","daydream/rules.py","daydream/server.py","daydream/skills/data.py","daydream/skills/effects.py","daydream/story.py","daydream/toons.py","daydream/variants.py","daydream/verbs.py","daydream/version.py","daydream/village.py","daydream/walkthrough.py","daydream/worldclock.py","daydream/worldstate.py","docs/model-eval/after-2026-09-26/results.json","docs/model-eval/before-2026-09-26/results.json","docs/pretty/lantern-bridge.png","migrations/016_inputs.sql","migrations/017_ask_verb.sql","tests/baselines/dialogue_refusal_probe.ratified.json","tests/baselines/growth_compose_moth_attic.golden.json","tests/conftest.py","tests/data/fixture_walkthroughs/moth-home.json","tests/data/fixture_walkthroughs/moth-kept.json","tests/data/story_fixture.json","tests/drift/aesthetics/portrait_bell.json","tests/drift/aesthetics/portrait_tace.json","tests/drift/test_dialogue_refusal_probe.py","tests/drift/test_growth_compose.py","tests/drift/test_journal_probe.py","tests/drift/test_parser_grounding.py","tests/model_eval/canon.json","tests/security/test_appearance_seed_gate.py","tests/security/test_data_skill_allowlist.py","tests/security/test_llm_spawn_gate.py","tests/security/test_set_property_gate.py","tests/story_helpers.py","tests/test_analyzer.py","tests/test_arbiter.py","tests/test_dialogue.py","tests/test_dream.py","tests/test_drift.py","tests/test_effects.py","tests/test_frontend_story.py","tests/test_generative.py","tests/test_growth.py","tests/test_inputs.py","tests/test_lost_hours_prologue.py","tests/test_lost_hours_world.py","tests/test_model_eval.py","tests/test_no_cloud_keys.py","tests/test_no_world_literals.py","tests/test_objects.py","tests/test_parser.py","tests/test_parser_zork.py","tests/test_play_bridge.py","tests/test_prebake.py","tests/test_quest_playthrough.py","tests/test_refresh.py","tests/test_soft_stakes.py","tests/test_starting_room.py","tests/test_story.py","tests/test_verbs.py","tests/test_walkthroughs.py","tests/test_warmth_and_variety.py","tests/test_world_integrity.py","tests/test_ws_forge.py","tests/test_ws_iris.py","tests/test_ws_rook.py","tests/test_ws_session.py","tools/assemble_world.py","web/assets/main.js","web/assets/style.css","web/index.html","worlds/clockmakers-loft.json","worlds/lost-hours.json","worlds/lost-hours/cast/bell-mott.json","worlds/lost-hours/cast/others.json","worlds/lost-hours/cast/tace.json","worlds/lost-hours/dreams/dream-2026-09-26/patch.json","worlds/lost-hours/regions/01-clocktower.json","worlds/lost-hours/regions/02-square.json","worlds/lost-hours/regions/03-lane.json","worlds/lost-hours/regions/10-residents.json","worlds/lost-hours/world.json"],"block":0,"warn":3,"note":2} -->
