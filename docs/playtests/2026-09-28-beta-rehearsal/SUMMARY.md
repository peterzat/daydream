# Beta rehearsal 2026-09-28: a small household of first players

A rehearsal of the first real audience: a handful of people who know each
other, play on different schedules, rarely at the same time, and have never
seen the game. Three agent playtesters in three archetypes played the fresh
dev village blind through `bin/game play`, against the real local models:

- **the gamer** (Vex): a teenage expert gamer, fast, mischievous, bored
  easily ([gamer.md](gamer.md));
- **the critic** (Wren): a teenage creative writer and reader who came to
  read everything and write into the world ([critic.md](critic.md));
- **the veteran** (Halloran): a seasoned MMORPG player and serious writer,
  arriving alone in the evening after the other two ([veteran.md](veteran.md)).

The gamer and the critic started together (siblings at home after school);
the veteran came two hours later. Between the sessions the village was
rebuilt in seven increments, the first dream was written from the digest
and installed, the clock was pinned to the next morning, and the critic and
the gamer came back for a coffee break each. Every session's critique is in
this folder; each was written blind, before the fixes it prompted.

## How the launch is likely to go

**The first evening is strong, and it is one person's.** Whoever opens the
invite first mends the clock in about fifteen minutes, plants the case's
dreamseed, meets Pim's Nap at the early first dusk, and can send it home
within the hour. The gamer did all of that in 60 commands. Everyone after
them takes the latecomer's path (the ledger's note, the first winding, Bell
hearing the new clock from the square, Mott's book), which two playtests
now confirm is a good ten minutes. The prologue's big moment happens once;
the first winding is everyone's own, and it lands.

**The others arrive into someone else's day, and that is the game.** The
household's experience is mostly asynchronous: each person walks into what
the last one left. Before this session, what they left was thin. A grown
room did not say who grew it; the Ledger credited bystanders; a friend's
letter, gift or "where are you" had no channel at all; the villagers, asked
about an absent friend, invented a room ("resting in the Orchard of
Evenings"). The veteran's whole critique is that she came looking for two
people and found two names in a book. After this session, the same evening
plays differently: the Ledger signs its last page with every keeper and when
they were last here; the room a friend grew says so at its door and on a
card in a keeper's hand; there is post at Fen's, an inbox to ask for, and a
line on arrival that says who was here while you rested; asked about a
friend by name, a keeper reads the record instead of guessing.

**Real-time overlap will happen more than expected, and it works.** The
siblings crossed paths in nearly every room. `say` carried; they pointed
each other at threads ("take the hush to the nap"); one watched the other
send the nap home and called it the best moment of the night. What they
could not do was hand each other anything (the game refused in the other
player's voice); now they can, and a gift to a friend who has stepped away
is tucked into their satchel for when they stir.

**The gamer will run out of authored things to do on day one; the daily
loop carries the rest.** After the prologue and one guest, the authored
day-one content is spent; boredom set in at the two rooms of pure scenery
(garden, orchard) and the flat first grown room. What kept the gamer
playing was the other player and the treehouse. From day two the village
brings one guest per dusk, one stray letter per dawn, three private stray
minutes per player per day, and the keeper arcs open on days two to four.
Six authored guests last about a week; after that the content is the
dreams. For this audience the operator's dream cadence is the single
largest lever on satisfaction (below).

**The two writers will love the authored lines and be let down by free
conversation, in the moment.** The critic's verdict: the chips are where the
writing lives; free talk hears one real question in five. The worst moment
of her session was telling Tace about a grandmother who forgot everyone and
hearing about clock oil. The same session showed the ceiling: Tace
remembered the notebook forty commands later and folded it into clockwork.
The fixes below raise the floor (a long question is no longer hijacked by
a passing topic word; the record of dreamers is in the prompt; a reply on
its way is visible), but the local model's voice is the local model's, and
the plan for these two is the one already in the roadmap: move their
favourite questions into authored topics through the dreams.

## The morning after

Both returning players saw the first dream's note on waking, found their
rooms rewritten and signed in a keeper's hand, and found each other's
traces. The critic's verdict on day two: the village did the three things
she asked for the night before (kept her writing, heard the question,
signed the rooms), and she wants to come back, with two conditions the
session then fixed (a nagging "letter waiting" line, a letter too long
vanishing without a word) and one it cannot (the Ledger's day-one lines
still credit her with the mending, written before the credit rule changed;
a fresh prod village will never carry them). The gamer's verdict on day
two was a clear yes: things had happened to his rooms while he was away
(Tace's card in the skate bowl, Bell's sooty chalk on his treehouse slate),
a letter about the brass hand he left for a friend was waiting, and he
delivered the first stray letter of the letters arc; boredom did not set
in. His two walls were a typed "ring bell" that found no bell (fixed: a
typed target now rides along as a clicked one did) and Bell's offer of a
lantern for the treehouse, which the dream's line promised and nothing
backed (a runbook lesson now: a topic line never promises a mechanic no
rule provides). Both returning players saw the "while you were away"
lines: who was here, the room that grew and whose seed, the letter
waiting; the gamer's arrival read "Wren, Halloran and Peek were here
while you rested."

## What was built this session

Each increment carries its tests; the short and medium tiers are green.

| Increment | What it fixes |
|---|---|
| Planting names its planter | The parent room's new sentence and the husk name who grew a place and their words; the payoff has a third-person telling for the room; refusals and the seed's question are the planter's alone; `plant dreamseed: <vision>` parses with no model call. |
| Between dreamers | `give X to <dreamer>` hands a thing over (tucked into the satchel of one who is dozing; refused for one resting); the margin lists who else is awake and where ("also dreaming"); leaving and returning re-snapshot the room and are announced; a page closed under 90 s is not yet dozing. |
| Letters through Fen | `write to <dreamer>: <words>` at the post office files a letter only that dreamer sees, takes and reads; told once on arrival, listed in threads, and at once if they are awake elsewhere (the counter bell). Fen answers "anything for me?" with what waits and from whom. Every line authored in `config.post`. |
| Honest credit and small fixes | Helpers are the players who moved an arc for everyone (a per-player beat earns none; reading the ledger earns none); a per-player beat's line is the asker's alone; the key in your hand opens the case; "use the hush on the nap" gives it; last words of a name ground ("brass hand"); a husk no longer answers to "dreamseed"; three stray minutes a day; drift's local rewording off by default. |
| While you were away | The first connection after a rest composes, once, who dreamed here meanwhile, the chronicle's new lines, guests that came, places that grew and whose seed, and post waiting; shown as the same leaf a dream's note uses. |
| A reply on its way, a seed for every keeper | "Tace considers..." while an improvised reply composes, and "the seed stirs" while a plant composes. Quill keeps a dreamseed for every keeper who has wound their clock and been to Mott. The closing player counts among the helpers. |
| The village remembers dreamers | `ask <keeper> about <dreamer>` reads the record (last seen, state, deeds this keeper knows); the dialogue prompt carries the same record and never guesses a place; the Ledger ends with the keepers who have dreamed here; the board of room keys shows the guest hours waiting and gone home; a long question that mentions a topic goes to the model with the topic's words as grounding. |
| The first dream | `dream-2026-09-28`: the four grown rooms furnished and signed, callbacks by name as facts and twin topics, Umber's label for the first evening, the while-you-slept note. |

WORLD_VERSION is 1.8. The play bridge waits for the reply itself (not the
player's own echo) and prints limit notices, so agent playtests no longer
read a resident's reply a move late.

## What the three most wanted, and where each stands

1. **Sign the traces** (all three). Built: rooms, husks, cards in a
   keeper's hand, the Ledger's signature page, the away note. Not built:
   a thing left in the dead-letter drawer carries no name (the veteran's
   dead-drop); a note on an object in a room. A letter through Fen covers
   the need; a "leave X for Y" that survives the other's absence is the
   next step if the drawer keeps being used that way.
2. **Let players interact** (the gamer, the critic). Built: hand over,
   letters, the inbox, who is awake and where, a truthful "where is Wren".
   Not built: a whisper across rooms (the fiction has no channel for it
   and letters cover the asynchronous case); a per-dreamer tally (the
   gamer wanted a score; the Ledger and the Book are the right shape and
   the signature page adds names, not numbers, on purpose).
3. **Make the people hear the question** (the critic, the veteran). Built:
   the select-or-ground rule, the record of dreamers in the prompt, the
   thinking line. Remaining and structural: improvised replies are the
   local model's reach. The critic's list of the questions writers ask
   (what do you miss, are you afraid, do you remember me) is the seed of
   the reply-bank work in BACKLOG (`reply-banks-select-dont-write`); each
   dream digest lists the local lines to turn into authored topics.

## Proposals not built (ranked for this audience)

- **A whisper's honest substitute: Bell at dusk names who walked through
  today.** A dusk ritual line in the square ("Two dreamers walked through
  today: Wren and Halloran") gives the evening player the day's company
  without a friends list. Cheap: a storylet whose text the engine fills
  from the input log.
- **Per-dreamer threads for the shared guest.** The gamer will close every
  guest arc within an hour of its dusk; the others meet a closed arc. The
  per-player beats already let everyone hear the guest's story; what the
  latecomer lacks is a small thing of their own to do for it (a "help it
  settle" beat with a keepsake, per player, after the ending). Medium.
- **Two guests a day for a household.** `config.director.max_open_guests`
  is 2 and one arrival per dusk; with four players it could be 3, and a
  second arrival on a dusk when an arc closed early. A content decision as
  much as a code one; six authored guests run out sooner.
- **"Leave X for Y" with Fen.** `give X to Fen for Wren` files a thing the
  way a letter is filed (private to the recipient, told on arrival). The
  post's machinery is there; it needs the parser form and a Fen line.
- **The scenery that answers** (BACKLOG `scenery-nouns`): the gamer and the
  critic both hit "You don't see the crumpled notes here" on things the
  prose named. A dream can furnish each named thing; a general map is the
  engine feature.
- **Time-of-day in room prose.** Grown rooms and furnish descriptions are
  written once and read at every hour ("deepening blue" at breakfast). A
  rule for authors (in the dream runbook now) and, later, a per-phase
  sentence the engine appends from authored data.

## The dream cadence is the product

Everything the returning players praised on day two was authored the night
before from the digest: the signed cards, the callback topics, the rooms
rewritten in the village's voice, the note on waking. The engine's own
memory (the away note, the record of dreamers, the Ledger) tells the truth
about what happened; the dream makes it mean something. For a household
that plays daily, a dream every night or two for the first fortnight is the
difference between a game they finish in a week and a place they keep
coming back to. The runbook is `docs/DREAM-RUNBOOK.md`; this session's
patch is a worked example of a small one (four furnishings, six facts,
eleven topics, one note; about forty minutes including rehearsal).

## What to watch in the first week

- Whether the gamer's pace strips the shared arcs before the others meet
  them (the `shared-thread-contention` entry); the digest's arc table shows
  who did which beat.
- Whether letters get written, and answered. If the household adopts the
  post, the "leave X for Y" proposal is next.
- The local lines in each digest: any that swerve from a real question, or
  invent, become authored topics in that night's dream.
- Whether anyone plants Quill's seed and what they ask for; the dream
  furnishes it.
- Phones: a page closed for more than 90 s reads as dozing; speech to a
  dozing friend says so and points at Fen.

## Rubric, all sessions

| Session | Surprise | Consequence | Remembered | Return |
|---|---|---|---|---|
| gamer, day one | 4 | 3 | 3 | 3 |
| critic, day one | 4 | 4 | 3 | 4 |
| veteran, day one | 4 | 3 | 2 | 3 |
| critic, day two | (no scores asked) | | | yes, with conditions since fixed |
| gamer, day two | (no scores asked) | | | a clear yes |

Being remembered was the lowest score again on day one, as on 2026-09-26,
and the one the day-two sessions moved most.
