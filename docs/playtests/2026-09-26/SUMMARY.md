# Playtest day 2026-09-26: summary and dispositions

Four agent playtesters (SPEC 2026-09-26 criterion 17) played the live Village
of Lost Hours at the same time, blind, through `bin/game play` over the real
WebSocket path, against the real local models, from 17:45 to about 18:02
Pacific (the prologue was mended mid-session and the first dusk fell around
them). Their critiques: [explorer](explorer.md), [completionist](completionist.md),
[chatterbox](chatterbox.md), [rule-breaker](rule-breaker.md). About 500
commands in all; no server errors (a log monitor watched for them).

## Rubric

| Persona | Surprise | Consequence | Being remembered | Reason to return |
|---|---|---|---|---|
| Explorer (Juniper) | 4 | 4 | 3 | 4 |
| Completionist (Marlow) | 4 | 4 | 3 | 4 |
| Chatterbox (Oona) | 4 | 3 | 2 | 3 |
| Rule-breaker (Vesper) | 4 | 3 | 2 | 3 |
| Mean | 4.0 | 3.5 | 2.5 | 3.5 |

All four would come back; two said "yes", two "probably" or "maybe". The
consistent reasons: the authored writing, the growing world (a room grew
from Marlow's words mid-session and everyone noticed), the Ledger of Returned
Hours naming who did what, the Book of Stray Minutes, and threads left open
(the W clock, the jar on the highest shelf, Bell's dawn).

## Reflexes, not voice: what the measurement says

Tagging every narration by source (`src: "local"`, docs/REFLEXES.md): 77 of
510 narrations (15%) were written by the local model; the rest were authored
or engine text.

- **The best moments were authored**: the clock case opening, the dreamseed
  falling out, Pim's Nap's red kite, Tock, the ledger, the chip answers
  ("the best writing in the game", chatterbox), Bell's "Dawns are for other
  people. I've got dusks."
- **The worst lines were local**: "I do not know your name, friend, nor do I
  know of bees" (right after being told both), Mott's invented and
  thread-closing "I gave the hush to Pim", "Of course one!", Tace speaking of
  themself by name, flat "I do not know" denials, a model line bleeding the
  fourth wall into another player's answer.
- **A few local lines landed**: Fen's "That is a question for the inside of a
  letter, not the front"; Bell noticing Pollen was taken; Tace refusing a
  planted false memory ("Marlow carried the escapement gear home to me");
  Linden chalking Oona's name on a saucer, which the chatterbox loved.

This confirms the stance: the local model is worth it as reflexes (parsing,
answering the unplanned, painting what players make) and is the weak voice.
After the fixes were in, `bin/game world refresh` carried the corrected
content into the live world without losing the playtest day, and the first
dream (dream-2026-09-26) digested it.

The playtest fixes lean further on authored lines: a free-form line that
names an NPC's topic now gets the authored answer ("select, don't write"),
and the dream digest lists recent local lines as candidates for authored
rewrites, so each dream can turn frequent improvisations into authored
topics.

## Defects and dispositions

Every defect the four critiques raised, grouped. "Engine" items are fixed in
commits 283aa22, 0d6dd82, 450031d (refresh), and the question-hint commit;
"Data" items in the world-data pass that follows; "Backlog" items are
recorded in BACKLOG.md.

### A shared room reads right (engine, fixed)

- Other players' private results reached everyone in second person ("You
  take the brass pendulum", "You turn the little key", "You think to
  yourself: eat the pocket watch", "They fold a small brass key into your
  hand"): narration that addresses "you" now goes to the actor alone, with
  optional third-person `others` lines; take/drop/open/put speak in the third
  person to the room; the unparsed-input fallback is private.
- NPC replies had no addressee and interleaved in a busy room: topic answers
  and improvised replies go to the asker; bystanders see one "X and Y talk
  quietly" line per pair per ten minutes.
- Entry greetings repeated to everyone on every arrival: once per NPC per
  session, to the arriving player only.
- "Marlow doesn't have much to say just now" (the game answering for a
  player): talking to another player is addressed speech.
- Gift refusals: one smiling template for everyone, a cat included, sent to
  the whole room: private, per-NPC variants (`declines_text` lists), neutral
  default.
- Players vanished silently when they left: "<name> drifts out of the dream
  for now."
- Replies arriving a command late in `bin/game play`: the bridge waits for a
  line addressed to the player.

### The parser (engine, fixed)

- Multi-sentence input split at every period, tails misparsed or dropped:
  periods and THEN split only command chains.
- `say` misread by the model (a `say` that moved the player, one that talked
  to a player as an NPC, one that vanished): `say ...` is deterministic.
- `talk to X: ...` lost sentences and cost a parser call: deterministic.
- "I keep bees back home" ran inventory: one-letter aliases act only alone.
- "You don't see the listen here" (and-lists and commas): a list only counts
  when something in it is here; long unmatched phrases go to the model.
- "take X from Y", "drop X in Y", "look through the telescope", "look out the
  window": handled.
- "You examine the Mott's tin", "the hush: a hush:", "on the The Lantern
  Square", lowercase character notes: fixed article and restatement handling.

### Improvised dialogue (engine, fixed where the engine can)

- Invented, thread-closing facts (Mott's hush) and generic answers to
  on-topic questions: a free line naming a topic or open beat gets the
  authored answer.
- Robotic "I do not know" denials, denying what the player just said, NPCs
  naming themselves: prompt changes plus reranker penalties.
- 7 to 9 second replies with four players: one candidate instead of two when
  the GPU is busy; `say` and `talk to` skip the parser call.
- Memory of what players told NPCs (being remembered 2.5): improved by
  keeping lines whole (the name and the bees now reach the NPC in one
  exchange); a durable memory of player self-disclosures is **backlogged**
  (`npc-memory-of-player-disclosures`).
- Model glitches ("Of course one!", "tucked away for now one"): no engine
  fix; the reply-bank direction is **backlogged** (`reply-banks-select-dont-write`).

### Stranded and stale content

- Quest items stranded with players who left (the spare pendulum, the letters):
  engine `rest_returns_things` + homes; a refresh sends home what resting
  players already hold.
- Stray minutes placed in rooms a newcomer never visits: the first daily find
  lands one exit from the player (engine).
- The dream digest skipped players who had left: fixed (`objects.is_player`).
- A grown room's parent never mentioned the new way: fixed (engine).
- A grown note named a baker in a village with no bakery: `never_words` on
  dreamseed growth (engine); the list itself is **data**.
- The plant prompt didn't say how to answer: `question_hint` (engine) and its
  text (**data**).
- **Data, fixed in 82451d4** (the world-data pass): stale lines after quests (Tace's gear topic,
  the nap's refusals, "Here's your first", the lullaby pendulum pointer, the
  hush after it was given), Tace's evasive W-clock framing, Umber's tea, Bell
  taking Pollen back, Linden's nap ending requiring a helper, per-resident
  refusals, everyday affordances (sit, wait, ring, pet, eat, sleep), scenery
  aliases and a west window, resident examine text as observable sentences,
  Tace's first-winding nudge and Bell's welcome for new keepers, `others`
  lines for shared moments, the clock-case seed, `never_words` (33) and the
  `question_hint` text. Two small gaps remain and are backlogged under
  `scenery-nouns`: a bare "read a letter" in the post office still asks
  which letter (a bare alias would collide with the rain-spotted letter),
  and a four-word target such as "scratch Tock behind the ears" still goes
  to the model.

### Backlogged

- `thinking-indicator`: a quiet "Tace considers..." while a reply is coming
  (explorer, chatterbox: "nothing tells you a reply is coming").
- `dusk-after-an-early-first-dusk`: the prologue's early dusk means the real
  18:00 dusk passes unmarked on day one; the Dusk Road's falling lights at
  dusk are data, the general beat is not.
- `shared-thread-contention`: latecomers found both open threads finished by
  others (rule-breaker); more concurrent threads per day or per-player
  variants.
- `npc-memory-of-player-disclosures`, `reply-banks-select-dont-write`
  (above).
- `scenery-nouns`: described details that don't exist when touched, in
  general (the data pass covers the ones the playtesters named).
- The grown room "The Case of Mended Ticks" is thin and slightly garbled:
  the first dream furnishes it.
