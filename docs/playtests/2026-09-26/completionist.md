# Playtest: The Completionist (Marlow)

Played 2026-09-27 00:45 to 00:54 UTC (17:45 to 17:54 Pacific, just before dusk), about 90 commands, as `Marlow` ("a neat young man with a notebook tucked under one arm and a pencil behind his ear"). Other dreamers present: Juniper, Vesper, Oona. Note on pace: I moved faster than a human would, so I covered about 90 commands in 9 minutes of wall time rather than 20 to 30.

## Session summary

I started in the Clocktower and read both books first. The repair ledger states the problem cleanly: the escapement gear "rolled out across the square and away south, toward the old well-court. Whoever carries it back to Tace in the loft will have earned the case-key." I climbed to the Clockmaker's Loft and worked through Tace's thirteen ask-about chips, which set up several threads (Wend, the frost, the highest shelf, the little brass clock marked W that Tace would not let me wind). I took a spare brass pendulum from the loft, went east to the Lantern Square (Bell), south to the Mossy Well-Court, found the gear lying in the moss, and peeked one room further south into the Pendulum Garden (Quill), who declined my spare pendulum.

Back in the loft I gave Tace the gear and got the case key. I unlocked and opened the clock case: the great clock started, a warm brass cog and a dreamseed dropped out, and the status line changed from "(time stands still here)" to "(day 1, dusk)". The Ledger of Returned Hours now reads "The great clock was mended by Marlow, and time began again in the village." I visited Umber in the Hour Cellar (jars of saved hours, a single jar on the unreachable highest shelf), then planted the dreamseed in the Clocktower with the phrase "a small quiet archive where every mended clock's story is written down". A new room opened north, The Case of Mended Ticks.

Returning to the loft I found Tock the cat and a new chip on Tace, "the first winding", which gave me a small clock of my own to wind. Tace then pointed me to Bell and Mott. In the square a dusk guest had arrived, Pim's Nap, a birthday nap too excited to be taken; Bell said Mott keeps "a hush in his tin". In the Old Workshop Mott gave me my first stray minute through the "the book" chip, but no hush.

Threads closed: the gear, the clock case, the dreamseed, the first winding, the first stray minute.
Threads left open: Pim's Nap and the hush; Tace's "lullaby clocks"; the jar on the highest shelf; the W clock, Wend, and the frost; Bell never having seen a dawn; the folded thing under Mott's thumb; 171 stray minutes. Unvisited: the Winding Balcony, the orchard, Lamplight Lane (Lamp House, Sorrel, Linden).

## Rubric

**Surprise: 4/5.** Opening the clock case was a genuine payoff ("high overhead the great clock takes its first slow tick in a long, long while"), and I did not expect the seed to fall out of it, the cat to materialize ("Between one tick and the next, a small grey cat is simply there, washing one white paw as if it had always been"), or a personified lost nap to be waiting in the square at dusk. Not a 5 because the core puzzle was a straight fetch with the item in plain sight one room from where the ledger said it would be.

**Consequence: 4/5.** Mending the clock visibly changed the world: the status line started keeping village time, Tace's mood went from "wistful" to "gladdened", new chips appeared on Tace ("the first winding") and Bell ("the yawning stranger", "the guests", "the great clock"), the ledger recorded the deed, and the dreamseed made a real, walkable room from my own words. Docked because some NPC state did not follow: Tace's gear topic still asks me to find the gear after I delivered it, and Mott's free-text reply falsely closed the nap thread.

**Being remembered: 3/5.** The Ledger of Returned Hours writing my name is exactly what a completionist wants, and Umber acknowledged my deed in free text ("Yes, the great clock ticks again; it was waiting for a hand to turn. Since you found the gear by the well..."). But no character ever called me Marlow. Everyone says "friend", and Tace addressed another player with "I do not know your name, friend".

**Reason to return: 4/5.** Yes, I would come back tomorrow. I left with at least seven named open threads, three unvisited areas, and a book to fill, and the writing is consistently lovely. What holds it back from a 5: I have no idea how to find stray minutes on my own. Mott says "They glint about the place, a few for each dreamer each day", but I saw nothing glinting in eight rooms, and "1/172" is a daunting denominator with no visible next step.

## Defects

1. **The game spoke for my character.** On `up` (entering the loft) and again on `take brass pendulum`, my meanwhile feed showed "Marlow doesn't have much to say just now." It looks like another dreamer addressed me and the game answered on my behalf with an NPC-style deflection, in the third person, about me. Expected: the other player's words delivered to me, or nothing. A player character should never be given a line.

2. **Tace's gear topic goes stale after the quest completes.** `give escapement gear to Tace` printed the lovely key handover, then immediately in the same response: "South, I think, toward the old well-court. A small brass gear, sound and whole. Bring it home to this bench, friend, and by custom the case-key is yours." A follow-up `ask Tace about the gear` still said "If you found it, friend, the case-key would be yours." Expected the gear topic to acknowledge the gear is home, or retire.

3. **Another player's second-person narration leaked into my feed.** On `up` back into the loft, my meanwhile showed "You turn the little key. The small clock hesitates, then begins to tick, soft and sure, a half-beat apart from every other clock on the shelf. Tace watches with their hands folded..." I had not wound anything (I got that exact line myself later from `wind small clock`). It reads as if I acted. Expected "Juniper turns the little key..." or third person.

4. **The first-winding beat is hidden behind a chip.** After mending the clock I tried `wind resting clocks` in the loft; it returned a generic flavor line ("You turn the key of a little painted clock. It hums, clears its throat, and begins again, a half-beat behind its neighbors.") and advanced nothing. The real beat needed `ask Tace about the first winding`, which handed me a "small clock", then `wind small clock`. Tace never offered it while I stood there. Expected Tace to hand me the clock when I returned, or the generic wind to nudge me toward Tace.

5. **Invented fact that closes a live thread.** `ask Mott for a hush for the birthday nap in the square` returned "I gave the hush to Pim for his nap, so the boy might finally rest. It is safe now." Bell had just told me "Mott keeps a hush in his tin", and the nap was still wide awake in the square. Pim is the child whose nap got lost, so the reply contradicts the setup. No hush was given, `ask Mott about the tin` lists "Button. Bent key. Thimble. Blue chalk." and no hush, and Mott has no hush or nap chip. Expected a hush, or a pointer to what Mott needs first. (If Oona, who left the workshop as I asked, took the hush, the game should say so, not claim Pim got it.)

6. **Umber's tea cannot be accepted.** Tace promises "she'll offer you tea" and Umber offers it ("Down here, there's tea, if you'll take some."). `accept Umber's tea` returned "You think to yourself: "accept Umber's tea". The daydream answers softly." `talk to Umber about tea. Yes please, I'd love a cup.` got talk about "welcome a new keeper" and "Remember to taste it before you label it 'done'", but no tea. Expected a cup, even flavor-only.

7. **My `say` was hijacked by an NPC.** `say Hello all. I'm Marlow. Anyone found the escapement gear yet? ...` in the loft produced no "You say" echo; instead Tace answered with the gear line as if I had talked to Tace. I could not tell whether the other dreamers heard me. Expected my words broadcast to the room with an echo, and no NPC treating a room-wide say as addressed to them.

8. **Tace's ignorance about the W clock contradicts the room.** In meanwhile (answering another dreamer): "That little brass clock with the W on it? I do not know what belongs on its face. It is not among the pieces I have mended, nor the things in Mott's tin. I cannot say where it came from." The clock's own examine says it is scratched with a W, has stood at eleven since the first hard frost, and Tace had just told me "Not that one, friend." Evasion would fit; flat "I cannot say where it came from" reads like an invented fact.

9. **Verbatim repeats flood the feed.** Entry lines replay every time anyone enters: "Tace looks up from a bench of small clocks, sets down a fine brass tool, and offers a tired, kind nod." (4 times), "Bell is up a small ladder coaxing a lantern alight, and lifts a sooty hand in greeting." (3 times), "A small rumpled figure yawns so wide its whole body tilts..." (twice), "Some shelves are too high for me" (twice), "It is a pleasure to meet you, Oona. Please, do not mind the ticking..." (twice), and the nap's Pim story (twice, once as another player's ask). Expected entry flavor only on my own arrival, and variety on repeats.

10. **Duplicated reply.** `ask Bell about the yawning stranger` printed Bell's full reply twice, once under "(meanwhile)" and once as my result.

11. **Slow free-text replies.** `talk to Umber about tea...` took 6.2 s; `talk to Umber: did you hear the great clock start ticking?...` took 9.5 s; the plant took 10.8 s; `ask Mott for a hush...` 5.2 s. The ask chips were consistently about 1.3 s, which felt great; the 9 to 11 second waits felt long.

12. **Grammar.** `examine Mott's tin` returned "You examine the Mott's tin: ...".

13. **Non sequiturs in free talk and chips.** Umber: "Keep your feet off the dusty floorboards." (unprompted, in the cellar). Umber's "the kept guests" chip answers about hours ("A kept hour sleeps well down here"), not guests. The grown room's "bundle of dried gears" is "used to patch the broken springs of clocks that refused to stop ticking", which is backwards, and its description mentions "the soft scratch of a quill", which collides with the gardener's name, Quill.

14. **The plant prompt is terse.** `plant dreamseed` alone returned only "Where does the new way lead?" It did not say how to answer. I guessed `plant dreamseed: <phrase>`, which worked. Expected a hint like "plant it with a few words about what you hope to find".

15. **No findable stray minutes on my path.** Mott's explanation implies minutes glint in the world, but no room I visited listed anything minute-like under "Around you". The only minute I got was handed to me through a chip. For the persona built around the Book this was the biggest frustration. Expected at least one visible minute on the starting route, or a description of what "glinting" looks like in a room listing.

16. **Tace's promise to Bell went nowhere.** After the first winding Tace said "Bell will want to meet you, down in the square." Bell greeted me with the same ladder line as before and nothing new happened until I picked the "yawning stranger" chip myself. Expected Bell to meet me, as promised.

## Three best moments

1. **The clock case opens.** "The little lock gives, the case door swings wide, and behind the glass the pendulum stirs, swings, and catches the light, and high overhead the great clock takes its first slow tick in a long, long while." Then the seed: "something small glows and drops softly to the floor of the case: a dreamseed, warm as a thank-you." And the status line quietly flipping from "(time stands still here)" to "(day 1, dusk)". Then the ledger with my name in it. That is a satisfying first quest close.

2. **Planting the seed.** My phrase became "The Case of Mended Ticks", a room that honored what I asked for ("Each timepiece sits beside a small card describing the gentle hour it saved for someone else"), with a payoff line I would quote to a friend: "Down in the square, a lantern comes alight early, the way a house does when someone dear is coming home."

3. **The minutes and the nap.** Mott's first minute, "the shut-door minute. It was bedtime with the door closed all the way for the very first time, and sleep coming anyway", and Pim's Nap: "Pim was seven, and there was cake and a red kite and too much singing, so Pim wouldn't sleep, and I got lost." Small, specific, and genuinely touching. This is the voice that makes me want to fill the book.
