# Pivot build log: The Village of Lost Hours

Working record for the SPEC 2026-09-26 turn. The contract is SPEC.md; the
design record is docs/PIVOT.md. This file holds the engine design decisions
made while building (operator autonomy, PIVOT section 8.6) and the running
state, so a fresh context can resume. Newest state at the bottom.

## Engine design decisions

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
