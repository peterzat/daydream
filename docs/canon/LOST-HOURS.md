# The Village of Lost Hours: canon bible

The single source of truth for the world (SPEC 2026-09-26 criterion 21).
Every authored line, every arc, and every future dream stays consistent with
this file. When a dream adds canon (a new resident, a revealed secret, a new
place), the dream updates this file in the same commit. Engine data lives in
`worlds/lost-hours/`; this file is for the authors.

Tone is governed by `WHIMSY.md` (including its stories section): cozy,
soft, painterly, soft stakes allowed (wants, gentle time, bittersweet
endings), never cruelty, horror, or grimdark. The village is kind. Nobody in
it is ever in danger. Things can be lost, missed, or let go.

## 1. Premise

Every hour that goes missing ends up somewhere. The afternoon someone
daydreamed through at school, the hour lost when the clocks went back, the
wait under an awning while the rain would not stop, the summer nobody can
quite remember. They drift down at dusk to a small clockmaker's village at
the bottom of the dream, where a few patient keepers catch them, mend them,
and, when they can, send them home.

Players are **dreamers**: visitors who fall asleep somewhere in the waking
world and wake here. The keepers call them dreamers or friends. A dreamer is
always welcome and never needed in a way that could go wrong.

The one who keeps the village from outside it (invites dreamers, wakes it
and puts it to sleep, writes its dreams) is the **Night Warden**. The title
lives only outside the story: the front door, the asleep page, invitations,
and a dream's while-you-slept note. No keeper knows of a Night Warden or
speaks of one, and the Night Warden is never the answer to whose dream this
is (section 6).

## 2. The rules of the world (hard canon)

- **Hours are people, softly.** A lost hour that arrives as a guest looks
  like a small, gentle figure shaped by what the hour was: a yawning child's
  nap is small and rumpled; a summer is sun-bleached and smells of salt. A
  guest speaks rarely and simply, in the voice of the moment it was.
- **An hour goes home when what it lost is found.** Every guest wants one
  thing the moment was missing. When a dreamer helps it find that, the
  guest goes home, and somewhere in the waking world someone's hour is
  finally whole. The keepers never know exactly where.
- **An hour that is not sent home is kept, not lost.** If no one helps a
  guest, it is not harmed: it settles somewhere in the village (a jar in the
  Hour Cellar, a corner of the Waiting House, a room a dreamer grew) and is
  kept. Kept is bittersweet, never bad.
- **Stray minutes** are the smallest lost time: single minutes (the minute
  before a sneeze, the last minute of a summer holiday). They are not guests;
  they glint, they can be picked up, and Mott catalogues them in the Book of
  Stray Minutes. Each dreamer keeps their own book.
- **The great clock is the village's heart.** While it was stopped, time did
  not pass in the village: no dusk, no arrivals. Mending it (the prologue)
  started the village's day. The clock now keeps a real day: dawn, day,
  dusk, and night, with hours arriving at dusk.
- **Dreamseeds** come from finished things: the prologue's clock case, most
  guests' thanks at a home ending, three pages of the Book (Growing Things,
  On Foot, Waiting), the fifth Unsent Letter delivered, and now and then a
  new seed found in a freshly grown place (propagation). Keeper arcs give
  none; their reward is the keeper's step. And Quill keeps one back in his
  coat pocket for every keeper who has wound their clock and stood and
  talked with him a while (`ask quill about a seed of your own`, once per
  dreamer; beta rehearsal 2026-09-28: the shared seeds all went to the
  fastest player, and the writers had nothing to plant). Planted, a
  dreamseed grows one new small place from the dreamer's own words. The
  village treats grown places as real and keeps them.
- **The dream turns over at night.** Some mornings the village has changed a
  little: someone new has come, a thread has moved, a keeper has news. The
  village calls this "the dream turning over". The Ledger of Returned Hours
  records every hour sent home or kept, and who helped.
- **Letters between dreamers go through Fen.** At the Little Post Office a
  dreamer may write to another dreamer (`write to <name>: <words>`): Fen
  hands over good paper and a soft pencil, reads only the front, and files
  the letter without a glance inside. It waits in the pigeonholes for the one
  it is addressed to, who alone can see, take and read it, and keeps it (a
  keepsake). Fen will not carry a letter to a keeper ("the keepers get their
  post by hand") or take one addressed to its writer, and turns back anything
  unkind. When post arrives for a dreamer who is awake elsewhere, the counter
  bell rings twice down Lamplight Lane. A thing may go the same way: handed
  to Fen "for Wren", she ties a label to it and files it, and it waits for
  Wren alone. (Beta rehearsal 2026-09-28; the words live in `config.post`,
  `worlds/lost-hours/world.json`.)
- **Bell counts the day at the last pole.** Every dusk, lighting the last
  lantern, Bell counts on sooty fingers who came through the village that
  day and tells the lantern, so somebody remembers besides Bell; asked "who
  came through today", Bell says.
- **The village remembers dreamers, not only deeds.** Asked about another
  dreamer by name (`ask bell about Wren`), a keeper tells the record and
  never guesses: when and where that dreamer was last seen, whether they are
  here, awake elsewhere, dozing or resting, and the deeds this keeper has
  heard of theirs. The Ledger of Returned Hours ends with the keepers who
  have dreamed here, signed in their own hands, newest first; the board of
  room keys in the Waiting House shows in Linden's chalk which guest hours
  are waiting and which have gone home or been kept. Fen, asked for one's
  post ("anything for me?"), says what waits and from whom, or that nothing
  has come yet. (Beta rehearsal 2026-09-28: keepers invented where absent
  friends were, and a friend arriving after friends found no signed trace.)
- **No one else lives here.** The residents are exactly the people listed in
  section 3, plus whatever guests are staying. There is no baker, miller,
  smith, innkeeper, mayor, farmer, fisher, doctor, teacher, or beekeeper, and
  the village has no shops. Nobody here invents neighbors.
- **No modern things.** No machines beyond clockwork, no vehicles, no
  screens, no phones. Letters, lanterns, kettles, brass, oak, moss, paper.

### The Book of Stray Minutes

Mott gives each dreamer a small blue book and their first minute during the
first winding (`ask mott about the book`, section 7). Every day after the
clock is mended, three stray minutes of each dreamer's own (private things
only that dreamer sees) glint somewhere in the 17 rooms, placed by a stable
roll that favors the page nearest completion (two until the beta rehearsal
of 2026-09-28, when a player who walked fifteen rooms met one). Taking one catalogues it.
There are 172 minutes on 12 pages (14 or 15 each), in
`worlds/lost-hours/minutes/`.

**The found-minute rule.** The engine reads a minute through
`config.collect.found_text`:

```
You cup the stray minute in your hands, and it settles: {name}. It was {text}. It slips into your Book of Stray Minutes.
```

So a minute's `name` is "the <word> minute", and its `text` is lowercase,
has no final period, and reads correctly after "It was" ("the grey minute
before the birds agreed it was morning"). Every shipped minute follows this;
new ones must too.

| Page id | Title | Completing it gives |
|---|---|---|
| `p-mornings` | Morning Minutes | a twist of sunrise (pink to pearl-grey); Bell +2; fact `page-mornings` (Bell, then Mott and Tace) |
| `p-kitchen` | Kitchen Minutes | a wooden spoon that smells of bergamot; Linden +2 |
| `p-weather` | Weather Minutes | a scrap of blue sky; Sorrel +2; fact `page-weather` (Sorrel) |
| `p-small` | Minutes from Being Small | a gold paper star |
| `p-creatures` | Minutes with Small Creatures | a silver whisker, exactly as long as a second (Tock's); Tock +2 |
| `p-garden` | Minutes of Growing Things | a dreamseed; Quill +2 |
| `p-journeys` | Minutes on Foot | a dreamseed |
| `p-letters` | Minutes of Letters and Words | a crooked stamp (a lantern stamp stuck on crooked on purpose); Fen +2; fact `page-letters` (Fen) |
| `p-waiting` | Minutes of Waiting | a dreamseed ("somewhere, very faintly, someone finally sneezes") |
| `p-brave` | Minutes of Small Bravery | a warm pebble; Mott +2; fact `page-brave` (Mott) |
| `p-evenings` | Evening Minutes | a fold of six o'clock evening light |
| `p-goodbyes` | Minutes of Gentle Goodbyes | a brown paper label in Umber's hand, readable: "Goodbyes, the gentle ones. Keep flat. Open when needed."; fact `page-goodbyes` (Umber, then Tace) |

Arc endings that grant "a stray minute" (section 7) give one of the
dreamer's missing minutes; the Rain-Wait's `stays` gives a specific one,
`m-porch-rain` (on `p-waiting`).

## 3. The residents

Pronouns are canon and never drift. Each resident's full voice sheet (30+
sample lines, habits, what they never do) lives in
`worlds/lost-hours/cast/`.

| Resident | Pronouns | Role | Home (day / night) |
|---|---|---|---|
| **Tace** | they/them | the clockmaker | the Clockmaker's Loft |
| **Bell** | they/them | the lamplighter | Lantern Square (day and dusk) / the Lamp House room above the Waiting House (night, dawn: asleep) |
| **Mott** | he/him | the sweeper; keeper of the tin and the Book of Stray Minutes | the Old Workshop |
| **Fen** | she/her | the postmistress of unsent letters | the Little Post Office |
| **Umber** | she/her | the keeper of the Hour Cellar | the Hour Cellar |
| **Sorrel** | they/them | the hour-catcher of the Dusk Road | the Dusk Road meadow (day, dusk) / the Lantern Bridge (night) |
| **Linden** | she/her | who keeps the Waiting House, where guests rest | the Waiting House |
| **Quill** | he/him | the gardener of the Pendulum Garden | the Pendulum Garden |
| **Tock** | it/its | the cat who only exists between ticks | wanders: the Winding Balcony at dawn, the square by day, the loft at dusk, the cellar at night |

**Tace.** Patient, precise, a little quiet since the clock stopped; warm
underneath and slow to hope. Speaks softly and briefly, often about the work
in their hands. Calls dreamers "friend". Wears a leather apron hung with fine
brass tools, spectacles pushed up into greying hair. Apprenticed as a child
to Wend, the old clockmaker (section 6). *Secret:* the escapement gear did
not simply slip its pin. On the night of the first hard frost, the night
Wend died, Tace sat with Wend through the last hour and could not bear for
that hour to end, so Tace stopped the clock by lifting the gear out, and
before that night was out let it fall and roll away, across the square and
south toward the well-court (every shipped line says "that night"). Tace has never told
anyone. Tace's arc is the long thread toward this.

**Bell.** Bright, kind, talkative in short warm bursts; notices small things
(a moth's route, a lantern burning a shade too blue). Lights every lantern at
dusk with a hooked pole; soot on one cheek; a butter-yellow scarf. Sleeps
through every morning and so has **never seen a dawn**, which Bell mentions
often, lightly, as if it does not matter. It matters. Bell saw the gear roll
away south toward the old well on the night the clock stopped.

**Mott.** Broad, calm, unhurried; says little and means it. Sweeps the Old
Workshop and keeps small found things in a tin (a button, a bent key, a
thimble, a stub of blue chalk). Sweeps stray minutes up with the dust and
catalogues them in the Book of Stray Minutes, which he helps each dreamer
keep. *Secret:* the oldest thing in the tin is a minute he has never been
able to catalogue, because it is his own: the minute he first arrived in the
village, long ago, before he remembers anything else. He is a little afraid
to learn what it holds.

**Fen.** Brisk, bright-eyed, tidy to a fault, a pencil behind one ear;
kind in a practical way. Runs the Little Post Office, where letters that were
written and never sent drift in overnight. She sorts them by who they were
meant for, even when that person is long gone. Talks in postal metaphors
("that's first-class news"). *Secret:* she wrote one herself, long ago, and
it has never arrived.

**Umber.** Old, deliberate, dry-humored; speaks the way labels are
written ("Tuesday, the long one. Keep upright."). Keeps the Hour Cellar under
the clocktower: shelves of small glass jars, each holding a folded paper hour
that someone saved and never spent, and the kept guests who chose to stay.
She knew Wend best of anyone living.

**Sorrel.** Gentle, weathered, talks in weather ("there's a lot of
Tuesday in the air tonight"). Stands in the long grass of the Dusk Road with
a wide soft net, catching hours as they drift down at dusk, and walks each one
to the square for Bell to light in. Never hurries.

**Linden.** Warm, a bustler, always has the kettle on; now and then calls
someone "pet" or "lamb" (never both in one line). Keeps the Waiting House, where guest hours rest while they wait
to be helped home; keeps a room ready for each one. Brews tea, never bakes.

**Quill.** Shy, green-fingered, speaks in the language of growing things.
Tends the Pendulum Garden, where spare pendulums hang from trellises and
sway each to its own count, as if they were plants. Believes a pendulum,
like a seedling, needs patience more than anything.

**Tock.** A small grey cat who only exists between one tick and the next.
Tock never speaks; every reply is a gesture (a slow blink, a tail curling
round a dreamer's ankle, a disappearance mid-step). Tock appears where time
is thin. Villagers treat Tock as a colleague.

## 4. Places

All reachable from the Clocktower (the start room). Compass-consistent.

| Room | Id | Exits | What it is |
|---|---|---|---|
| The Clocktower | r-clocktower | up loft, east square, down cellar | the base of the great clock; the tall oak clock case; the repair ledger; the Ledger of Returned Hours |
| The Clockmaker's Loft | r-loft | down clocktower, up balcony | Tace's workbench; shelves of small resting clocks |
| The Winding Balcony | r-balcony | down loft | a small oak balcony above the clock face; faces east, toward where dawn would come |
| The Hour Cellar | r-cellar | up clocktower | Umber's jars of saved hours; Umber's cellar tea, poured into a chipped cup labelled DRINK WHILE WARM |
| The Lantern Square | r-square | west clocktower, north workshop, south well, east lane | paper lanterns, cobbles; guests arrive here at dusk |
| The Old Workshop | r-workshop | south square | Mott's sweeping; the tin |
| The Mossy Well-Court | r-well | north square, south garden | the old well; where the gear rolled |
| The Pendulum Garden | r-garden | north well, east orchard | Quill's trellises of pendulums |
| The Orchard of Evenings | r-orchard | west garden | small trees whose fruit are evenings; the light there is always six o'clock |
| Lamplight Lane | r-lane | west square, north post, east waiting, south bridge | a narrow lane of lanterns |
| The Little Post Office | r-post | south lane | Fen's pigeonholes of unsent letters |
| The Waiting House | r-waiting | west lane, up lamphouse | Linden's; guest rooms |
| The Lamp House | r-lamphouse | down waiting | Bell's little room of spare wicks, above the Waiting House; one west window over the narrow bed (the sunset view), nothing facing east |
| The Lantern Bridge | r-bridge | north lane, south duskroad, down river | a bridge hung with lanterns over the slow river |
| The Slow River's Edge | r-river | up bridge | reeds; a river that moves like an afternoon |
| The Dusk Road | r-duskroad | north bridge, east hill | a long meadow road where hours drift down at dusk; a dreamer who stands still there at dusk is given one stray minute, once |
| The Hill of Long Shadows | r-hill | west duskroad | the highest place; the one spot you might see a dawn from |

## 5. Time in the village

- Phases: dawn 06:00, day 08:00, dusk 18:00, night 21:30 (village time,
  America/Los_Angeles).
- Before the clock is mended: no phases (the village holds still at an
  endless amber almost-dusk).
- The mending brings an early **first dusk** at once, which lingers until the
  next real boundary, and the first guest (Pim's Nap) arrives in it.
- At every dusk Bell lights the lanterns (a ritual), Sorrel brings in any
  arriving hour, and hours that have waited too long are kept.
- NPCs keep their day/night homes (section 3).

## 6. The long mystery (and its answer)

**The question players meet:** whose dream is this, and why do hours go
missing?

**The answer (never stated outright until the dreams choose to):**

The village is the dream of **Wend**, the old clockmaker who built the great
clock and taught Tace. Wend spent a long life noticing how many hours people
lose: to worry, to hurry, to grief, to delight too big to hold. Near the end,
Wend wished that no one's lost hours would ever be truly lost, and put that
wish into the clock. The clock is the heart of the dream; while it runs, the
dream keeps catching hours. Wend died on the night of the first hard frost,
and Tace, unable to let that last hour end, stopped the clock. The dream
began to hold still around them.

Hours go missing because everyone loses some: an hour is lost when someone
is too full, too tired, too sad, or too happy to hold it. Losing an hour is
not a fault. The dream catches them because Wend promised it would.

**How it resolves (the far end of Tace's arc, for a future dream):** in the
Hour Cellar, on the highest shelf, is a jar labeled in Wend's hand: *For
Tace, when they're ready.* It holds the hour Tace stopped the clock to keep.
When Tace finally opens it (with a dreamer beside them), the hour can go
home at last, and Tace learns that Wend had meant the dream to be shared,
kept by whoever arrives. That is why the village always has room for
dreamers.

**Where the thread stands after `tace-hour` (as shipped).** The keeper arc
The Hour Before (section 7, arc 7) takes Tace one small step, never the
whole way. It closes in one of three states, and a dream that resolves the
mystery starts from whichever one the live world holds (check the
`arc:tace-hour` worldstate and the objects named here):

- `within-reach`: Tace climbed Wend's ladder, humming Wend's climbing song,
  and brought the jar down. The dusty jar (`o-tace-hour-jar`) now sits
  sealed on the **lowest shelf** of the Hour Cellar, where the lantern
  reaches, its label turned to the wall. The highest shelf keeps only a
  clean circle in the dust, with the ladder still leaning on it. Tace: "Not
  yet. But I'd like to see it from the stairs." Umber turns the lantern
  toward the jar each night and asks Tace nothing. Rules refuse any dreamer
  who tries to take or open it ("Some jars wait for one pair of hands").
  The dreamer Tace gave the little brass clock to still carries it, stopped
  at eleven; offered back, Tace says "Keep it a while longer, friend."
  This is intended: the clock is that dreamer's keepsake of the frost hour,
  and a future dream may ask for it back.
- `past-eleven`: the jar is still alone on the highest shelf, Wend's ladder
  stands against it, and Tace's little brass clock ticks on the ladder's
  bottom rung, its hands past eleven.
- `another-season`: the jar is still on the highest shelf; the little clock
  is back on the loft's top shelf, stopped at eleven; a cup of Umber's tea
  waits on the bottom cellar step "for next time". (The ladder stands only
  if a dreamer set it.)

**Reserved for a future dream.** The jar's label, *For Tace, when they're
ready*, never appears in shipped text. The jar is only ever described as
labeled "in an old looping hand", label to the wall, and
`walkthroughs/tace-hour-within-reach.json` asserts the words are absent when
the jar is examined. Also reserved and unstated: what the jar holds; that
Tace lifted the gear out and let it roll away; Wend's wish; that the village
is Wend's dream; that Wend meant it to be shared. Tace's voice sheet still
forbids saying how the gear left the clock or when Wend died, and Umber
never says what is in the jar. What IS now revealed, as facts some residents
know (`tace-hour-wends-night`, `tace-hour-ladder`): the first hard frost,
the night the great clock stopped, was also the night Wend died; Tace sat up
with Wend in the loft through the last of it; Wend's ladder was put away at
Tace's asking the next morning.

**Clues in the shipped text:**

- The stopped hour is the hour before midnight on the night of the first
  hard frost: Sorrel saw a lamp burn in the loft window "until the hour
  before midnight", Umber "took the tea at eleven", and both Tace's little
  brass clock and the clock face drawn in the window frost stand at eleven.
- The repair ledger's first pages are in an older, looping hand signed with
  a single W (Wend's). The little brass clock has a W scratched on its back
  in an old looping hand, and the jar's label is in an old looping hand.
- Umber knew Wend best of anyone living; she answers questions about the
  highest shelf with tea, and asked whose dream this is says "Somebody
  kind's, I should think."
- Tace's hands go still at the frost, at Wend's last days, and at the
  highest shelf.
- No ladder in the cellar is tall enough for the highest shelf; the only one
  that ever reached was Wend's, which Mott kept folded behind the shavings
  (the Tace-hour chain, section 7).
- A dreamer who reaches for the jar (`get the jar`) hears why in the
  highest shelf's own words (its `glimpsed` lines, 2026-09-29b): far above
  the lantern's reach with no ladder tall enough; with Wend's ladder
  standing, "the climb isn't yours to make"; after `within-reach`, only the
  clean circle in the dust. A look sees a glint of glass and the pale edge of
  a label, too far up to read: the label's words stay reserved.
- The keepers' arrival stories (the Unsent Letters) show Wend welcoming
  newcomers: Wend handed Bell the lamplighter's pole and Tace a loupe, and
  knew every hour by name in the cellar Umber came to. Mott's oldest minute,
  if he looks, shows someone old and kind, smelling of clock oil, saying
  "There you are." These echo the answer (the dream was meant to be shared)
  without stating it; the shipped text never names the person in Mott's
  minute.
- Mott's uncatalogued minute and Fen's unarrived letter (her unlabeled
  pigeonhole) are echoes of the same theme: a keeper's own lost time. Mott's
  may now be looked at; Fen's stays unstated.

## 7. The arc library as shipped

Every arc has at least two endings chosen by what players do or by elapsed
time, and none is a fail state. This section records the arcs as they
shipped after two critic passes; where it differs from the original design
plan, the shipped data in `worlds/lost-hours/arcs/` wins. Beat and ending
ids are canon (dreams reference them, as in `{"ending": "summer/meadow"}`).
Each ending ships a walkthrough,
`worlds/lost-hours/walkthroughs/<arc>-<ending>.json`, with extras and
exceptions noted per arc.

**How the arcs run.**

- A talk beat advances with `ask <npc> about <topic>` (the topic label is
  quoted below; each has aliases). Other beats advance by a verb in a rule,
  and a rule-advanced beat still speaks its authored line and runs its
  effects. A beat marked *pp* is per player: every dreamer can do it once.
- Guest arcs arrive at dusk in the Lantern Square through the director,
  never before their earliest day, with at most two guests open at once.
  Pim's Nap is fixed as the first guest, at the first dusk. Keeper arcs and
  the letters arc open by a once-only storylet when the clock is started and
  a day threshold is met.
- Three keeper beats are gated on a relationship of 2 or more with that
  keeper. A talk beat gives +1 by default; `gave-gear` gives Tace +3, and
  the first winding gives Tace +2.
- A timed ending (`after_days`) closes at the dusk N days after its arc
  opened, names no dreamer, and grants nothing.
- Keepsakes and dreamseeds go to the dreamer whose action closed the ending
  (or to the room, where noted). "A stray minute" means one of that
  dreamer's missing minutes (section 2).
- The Ledger's "who helped" names the dreamers who moved the arc for
  everyone: a world beat or the ending. A per-player beat (a story told to
  each) earns no credit unless it says so, and reading the repair ledger
  earns none (`credit: false`), so `mended-together` means two pairs of
  hands on the gear, the key or the case (beta rehearsal 2026-09-28: a
  ledger that credited a bystander twice).
- The pattern for guests: an ending that sends the guest home grants a
  dreamseed, usually with a keepsake (the Extra Hour's `sat-down` is the
  exception: a keepsake and a stray minute instead); an ending where it
  chooses to stay grants a stray minute (and sometimes a keepsake); the
  timed ending keeps it and grants nothing. Keeper arcs grant no
  dreamseeds.

| Arc | Kind | Opens | Timed ending |
|---|---|---|---|
| `prologue` | village | at world start | none |
| `pim` | guest | the first dusk | `jar`, 3 days |
| `extra-hour` | guest | arrival, day 2+ | `everyones`, 3 days |
| `rain-wait` | guest | arrival, day 3+ | `river`, 4 days |
| `summer` | guest | arrival, day 3+ | `meadow`, 3 days |
| `margin` | guest | arrival, day 4+ | `pigeonhole`, 3 days |
| `nell-evening` | guest | arrival, day 5+ | `armchair`, 3 days |
| `tace-hour` | keeper | dawn storylet, day 3+ | `another-season`, 7 days |
| `bell-dawn` | keeper | dusk storylet, day 2+ | none |
| `mott-minute` | keeper | day storylet, day 4+ | none (a transit storylet can close it) |
| `letters` | village, cumulative | dawn storylet, day 2+ | `dead-letter`, 14 days |

### The prologue: The Stopped Clock (`prologue`, village)

Opens at world start; the village holds still at an amber almost-dusk until
it closes.

- Beats (all rule beats):
  - `read-ledger`: read the repair ledger.
  - `found-gear`: take the escapement gear from the moss at the well's foot.
  - `gave-gear`: give the gear to Tace, who hands over the case key (Tace +3; deed fact `gave-gear`).
  - `unlocked`: use the case key on the clock case.
- Endings, both on `open case`: `mended-together` (two or more helpers) and
  `mended` (one). Both start village time, drop a dreamseed from behind the
  pendulum (it lands in the clocktower), fire the `first-dusk` fuse (dusk
  comes early, and Pim's Nap arrives in it), and add fact `mended-clock`
  (everyone). The case also holds a warm brass cog.
- Canon: the case key goes "by long and gentle custom" to whoever mends the
  clock. Once the clock ticks, the repair ledger's newest page, in Tace's
  careful script signed "T.", sends new keepers up to the loft to ask about
  the first winding. The Ledger of Returned Hours is a blue cloth book by
  the clock case. Walkthroughs: `prologue.json` (`mended`),
  `prologue-together.json`.

### The first winding (per player, not an arc)

Every newcomer's first session once the clock ticks (player flags
`GIVEN-CLOCK`, `WOUND`, `MET-BOOK`):

- `ask tace about the first winding`: Tace takes a small resting clock down
  from the shelf ("This one has been waiting for you"). Only its owner sees
  it; once is the custom.
- `wind clock`: it ticks "a half-beat apart from every other clock on the
  shelf". With Tace present: "Now there's an hour here that's yours," and
  Tace sends the dreamer to Bell in the square and to Mott, who "keeps
  something for every new keeper" (Tace +2; deed fact `first-winding`).
- `ask mott about the book`: Mott gives the small blue Book of Stray Minutes
  and tips the first minute from the tin into the dreamer's palm.
- Walkthrough: `latecomer.json`.

### Guest arcs (six)

#### 1. Pim's Missing Nap (`pim`)

**Guest:** `t-pims-nap`, Pim's Nap (it/its): the nap a boy named Pim was too
excited to take on his seventh birthday. **Arrives** at the first dusk:
Sorrel walks it up the lane beside the long net, and it sits by the nearest
lantern and cannot settle.

- Beats:
  - `bell-notices`: ask Bell about "the yawning stranger" (in the square; *pp*). Bell points to Mott's hush and Tace's lullaby clocks.
  - `hear-pim`: ask the nap about "Pim" (*pp*): cake, a red kite, too much singing.
  - `mott-hush`: ask Mott about "a hush": he gives the hush, a small grey quiet he swept up the night the clock stopped.
  - `hushed`: give the hush to the nap (after `mott-hush`).
  - `tace-lullaby`: ask Tace about "a lullaby clock": Wend made one once, for a colicky hour.
  - `pendulum-given`: give Tace the spare brass pendulum from the loft window (after `tace-lullaby`): Tace makes the walnut lullaby clock.
  - `linden-bed`: ask Linden about "keeping the nap here" (after `hushed`): closes `stays`.
- Endings:
  - `home`: wind the lullaby clock with the nap present, after `hushed`. The nap goes home; Pim sleeps with a red kite by his bed. Grants a dent in a pillow and a dreamseed.
  - `stays`: via `linden-bed`. It sleeps in the littlest armchair at the Waiting House, the hush under one cheek. Grants a stray minute.
  - `jar` (3 days): asleep in a small jar on a low shelf of the Hour Cellar, labeled NAP. BIRTHDAY. DO NOT WAKE.

#### 2. The Extra Hour (`extra-hour`)

**Guest:** `t-extra-hour`, the Extra Hour (it/its): the hour that comes back
when the clocks go back in autumn, one o'clock in the morning happening
twice. Small, in an autumn coat, smelling of woodsmoke and fallen leaves; it
casts two shadows, one a little behind the other. **Arrives** day 2+: Sorrel
brings it in ("Caught that one twice").

- Beats:
  - `bell-shadows`: ask Bell about "the hour with two shadows" (in the square; *pp*). Bell would spend it on the hill bench, facing east.
  - `hear-autumn`: ask the Extra Hour about "the night the clocks went back" (*pp*).
  - `tace-turnback`: ask Tace about "turning the clocks back": Tace gives the turned-back clock (a small resting clock set back one hour).
  - `linden-sit`: ask Linden about "sitting down".
- Endings:
  - `sat-down`: give the turned-back clock to Linden after `linden-sit` (before it she laughs and hands it back). She sits in the softest armchair for one whole hour, on purpose, and her tea goes cold; the Extra Hour goes home from the square. Grants the cold teacup (the first cup ever to go cold in the Waiting House) and a stray minute; Linden +2; the clock stays with Linden.
  - `hilltop`: wind the turned-back clock on the Hill of Long Shadows. The dreamer spends the hour on the east-facing bench; the guest goes home. A dreamseed is left in the grass.
  - `everyones` (3 days): kept in a jar on the lowest shelf of the Hour Cellar, labeled THE EXTRA HOUR. AUTUMN. EVERYONE'S: HELP YOURSELF, turned to face the stair. Winding the turned-back clock afterward makes the jar tick back.
- Canon: Tace will not touch the great clock's hands for it ("that one has
  been held back enough"). Linden had not sat down in years. Umber will not
  jar it while it wants spending. The Extra Hour never says "mine". It
  crosses Bell's dawn as flavor only: Bell has worked out that one extra
  hour will not stretch from dusk to dawn.

#### 3. The Rain-Wait (`rain-wait`)

**Guest:** `t-rain-wait`, the Rain-Wait (it/its): the long wait under an
awning while the rain would not stop, when a stranger began a story and the
rain stopped before the end. It holds a scrap of striped awning over its
head, and wherever it stands it rains on one cobble. **Arrives** day 3+:
Sorrel walks in holding the net over it like a coat in a shower.

- Beats:
  - `bell-rain`: ask Bell about "the rain on one cobble" (in the square; *pp*).
  - `hear-beginning`: ask the Rain-Wait about "the story" (*pp*): the lighthouse beginning.
  - `fen-letter`: ask Fen about "the end of a story" (after `hear-beginning`): Fen fetches the rain-spotted letter from her pigeonholes.
  - `sorrel-finishes`: ask Sorrel about "the lighthouse" (after `hear-beginning`; *pp*): Sorrel makes up an ending.
  - `told-sorrels-end`: ask the Rain-Wait about "Sorrel's ending" (after `sorrel-finishes`): closes `stays`.
- Endings:
  - `the-end`: read the rain-spotted letter aloud with the Rain-Wait present. It folds its awning and goes home dry. A dreamseed glows on the stone where it stood; Fen +2.
  - `stays`: it takes the window seat at the Waiting House, to tell the lighthouse story Sorrel's way on rainy evenings. Grants the kept raindrop (a tiny lit lighthouse inside it) and the minute `m-porch-rain`.
  - `river` (4 days): it sits among the reeds at the Slow River's edge, listening to the river's one long word, which never ends, and does not mind.
- Canon: the story begins "Once there was a lighthouse on a hill, miles from
  any sea, and every night its keeper lit the lamp, and every night, nothing
  came." The stranger's own ending (the letter, addressed "To the one under
  the awning", sealed, never posted): one wet night someone small and soaked
  came up the hill following the light; the keeper let them in and put the
  kettle on, and never minded the empty nights again, because now she knew
  what the light was for. Sorrel's ending: the keeper stands still in the
  doorway instead of climbing the stair, and the thing she waited for comes
  up the hill to find her. The stranger is never named (a voice "like a
  kettle nearly boiling"); the Rain-Wait never makes up an ending itself.

#### 4. Marram, the Summer (`summer`)

**Guest:** `t-marram`, Marram (it/its): a whole summer someone spent at the
edge of the dunes when they were small, and can no longer quite remember.
Sun-bleached, salt-smelling, a faded striped towel for a cape; it has kept
one word of its name. **Arrives** day 3+: a warm salt wind comes up the lane
ahead of Sorrel, who has sand on their boots.

- Beats:
  - `bell-salt`: ask Bell about "Marram" (in the square; *pp*). Bell points to Quill and Umber.
  - `hear-marram`: ask Marram about "the summer" (*pp*): it gives a stalk of marram grass.
  - `quill-grass`: ask Quill about "the marram grass" (or give him the stalk): an evening that smells of salt has fallen early in the Orchard of Evenings.
  - `found-evening`: take the fallen evening in the orchard (after `quill-grass`).
  - `umber-label`: ask Umber about "a label for Marram".
  - `labeled`: give the fallen evening to Umber (after `found-evening`): she jars it and hands back the labeled summer jar.
- Endings:
  - `home`: give the summer jar to Marram. It reads its whole name and goes home; far off, someone long grown up shakes out an old striped towel and says "marram". Grants a pinch of warm sand and a dreamseed.
  - `downstream`: give Marram the fallen evening instead. It settles where the reeds thin at the Slow River's edge, facing downstream toward the sea, the evening in its lap. Grants a stray minute.
  - `meadow` (3 days): asleep in a warm hollow in the Dusk Road's long grass, where Sorrel says it is always a little bit August. The jar can still be given afterward: Marram keeps the label tucked under its chin and stays (fact `summer-late-label`; walkthrough `summer-meadow-late.json`).
- Canon: its whole name is THE SUMMER THE MARRAM GRASS SANG (the label goes
  on: "Long days at the edge of the dunes. Salt, one striped towel, and a
  sea that came right up to the door to say good morning. Keep in the
  light."). Marram grass holds whole hills of sand together and whistles
  when the wind comes. Summers fade their own labels worst; Umber writes a
  label that stays if brought something with the summer still inside it.
  Marram never names the one it belonged to.

#### 5. The Margin Afternoon (`margin`)

**Guest:** `t-margin`, the Margin Afternoon (it/its): an afternoon a child
daydreamed through in class, papery, the color of an exercise-book page,
covered in half-finished doodles. A bell rang before it could finish its
best drawing, and it jumps at the word "bell". **Arrives** day 4+: Sorrel
carries it in folded like a note.

- Beats:
  - `bell-startles`: ask Bell about "the Margin Afternoon" (in the square; *pp*). "Not that bell, sorry!"
  - `see-drawing`: ask the Afternoon about "the drawing": it hands over the margin drawing (giving it a pencil first also advances this).
  - `fen-pencil`: ask Fen about "a pencil" (*pp*): a soft pencil from the jar on her counter.
  - `quill-middle`: ask Quill about "the drawing" while carrying it, or give it to him (after `see-drawing`): the middle is where the newest pendulum hangs.
  - `drawn`: use the pencil on the drawing in the Pendulum Garden (after `quill-middle`): the dreamer draws in the littlest pendulum.
- Endings:
  - `finished`: give the finished drawing to the Afternoon. It goes home; far off, a grown-up finds the little garden finished in an old sums book. Grants a curl of pencil shaving and a dreamseed.
  - `doodling`: give it the pencil (after `see-drawing`, before `drawn`). It stays under the trellises of the Pendulum Garden, doodling pendulums, happily unfinished. Grants a stray minute.
  - `pigeonhole` (3 days): folded small as a passed note in Fen's pigeonhole marked TO ME, LATER. The finished drawing can still be given; it tucks it inside itself (fact `margin-late-drawing`; walkthrough `margin-pigeonhole-late.json`).
- Canon: the drawing holds spirals, a boat with no sail, a four-pointed star,
  and a little garden where pendulums hang from trees like fruit, around an
  empty middle. The littlest pendulum (`o-margin-littlest`, in the garden
  from the start) is no bigger than a raindrop, hangs on a silk thread from
  the lowest trellis right in the middle, and is the newest. Fen keeps a jar
  of soft pencils on her counter ("A pencil's only a letter that hasn't
  started yet").

#### 6. Nell's Early Evening (`nell-evening`)

**Guest:** `t-nells-evening`, Nell's Evening (it/its): the early evening a
grandmother named Nell dozed through at her own eightieth birthday party
while her family sang. Small, rosy, in a crocheted shawl of every color and
a paper party hat. **Arrives** day 5+: Sorrel carries it up the lane in the long
net, held low and careful, trailing candle smoke (Sorrel walks every guest
in).

- Beats (all *pp*):
  - `bell-notices`: ask Bell about "the sleepy evening" (while Bell is awake): songs come down in pieces.
  - `hear-nell`: ask the evening about "Nell": the song went up the chimney in bits, "one to the road, one to a kettle, one to a broom".
  - `sorrel-line`: ask Sorrel about "Nell's song": the first line.
  - `linden-line`: ask Linden about "Nell's song": her kettle whistles the second line.
  - `mott-line`: ask Mott about "Nell's song": the last line.
  - `quill-windfall`: ask Quill about "a windfall": a small glowing evening fruit ("the ones that fall are ready").
- Endings:
  - `home`: `sing` with the evening present, having learned all three lines yourself. It goes home; an old woman wakes in her armchair to the end of the singing and asks who is cutting the cake. Grants a pink birthday candle stub and a dreamseed.
  - `orchard`: give the evening the windfall. It rests on the lowest branch of the Orchard of Evenings, glowing rosier than the rest. Grants a stray minute.
  - `armchair` (3 days): it dozes in the best armchair by the kettle at the Waiting House, and Linden keeps it.
- Canon: Nell was eighty ("eighty candles, or near enough"), the cake was
  pink, and she only closed her eyes a moment. The song is in "New canon"
  below. The evening never names Nell's family.

### Keeper arcs (three)

#### 7. The Hour Before (`tace-hour`, Tace)

**Opens** at the first dawn on day 3+ (storylet `tace-hour-opens`): the
season's first frost lies like lace across the loft's round window, with a
small clock face drawn in it by one fingertip, both hands at eleven. Tace
stands at the glass, hands in apron pockets, and picks up no tools.

- Beats:
  - `tace-frost`: ask Tace about "the frost" (Tace relationship 2+). Tace's hands go still; they give the dreamer the little brass clock to keep "a while" and mention that Umber keeps a lamp lit on frost mornings.
  - `umber-frost`: ask Umber about "the first hard frost" (after `tace-frost`): "First hard frost. Wend's last night. Tace sat up; I took the tea at eleven."
  - `mott-ladder`: ask Mott about "Wend's ladder" (after `umber-frost`): he gives the folded tall ladder.
  - `sorrel-song`: ask Sorrel about "Wend's climbing song" (after `umber-frost`): Sorrel folds the song into the dreamer's hands.
  - `ladder-set`: use (or put) the ladder on the highest shelf, or drop it in the cellar (after `mott-ladder`). Umber: "Not mine to climb. Not yours either. Tell Tace: ladder, standing."
  - `tace-told`: ask Tace about "Wend's ladder" (after `ladder-set`): "Standing again. I'd go down, I think, if I had something to carry."
- Endings:
  - `within-reach`: give Tace the climbing song after `tace-told`. Tace climbs the ladder humming and sets the jar, unopened, on the lowest shelf, label to the wall. Window thawed; Tace gladdened, +2.
  - `past-eleven`: give Tace the little brass clock after `tace-told`. Tace winds it past eleven for the first time since the frost and leaves it ticking on the ladder's bottom rung: "Not the ladder. Not this season. But it's going again." Window thawed; Tace +2.
  - `another-season` (7 days): Tace goes down the cellar stair alone, as far as the bottom step, and climbs back to bed; the little clock goes home to the loft's top shelf, stopped; Umber leaves tea on the step.
- Grants no keepsake and no dreamseed: the reward is Tace's step. Section 6
  records the jar's state after each ending; the full clue chain is in "New
  canon" below.

#### 8. Bell's First Dawn (`bell-dawn`, Bell)

**Opens** at the first dusk on day 2+ (storylet `bell-dawn-opens`): after
the last lantern Bell stands looking east. "Someone told me the dawn comes
up over the hill. Pink. Imagine."

- Beats:
  - `bell-confides`: ask Bell about "staying up" (Bell relationship 2+, Bell awake): Bell would need company and something of Linden's, hot and strong, or a sunrise to light at dusk ("Tace can bend brass into anything").
  - `linden-flask`: ask Linden about "night tea" (after `bell-confides`; *pp*): the dented flask of night tea.
  - `bell-woken`: give the flask to Bell in the Lamp House at night (after `linden-flask`). Bell clatters down and walks up to the hill bench; their schedule moves to the hill for the night.
  - `named-stars`: ask Bell about "the stars" on the hill at night (after `bell-woken`).
  - `tace-sunburst`: ask Tace about "a sunrise lantern" (after `bell-confides`).
  - `sunrise-made`: give Tace a lantern-skin from the Lamp House (after `tace-sunburst`): Tace fans spare clock hands into a half-sun under the skin.
- Endings (no timed ending):
  - `first-dawn`: closed by the dawn storylet if `named-stars` happened and Bell is still on the hill. Bell sees it and goes to bed smiling; a sliver of first light stays on the bench (takeable). Afterward, each helper who meets Bell by day or dusk hears about it once.
  - `dusk-enough`: give Bell the sunrise lantern at dusk. It hangs on the easternmost pole of the square, and Bell lights it last every dusk. Grants a thumbprint of soot, dabbed on the dreamer's cheek for luck; Bell +2.
- Safety valves: woken without stars, Bell dozes through the dawn on the
  bench and goes home to try another night. While the sunrise lantern is
  unmade and the first skin is gone, a spare lantern-skin turns up in the
  Lamp House at dusk. Walkthroughs add `bell-dawn-second-flask.json` and
  `bell-dawn-spare-skin.json`.

#### 9. The Oldest Minute (`mott-minute`, Mott)

**Opens** by day on day 4+ (storylet `mott-minute-opens`): Mott sweeps the
same corner three times, his free hand drifting to the lid of the tin.

- Beats:
  - `mott-confides`: ask Mott about "the oldest minute" (Mott relationship 2+): "A minute. Mine. The one I arrived in, before I remember anything else. Bit afraid to look, truth be told."
  - `umber-remembers`: ask Umber about "when Mott came" (after `mott-confides`).
  - `tace-loupe`: ask Tace about "a loupe" (after `mott-confides`): a spare loupe on a faded ribbon; open it "along its own creases, never new ones, and in good light."
  - `fen-envelope`: ask Fen about "an envelope for later" (after `mott-confides`): a stiff cream envelope marked TO ME, LATER.
  - `sealed`: give Mott the empty envelope (after `fen-envelope`): he seals the minute inside unread and asks the dreamer to take it to Fen.
- Endings (no timed ending):
  - `looked-together`: give Mott the loupe (after `mott-confides`, before `sealed`). He unfolds the minute with the dreamer beside him. Grants a curl of cedar shaving, the first thing he sweeps afterward; Mott +2.
  - `kept-for-later`: give the sealed envelope to Fen (the courier gets a lantern stamp, "first class", and Mott +2), or, if no one carries it, Fen finds it on the post office mat on the third morning after sealing and files it. It waits in the pigeonhole marked TO ME, LATER.
- Walkthroughs add `mott-minute-kept-for-later-mat.json`.

### The village arc (multiplayer, cumulative)

#### 10. The Unsent Letters (`letters`)

**Opens** at the first dawn on day 2+ (storylet `letters-begin`): a crayon
letter has come under the post office door, Fen sets it in the dead-letter
drawer ("Nearly counts, in this office"), and the counter bell rings twice
down Lamplight Lane: there is post. One more stray arrives each dawn after,
in fixed order, seven in all (world counter `letters-arrived`); none arrive
after `dead-letter`.

- Beats:
  - `fen-strays`: ask Fen about "the stray letters" (*pp*): read the front, take each to whoever it nearly means; five home brings a Night of Found Letters.
  - `bell-letter`: give the crayon letter to Bell (refused while Bell sleeps).
  - `tace-letter`: give the marble letter to Tace.
  - `mott-letter`: give the button letter to Mott.
  - `umber-letter`: give the string-tied letter to Umber.
  - `linden-letter`: give the tea-stained letter to Linden.
  - `sorrel-letter`: give the grass-stained letter to Sorrel.
  - `quill-letter`: give the seed-packet letter to Quill.
- Each delivery while the arc is open adds to world counter
  `letters-delivered`, and the counter bell rings once by itself
  ("Delivered"). Every delivery gives that keeper +2 and Fen +1 and reveals
  how the keeper came to the village, even after the arc has closed.
- Endings:
  - `found-letters`: the fifth delivery, by anyone. Fen waves her pencil like a baton ("Five home!"); the fifth deliverer gets a dreamseed "folded like a tiny letter". At the next dusk, the Night of Found Letters (storylet `letters-night`): a paper star Fen folded from a spare envelope hangs under every lantern in the square, and letters are read aloud from the loft, the cellar stair, and the Waiting House.
  - `dead-letter` (14 days): Fen ties the rest with blue ribbon and shuts the drawer, chalked ANOTHER WINTER. "Letters are patient; it's the one thing they're good at."
- Canon: the seven letters and their reveals are in "New canon" below. No
  stray letter comes for Fen.

### New canon established by the arcs

Everything below is in shipped data and must not be contradicted.

#### How the keepers came to the village (the Unsent Letters)

Each stray letter is addressed "nearly" to a keeper by someone in the waking
world; the writers are never named.

| Letter | Address on the front | Keeper | What the keeper tells |
|---|---|---|---|
| crayon letter | TO THE ONE WHO LIGHTS THE LAMP OUTSIDE MY WINDOW (a lantern drawn for a stamp; inside, I WAVE) | Bell | "I waved back, you know. Every window." Bell's first dusk here, Wend was lighting the square alone, "slow as moss", held out the pole, and said the lanterns liked company; Bell never gave it back. Bell keeps the letter folded in the butter-yellow scarf. |
| marble letter | TO WHOEVER MENDS THINGS (PLEASE) (a glass marble inside) | Tace | As a child "about as big as this handwriting", Tace broke a clock and carried the pieces up the loft stairs in an apron. Wend wanted no payment, handed Tace a loupe, and Tace never went back down. |
| button letter | TO WHOEVER FINDS MY BUTTON. IT MATCHES THIS ONE. (a brown coat button stitched on in thick grey thread) | Mott | The brown button that has lived in Mott's tin for years matches it, thread and all. Mott does not remember coming; the first thing he remembers is the broom and the floor. (After `mott-minute/looked-together` he adds that he looked, and knows he was expected.) |
| string-tied letter | TO THE ONE WHO KEEPS THINGS FOR LATER; on the back, OPEN WHEN THERE IS TIME | Umber | She labels it KEPT FOR LATER. ARRIVED. and shelves it. When she came, the cellar held three jars and one lantern, and Wend knew every hour in it by name; Wend could never bear to throw a thing away. |
| tea-stained letter | TO WHOEVER WAITED UP FOR ME (a pale teacup ring) | Linden | She came waiting up for someone, long ago, and can't think who now. She waited so long she got good at it, and the Waiting House grew up round her. The letter lives behind the kettle. |
| grass-stained letter | TO THE ONE WHO WALKED ME HOME (smells of cut grass; a pressed clover inside) | Sorrel | "Walked someone home once, I think." Sorrel came along the Dusk Road one evening with nowhere in particular to be, found the sky so kind they stayed to watch it, and are still watching. The clover rides in Sorrel's hatband beside the sorrel. |
| seed-packet letter | TO WHOEVER IS MINDING MY GARDEN (written on an old seed packet; seeds rattle inside) | Quill | He came to see whether a pendulum would grow if you planted it. It didn't, not really, but he stayed to find out, and has been finding out ever since. |

#### Nell's song

The whole song, as the dreamer sings it at `nell-evening/home`: *here's to
Nell, and her candles bright, here's to the kettle and the window light,
doze if you like, love, we'll sing it soft tonight.*

- Line 1, "Here's to Nell, and her candles bright": Sorrel caught it on the
  Dusk Road, just ahead of the evening, "like the first drops before rain".
- Line 2, "here's to the kettle and the window light": Linden's kettle has
  been whistling it ("Singing about itself, the vain thing").
- Line 3, "doze if you like, love, we'll sing it soft tonight": Mott swept
  it up with the dust and kept it in his head.

#### The Tace-hour clue chain

In the order a dreamer meets it:

1. The frost on the loft's round window, with a clock face drawn in it by
   one fingertip, both hands at eleven. After any ending the window thaws,
   leaving a faint round mark "like a breath that hasn't quite faded".
2. Tace's little brass clock: no bigger than a pocket watch, a single W
   scratched on its back in an old looping hand, stopped at eleven since the
   first hard frost, kept apart on the loft's top shelf. Tace will not let
   anyone take it until they hand it over themselves ("Keep this one for me
   a while, friend"); its key will not turn for a dreamer. Umber keeps a
   lamp lit on frost mornings.
3. Umber: "First hard frost. Wend's last night. Tace sat up; I took the tea
   at eleven." Wend's ladder reached the highest shelf, once; "Mott carried
   it off."
4. Mott: the morning after the frost, Tace asked him to put Wend's ladder
   where they wouldn't have to see it, and he kept it behind a drift of
   shavings. It is Wend's tall oak library ladder, rungs worn pale, and like
   most dream things it folds far smaller than it should. "Wend never
   climbed it without singing."
5. Sorrel: "First hard frost, a lamp burned in the loft window until the
   hour before midnight. Then the clock went quiet, and the frost came down
   like a held breath." Sorrel still knows Wend's climbing song, slow and a
   little off-key, and it makes a climber's feet feel surer.
6. The ladder stands against the highest shelf again, and up in the shadow
   a single jar glints, set apart. It is the only ladder that ever reached.
7. Tace: "I'd go down, I think, if I had something to carry." The song lets
   Tace climb; the little clock lets Tace wind past eleven instead.

#### Mott's oldest minute

- Umber remembers the evening he came: "on a Tuesday, a long one, with
  sawdust in his hair and nothing in his pockets but that minute." Her
  counsel: "Some things you keep folded because you're not ready, and some
  because you're afraid they're empty. Either is allowed."
- If he looks (`looked-together`): a doorway full of evening, a broom
  leaning in the corner, and someone old and kind, smelling of clock oil,
  saying "There you are," as if he were only a little late. "Somebody was
  waiting. I thought I'd only been swept in." He writes it as *the minute I
  was expected* into a Book of Stray Minutes of his own, in his slow, square
  hand, keeps it unfolded in the tin, and hums while he sweeps.
- If he seals it (`kept-for-later`): it waits unread in Fen's TO ME, LATER
  pigeonhole, "exactly where he left it", and his tin has an empty corner.
- The tin's other contents stay canon: a brown button (the one matching the
  button letter), a bent key, a thimble, a stub of blue chalk. The hush he
  gave for Pim's Nap was "the quietest thing I own", swept up the night the
  clock stopped.

#### Bell's dawn, the lanterns, and the stars

- Bell's lanterns have names: Pollen (sulks if lit last), Old Blue (burns
  steady), Thimble (the smallest, brightest for her size), and the one that
  hiccups. There are forty-one lanterns in the square and the lane. Pollen
  is the square's paper lantern on its hooked pole, the one a dreamer can
  lift down; Bell is glad to have her back and hangs her again.
- On the hill, Bell names stars like lanterns: "Pollen's cousin", "Old Blue,
  gone up in the world", and Thimble, "the little one".
- What Bell saw at `first-dawn`: the sky went grey, then pearl, then the
  faintest rose, and the first gold edge came over the rim of the world.
  Bell laughed out loud, once, like a lantern catching, and whispered: "Oh.
  It really is pink." Afterward Bell tells every lantern ("grey, then pearl,
  then pink"), says once was plenty, and still likes dusk best.
- The Lamp House's one bed faces its one window, west; the Hill of Long
  Shadows is the one place in the village to watch a dawn from. The hill
  bench has a tiny sun carved in one arm and a lantern in the other.
- The sunrise lantern (`dusk-enough`) is a paper lantern-skin over a
  half-sun of fanned brass clock hands, bound with fine wire. On the
  easternmost pole, lit last each dusk, it turns the square rose and gold.

#### Fen's post office

- Pigeonhole labels, in Fen's tidy hand: TO THE ONE WHO LIGHTS THE LAMPS,
  TO WHOEVER FINDS THIS, TO MY SISTER, TO ME, LATER. TO ME, LATER holds
  things not ready to be read: the unhelped Margin Afternoon folds itself
  in there, and Mott's sealed minute is filed there.
- **Fen's secret stays unstated.** One unlabeled pigeonhole sits near the
  top. Fen's hand or pencil pauses over it and moves briskly on; on the
  Night of Found Letters she runs a finger along it ("Empty, as always"),
  gives it a pat, and murmurs "Scenic route." That is the only hint. No
  shipped line says what the pigeonhole is for or mentions her own letter.
- The dead-letter drawer is a deep oak drawer under the counter, lined with
  blue paper, left open a hand's width. The counter bell rings by itself
  when a stray letter finds its door.
- Fen keeps soft pencils in a jar on the counter and spare stamps printed
  with a tiny lantern, and will not take back a letter that is "out for
  delivery".

#### Where the kept and staying guests live

| Guest | Ending | Where it stays |
|---|---|---|
| Pim's Nap | `pim/stays` | the littlest armchair, the Waiting House, the hush under one cheek |
| Pim's Nap | `pim/jar` | a small jar on a low shelf of the Hour Cellar (NAP. BIRTHDAY. DO NOT WAKE) |
| the Extra Hour | `extra-hour/everyones` | a jar on the lowest shelf of the Hour Cellar, where anyone can reach |
| the Rain-Wait | `rain-wait/stays` | the window seat at the Waiting House |
| the Rain-Wait | `rain-wait/river` | among the reeds at the Slow River's edge |
| Marram | `summer/downstream` | where the reeds thin out at the Slow River's edge, facing downstream |
| Marram | `summer/meadow` | a warm hollow in the long grass of the Dusk Road |
| the Margin Afternoon | `margin/doodling` | under the trellises of the Pendulum Garden |
| the Margin Afternoon | `margin/pigeonhole` | Fen's TO ME, LATER pigeonhole |
| Nell's Evening | `nell-evening/orchard` | the lowest branch of the Orchard of Evenings |
| Nell's Evening | `nell-evening/armchair` | the best armchair by the kettle, the Waiting House |

#### Other fixed details

- The Waiting House's chairs: the littlest armchair, the softest armchair
  (where Linden sat for the Extra Hour), the best armchair by the kettle,
  and the window seat, where the rain sounds best on the glass.
- Linden's night tea is strong enough to stand a spoon in, and comes in a
  dented tin flask that stays hot however long it is carried.
- Wend once made a lullaby clock, for a colicky hour.
- Umber's labels are short, true, and often end in an instruction. Beyond the
  jars above, the cellar holds "Tuesday, the long one. Keep upright.", "the
  hour before the recital", "rain, unspent", and "the afternoon it rained on
  the picnic, unspent".
- Quill never picks an evening; they fall when they're ready, and a
  windfall knows the way back to the orchard.

## 8. Voice rules for every line

- Present tense narration, third person for NPCs, second person ("you") for
  the dreamer's own actions.
- An NPC reply is one small gesture and one spoken line; at most two short
  sentences.
- Concrete sensory beats (brass, oil, wick-smoke, moss, rain) over abstract
  ones.
- Soft stakes: wanting, waiting, missing, letting go. Never danger, never
  urgency ("hurry", "you must", deadlines), never cruelty.
- Proper nouns: only the residents, the guests, and Wend. Pim, Nell, and the
  other people the hours belonged to are mentioned, never met.

### Voice tics to avoid

Two blind critic passes found these patterns overused in the shipped lines.
New lines (dreams included) should not add more of them.

- **Tace:** "hands go still" is reserved for the frost and Wend (the
  highest shelf counts: it is Wend's thread). Never use it as a general
  pause.
- **Bell:** "Bell crouches" was overused. Give Bell ladder, pole, wick,
  scarf, and soot business instead.
- **Mott:** leaning on the broom as the opening gesture was overused. Use
  the tin, the slant light, or one slow arc of the broom.
- **Fen:** "scenic route" is spent. It closes the Night of Found Letters as
  the one hint at her own letter (and appears once among her voice
  samples). Do not use it again.
- **Umber:** never says "lamb" (that is Linden's). She speaks in label
  style: short phrases, often ending in a dry instruction ("Keep upright").
- **Sorrel:** the sky-glance opener (glances at, squints at, or studies the
  sky before speaking) was overused. At most one per scene; use the net, the
  hat brim, or the grass.
- **Linden:** at most one pet name per line, "pet" or "lamb", never both,
  and not in every line.
- **Quill:** "goes pink" was overused. Ration it; use the hat brim, the
  watering can, or straightening a trellis.
- **Everyone:** "a long while" and "a long moment" were overused. Prefer a
  concrete measure: a tick, a breath, one slow arc.

## 9. Dreams (canon added after launch)

Each dream's patch lives in `worlds/lost-hours/dreams/<id>/` with its digest
and rehearsal. What each made canon:

### dream-2026-09-28: The Night the Lamps Learned Three Names (after the beta rehearsal's first evening)

Written for the dev village of the beta rehearsal (three agent playtesters,
docs/playtests/2026-09-28-beta-rehearsal/); the prod village had not yet
opened. What it made canon, and the shapes a later dream can reuse:

- A grown place is signed: a card in a keeper's hand (Tace's, Fen's,
  Umber's) names who grew it and what they wished for, in their words. The
  Bowl of Turned Time (Vex, "a skate bowl where the ramps are giant clock
  hands") is a sunken bowl whose sides are the great clock's hands laid
  down; Tock skids down the minute hand between ticks and lands on the
  hour. The Waiting Bell Loft (Vex, a treehouse with a rope ladder, a
  password and a bell) has a bell that rings and carries to the square,
  where Pollen flares; its slate reads, in Bell's sooty capitals, THE WORD
  IS POLLEN. The Warmth of Unsent Words (Wren, "a lamplit room of unsent
  letters, kept warm until their writers come back for them") is sorted by
  Fen, oldest nearest the stove; the oldest begins "Dear Gran, I am writing
  this down so that one of us remembers it." The Quiet Bookmark Shelf
  (Halloran, "a reading nook where three housemates leave bookmarks in each
  other's books") holds three open books with the three keepers' names in
  them and a fourth, closed, with a blank bookmark.
- Tace leaves the loft door open at dusk since Vex came up the stair with
  the gear. Bell chalked a small W on Pollen's pole after Wren carried her
  home. Fen keeps a pigeonhole for every keeper since Halloran posted the
  first two letters between dreamers. Umber's label: THREE KEEPERS. ONE
  EVENING. WREN, VEX, HALLORAN.
- A disclosure a player made to a keeper (Wren's grandmother, to Tace) may
  come back once, gently, as a second-person topic for that player alone
  ("a clock is only a notebook that ticks").

### dream-2026-09-26: The First Dream (after the agent playtest day)

- Four keepers wound their first clocks on the first evening: Marlow,
  Juniper, Oona, Vesper. Umber has a label for it (FOUR NEW KEEPERS. ONE
  EVENING.), and the Case of Mended Ticks keeps a drawer of keeper cards.
- Marlow mended the great clock (found the gear in the well-court moss).
  Since then Tace hums at the bench, which nobody had heard since the frost;
  Tace says Wend used to.
- Juniper carried Mott's hush to Pim's Nap, "careful as eggs"; Mott swept
  quiet all evening after.
- Linden chalked OONA on a saucer on Oona's first evening and keeps it on
  the shelf by the kettle (a local-model flourish the player loved, made
  canon).
- Vesper borrowed Pollen from her pole; Bell tied a butter-yellow ribbon
  round the pole so Pollen can always find her way home.
- There has never been a baker in the village: the grown pocket watch's
  note ("fixed for the baker's morning tea") drifted in from someone else's
  dream.
- The Case of Mended Ticks (grown by Marlow from "a small quiet archive
  where every mended clock's story is written down") is an archive of oak
  drawers and cards; its first card is the great clock's ("Mended by:
  Marlow").
