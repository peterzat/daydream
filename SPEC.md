## Spec — 2026-09-26 — The Village of Lost Hours: the pivot turn

**Goal:** Turn daydream from a platform carrying one fifteen-minute quest into
The Village of Lost Hours: a shared, persistent, coffee-break world whose story
arcs respond to what players do. Opus authors the story (at design time, and
in-session "dreams" that read what players did), the local 9B performs it live
with real game state injected, and the deterministic engine keeps it honest and
completable. The turn ends with the operator playing the world the morning
after its first dream.

### Acceptance Criteria

- [x] **1. The Village of Lost Hours is the live world.** A format-2 world
  replaces the Clockmaker's Loft as the default for `bin/game world reset` and
  is installed as the live world (the live Zork world archived first). It holds
  at least 15 rooms, at least 8 resident NPCs (guests not counted), at least 10
  arcs (at least 6 guest arcs, the 3 keeper arcs for Tace, Bell, and Mott, and
  at least 1 cumulative multiplayer arc), and at least 150 authored stray
  minutes. A static analyzer, run in tier_short, proves every room reachable
  and every arc solvable (every beat reachable, every needed item obtainable),
  and fails on a deliberately broken fixture.

- [x] **2. Every arc ending is a contract.** Every arc has at least two
  endings, chosen by what players did or by elapsed real time, and none is a
  fail state (no death, no lost progress, no player locked out of the world's
  content). Each ending ships a walkthrough: a command dataset replayed under a
  zero-LLM spy that ends at an asserted world state, run in tier_medium. The
  whole world is therefore completable with vLLM and ComfyUI down.

- [x] **3. The prologue starts time, and latecomers still get a beginning.**
  The existing clock quest opens the world: before the great clock is mended the
  village has no day cycle; mending it starts time, and the first dusk brings
  the first guest. A player who first arrives after someone else has already
  mended the clock still gets a complete authored first session, proved by a
  walkthrough for a second player joining a post-prologue world.

- [x] **4. Real time moves the village.** Each world keeps a wall-clock day
  (dusk time configurable). Authored dusk events fire once per real day even
  with no one connected; a server restart neither skips nor double-fires a day;
  NPCs follow authored schedules between rooms by time of day. Tests drive all
  of this with a fake clock. Story randomness keys on stable purposes (date and
  entity), never on turn index.

- [x] **5. A background director chooses what happens.** Which eligible
  arrival comes at dusk, and which small NPC events occur, are chosen among
  authored storylets. When the local LLM ranks the choices, it runs in a
  background arbiter class that never delays a player-facing call and never
  starves a queued render (tested); with vLLM down the director falls back to a
  seeded deterministic choice, and a choice outside the eligible set changes
  nothing.

- [x] **6. Talk moves the story.** Each NPC exposes the open beats it can
  advance (authored, condition-gated). A talk turn's single LLM call returns the
  spoken line plus at most one beat id chosen from the enumerated open beats,
  and the engine applies that beat's authored effects deterministically. An id
  that was not offered, or a beat whose conditions no longer hold at commit,
  changes nothing. Every talk-advanceable beat is also reachable through a
  deterministic producer (a clickable ask-about topic or an exact phrasing), so
  walkthroughs need no LLM.

- [x] **7. NPCs know things, and the village talks.** NPC knowledge is data:
  authored facts plus facts created by player deeds that name the player. A
  deed fact spreads from NPC to NPC on an authored real-time schedule, and an
  NPC's dialogue context includes what it knows. Tested: after player A gives
  something to Tace, Bell's dialogue context names A's deed after the gossip
  interval and not before.

- [x] **8. Relationships are per player.** Each (NPC, player toon) pair has
  relationship state that rules and effects can read and change and that the
  NPC's dialogue context receives. Two players' relationships with the same NPC
  are independent; world-scoped flags, counters, and score behave as before.

- [x] **9. Rules can follow, not only replace.** A rule can run after a verb's
  normal handling succeeds without suppressing it. The Zork walkthrough still
  ends at exactly 350 in tier_medium, and Zork is frozen: no edits under
  `worlds/zork1*` or `tests/data/zork1_walkthrough.json` this turn.

- [x] **10. Dialogue is grounded (measured).** The dialogue prompt carries the
  NPC's authored voice sheet (including pronouns), the player's name, what the
  NPC knows, its relationship with this player, its current wants, and its
  recent exchanges with this player. `bin/game model-eval` gains a canon suite
  (questions whose answers are fixed by authored facts, scored mechanically for
  contradiction) and an opener-distinctness metric. A before run (the current
  production prompt, recorded this turn before any dialogue change) and an
  after run are committed. After: zero canon contradictions on the suite; no
  more than two of any NPC's dialogue-suite replies share their first six
  words; JSON validity at least 99%; dialogue p50 no worse than 3.5 s.

- [x] **11. Authored voice leads, and nothing repeats verbatim.** Drift for an
  NPC with authored pools emits authored lines first (the LLM may vary them);
  the loft's `wind` and `listen` room skills are replaced by world-declared
  affordances that narrate authored variants; no NPC beat or affordance repeats
  the same line verbatim within its last several tellings in a room (tested).
  Prose surfaces run warm (temperature above 0); the parser stays deterministic.

- [x] **12. A daily find for everyone.** Each player can find at least one new
  stray minute per real day regardless of what other players have collected.
  Found minutes are catalogued in a per-player book viewable from the satchel,
  and completing an authored page of the book grants something authored.

- [x] **13. Dreamseeds come from arcs, and grown rooms join the story.** Some
  arc endings grant a dreamseed. Planting still composes one room inside
  authored boundaries, and the existing growth guarantees (every failure path
  preserves the seed, direction hints, dedup) stay green. A dream can furnish a
  grown room (a resident, a hook, or a stray minute) while preserving the
  planter's phrase verbatim in its provenance.

- [x] **14. The dream works, in-session.** `bin/game dream digest` writes a
  deterministic digest of play since the last dream (raw inputs, deeds per
  player, beats advanced, arcs opened and closed, grown rooms, gossip).
  `bin/game world patch` validates a dream patch fail-loud with zero writes on
  error, applies additive content without deleting or overwriting
  player-created objects or per-player state, rejects id collisions, and is
  idempotent. A rehearsal step snapshots the live world, applies the patch to a
  side copy, and replays every walkthrough against it; only if all pass is the
  patch installed on the live world, and installing never discards a player
  action taken meanwhile (a brief restart that applies the proven patch to the
  current live database is enough; no hot-patch mechanism is required). A
  failed rehearsal installs nothing, and the pre-dream snapshot restores
  cleanly (tested). A runbook lets the operator trigger a dream by name in any
  Claude Code session. Dreams run in-session only; no headless or scheduled
  runs.

- [x] **15. Returning players see what changed.** A player's first snapshot
  after a dream carries that dream's "while you slept" note exactly once; the
  SPA shows it as a dismissible storybook leaf, and it does not repeat on
  reconnect. The Ledger of Returned Hours is a readable in-world book whose text
  reflects every closed arc and who helped.

- [x] **16. Every word a player types is kept.** Raw input for every command
  (free text and structured) is persisted with actor, time, and the resolved
  command; it is never broadcast to other players; the dream digest includes
  it; and a recorded session can be exported as a walkthrough dataset.

- [x] **17. Agent playtesters.** `bin/game play` lets an agent drive a live
  session through the same WebSocket path a player uses, across repeated shell
  invocations (each prints the narration caused since the previous one) and
  with several concurrent toons. Before the operator gate, at least four
  persona sessions (explorer, chatterbox, completionist, rule-breaker; at least
  two concurrent in the same world) play the live stack against the real local
  models. Each critique is recorded in a playtest log against a rubric
  (surprise, consequence, being remembered, reason to return), and every
  experience defect they surface is fixed or backlogged.

- [x] **18. The first dream happened.** After the agent playtest day, one
  dream digests that play, is authored in-session, passes rehearsal, and is
  live. It furnishes every room grown during the playtest day and calls back to
  at least one specific player deed. Its digest, patch, and rehearsal result are
  committed, and a later agent session records observing the callback in play.

- [x] **19. The security side findings are closed.** An LLM-originated
  `spawn_object` cannot carry authored-only properties (rules, growth, extra
  verbs, combat, light, container, scoring); room data skills honor their
  declared effect allowlist or are retired; each has a regression test under
  `tests/security/`, and SECURITY.md records both.

- [x] **20. Art is pre-baked and graded.** Every room and NPC portrait in the
  new world is rendered at design time through the production pipeline, graded
  by the agent against WHIMSY.md (weak renders re-seeded or reframed, verdicts
  recorded), and cached so a first entry never waits on a render. Image anchors
  and goldens that change are re-ratified deliberately.

- [x] **21. Tone and docs tell the truth.** WHIMSY.md gains a stories section
  (soft stakes, wants, gentle time, and bittersweet endings allowed; cruelty,
  horror, and grimdark still banned), and the safety banlist matches it: a
  corpus of soft-stakes lines passes, and each still-banned category still
  blocks. A canon bible (characters, secrets, voice sheets, the arc library, the
  long mystery and its answer) exists for future dreams to stay consistent.
  README's purpose sections reflect the pivot; CLAUDE.md documents the story
  layer, the dream runbook, and the in-session-only policy; `docs/prompts.md`
  lists every new or changed prompt surface; no cloud LLM key exists anywhere
  (grep-verified).

- [ ] **22. The operator plays.** The morning after the first dream, the
  operator plays the live world in a browser. Findings and the verdict are
  recorded, and experience defects are fixed or backlogged. This is the only
  criterion that needs the operator.

### Context

**Read `docs/PIVOT.md` first.** It is the approved design record: the evidence
(about 19 minutes of human play ever; every moment that landed was
Opus-authored; the local layer was texture at best), the six misalignments,
the three-tier architecture, the creative direction with worked arc sketches,
the quality-convergence instruments, and section 9's jobs for the save/load and
walkthrough machinery. Where this spec and PIVOT.md differ, this spec wins
(the operator chose the full world over a slice, and in-session-only dreams).

**Operator autonomy (2026-09-26).** Make product, design, scope-detail, and
housekeeping decisions yourself and record them in this file, PIVOT.md, or the
canon bible; do not stop to ask. Spend subscription tokens freely on creative
exploration: use subagents for parallel authoring (arcs, voice sheets, stray
minutes, the mystery) and for independent critique. Builder/verifier
separation applies to content too: an author subagent never grades its own
arcs or prose; a fresh subagent does, blind where possible.

Constraints:

- **Generation policy is absolute.** The running game calls only the local
  engines; no API key exists in runtime, tooling, tests, or CI. Opus authors
  at design time and in dreams, in-session only.
- **The 9B's job is narrow.** Select, judge, compress, and lightly voice, with
  game state injected; never invent structure. Measured facts (docs/PIVOT.md
  section 1, the model-eval runs under `~/data/daydream/model-eval/`): ~40
  tok/s single-stream, ~100 tok/s aggregate at three concurrent calls, so
  parallel calls are nearly free and serial chains are not; talk p50 ~2.7 s;
  JSON 100% even at temperature 0.8; no production call has exceeded ~1.1k
  prompt tokens of the 8192 window. Its known failure modes: invents facts it
  is not given, repeats openers at temperature 0 with enumerated template
  beats, drifts pronouns when none are stated. Author the lines that matter.
- **SDXL carries mood, not information.** Soft interiors, landscapes, and
  faces render well; hard objects do not (BACKLOG `forge-render-legibility`).
  Never make a puzzle depend on reading an object from the art.
- **Keep the engine world-agnostic.** All Lost Hours content lives in world
  data; `tests/test_no_world_literals.py` guards engine purity for Zork and
  sets the standard for any world.
- **Format facts.** Format 1 is capped at 5 rooms and 4 toons and cannot
  author rules; format 2 cannot author room data skills. `worlds/bunny.json`
  stays as the format-1 loader fixture. The region-source pattern
  (`tools/assemble_world.py`, byte-match `--check`) is available if the world
  outgrows one file.
- **Test discipline.** The medium tier is green at every commit. Tests that
  encode behavior this spec deliberately retires (the format-1 loft, the
  `wind`/`listen` skills, LLM-first drift) are rewritten to the new contract,
  with each retirement named in its commit message; never loosen a test to hide
  a regression. The Zork walkthrough is the engine's regression net for the
  rule-engine changes.
- **Determinism.** The Zork walkthrough taught that turn-keyed rolls make
  datasets brittle; key story rolls on date plus entity, as dreamseed
  propagation already does.
- **Dream installs never discard play, cheaply.** Do not install by swapping
  in the rehearsal copy (it would drop actions taken after the snapshot). The
  simple path: rehearse on the copy while the game runs, then `bin/game down`,
  apply the proven patch to the current live database, `bin/game up`. Players
  see a few seconds of the calm "the dream is sleeping" overlay, which fits a
  dream turning over. Do not build a live hot-patch endpoint for this.
- **GPU discipline.** tier_long runs and the art pre-bake happen with the game
  server down (the arbiter is in-process). Dev-mode policy allows cycling the
  server; leave a one-line note when you do.
- **Live world.** The live Zork world holds only the 68-second automated
  replay, and `archives/w-zork1-20260707-140643.tar.gz` exists; take a fresh
  archive before the reset anyway.
- **Versions and git.** Bump `WORLD_VERSION` per its discipline in CLAUDE.md.
  No release tag or GitHub release this turn; never move the `pre-pivot` tag.
  Commit locally in small increments (no Co-Authored-By trailers); push only
  when the operator asks.
- **Code pointers from the research pass.** The unrecorded security gap is
  the `properties` passthrough in `daydream/skills/effects.py` `spawn_object`
  (around line 309), reachable from `talk`; room data skills ignore their
  `effects_schema` (`daydream/skills/data.py` around line 17). LLM drift
  overrides authored pools (`daydream/drift.py`, `_tick` and `_pools_for`).
  The dialogue prompt sees only `player_input`, `actor_id`, `room_id`, and
  `memories` (`daydream/skills/data.py` around line 360). Rules replace verbs
  and never follow them (`daydream/verbs.py` around line 429). Fuses and
  daemons count commands, not seconds (`daydream/clock.py`). The event log
  stores effects but not what the player typed. `tools/ws_playthrough.py` is
  the base for the play bridge.
- **Suggested order (not binding).** Security fix and input logging; the
  model-eval canon baseline; performer fixes; story primitives; world
  authoring (parallel subagents) with walkthroughs as each arc lands; art
  pre-bake; agent playtest day; first dream; operator gate. Scale the arc
  library and stray minutes up from a working prologue plus one arc rather
  than authoring everything before anything plays.

BACKLOG entries this turn touches: `drift-variety-richer-beats` (criterion
11), `snapshot-enrichments-for-reading-room`, `per-npc-event-log-visibility-filtering`
(facts and gossip replace it), `user-authored-llm-driven-world-building-verbs`
(dreams furnish grown rooms), and the Zork and retell entries (frozen). Close or
annotate them at turn end.

---
*Prior spec (2026-07-07): daydream v1.0, the release turn. Closed 14/16;
criteria 7 (the loft reset) and 9 (the Zork playtest) were superseded by the
2026-09-26 pivot.*

<!-- SPEC_META: {"date":"2026-09-26","title":"The Village of Lost Hours: the pivot turn","criteria_total":22,"criteria_met":21} -->
