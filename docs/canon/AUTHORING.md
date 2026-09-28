# Authoring guide: The Village of Lost Hours

For anyone (a person, an author subagent, a future dream) adding content to
`worlds/lost-hours/`. Read `docs/canon/LOST-HOURS.md` (the canon bible)
and `WHIMSY.md` (the tone bible) first. This file is the format reference
and the rules of the road.

## 1. Where things go

```
worlds/lost-hours/world.json          top-level config (do not edit for arcs)
worlds/lost-hours/regions/*.json      rooms, residents, their things, facts, rituals
worlds/lost-hours/cast/*.json         resident voice sheets, topics, schedules, drift pools
worlds/lost-hours/arcs/NN-<id>.json   one file per arc: the arc, its guest, its things,
                                      facts, rules, storylets
worlds/lost-hours/minutes/*.json      stray minutes and pages
worlds/lost-hours/walkthroughs/*.json one file per arc ending (at least)
worlds/lost-hours.json                ASSEMBLED ARTIFACT, never hand-edit
```

Assemble after every edit, then validate and test:

```sh
.venv/bin/python tools/assemble_world.py --source worlds/lost-hours
.venv/bin/python -m pytest -q tests/test_lost_hours_world.py tests/test_walkthroughs.py -p no:cacheprovider
```

`test_lost_hours_world.py` checks validation (named errors, zero writes),
the static analyzer (every room reachable, every beat and ending
producible, every needed item obtainable), and that every ending has a
walkthrough. `test_walkthroughs.py` replays every walkthrough with ZERO LLM
calls. Both must be green.

An arc file may contain these sections: `arcs`, `toons` (its guest),
`things`, `facts`, `rules`, `storylets`. It must not add rooms or edit other
files. Ids you introduce are namespaced by your arc id: things
`o-<arc>-<name>`, facts `<arc>-<name>`, storylets `<arc>-<name>`, guest
toons `t-<name>`. Guest slots are assigned to you (unique integers >= 120).

## 2. What exists (use these ids)

Rooms: r-clocktower (start), r-loft, r-balcony, r-cellar, r-square,
r-workshop, r-well, r-garden, r-orchard, r-lane, r-post, r-waiting,
r-lamphouse, r-bridge, r-river, r-duskroad, r-hill. Exits in the bible
(section 4).

Residents (toon ids): t-tace (they), t-bell (they), t-mott (he), t-fen
(she), t-umber (she), t-sorrel (they), t-linden (she), t-quill (he),
t-tock (it, never speaks). Where they are by time of day: bible section 3.
Bell is at r-square by day and dusk and ASLEEP in r-lamphouse at night and
dawn; Sorrel is at r-duskroad by day/dusk and r-bridge at night/dawn; Tock
wanders; everyone else stays home.

World flag: CLOCK-STARTED (set when the prologue ends). Player flags
include MET-BELL (Bell's once-only welcome) and WAITED-DUSK (the Dusk Road's
minute). Templates: `dreamseed`, `small-clock`. World verbs: `wind`
(windable things), `listen`, `sing`, `sit`, `wait`, `ring`, `pet`, `eat`,
`drink`, `sleep` (each with gentle defaults; room and object rules give the
specific moments). Engine verbs: look (also "look through / out of / into
X", which examines X), examine, take, drop, give X to Y, use X on Y, open,
close, put X in Y, read, plant, say, go (directions), inventory, talk to X,
ask X about TOPIC (alias: tell X about TOPIC). A free-form line to an NPC
that names one of its topics or open beats (whole words, plural-tolerant)
gets that authored answer, so name topics the way players will say them.

Who reads a line (2026-09-26). A line whose narration addresses "you" (opens
"You ..." or says "your hand" outside quoted speech) reaches only the acting
player. Give such a moment an `others` line (third person, `{actor}` for the
player's name) so everyone else in the room sees it; `"to": "everyone"`
forces a broadcast. Both work on narrate effects, beats, endings, and topics.
Topic answers and improvised replies are the asker's alone (bystanders see a
short "X and Y talk quietly" line). An NPC's `declines_text` (a refused gift)
may be a list of variants with `{item}`; it reaches only the giver.

Things that go home. The world sets `config.rest_returns_things`, so every
authored non-fixture thing remembers its authored room, and a player who
leaves the dream leaves world objects there. Spawned quest items carry
`"properties": {"home": "<room>"}` for the same; `"home": null` opts a
keepsake out. Keepsakes and stray minutes have no home and stay with the
player.

Letters between dreamers (`config.post`, engine `daydream/post.py`). The
world names the room where letters are written and wait (`room`) and every
telling a player reads: `write_text` / `write_others` (the writer's line and
the room's, `{to}` and `{actor}`), `elsewhere_text`, `unknown_text`,
`self_text`, `resident_text`, `off_tone_text`, `waiting_text` (the
recipient's thread and arrival note), `rings_text` (the recipient, awake
elsewhere, at once), and the letter itself: `letter_name`, `letter_seed`,
`read_text` (`{from}`, `{to}`, `{text}`). The letter is a keepsake
(`home: null`) that only its recipient sees. A world without `config.post`
has no post. Keep these in the keeper's voice; the engine's own fallbacks
name nothing.

Dreamseed growth boundaries (the `dreamseed` template) also take
`never_words` (canon-breakers the gardener must never write; a composition
with one is rejected, seed kept, and a planted phrase with one is turned
away before any model call; a capitalized entry is a name and matches only
as written, a lowercase one matches any case) and `question_hint` (how to
answer, added to the question when a player plants with no words).

Changing authored content after launch: edit the sources, re-assemble, run
`bin/game world refresh --check` (writes nothing), then `bin/game world
refresh`, which carries it into the live world without losing play
(players, positions, object state, arc progress, relationships, finds,
deeds, grown rooms, and anything play wrote are kept). A reset is a new
village; a dream patch is additive only. Anything players say often enough
to reach the local model is a candidate topic: each dream digest lists the
recent local lines for exactly this.

## 3. An arc

```json
{"arcs": {"<arc>": {
  "title": "Pim's Missing Nap",
  "kind": "guest" | "keeper" | "village",
  "summary": "one or two sentences, for the director and future dreams",
  "guest": "t-<guest>",                 // guest arcs: the guest toon, room "offstage"
  "cumulative": true,                   // the multiplayer arc only
  "opens": "start" | "arrival" | "rule",
  "arrival": {"room": "r-square", "text": "...", "earliest_day": 2,
              "weight": 1, "after_arcs": ["pim"], "if": [conds]},
  "beats": {"<beat>": {...}},
  "endings": {"<ending>": {...}}
}}}
```

- **Guest arcs** arrive through the director at dusk: give an `arrival`
  (room r-square unless there is a reason; the guest is placed there) with
  an `earliest_day` of 2 or more (the prologue guest is day 1). At most two
  guest arcs are open at once.
- **Keeper and village arcs** open through an `open_arc` effect: usually a
  storylet with `always: true, once: true` and conditions (for example
  `{"flag": "CLOCK-STARTED"}, {"day": {"gte": 2}}, {"arc": "<arc>", "eq":
  "dormant"}`), so it opens deterministically at the first eligible
  boundary. `opens: "rule"` documents this.

### Beats

```json
"<beat>": {
  "npc": "t-bell",                      // a TALK beat: this NPC can advance it
  "topic": "the yawning stranger",      // REQUIRED for talk beats: `ask bell about <topic>`
  "topic_aliases": ["the stranger", "stranger"],
  "hint": "the player asks Bell about the stranger",   // what the local model sees
  "after": ["other-beat"],              // prerequisites (same arc, or "arc/beat")
  "if": [conditions],                   // checked for the asking player at commit
  "per_player": true,                   // each player can do it once (a story told to each)
  "text": "the authored line" | "variants": ["...", "..."],
  "do": [effects],
  "rel": 1,                             // relationship gain with the NPC (default 1)
  "credit": false                       // no helper's credit for the Ledger (default: true
                                        // for a world beat, false for a per-player one)
}
```

A per-player beat's line is the asking player's alone (the room reads the
bystander note); a world beat's line goes to the room unless it addresses
"you".

A talk beat's `text` is spoken instead of the model's line: write it as a
complete moment (a gesture and a spoken line, third person, naming the
NPC). Non-talk beats are advanced by an `advance_beat` effect in a rule.
Every beat needs a producer a player can reach (the analyzer checks).

### Endings

At least two per arc; none a fail state (no kill_actor, teleport_actor,
destroy_object). Exactly zero or one may be timed:

```json
"<ending>": {"text": "...", "ledger": "{helpers} sang Pim's nap home.",
             "do": [effects], "after_days": 3, "room": "r-cellar", "summary": "..."}
```

- `ledger` is the line the Ledger of Returned Hours shows; `{helpers}` is
  replaced by the names of every player who advanced a beat.
- A timed ending (`after_days`) closes the arc at the dusk N days after it
  opened. It has no actor: never use `@actor` in it. It is the "unhelped"
  ending and must be gentle and bittersweet (kept, not lost).
- A player-driven ending is closed by a `close_arc` effect in a rule, a
  talk beat's `do`, or a storylet.
- Guest endings usually move the guest: `{"kind": "move_toon", "toon_id":
  "t-guest", "room_id": null}` (gone home) or to a room (it stays).
- Some endings grant a dreamseed: `{"kind": "spawn_template", "template":
  "dreamseed", "location_id": "@actor", "generated_by": "<arc>:<ending>"}`.

### Threads

Give every arc its **threads**: what a player is in the middle of, listed in
their satchel and read back when they type "what now". A thread shows while
its conditions hold for that player, so gate it on the player having met the
thread (a per-player beat `"by": "@actor"`, or `{"helped": ARC}`) and on the
arc being open, and end it with the beat that finishes that step. Restate
what the player was already told, never the solution; `{count}` counts how
many of a list of conditions hold, in words ("two of five").

```json
"threads": [
  {"id": "letters", "text": "Fen's stray letters: {count} of five home so far.",
   "if": [{"arc": "letters"}, {"beat": "letters/fen-strays", "by": "@actor"}],
   "count": [{"beat": "letters/bell-letter"}, {"beat": "letters/tace-letter"}]}
]
```

A room may say how you are there: `"properties": {"at": "on"}` reads "You are
on the Winding Balcony" (in, on, at; in by default).

## 4. Rules

World rules in an arc file fire for the whole world, so make every rule
SPECIFIC: name the dobj/iobj ids and gate on the arc (`{"arc": "<arc>"}`
means the arc is open).

```json
{"on": "give", "as": "iobj"?, "if": [conds], "do": [effects], "after": true?}
```

- A **before** rule (the default) REPLACES the verb when its conditions
  hold (the first matching rule wins, scanning the dobj's rules, the iobj's,
  the room's, then the world's in file order).
- An **after** rule (`"after": true`) runs only after the verb's normal
  handling succeeded (the take happened, the give was accepted) and never
  suppresses it.
- Engine give: an NPC with `properties.wants` = a thing's name accepts it
  (and says its `gives_text`, runs `gives`). For a keeper who should accept
  an arc item, write a before-rule on `give` with `{"dobj": ...}, {"iobj":
  ...}` that moves the item (`move_object`) and narrates.

## 5. Conditions (closed vocabulary)

```
{"flag": NAME, "eq": bool?}           {"counter": NAME, <op>: N}
{"carried": ID} {"present": ID}       {"dobj": ID} {"iobj": ID} {"in": ROOM}
{"prop": KEY, "of": REF, <op>: V}     {"arc": ARC, "eq": "dormant|open|closed"}  (no op = open)
{"beat": "arc/beat", "by": "@actor"?} {"ending": "arc/ending"}  {"helped": ARC}
{"helpers": ARC, <op>: N}             {"rel": NPC, <op>: N}
{"pflag": NAME}  {"pcounter": NAME, <op>: N}   (declared in world.json)
{"phase": "dawn|day|dusk|night"|[...]}  {"day": {<op>: N}}
{"knows": FACT, "who": NPC, "about": REF?}     {"collected": {<op>: N}}
```

`<op>` is one of eq, ne, lt, lte, gt, gte, in. Any condition may add
`"not": true`. REFs: literal ids or `@actor`, `@dobj`, `@iobj`, `@room`,
`@self`.

## 6. Effects (authored rules only)

```
narrate {text | variants, to?: "@actor", room?}   variants never repeat soon
set_flag {name, value?}      adjust_counter {name, delta}
move_object {object_id, dest_id}                  spawn_object {name, seed, location_id,
  aliases?, verbs?, readable?, properties?, generated_by}
set_property {target_id, key, value}              start_fuse / stop_fuse {name}
open_arc {arc}  advance_beat {arc, beat}  close_arc {arc, ending}
adjust_rel {npc, delta}      set_pflag {name}     adjust_pcounter {name, delta}
add_fact {id, text ("{actor}" = player name), known_by: [npc ids]|"all",
          spread: [{to: [npcs]|"all", after_minutes: N}]}
grant_collectible {id?}      spawn_template {template, location_id, private?}
move_toon {toon_id, room_id (null = offstage), arrive_text?, leave_text?}
```

## 7. Facts

What NPCs know is the ONLY thing the local model may state in dialogue.
Give every arc facts for the NPCs who would know them, gated on the arc:

```json
"facts": {"<arc>-<name>": {"text": "A lost hour ... is staying at the Waiting House.",
                           "known_by": ["t-linden", "t-bell"], "if": [{"arc": "<arc>"}]}}
```

Deeds (what a player did) become facts at runtime through `add_fact`,
naming the player and spreading on a schedule. Add one for every
meaningful player action in your arc, so the village talks about it.

## 8. Walkthroughs

One per ending at least (`worlds/lost-hours/walkthroughs/<arc>-<ending>.json`).
Start from a mended village (copy the prologue commands from
`prologue.json`), then `summon` your arc so the walkthrough tests your arc,
not the director's choice.

```json
{"name": "<arc>-<ending>", "clock": "2026-10-01T17:00:00+00:00",
 "players": [{"as": "A", "name": "Wren"}],
 "segments": [
   {"name": "prologue", "commands": [ ...the prologue steps... ]},
   {"name": "...", "commands": [
     {"summon": "<arc>", "expect": {"arc": {"<arc>": "open"}}},
     {"cmd": "ask bell about the stranger", "expect": {"beats": ["<arc>/<beat>"]}},
     {"clock": "@dusk"}, {"clock": "+2d"},
     {"join": {"as": "B", "name": "Tamsin"}},
     {"as": "B", "cmd": "give letter to fen", "expect": {"ending": {"<arc>": "<ending>"}}}
   ]}]}
```

- `"clock": "2026-10-01T17:00:00+00:00"` is 10:00 in the village (day).
  The prologue's early dusk holds until 18:00; `@dusk`, `@dawn`,
  `@night`, `@day` jump to just past the next such boundary; `+Nh`, `+Nd`
  are relative. Keepers move by schedule (Bell sleeps at night!).
- Every typed command must parse deterministically: directions, `verb
  <name>`, `give X to Y`, `use X on Y`, `put X in Y`, `ask X about TOPIC`,
  `wind X`, `read X`. Free talk (`talk to X ...`, `say ...`) needs the LLM:
  never use it in a walkthrough. Names must match a thing's name or an
  alias EXACTLY (case-insensitive); two in-scope things sharing a name
  makes the parser ask which.
- Expectations are listed in `daydream/walkthrough.py`'s docstring
  (room, carrying, not_carrying, flag, pflag, arc, ending, beats, rel,
  collected, phase, day, knows, located, narrate_contains, narrate_lacks,
  chronicle_contains, threads_contains, threads_lack). When a line has
  variants, assert on a word they all share, or on state instead. Assert
  your arc's threads at the steps that open and close them.

## 9. The quality bar

- WHIMSY: cozy, soft, painterly, Spiritfarer-warm. Soft stakes (wanting,
  waiting, missing, letting go) are welcome; cruelty, horror, grimdark,
  danger, and urgency ("hurry", "you must", deadlines) are not.
- Canon: only the residents, the guests, and Wend are named. No shops, no
  bakers, millers, smiths, beekeepers, or other invented neighbors. No
  modern things. Pronouns never drift.
- Every authored line reads well aloud: a concrete sensory beat, then a
  short spoken line; at most two or three sentences. Vary openings: never
  start two lines in a row the same way.
- A guest is a lost hour: it speaks rarely and simply, in the voice of the
  moment it was. Its arc is 3-6 beats across the village's people and
  places, and each ending is a different, satisfying shape of the story.
- Walk the arc as a player would: every clue points somewhere a player can
  reach; a player who talks to the obvious people finds the way.
