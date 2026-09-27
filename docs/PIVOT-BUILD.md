# Pivot build log: The Village of Lost Hours

Working record for the SPEC 2026-09-26 turn. The contract is SPEC.md; the
design record is docs/PIVOT.md. This file holds the engine design decisions
made while building (operator autonomy, PIVOT section 8.6) and the running
state, so a fresh context can resume. Newest state at the bottom.

## Engine design decisions

Naming note (read first): several identifiers below changed during the
build. Story sections are validated in `daydream/llm/story_format.py` (not
`format2.py`); `minutes` became `collectibles`, `grant_minute` became
`grant_collectible`, `pq:<toon>:minutes` became `pq:<toon>:collected`, and
the `minutes_found` condition became `collected`. The code and
docs/canon/AUTHORING.md are authoritative.

**Where story data lives.** Format 2 gains authored sections, validated
fail-loud by `daydream/llm/format2.py` and stored as worldstate `def:*` rows:
`arcs`, `facts`, `storylets`, `minutes`, `pages`, `time`. Per-NPC story data
rides toon properties: `voice` (the voice sheet: pronouns, sheet, habits,
samples, wants, never), `schedule`, `topics`. A dream patch merges into these
blocks additively.

**Arcs, beats, endings.** An arc is `{title, kind: guest|keeper|village,
summary, guest?, arrival?, opens?, beats: {id: beat}, endings: {id: ending}}`.
Arc runtime state is worldstate `arc:<id>` = `{status, opened_day, opened_at,
beats: {id: {at, by}}, helpers: [toon ids], ending?, closed_day?}`. Beats
advance only through the `advance_beat` effect, which re-checks the beat's
`if` conditions and `after` prerequisites at commit (a stale beat changes
nothing). Endings close through `close_arc`; exactly one ending per arc may be
timed (`after_days`), and the dusk pass closes it when the arc has sat open
that long. No ending is a fail state.

**Talk moves story.** A beat with an `npc` is talk-advanceable and must author
a `topic` (validator-enforced), which is its deterministic producer: the
`ask` verb (`ask bell about the yawning stranger`, or a clickable topic chip)
advances it with zero LLM calls. The LLM talk path offers the open beats for
that NPC as a JSON-schema enum on an `advance` field; an advanced beat speaks
its AUTHORED text (the model chose the moment, the author wrote it).

**Per-player state.** Worldstate KV, no migration: `rel:<npc>:<toon>` (int),
`pq:<toon>:<name>` (per-player flag/counter/value), `talk:<npc>:<toon>`
(last exchanges). World flags, counters, and score keep their existing keys
and behavior. New rule conditions: `rel`, `pflag`, `pcounter`, `beat`, `arc`,
`ending`, `phase`, `day`, `knows`, `minutes_found`; new rule effects:
`adjust_rel`, `set_pflag`, `adjust_pcounter`, `advance_beat`, `open_arc`,
`close_arc`, `add_fact`, `grant_minute`, `move_toon` (NPC walks with a line).

**Facts and gossip.** Authored facts `{text, known_by: [npc]|"all", if?}`.
Deed facts are created at runtime by `add_fact` with `{actor}` substituted by
the player's name, stored as worldstate `fact:<key>`, and spread by an
authored schedule of stages `[{to: [npcs], after_minutes: N}]`. "Knows" is
evaluated lazily against the wall clock, so spreading needs no background
task, survives restarts, and is testable with a fake clock.

**Real time.** `daydream/worldclock.py` owns wall-clock time (fake-able for
tests), the world's `time` config (tz + phase boundaries), the village day
(days since the clock started), and the catch-up pass. Before the start flag
is set the village has no day cycle. Dusk processing is keyed by local date
(`dusk_done:<date>`), so a restart neither skips nor double-fires; missed
days catch up in order (capped at 7). The pass runs from a background loop
and opportunistically at the head of every command.

**Director.** Eligible storylets (arc arrivals at dusk, small day/night
events) are enumerated from authored data. With the LLM available, one call
in the arbiter's new `background` class ranks them; the class never delays a
player-facing call (it does not count against the LLM cap, vLLM's
max-num-seqs is 4 for exactly this), is admitted only when no render or LLM
call is queued, and holds at most one slot. An LLM answer outside the
eligible set is treated as an outage: nothing it named is applied and the
seeded deterministic choice stands. Story rolls use `worldstate.rng_stable`
(seed + purpose, no turn), keyed on date and entity.

**After-hooks.** A rule may author `"after": true`: it runs only after the
verb's normal handling succeeded (engine handlers now return success) and
never suppresses it. Before-rules are unchanged, so Zork is untouched.

**Private things.** `properties.private_to = <toon id>` makes a thing visible
and in scope only for that toon (daily stray minutes, a newcomer's own small
clock). Scope, snapshots, and look all honor it.

**Stray minutes.** Authored `minutes` (id, name, text, page) and `pages`
(title, reward). Each player gets their own daily finds (private things,
seeded by date + toon), independent of every other player. Taking one
catalogues it in the per-player book (`pq:<toon>:minutes`) and removes the
object; completing a page applies its authored reward once.

**Dreams.** `daydream/dream.py`: `digest` (deterministic, from events + the
new raw-input log since the last dream marker), `patch` (validate fail-loud
with zero writes; additive; id collisions rejected; idempotent by patch id;
never touches player-created objects or per-player state), `rehearse`
(snapshot live, apply to a side copy, run the analyzer and every walkthrough
against a fresh base+patches world, run the patch's own walkthroughs on the
side copy), `install` (down, apply to the current live DB, up). Applied
patches are recorded in worldstate so fresh rebuilds replay the chain.

**Walkthroughs.** `daydream/walkthrough.py` is the shared replayer (tests,
rehearsal). Datasets live in `worlds/lost-hours/walkthroughs/`, one per arc
ending plus the prologue and the latecomer, with `clock` steps for the fake
clock and `summon` steps that open an arc directly (so an arc's walkthrough
tests the arc, not the director's choice).

**Security (criterion 19).** LLM-originated `spawn_object` keeps only name,
seed, aliases, location, and provenance; `properties`, `verbs`, `readable`
are dropped. Room data skills dispatch under their declared allowlist.

## Order of work

1. Security fixes; raw input log.
2. model-eval canon suite + opener metric; BEFORE run on the current prompt.
3. Story primitives (worldclock, story, knowledge, director, minutes,
   private things, after-hooks, ask verb, format-2 extensions, analyzer,
   walkthrough replayer).
4. Grounded dialogue (voice sheets, state injection, advance enum), warm
   sampling, authored-first drift, variant narration, AFTER run.
5. World: prologue + latecomer + Pim end to end, then the rest of the arc
   library, cast, rooms, minutes via author subagents, graded by fresh
   subagents. Loft retired (tests ported).
6. Dreams: digest, patch, rehearse, install, runbook; while-you-slept;
   chronicle (the Ledger of Returned Hours).
7. SPA: topics, book, while-you-slept leaf, time ribbon.
8. Art pre-bake + grading. Live reset (archive Zork first).
9. `bin/game play`; agent playtest day; fixes.
10. First dream; later agent session observes the callback.
11. Docs (WHIMSY stories, canon bible, README, CLAUDE.md, prompts.md).
12. Operator gate.

## State

- 2026-09-26: plan written; baseline medium tier green (1234 passed).
- 2026-09-26: security fixes (a932d6e); raw input log (2c1110e); canon suite +
  BEFORE run: 20/34 canon replies contradict, 8 pronoun breaks, opener max 6,
  JSON 100%, dialogue p50 3.15 s (63b1229, docs/model-eval/before-2026-09-26);
  story primitives (c2f9780); grounded dialogue, authored-first drift, warm
  prose (c88b376). Next: walkthrough replayer + analyzer, then the world.
- 2026-09-26 (later): walkthroughs + analyzer (b09c5c3); the world's working
  core (06ecbb0: canon bible docs/canon/LOST-HOURS.md, 17 rooms, 9 residents,
  prologue, first winding, Pim); authoring guide docs/canon/AUTHORING.md;
  dreams + play bridge (d5ea14b); SPA story surfaces (35ac88e); the loft
  retired (d707a4e, WORLD_VERSION 1.5); 172 stray minutes on 12 pages
  (c314076); soft stakes in WHIMSY + banlist (4005de3); prebake (59a4aa4);
  dream runbook docs/DREAM-RUNBOOK.md; prompt ledger; session export.
  In flight: six author subagents in worktrees (arcs: extra-hour+rain-wait,
  summer+margin, nell-evening+letters, the three keeper arcs; voice sheets;
  minutes MERGED). Next: merge arcs + voices, critic pass, AFTER model-eval,
  remove config.under_construction, archive Zork + reset live + prebake +
  grade art, agent playtest day, first dream, README/CLAUDE.md, operator.
- 2026-09-26 (evening): arcs + voices merged (f59d9bc: the world complete,
  criterion 1 scale test armed); art pre-graded on a scratch copy (efc57bd:
  four room seeds rewritten, reseeds r-clocktower=5, t-quill=11). Two blind
  critic passes over all eleven arcs, the cast, and the minutes; two fixer
  passes in flight (arcs 00-05 + cast/regions; arcs 06-10). The critic's
  twelve weakest minutes rewritten and six relationship-only pages given a
  keepsake. Engine: drift buckets keyed `<phase>@<room>` (a keeper asleep in
  bed, awake on a hill); phase buckets never borrowed as a talk gesture.
- 2026-09-26: the operator adopted **"the local GPU is the game's reflexes,
  not its voice"** as the framing for runtime generation (docs/REFLEXES.md,
  README top). Two obligations follow: (a) the playtest report tags each line
  players read as authored or local and shows where defects and best moments
  cluster; (b) **before calling the turn ready to push, a significant review
  of README and the design docs** (PIVOT, CLAUDE.md, WHIMSY, DESIGN, ROADMAP,
  canon bible, REFLEXES) through this framing and the pivot, then the full
  test run. Operator's words: "Use this addition, and our pivot, to
  significantly review our README and design docs when you're done building
  all of it (before you think we're ready to push, and then test)."
- 2026-09-26 (night): AFTER model-eval committed (criterion 10: canon 20 -> 0,
  pronoun 8 -> 0, openers 6 -> 1, p50 3.15 -> 2.24 s; the canon scorer now
  skips authored gesture lines, both runs rescored). Canon bible section 7
  rewritten as shipped. Live world reset to Lost Hours (Zork archived) and
  prebaked (32 targets). **Agent playtest day** (17:45-18:02 PT, four
  personas at once, ~500 commands, no server errors): 15% of narrations were
  local-model lines, and nearly every worst line was one of them. Fixes:
  multiplayer routing (private "you" lines + `others`, private conversations
  with a bystander line, once-per-session greetings), the parser (utterances
  stay whole, deterministic say/talk), select-don't-write topic routing,
  prompt and reranker changes, the play bridge, rest-return of world objects,
  never_words, question_hint, provenance tags, and a large world-data pass
  (docs/playtests/2026-09-26/SUMMARY.md). New tool: **`bin/game world
  refresh`**, a content deploy that keeps play (a reset is a new village; a
  dream is additive only), used to carry the fixes into the played world.
  **The first dream** (dream-2026-09-26) is live: callbacks to all four
  players by name, the grown room furnished; a returning agent session is
  recording what it observes (criterion 18). Remaining: the observed.md
  record, the README/design-doc review (a fresh reviewer is critiquing
  first), tier_long with the server down, and the operator's morning play.
- 2026-09-27 (late): returning agent session observed the first dream's
  callbacks (observed.md; criterion 18, SPEC 21/22) and its follow-up fixes
  landed (reclaim keeps location, greetings remembered on the toon, examine
  never doubles a name, the `actor` condition). tier_long found and fixed an
  exemplar near-copy in growth (rejected now, one warm retry) and two probe
  bugs; full `bin/game test long` green (1471). README rewritten and the
  design docs reviewed against the pivot and "reflexes, not voice" (a fresh
  reviewer critiqued first). Final `world refresh` proved dreams and refresh
  compose on the live world. **Waiting on the operator's playtest
  (criterion 22)**; findings go to docs/playtests/2026-09-27/operator.md.
