# The pivot: from platform to story (2026-09-26)

Status: direction approved by the operator 2026-09-26 ("lock in what you
want"); decisions recorded in section 8. Built 2026-09-26 (SPEC.md 21 of 22;
the operator's playtest is the last); this file is now the historical design
record, and where it differs from SPEC.md the spec wins. Unbuilt promises are
tracked in docs/ROADMAP.md ("Next"). Baseline for
diffs and reverts is the `pre-pivot` tag. Written after a full read of the docs, the engine, the model
bake-off, and the archived play data (three research passes: play forensics,
local-model capability, engine authoring surface). Every claim below about
what happened in play comes from the archived event logs and eval outputs
under `~/data/daydream/`.

## 1. What the evidence says

**Almost nobody has played daydream.** The recorded human play across the
project's life is about 19 minutes of Clockmaker's Loft (2026-07-02), a few
short developer pokes in the bunny world, and one Zork session that was not
archived. The live world holds a 68-second automated walkthrough replay. The
v1.0 flagships (journal, portraits, propagation, endings, onboarding) have
never met a player: the 1.4 loft has never been the live world, and no
journal entry exists in any database.

**Every moment that landed was authored by Opus at design time.** The
ledger's quest text, Tace's line on receiving the gear ("You found it. You
carried it all the way home."), the clock case opening, the Zork prose. In
the one real loft session, the local-model surfaces the player touched were
either verbatim repeats (`listen` returned the same 60-word line six times,
`wind` the same line five times) or broken (both NPC conversations narrated
the NPC's actions as the player's body).

**The new 9B fixed polish, not function.** Qwen3.5 9B removed the voice bug
and raised blind-graded prose from 2.67 to 3.36 of 5. But in the eval runs
the NPCs still contradict the quest canon in ways that would send a player
to the wrong place (Tace: "I found one tucked beneath the pendulum"; Mott
tucks the gear into his tin; the gear is at the well), invent villagers
("the baker's daughter keeps bees"), never acknowledge what the player did,
and open most replies with the same sentence. The cause is not model size
(Gemma 12B and Qwen3 14B invent the same way). The dialogue prompt is given
only a persona, the player's line, and three embedding-retrieved memories.
It is never told the quest state, where things are, what the player has
done, or its own pronouns. The 8192-token window is 87% empty on every call.

**The engine is far ahead of the content.** The rule engine (closed
condition vocabulary, ordered first-match rules, flags, counters, fuses,
daemons, world-declared verbs, containers, conditional exits) is used almost
entirely by the Zork transcription. The canonical cozy world is a format-1
envelope (the old loader: exactly 5 rooms, 4 toons) that uses none of it:
5 rooms, 3 NPCs, one linear fetch quest of about six actions, and a
dreamseed. Roughly 16k lines of engine and 21k lines of tests carry one
fifteen-minute quest.

**No story, no consequence, no reason to return.** No NPC has ever referred
to anything a human did. Memory captured nothing from the human's
conversations (a binding bug, since fixed). The single player-shaped change
in any world is one grown room, and grown rooms have no resident, no hook,
and nothing to do. Nothing changes while you are away except drift lines
narrated into empty rooms (one bunny NPC repeated two sentences 30 times
over 2.5 hours). The quest is one-shot.

**The runtime has headroom we are not using.** The text side of the GPU is
more than 99% idle with no players and uses 5-10% with one active player.
Decode is about 40 tok/s single-stream, about 100 tok/s aggregate at three
concurrent calls, so fan-out is nearly free and serial chains are expensive.
The model is strong at exactly the jobs a story engine needs from a runtime:
choosing among enumerated options (47/48 parser grounding, 100% JSON) and
compressing events (journal 4.2/5, its best surface). It is weak at the job
we keep asking it to do: inventing content and remembering facts nobody told
it.

**The platform intuition was right; the other half never got built.** The
rule engine is a storylet precondition language. The effect allowlist is the
right safety model. The format-2 loader is a fail-loud content pipeline. The
arbiter, image cache, snapshot/swap, and world admin are all what a living
world needs. What is missing is (a) authored content at real volume, (b) a
story layer (arcs, NPC wants, per-player consequence, time), and (c) an
author who keeps writing after launch.

## 2. Where the stated purpose is misaligned

Six places where how we describe the project pulls against what you are
after (a compelling, open-ended experience with story arcs generated from
what exists plus what the player does).

1. **Player-as-builder versus player-as-protagonist.** README's thesis is
   "a game that players can meaningfully expand with a little in-game
   prompting". That is a creation mechanic. Your goal is emergent story,
   which is a narrative mechanic. Dreamseeds serve the first and nothing
   serves the second. A grown room is a new noun, not a new story. Proposed
   reframe: expansion is one of the ways a player's actions feed the story,
   not the point of the game.

2. **A research question versus a product goal.** README says the local GPU
   is "a rule of the game we are actually playing" and the interesting
   question is "how far can small models be pushed". That is a fine research
   question, but it conflicts with "genuinely compelling" whenever the small
   model is the bottleneck, and in the evidence it has been the bottleneck
   for nearly every line that disappointed. Proposed reframe: the product
   goal wins. The runtime stays local and keyless, but the local model's job
   shrinks to what it is good at (selecting, judging, compressing, lightly
   voicing), and the question becomes "how much Opus-quality story can we
   bake per day" rather than "how far can a 9B carry it".

3. **Design time was defined as once, before launch.** A living world needs
   an author on a cadence. Animal Crossing feels alive because its designers
   pre-authored a year of events. Our equivalent is that Opus writes
   tomorrow tonight, from today's play. This is the single biggest lever in
   this document, and it needs a policy decision (section 8).

4. **Coffee-break and daily return versus a one-shot storybook.** The
   original prompt asked for a coffee-break game with Animal Crossing-style
   self-driven storytelling for players who like Farmville. What exists is a
   literary text adventure with a fifteen-minute quest and no return loop.
   The daily rhythm (something new since you left, a small thing to do,
   progress on a longer thread, a trace you leave for others) is absent.

5. **WHIMSY conflates gentle with wantless.** The banlist forbids urgency,
   pressure, and darkness in all narration; growth forbids "darkness"; every
   prose surface runs at temperature 0. The result is pleasant stasis.
   Stories need want, obstacle, and change. The touchstones have them:
   Spiritfarer is about death and letting go; A Short Hike has a goal and a
   climb. Cozy stories have soft stakes (something lost, a strained
   friendship, a goodbye, a festival to get ready for). WHIMSY should keep
   banning cruelty, horror, and grimdark, and gain a section on how cozy
   stories carry tension.

6. **Verification measures correctness, not delight.** About 1,270 tests
   against 19 minutes of recorded human play. The v1.0 review sheet showed
   the voice bug on the eve of release and did not stop it. FIRST-FABLE's
   "green is not good" is still the operating reality. Quality convergence
   needs instruments that measure play (section 5).

On "overbuilt": partly true. The engine is not the waste; the pivot uses
nearly all of it. The imbalance is verification and operations relative to
content, plus detours that produced capability without experience (the Zork
transcription as a platform proof, the retell layer, the voice-bench
harnesses). The fix is not deleting the platform; it is finally pointing it
at a story.

## 3. The proposed shape: Opus writes, the 9B performs, the engine keeps it honest

Three tiers, each doing only what it is good at.

### 3.1 The deep dreamer on a cadence (Opus, via Claude Code)

The generation policy stays: the running game never calls a cloud model and
no API key exists anywhere. What changes is when the design-time author
works. Instead of once, before launch, Opus authors on a cadence, reading
what players did.

- **The world bible (one-time, large).** Places, a cast with wants, secrets,
  relationships, and voice sheets (pronouns, verbal habits, 30-plus authored
  sample lines each), an arc library, a collectible corpus, and director
  rules. All as format-2 data, validated by the loader. Art pre-rendered
  through the same SDXL pipeline and graded by the agent against WHIMSY
  before it ships.
- **The nightly dream (recurring).** A new `bin/game dream` flow:
  1. `digest`: a deterministic summary of the day (who did what, which arc
     beats advanced, what players said to NPCs, what was planted, open
     threads).
  2. Opus reads the digest and writes a **dream patch**: new arrivals and
     arcs, callbacks that name specific player deeds, off-screen progress in
     NPC lives, gossip facts the NPCs now know, a resident or hook for any
     room a player grew, and a "while you slept" page for returning players.
  3. `patch --check` validates it with the same fail-loud loader rules
     (additive only; it can never delete player creations), the world is
     snapshotted, and the patch is applied (live, through the existing swap
     and re-snapshot machinery, or at a quiet hour).
- **Cadence: in-session only (decided 2026-09-26).** The operator triggers a
  dream by name in a Claude Code session after play; the agent follows a
  runbook. No headless or scheduled runs.

### 3.2 The story layer in the engine (deterministic)

What the engine needs so authored arcs can respond to players. Most of it
extends primitives that already exist.

- **Storylets and arcs as data.** An arc is a small set of beats; a beat has
  preconditions (the existing rule condition vocabulary), a trigger (a verb,
  a talk topic, entering a room, a time of day), authored outcome text with
  variants, and effects. Multiple endings per arc, chosen by what players
  did, with no fail states (an unhelped arc ends differently, not badly).
- **Per-player state.** Relationship counters per NPC per player, per-player
  qualities, and deeds (flags, score, and turns are all world-shared today).
- **Knowledge and gossip.** Facts as data: what each NPC knows, including
  facts about players ("someone sent the lighthouse keeper's Tuesday home").
  Facts spread between NPCs on a schedule, so the village talks about you.
- **Real time.** A wall-clock day with dusk and dawn events and NPC
  schedules (fuses and daemons count commands today, so nothing happens
  while nobody types).
- **After-hooks.** Rules can only replace a verb today, never follow one;
  arcs need "after the gear is given, also do X".
- **Talk as a verb that moves story.** A talk turn can advance an authored
  beat, chosen by the local model from an enumerated list (below), then
  applied deterministically.
- **Patch merge.** `world patch` applies additive format-2 content to a live
  world (today's loaders build a world from scratch).

### 3.3 The local performer, re-scoped (Qwen3.5 9B at runtime)

- **Dialogue with state injected.** Voice sheet, current wants, what this
  NPC knows (including gossip about this player), the relationship with this
  player, the last few exchanges, and the beats this NPC may advance.
  Output is the spoken line plus an optional `advance` field constrained to
  the enumerated beat ids (a JSON-schema enum). One call, not a chain.
- **Beat judging.** Free-text actions matched against open beat conditions
  ("tell Bell about the song" satisfies `bell-hears-song`). Same shape as
  parser grounding, which it does at 47/48. Needs its own eval suite before
  anything depends on it.
- **Authored first, varied second.** Key lines are authored; the model
  varies incidental ones at warmer sampling (about 0.7) with n-best and a
  novelty rerank against recent output (three parallel samples cost about
  17% more latency). Drift inverts today's order: authored pools lead, the
  model varies them.
- **A background director tick.** A new arbiter class below renders, capped
  at one slot. Every few minutes it picks among eligible authored storylets
  (who arrives, where an NPC walks, what small thing happens), all
  enumerated choices dispatched through the effect allowlist.
- **Memory as compression.** Per-player "story so far" and per-NPC
  relationship notes refreshed in the background (its best surface),
  replacing raw embedding recall as the main source of continuity.

**Local limits, flagged per the pact.** The 9B will not write arcs, and any
design that needs live invention of structure will be flat. NPC chat will
top out near today's quality for anything not authored, so the lines that
matter are authored. Dialogue is about 2.7 s; state injection adds prompt
tokens, which are nearly free here, but a second serial call is not, so
beat-selection rides in the same call. SDXL cannot render legible objects,
so art carries mood and text carries information.

## 4. Creative direction: The Village of Lost Hours

A proposal, evolving the existing loft rather than replacing it, so the cast,
art, and quest carry forward.

**Premise.** Every hour that goes missing ends up somewhere. The afternoon
you daydreamed through in a classroom, the hour lost when the clocks went
back, the wait at a rainy bus stop, the summer you cannot quite remember.
They drift down at dusk to a small clockmaker's village at the bottom of the
dream, where a few patient keepers catch them, mend them, and when they can,
send them home.

**The prologue is the existing quest.** Before the great clock is mended,
time does not pass in the village. Mending it (ledger, gear, Tace, key,
case) starts time. From then on the village keeps a real day: lanterns at
dusk, arrivals at dusk, the dream turning over at night. The prologue is the
onboarding: fifteen fully authored minutes that teach every verb, ending on
the first dusk and the first arrival.

**Guests are arcs.** Each lost hour arrives as a guest looking for what it
lost. A guest arc is three to six beats across the village's people and
places, resolved with player help, and it ends in one of several ways
depending on what players did. Two sketches:

- *Pim's missing nap.* A small, yawning stranger at the lantern square: the
  nap a boy named Pim was too excited to take on his seventh birthday. It
  cannot settle without the quiet it came from. Bell notices it first;
  Mott's tin holds a hush; Tace can mend a lullaby clock if someone brings
  the spare brass pendulum (an existing object finally gets a purpose).
  Endings: sent home (somewhere, Pim finally naps, and the helper keeps "a
  dent in a pillow"); it chooses to stay and curls up in a room a player
  grew, becoming its resident; or, if no one helps within a few days, it
  falls asleep in a jar in the Hour Cellar, kept but not home. Later, the
  nightly dream can call back to whichever happened.
- *The unsent letters.* Letters that were never sent begin arriving at the
  village's little post office. Any player can deliver one to a keeper, and
  each delivery reveals a piece of how the keepers know each other. After
  enough deliveries across all players, the village holds the Night of
  Found Letters, written by the nightly dream from what the letters
  revealed. A multiplayer arc by construction.

**Keepers have their own slow arcs.** Bell lights every dusk and has never
seen a dawn. Tace is slow to hope, and the hour before the clock stopped is
Tace's own lost hour (the thread toward the long mystery). Mott sweeps up
stray minutes into the tin. New residents fill out the cast: a postmistress
of unsent letters, a keeper of the Hour Cellar (the growth exemplar made
real), a cat who only exists between ticks.

**Stray minutes (the collection loop).** Tiny found things with authored
one-line stories: "the minute spent watching a kettle that would not boil",
"the minute before a sneeze", "the last minute of a summer holiday". Opus
writes a few hundred; a seeded daily roll scatters a few around the village;
Mott catalogues them in a Book of Stray Minutes, and completing a page
unlocks something. Cheap to author at scale, and exactly the size of a
coffee break.

**Dreamseeds get narrative weight.** Seeds come from returned hours, a guest's
thanks. Planting still composes the room live (the local model inside
authored boundaries), but the nightly dream then furnishes it: a resident, a
stray minute, a hook, a description pass at Opus quality that keeps the
player's own phrase. Your words become the premise of a later chapter.

**The village talks.** Keepers mention what other players did. The Ledger
of Returned Hours in the clocktower records every returned hour and who
helped, written up nightly. Returning players open on a "while you slept"
page: who arrived, what others did, what changed.

**The long mystery.** Whose dream is this, and why do hours go missing?
Revealed slowly by the nightly dream over weeks, in response to what players
have done.

**What a session feels like.**
- Day 1, fifteen minutes: the prologue, the clock's first tick, the first
  dusk, a yawning stranger in the square, one stray minute in your pocket.
- Day 2, ten minutes: "while you slept" (another dreamer delivered a
  letter; Mott has been humming). Pim's nap is still yawning. Tace mentions
  the gear you carried home. You find the hush in Mott's tin.
- Day 14, ten minutes: three guests in the village, one of them living in
  the room you grew, asking you for something. Your name in the Ledger
  twice. Bell has started asking everyone what morning looks like.

**Alternatives, in one line each.** *The Inn at the Edge of Sleep*: the same
guest-arc structure in a new setting, a waystation where dreamers and guests
check in each night (costs the existing cast and art). *The Unfinished
Atlas*: exploration first, the dream as an atlas players ink region by
region, the nightly dream populating what was charted (more expansion, less
story).

## 5. Quality convergence: how we will know it is good

1. **Log what players type.** The event log records effects but not input,
   so the one real playtest had to be reconstructed by inference. Store raw
   input per command.
2. **Agent playtesters.** A small `bin/game play` bridge over the existing WS
   driver (`tools/ws_playthrough.py`) so Claude subagents can play the live
   game against the real local models. Personas (the explorer, the
   chatterbox, the completionist, the one who tries to break it) play 15-20
   minute sessions, several at once to exercise multiplayer, then critique
   against a rubric: did anything surprise me, did anything I did matter
   later, did an NPC remember me, would I come back tomorrow. This is a good
   use of subscription tokens and catches "green is not good" before you
   play. It does not replace you; FIRST-FABLE's lesson stands.
3. **Simulated weeks.** A fake clock plus agent players plus the nightly
   dream, run through several dream cycles, to see whether arcs actually
   form over time before a human spends a week finding out.
4. **You play.** The new opening plus one dream cycle, for pleasure. Feel
   notes drive the fix rounds.
5. **Grow the test suite deliberately.** New story code gets paired tests
   and a golden playthrough of the opening; old goldens that constrain the
   pivot (voice baselines, drift samples, retell) get re-ratified or
   retired consciously rather than defended.

## 6. Keep, freeze, retire

- **Keep and build on:** the object store, verb bus, parser, rule engine,
  effect allowlist, format-2 loader, arbiter, image pipeline and cache,
  portraits, journal, snapshot/swap/archive, the Reading Room UI.
- **Freeze:** Zork (a platform regression fixture, off the live server, no
  new investment); the retell layer (the evidence says it flattens good
  prose); embedding memory as the primary continuity source.
- **Retire or replace:** the loft's format-1 envelope (converted to format 2,
  which the pivot needs anyway since format 1 is capped at 5 rooms and 4
  toons); LLM-first drift (inverted to authored-first); the legacy room data
  skills `wind` and `listen` (replaced by authored affordances with
  variation); the growth cap and propagation settings, revisited once the
  nightly dream furnishes grown rooms.
- **Close out:** SPEC 2026-07-07's two open operator playtests (criteria 7
  and 9) are superseded by the pivot; archive that spec as closed with
  deferrals when the pivot spec is written.

## 7. Sequence: the full world, grown from a working core

The operator chose the full world over a vertical slice (2026-09-26). The
acceptance contract is SPEC.md (2026-09-26, 22 criteria). The build still
grows outward from something playable rather than authoring everything before
anything runs:

1. **Instrument and secure.** The security side findings; raw input logging;
   the agent play bridge.
2. **Measure, then fix the performer.** Record the model-eval canon baseline
   on the current prompts, then state injection, voice sheets and pronouns,
   authored-first drift, warmer sampling, and re-measure.
3. **Story primitives.** Format 2 for the loft; facts and gossip,
   per-player relationships, talk beats with deterministic twins,
   after-hooks, the wall-clock day and schedules, the background director,
   patch merge and rehearsal.
4. **A working core.** The prologue plus Pim's nap, with walkthroughs per
   ending, played by agents.
5. **Go wide.** The canon bible, the full cast and arc library, stray
   minutes, the Ledger, the long mystery, authored in parallel by subagents
   and graded by different subagents; art pre-baked and graded.
6. **The playtest day and the first dream.** Agent personas play the live
   stack; the first dream digests their play in-session; rehearsal; install.
7. **The operator plays** the morning after.

## 8. Decisions (locked 2026-09-26)

1. **Opus between sessions: in-session only.** The dream is an in-session
   step the operator triggers by name, gated by the validators, the
   walkthrough proofs, and an automatic snapshot (section 9). No headless or
   scheduled runs, and no API key, ever.
2. **Creative direction: The Village of Lost Hours**, evolving the loft.
3. **Scope: the full world this turn** (section 7; SPEC.md is the contract).
4. **Tone: WHIMSY gains soft stakes.** Wants, gentle time, and bittersweet
   endings are allowed; cruelty, horror, and grimdark stay banned.
5. **Zork frozen, v1.0 spec closed.** Zork leaves the live server and gets
   no new content, but stays in the suite as the engine's regression net
   (section 9). SPEC 2026-07-07's criteria 7 and 9 close as superseded.
6. **Operator autonomy.** From here on the agent makes product, design,
   scope-detail, and housekeeping decisions itself and records them in
   SPEC.md, this file, or the canon bible, spending subscription tokens
   freely on creative exploration (subagents for parallel authoring and for
   independent critique). The operator plays and judges feel.

## 9. Leveraging the save/load and walkthrough machinery

The Zork turn and the world-admin work built instruments the pivot needs
more than Zork ever did. Each gets a named job.

- **Walkthroughs as the contract for every arc.** The Zork pattern (a
  command dataset replayed as cumulative prefixes under a zero-LLM spy,
  ending at an exact asserted state) becomes the acceptance test for
  authored story. Every arc ships one walkthrough per ending; the prologue
  ships its own (the existing loft golden playthrough, extended). The static
  world analyzer grows an arc-solvability check (every beat reachable, every
  needed item obtainable). This is what makes Opus-authored arcs safe to
  load without a human proving each one by hand.
- **Side-DB rehearsal before every dream patch.** The nightly dream never
  touches the live world first. It snapshots live, applies the patch to a
  side copy, replays the patch's own walkthroughs plus the existing ones on
  that copy, runs an agent playtest against it, and only then installs it
  live. A failed rehearsal installs nothing. Install never discards play,
  and it stays cheap: a few seconds of downtime (down, apply the proven patch
  to the current live database, up), which players see as the calm "the
  dream is sleeping" overlay. Swapping in the side copy is avoided because it
  would drop actions taken after the snapshot; no hot-patch endpoint is
  needed.
- **Snapshots as a time machine.** Every dream is preceded by a snapshot,
  so a bad night is one `snapshot-restore` (offline) or `swap` (live) away
  from undone. The snapshot series is also the world's history, which the
  digest and the long mystery can read.
- **Snapshots as save states.** Interesting world moments (day 3 of the
  village, the minute before an arc resolves) are captured as named
  fixtures, so agent playtesters and the operator can start where the
  question is instead of replaying from the prologue.
- **Real play becomes a regression oracle.** The differential oracle
  compared us to the real 1980 game. There is no reference game for Lost
  Hours, but once raw input is logged, every human session is a replayable
  dataset: after a code change, replay the operator's own sessions and diff
  state and deterministic narration. The operator's play becomes ground
  truth.
- **The live WS driver becomes the agent play bridge.**
  `tools/ws_playthrough.py` (login, claim a slot, send free text, collect
  narration) is the base for `bin/game play`, so agent players drive the
  same path a typing human does.
- **Zork stays as the engine's regression net.** The story layer extends
  the rule engine (after-hooks, per-player state, new conditions). The
  380-command walkthrough ending at exactly 350 is a free, deep regression
  suite for those changes, so it stays in the medium tier.
- **A lesson carried from the Zork RNG.** Turn-keyed rolls made the Zork
  walkthrough brittle: inserting one command shifted every later roll. Story
  rolls key on stable purposes (date plus entity, as dreamseed propagation
  already does with `seed-propagation:<room-id>`), never on turn index, so
  a patched world and a replayed walkthrough stay deterministic.
- **Archives for handoff.** The day-0 village is archived as a golden
  bundle; `archive`/`restore` ships a whole village with its art to another
  box.

## 10. Side findings

- **Security gap (unrecorded in SECURITY.md or CODEREVIEW.md).**
  `spawn_object` passes `properties` straight through
  (`daydream/skills/effects.py` around line 309), and `talk` may emit
  `spawn_object`. An NPC dialogue model could therefore spawn a thing whose
  properties carry `rules`; when a player later acts on it, those rules run
  under the full rule allowlist (set_flag, win, teleport, kill). The same
  route can mint a plantable seed, a light, or combat stats. Fix: strip or
  allowlist `properties` on LLM-originated spawns.
- **Room data skills ignore their declared allowlist.** The loft's `wind`
  and `listen` get the default effect kinds (including an unscoped
  `move_object`); the envelope's `effects_schema` is documentation only.
- **The prompt ledger is stale on temperature.** `docs/prompts.md` says
  raising temperature trades JSON reliability on a 7B; the 9B parsed 20/20
  at 0.8.
