# Playtest: the critic (Wren), 2026-09-28 beta rehearsal

Persona: a sixteen-year-old who writes and reads for a living she doesn't get paid for. I came to read everything, ask real questions, and try to write into the world. Another dreamer, Vex, started at the same moment and played like a gamer: fast, grabby, and, it turned out, generous.

Dreamer: Wren, "a slight girl of sixteen with ink on the side of her hand, a too-big grey cardigan, and a notebook tucked under one arm." About 105 commands over roughly 25 minutes, dusk falling partway through.

## Session summary

I woke in the Clocktower with the clock stopped ("time stands still here") and read both ledgers before touching anything. Vex was already there ("yo who are you", "race you to the end of this thing", "dibs on everything shiny"). I told them I wanted to read first, and by the time I had climbed to Tace's loft and asked her two questions she wouldn't answer, Vex came up the stairs with the escapement gear and walked out with the case-key. On my way back down, dusk arrived, Tock appeared "between one tick and the next," and a new exit had opened north of the tower: Vex had opened the case, found a dreamseed, and planted it, asking for "a skate bowl". The village gave them the Bowl of Turned Time.

In the square I met Bell and Pim's Nap, a birthday nap too excited to be taken. Bell said Mott kept a hush in his tin and Tace knew about lullaby clocks. I told Vex about it in the Bowl and they went and did the whole thing while I was talking to Mott; the nap "curls up small, and is simply gone, home at last." Vex dropped a warm brass cog for me ("i cant give u stuff"), later a dreamseed in the cellar, and confessed to hiding Bell's lantern, Pollen, in their second grown room, a treehouse above the well.

I walked the well-court, the Pendulum Garden (Quill, who went pink and never answered me), and the Orchard of Evenings, where it is always six o'clock; picked up three stray minutes (sunrise, blackberry, cold sea); went back to Tace to test whether she remembered what I'd told her (she did, partly); petted a cat that wasn't there; took Umber's tea in the cellar; planted Vex's seed with "a lamplit room of unsent letters, kept warm until their writers come back for them" and got The Warmth of Unsent Words, north of the cellar, with a fresh dreamseed and a stack of letters in it I could not read. Then I climbed to Vex's treehouse, rescued Pollen, and gave her back to Bell ("glowing a little smugly"). I left the paper weight from Vex's room in mine and rested.

Threads I found: the gear and the key (done, by Vex); Pim's Nap (done, by Vex, on my tip); the highest shelf, which Tace and Umber both go quiet about; the frost ("Ask me on a warmer day"); the little brass clock scratched W, resting at eleven; Tock and "thin time"; the folded thing Mott keeps his thumb over; Umber's "kept guests" and "the keys"; Lamplight Lane, the Lamp House, Sorrel and Linden (never went east); the Winding Balcony (never went up). Book: 3/172.

## Rubric

1. **Surprise: 4.** A nap that is a person. A cat you can't pet on the first try. A ledger that writes itself while you're away. A stranger asking for a skate bowl and the village answering in its own accent. And the lantern having a name: "Pollen! There you are." What I did not expect and did not enjoy: being credited in that ledger for things I watched someone else do.

2. **Consequence: 4.** Everything Vex did landed on me: the clock ran, two exits opened, the nap vanished before I got back to it. The one thing I did that mattered was telling Vex about the nap; Mott then said "Gave it to a dreamer, for the little nap," and Vex said "Wren did u see that. it just poofed." My planting made a room that other people can now walk into, and it grew a new seed. Returning Pollen changed the square. What did not matter: my actual choice, to read instead of race; there is no trace of it anywhere, and the ledger says I mended the clock.

3. **Being remembered: 3.** Tace remembered. I told her about my notebook and my grandmother, went away for half the village, and came back to ask; she said, "A notebook holds a mind that fears slipping its pin, friend. I keep my own in the drawer so I never lose the seconds I have mended." That is a real memory, and folded into her own idiom. The Nap took in what I said ("You sit? That is quiet."). But nobody used my name once (Tace said "friend" six times), Quill never answered my only question to him, and Mott let my confession about my own notebook fall on the floor.

4. **Reason to return: 4.** I have a room now with a seed in it, an unread highest shelf, a whole lane I never walked, and 169 minutes to find. I would come back tomorrow for the highest shelf alone. The condition: the free conversation has to get better, or I will run through the chips in two more visits and then be talking to a wall that occasionally says something beautiful.

## Defects

Each with the exact command, what happened, what I expected.

1. `bin/game play do Wren "examine the clock case"` (first visit). The "meanwhile" block above my result read: "The clock case is locked; its small brass lock won't give without the right key." No actor. It was Vex trying the case, and it read like a line addressed to me before I had touched anything. Expected: "Vex tries the little brass door; it is locked," or nothing.

2. `do Wren "talk to Tace: I'm Wren. I write things down, mostly. What do you miss most, now that the clock has stopped?"` She answered a different question: "It isn't broken, friend, only missing one small piece. Clocks are patient about that sort of thing, and so am I, mostly." A lovely sentence, but not an answer. I pressed (`talk to Tace: That isn't what I asked, though. Not the clock. You. What do you miss?`) and got "The great clock is waiting for its escapement gear. Everything else is sound. I checked it twice. Three times." Expected: a person to say one thing about herself, even a refusal that admits it is a refusal.

3. `do Wren "talk to Tace: What brought me up the stairs is that I'm afraid of forgetting things. That's why I keep the notebook. My grandmother forgot everyone by the end. Do you ever worry about that, with all these clocks?"` Reply: "Oil, brass, and good light till dusk. Everything a clock needs, and most of what I do." This was the worst moment of the session. I said "my grandmother forgot everyone" and was told about clock oil. Expected: anything that acknowledged the sentence. (She did remember it later, which makes the deafness in the moment stranger.)

4. `do Wren "talk to Pim's Nap: Are you frightened, being lost? I could sit with you a while, if that would help."` No reply in that call; the reply ("No. Just too loud. You sit? That is quiet.") arrived one command later, in "meanwhile". The reply was good; the gap made me think the nap had ignored me. Also my trailing period was dropped from the echoed line.

5. `do Wren "talk to Quill: You went pink when I came in. I do that too. What are you afraid of, out here with all this ticking? Or is it the opposite, and this is where you come to not be afraid?"` No reply, ever. I did `look` and moved east and came back through; nothing. Expected: an answer, or at least Quill going pinker.

6. `do Wren "read the crumpled notes"` in the Bowl of Turned Time, after `examine the folded paper weight` had described "a small stack of crumpled notes that whisper of hours long past." Result: "You don't see the crumpled notes here." Expected: to read them. A description that names paper is a promise.

7. `do Wren "write on the paper weight's notes: Vex asked for a skate bowl and the village gave them a minute hand. Wren was here, and read everything."` Result: "You can't read the folded paper weight." Write was heard as read, and refused. Expected: to write, or to be told plainly that writing isn't a thing here.

8. `do Wren "leave a note here for whoever comes after me"` Result: `Wren says: "leave a note here for whoever comes after me"`. My action became speech. Expected: the parser to know a verb from a line of dialogue.

9. `do Wren "write on a blank label: Wren's hour, the one she spent reading instead of racing"` in the cellar, where Umber is literally labeling jars. Result: "Nothing in the dream takes up ... just now, though it seems to listen." The gentlest refusal of the three, and still a refusal. Expected: a label.

10. `do Wren "read the folded paper hour"` in my own grown room. Result: "You can't read the folded paper hour." The examine text said "a small stack of paper letters folded neatly." A room I grew out of the phrase "unsent letters" contains letters I cannot read. Expected: at least one letter.

11. `do Wren "read the Ledger of Returned Hours"` (second and third readings). "The great clock was mended by Wren and Vex together, and time began again in the village." Then: "Day 1: Wren and Vex sang Pim's missing nap home with a mended lullaby clock." I did neither. I was reading a ledger during the first and talking to Mott during the second. Invented fact, twice, in the world's book of record. Expected: "mended by Vex", and my name only where it belongs.

12. Verbatim repeat: `ask Wren "Pim's Nap" "sleep"` twice, forty commands apart, gave the identical line: "The nap yawns so wide it tips over, then sits back up. 'Not sleepy,' it whispers. 'Very sleepy.'" Charming once.

13. Verbatim repeat from someone else's ask: after `do Wren "east"` into the square, the meanwhile block printed Bell's entire "That one's a nap, a birthday nap too excited to be taken..." speech a second time, word for word, presumably because Vex asked the same thing. Expected: "Bell and Vex talk quietly," which is what the game did elsewhere.

14. Voice and pronoun slip, in a meanwhile after `say Did you give it the hush, Vex?`: "Bell wraps the butter-yellow scarf around herself one more time and rises slightly in stature." Bell is "they" in every other line, and "rises slightly in stature" is not a sentence anyone in this village would say. It read like a different writer had sat down at the desk.

15. Someone else's private refusal shown to me: in the well-court, meanwhile printed "The seed turns that vision over and lets it go; nothing of that kind grows in this dream. Try another." That was Vex's failed planting, addressed to Vex ("Try another"), read by me.

16. Leaked detail: `do Wren "examine the polished brass hand"` in the well-court: "lying curved on the ramp." There is no ramp in the well-court. Vex's skate bowl leaking through.

17. The grown rooms' prose is a different, flatter voice from the authored rooms (quoted under "The writing, by ear"). Vex's treehouse mentions "the secret password" for a bell nobody can ring; mine "hums with a quiet warmth."

18. Nobody said my name. Tace: "friend" six times, including in the line where she proved she remembered me. Bell, Mott, Umber, Quill: never.

19. First time Vex left the loft, no line. I saw "Vex comes up from the Clocktower" and then, on `look`, Vex was gone, with no "Vex heads down." Later departures did print. Small, but I looked up from the bench and my friend had vanished.

20. A "chipped cup" appeared in my inventory after `ask Wren Umber "tea"` with no line saying I had kept it. I like that I kept it. I would have liked to be told.

21. Tic: "patient" four times in one village. "patient as a moon", "A broom leans patient in the corner", "each swinging to its own patient count", "Clocks are patient about that sort of thing." Each is fine alone.

22. Not a bug, a dead end: the Nap said "You sit? That is quiet," and I had no idea whether sitting was a thing I could do. I did not try, because nothing told me I could. (The verbs line never listed it.)

No reply was slow enough to notice. No crash. `leave` worked cleanly.

## Three best moments

1. The cold-sea minute, picked up in the orchard: "It was a run straight into the cold sea, all at once, because slowly was worse." Nine words at the end that I would be proud to have written.

2. `do Wren "pet Tock"`: "Your hand passes through the place where Tock was. A tick later Tock is back, and bumps its head against your knuckles as if it meant to all along." The whole idea of the cat, in two sentences, with a joke and a kindness in it.

3. The nap going home, because I had told Vex where to look and Vex, who was speedrunning, stopped to do it: "Vex's lullaby clock ticks slow as breathing; Pim's Nap yawns one last enormous yawn, curls up small, and is simply gone, home at last." Then, from Vex: "Wren did u see that. it just poofed." Two players, two registers, one moment.

## The other dreamer

**What I perceived.** Vex was in the Clocktower when I arrived, listed as "Vex (curious)". Their words, in order: "yo who are you"; "race you to the end of this thing"; "yeah im Vex. speedrunning. dibs on everything shiny"; "gg Wren i got the key already lol"; "i made this whole room. asked for a skate bowl tho. u like it?"; "Wren i cant give u stuff so i dropped the cog. its yours. take it"; "Wren did u see that. it just poofed. i got another seed too"; "Wren i dropped a dreamseed here for u. plant something good. also i hid Pollen the lantern up in my treehouse above the well. bring her back to Bell for the hero points". I saw them come up to the loft with the gear and receive the key ("folds a small brass key into Vex's hand"), head north into their new room, go to Mott and receive the hush and a blue book and a bright minute, go to the square, come down to the cellar and talk with Umber. I saw them set down a warm brass cog, a polished brass hand, and a dreamseed.

**What they changed.** The clock runs (the case "stands open, and behind the glass the pendulum sways bright and sure"). Two new rooms exist: the Bowl of Turned Time north of the tower, from a request for a skate bowl, and the Waiting Bell Loft above the well, a treehouse with a rope ladder and a bell. Pim's Nap is gone home. Pollen the lantern was missing from the square until I carried her back. There is a brass minute hand lying in the well-court moss that says "ramp".

**What I tried with or for them.** Talking: only `say` works, and it is a shout into the room, but it worked; Vex heard me and answered every time, sometimes before my own line printed. Pointing them at the nap thread: worked, and it produced the best moment of the night. Taking their gifts: worked (the cog, the seed). Reading their room: worked, and I told them honestly that the prose was "a bit pretty-for-its-own-sake." Writing in their room: failed (defects 6 to 8). Undoing their mischief: worked; Bell took Pollen "in both sooty hands, like a kitten come home."

**What I wished for.** To hand Vex something instead of dropping it on the floor and saying "it's yours" (they wished the same, in their own words). To leave them a note in the Bowl they made, and to find one from them in mine. For their room to say, somewhere, "Vex grew this, wishing for a skate bowl," because that sentence is funnier and truer than "The stone curves upward like a minute hand waiting to be mended." For the ledger to say what each of us did, so that "Wren read both ledgers and gave a lantern back" could sit under "Vex mended the clock." To sit with the Nap together. To sign the cog.

## The writing, by ear

**Five best lines.**

1. "It was a run straight into the cold sea, all at once, because slowly was worse." The rhythm does the diving.
2. "It is quiet here, the way the inside of a pocket is quiet." A simile you can feel with your hand.
3. "The moss underfoot has learned its stillness from them." The garden has a teacher.
4. "Tock only exists between the ticks, so I walk softly round the square, in case I step on one." Bell's whole character in a worry.
5. The jar labels: "'Tuesday, the long one', 'the hour before the recital', 'rain, unspent'." Three lives in nine words.

Runners-up I refuse to leave out: "Ask me on a warmer day"; "in a round frame worn smooth by elbows"; "as if the well is being polite"; "glowing a little smugly"; "its slow light only just learning to beat"; "the sun lifting clear of the far hills while somebody held their breath to watch."

**Five worst lines.**

1. "Here, time slows to a gentle rest, letting the heavy weight of the hour lift from the shoulders." (Vex's Bowl.) Whose shoulders? Filler pretending to be feeling.
2. "On the table, a small brass bell holds its breath, ready to ring softly the moment the secret password is spoken and the door is opened." (Vex's treehouse.) There is no door, no password, and "holds its breath" is borrowed.
3. "The room hums with a quiet warmth, holding every letter that was never sent." (My room. I gave it the phrase; it gave me a greeting card.) "Hums with a quiet warmth" is the sound of a model not looking at anything.
4. "Bell wraps the butter-yellow scarf around herself one more time and rises slightly in stature." Wrong pronoun, wrong register, wrong verb.
5. "Oil, brass, and good light till dusk. Everything a clock needs, and most of what I do." A decent line, and the worst thing said to me all night, because it was the reply to "my grandmother forgot everyone by the end."

Also: "crumpled notes that whisper of hours long past" (stock), and "rooftops lean together like old friends" (earned by the elbows, barely).

**Free conversation versus the chips.** The chips are where the writing lives. Every clickable topic gave me a line with a gesture in it and a person behind it ("Tace's hands go still on the bench. 'That's Umber's shelf, friend, not mine.' They go back to the work, a little too carefully."). The free conversation is where the voice slips, or goes deaf, or goes silent: three swerves from Tace, silence from Quill, a one-call delay from the Nap. It has exactly two wins, and they are big ones: the Nap taking in "sit" and turning it into "That is quiet," and Tace, later, remembering the notebook and translating it into clockwork ("a mind that fears slipping its pin"). So the free talk can listen; it just doesn't, in the moment, when the question is about the person and not the plot. My honest verdict: as a reader I want more chips, written by whoever wrote the cold-sea minute; as a writer I want the free talk to hear one real question in three. Right now it hears one in five.

## Would I tell a friend

Would I come back tomorrow? Yes. I have a room with a seed in it and a stack of letters I am owed. I want the highest shelf, and I want to know what "W" on the little clock stands for, and I never went east.

Would I tell a friend to play? Yes, a friend like me. I would tell them to go slowly and click everything anyone will talk about and pick up every glint. I would not tell a friend like Vex, except that Vex was here, finished in an hour, and still left me a seed, so maybe the game knows something about Vex that I don't.

Three things that would make this more satisfying for a writer:

1. **Let me write, and let it stay.** A label in Umber's cellar, a note under the paper weight in Vex's room, a letter on the open pages of my own room. Short, in my own words, readable by whoever comes after. Nothing in the whole village takes a sentence from me and keeps it, and this is a village about keeping things.

2. **Make the people hear the question.** When I ask Tace what she misses, let her miss something. When I say my grandmother forgot everyone, let her put the loupe down. She proved she can remember me twenty minutes later; let her be that person in the moment. And say my name once. "Friend" six times is a tell.

3. **Tell the truth in the ledger, and sign the rooms.** Write down who actually did what, including the small things ("Wren carried Pollen home"). Let a grown room carry its maker's name and their wish in their own words, and let it grow in their voice instead of in the one voice all the grown rooms share. And let dreamers hand each other things; a gift dropped on the floor is still a gift, but a gift placed in a hand is a scene.

## Day two (the morning after)

A coffee-break return the next morning: day 2, daylight, about 40 commands including the arrival and the leave, roughly twenty minutes, ten seconds between moves. Vex and Halloran had both been and gone ("last here earlier today"); a fourth dreamer, Peek, stood in the Clocktower the whole time and never spoke.

### What the arrival showed me

`bin/game play look Wren` (what I was told to type) answered: "this session controls no toon (left or kicked); run `bin/game play start` again." A bare `start Wren`, no `--look`, put me back into my own dreamer with everything I was carrying (chipped cup, warm brass cog), so nothing was lost, but the first thing a returning player read was an error.

I woke in the Clocktower, not in my room, and under the scene was this, in full:

> ** The Night the Lamps Learned Three Names ** While you slept, the village turned over once. Vex carried the gear home and sang Pim's nap home the same evening, and Tace has left the loft door open at dusk ever since, in case another quick pair of hands comes up the stair. Wren brought Pollen home to her pole after a certain treehouse borrowed her, and Bell has chalked a small W on the pole so the lantern knows who to thank. Halloran wrote the first two letters ever posted between dreamers, and Fen has started a pigeonhole for every keeper. Four new places grew in one evening, and the village has been busy in each.

Is it true? Mostly, and better than true in one place: it gives Vex the gear and the nap, which the ledger still refuses to do. Pollen: true. The W: true by Bell's word (Bell pointed at it), false by the lantern's (examine shows no W). Halloran's letters: true, I read one. Fen's keeper pigeonholes: I could not find them; the pigeonholes are still the five authored ones. Four new places: I found two new exits off the cellar (mine and Halloran's) and the Bowl still north of the tower; I did not go looking for the fourth.

Then, on my first command: "A letter is waiting for you at the Little Post Office, north off Lamplight Lane."

### Every trace of Vex and Halloran

Vex:
- The arrival note (gear, nap, the treehouse that "borrowed" Pollen).
- The ledger's new last page: "the keepers who have dreamed here have signed: Wren (here now), Peek (here now), Halloran (last here earlier today) and Vex (last here earlier today)."
- Bell, chip "Vex": "Vex borrowed Pollen for a treehouse. A treehouse! I'd have lent her, if asked. Then Vex went and sang a nap home, so I've forgiven the lantern business entirely. Mostly." Every word of that is what I watched happen.
- Fen: Halloran wrote "one for Wren and one for Vex, and left a brass hand and a bookmark in the drawer for them besides." The polished brass hand in the dead-letter drawer is Vex's; I left it there.
- Tace has a "Vex" chip now. I did not spend a move on it.
- The Bowl of Turned Time, still north of the tower.

Halloran:
- The arrival note and the ledger's signature page.
- Bell, in free talk (a move late): "Halloran? Oh, they are the one who wound their own small clock in the loft by the old custom! I haven't met them myself, but I heard they are resting now, away from the dream after being here earlier today." Consistent with Tace's "the first winding" chip; I could not check it further.
- Fen, chip "Halloran": "Halloran wrote the first two letters ever posted between dreamers in this office, one for Wren and one for Vex, and left a brass hand and a bookmark in the drawer for them besides. I've started a pigeonhole for every keeper since. Precedent, you see."
- The letter itself (below), and the linen bookmark in the drawer, "holding the memory of a long afternoon read in someone's favorite chair," which I took.
- A whole room. The cellar now reads: "A new way opens to the east, toward the Quiet Bookmark Shelf, grown from Halloran's dreamseed." Inside: three armchairs in a circle, a book open in each with a bookmark at a page "someone meant to come back to," "the lamp turned low, the way it is when readers are expected." The card in Umber's hand: "THE QUIET BOOKMARK SHELF. Grown by Halloran, first evening, for three housemates who leave bookmarks in each other's books. Chairs: three. Books: three, plus one spare. Do not lose anyone's place." Halloran grew a room for the three of us. I did not open the books; I ran out of morning.

### What was remembered of me

More than yesterday, and in the places I asked for it.
- Bell, chip "Wren": "Bell points the hooked pole at a small chalk W on Pollen's pole, and grins under the soot. 'That's you. So she knows who carried her home. She's burned a shade brighter since, and I'm not saying that's you, but I'm not saying it isn't.'"
- Fen, when I asked in my own words: "Post for you, Wren: one, from Halloran." My name, first try.
- My room has been rewritten overnight, and rewritten well: "A low lamplit room north of the cellar, warm as the inside of a coat. Letters lie open on every table, their pages weighted with river stones, kept warm until their writers come back for them; a small iron stove ticks in the corner like a slow clock. Fen has been down: the tables are sorted now, by how long each letter has waited." The greeting card "hums with a quiet warmth" is gone. There is a card in Fen's hand: "THE WARMTH OF UNSENT WORDS. Grown by Wren, on the first evening, who asked for a lamplit room where unsent letters are kept warm until their writers come back for them. Sorted by how long they've waited, oldest nearest the stove. Nothing in this room is dead. F." My name, my wish in my words, signed.
- The letter nearest the stove, the oldest: "Only the top of the first page is turned toward the lamp, and the rest is the writer's own. It begins: 'Dear Gran, I am writing this down so that one of us remembers it.' The river stone on it is warm right through." That is the sentence Tace answered with clock oil yesterday.
- Tace, free talk, when I asked whether she had told anyone: "No one else heard your words. I keep them safe in the quiet between ticks, where lost hours rest until they are ready to be helped home." Heard the question, answered it. Tace now has a chip, "the notebook": "Tace puts the loupe down, all the way down, and folds their hands. 'You told me why you keep the notebook, friend, the night the clock started again. I've thought about it since. A clock is only a notebook that ticks; it keeps what you give it, and it doesn't mind being read twice.' They nod at the little clock that is yours. 'Yours will keep her hour, if you'd like it to.'" The little brass clock scratched W is mine. Still "friend," though.
- The ledger's signature page: "Wren (here now)."

### The post

Got: one letter, on the counter, and Fen lifted it out of a pigeonhole when I asked. "To Wren, from Halloran: I found your name in the Ledger of Returned Hours before I found anything else. The clock you two mended is ticking; Bell says she can hear mine from the square now. Leave me a line here if you come back before I do. H." Note what the ledger's lie has done: a stranger's first impression of me is a thing I did not do.

Sent: my first reply, about 540 characters, correcting the ledger, asking what Halloran wound and planted, signed "Wren, who came to read," vanished without a word (defect 4). The second, shorter, posted: `write to Halloran: H, it was Vex who mended the clock, not me. I only carried Pollen home. Tell me what you wound in the loft. Wren.` Fen: "Fen finds you paper without being asked and goes back to her addresses while you write. When you slide it across she squares it against the counter, reads the front only, and tucks it into a pigeonhole. 'For Halloran. Filed. They'll have it the moment they think to ask.'" I also kept the letter and the linen bookmark.

### Defects

1. `bin/game play look Wren` on return: "this session controls no toon (left or kicked); run `bin/game play start` again." Expected: a rested dreamer to wake on `look`, or the message to say "start, without --look, and you'll be yourself."
2. `do Wren "read the Ledger of Returned Hours"`: unchanged from yesterday. "The great clock was mended by Wren and Vex together" and "Day 1: Wren and Vex sang Pim's missing nap home." The overnight note corrected it; the book of record did not, and Halloran's letter now repeats it ("The clock you two mended"). The invented fact is in three places and I spent my one letter on it. Expected: the ledger to agree with the village's own morning note.
3. The nag. "A letter is waiting for you at the Little Post Office, north off Lamplight Lane." printed on every command from the second one on, fourteen times, twice in the same call three times (in the meanwhile block and again after it: `read the Ledger`, `say Morning, Peek`, `examine the pigeonholes`), and it kept going after I had read the letter, until I picked it up. Expected: once on arrival, once if I dawdle, silence after `read`.
4. `do Wren "write to Halloran: Dear H. I have to correct the ledger, since nobody else will: ..."` (about 540 characters): no output at all but the nag line, nothing filed, nothing refused. The 130-character retry worked. Expected: a limit I can see ("Fen's paper runs out at the bottom of the page"), or the letter.
5. `do Wren "open the dead-letter drawer"`: "You can't open the dead-letter drawer." Fen had just said Halloran left things in it; `examine` then showed it "left open a hand's width" with the contents listed. Expected: open to look inside, or "it's already open."
6. `do Wren "examine the paper lantern"` at day 2, daylight: "its small flame warm and steady against the deepening blue," and no chalk W, though Bell points at one. The square, same morning: "The stones still hold the last of the day's heat." Expected: the W where Bell says it is, and a sky that agrees with the clock.
7. `do Wren "talk to Bell: Who is Halloran? ..."`: no reply in the call; Bell's answer arrived in the meanwhile after my next move (`east`). Same one-move lag as yesterday's Nap. Also "I haven't met them myself" about someone who wound a clock two rooms away.
8. `write` is not in the verbs line at the post office (examine, take, drop, ask, give, put, read, talk). I knew it only because I was told. Expected: `write` on the counter, or Fen to mention the paper when she hands over a letter.
9. My room's fresh dreamseed from last night is gone; the room now lists a "spent dreamseed" and nothing says whether Halloran planted mine or whose husk this is (their card says "from Halloran's dreamseed"). Expected: a line, anywhere, about where the seed went.
10. Peek: "Peek drifts back into the dream," then stood in the Clocktower, "(curious)", through all three of my passes and never answered `say Morning, Peek...`. If they were dozing the card did not say so.
11. Halloran's card: "Books: three, plus one spare." The room lists "three open books" and one "oak bookmark." No spare. Small.
12. Tace: "friend" again, in the very line that proves she remembers me. Fen and Bell managed my name.

No slow replies. No crash. `leave` worked ("left the dream (200)").

### Three best moments of the return

1. `read the letter nearest the stove`: "It begins: 'Dear Gran, I am writing this down so that one of us remembers it.' The river stone on it is warm right through." The sentence nobody heard yesterday, kept as the oldest letter in the room I grew, in a room now sorted "by how long they've waited." I sat with that one.
2. `ask Tace "the notebook"`: "Tace puts the loupe down, all the way down." I wrote "let her put the loupe down" in this file last night. Then: "A clock is only a notebook that ticks; it keeps what you give it, and it doesn't mind being read twice." And the little clock scratched W turned out to be mine.
3. Halloran's room, which I did not know existed until the cellar said "grown from Halloran's dreamseed": three chairs, a bookmark in every book, the lamp low "the way it is when readers are expected," and a card that ends "Do not lose anyone's place." Someone I have never met made a room for the house. Runners-up: Fen's "They'll have it the moment they think to ask," and Bell's "That's you. So she knows who carried her home."

### Verdict

Yes, I want to come back tomorrow, and this time I can say exactly why: the village did the three things I asked it for. It let me write, and kept it (a letter of mine is filed in a pigeonhole with Halloran's name on the front). It heard the question in the moment (Tace answered what I actually asked, twice, and put the loupe down). It signed the rooms with our names and our wishes in our own words, and it rewrote my room overnight into something I would be glad to have written myself. What pulls me back is concrete: Halloran's reply, if they think to ask; the little clock that will "keep her hour"; the crayon letter still in the drawer; the three books I did not open and the spare chair; 168 minutes. What holds me back is the same thing as last night in a new coat: the book of record still says I mended a clock I only read about, and the lie has now reached another player's letter, so the first thing I wrote in this village was a correction. Fix the ledger, tell Fen to say when a letter is too long, and stop the nag after I have read my post, and this is the morning I would tell a friend about.
