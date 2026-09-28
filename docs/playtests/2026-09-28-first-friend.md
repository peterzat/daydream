# A first friend's ten minutes (2026-09-28)

An agent playtest in the browser, as a new friend would meet the village:
a fresh invite, a new account and dreamer (Wren), then about ten minutes of
play through the Clocktower, the loft, the Lantern Square, Lamplight Lane,
the Little Post Office, the Waiting House, the Old Workshop and the Winding
Balcony, a second device (a phone) signing into the same account, and
leaving from there. Driven through headless Chromium at 1440x900 and an
emulated 390x844 phone against dev, with screenshots read at every step.
The dev village had its clock mended already, so this is a later friend's
arrival, not the prologue.

The operator added one finding after reading it: scrolling in the base UI
is not discoverable. On a laptop the margin ends at "around you" with the
inventory below the fold, and the reading column gives no sign it scrolls.

## What worked

The authored writing carries the game: the repair ledger's note sends you
to Tace, winding your first clock is a real moment, Fen's stray letters are
a lovely quest whose deliveries each open a little of Wend's story, and the
wrong-recipient refusals are hints in themselves. Stray minutes delight.
Invite to first line took about a minute; the portrait painted within a
minute and is beautiful. No page errors or failed requests all session.

## Findings and the fix plan

Each finding carries its fix; the status line is kept current as the fixes
land.

### Bugs

1. **Arrival order.** Bell's welcome beat (a room `enter` rule) landed above
   "You head east to the Lantern Square", dimmed as an earlier line, and
   Bell's usual greeting followed it ("Bell is up a small ladder"), right
   after Bell had come down to shake hands. Cause: lines a move causes are
   appended before the arrival snapshot, and the SPA cut "earlier" at the
   snapshot's last seq. Fix: the snapshot names the move's seq
   (`arrival_seq`) and the SPA cuts there; an NPC named in a line the move
   caused has already greeted the player, so their presence line is skipped.
2. **A quest thing went home unannounced.** Tace's turned-back clock went
   back to the loft when Wren rested, though the satchel called it "a
   keepsake". Fix: the satchel tags only what stays with you as a keepsake
   (village things read "goes home when you rest"), and a returning player
   is told what went home, and where.
3. **The help book opened on leaving.** A second device walks straight in
   (no help), then "leave the dream" opened it. Fix: the help shows on the
   first visit only (an account with no dreamer yet), and being in the
   dream marks it seen for that browser.
4. **The local model repeated the player's words back as its own.** Fix: a
   dialogue candidate that copies the player's line is rejected like any
   invalid candidate.
5. **"wind the turned-back clock for linden"** wound the small clock. Fix:
   the fast path grounds a verb plus an exact in-scope name, ignoring a
   trailing "for/to/with ..." phrase, before the model is asked.
6. **"take both letters"** read "You don't see the both letters here." Fix:
   "both X" and "all the X" mean every in-scope X, and a not-seen line drops
   the determiner.
7. **Typing "help"** got a chatter line. Fix: the SPA opens the guide; the
   server answers "help" and "what now" deterministically (the threads).
8. **Another player looked present but was not.** Marlow's toon was still
   claimed by a session with no socket. Fix: a player with no live
   connection shows as dozing, and speaking to them says so.
9. **Stale satchel text.** The wound small clock still said its hands had
   stopped. Fix: winding sets its state, the card shows the state line, and
   the seed no longer claims a state.
10. **Small contradictions.** Tock "is somewhere else entirely" but stays;
    an authored answer opened with the same gesture a model reply had just
    used. Fix: authored lines.
11. **The journal missed the big moments** and said dusk at noon. Fix: the
    journal prompt is told the time of day, and lines that moved a story
    (beats, deliveries, gifts) are marked as the ones to keep.

### Visual

12. **Scrolling is not discoverable** (the operator's note). Fix: an always
    visible storybook scroll rail on the reading column, the margin, the
    phone's log and the book's pages, and a thumb index at the margin's foot
    naming the sections below the fold ("you carry"), each a click away.
    New things in your hands glint the index.
13. **The top fade greyed the line the view rests on.** Fix: the view rests
    a fade's height above the paragraph, and the fade runs to transparent.
14. **Phone log opened mid-paragraph with clipped glyphs.** Fix: the same
    resting rule and fade.
15. **Drop cap on one-line entries**, and "The" capitalized mid-sentence.
    Fix: the drop cap is for a real paragraph; titles mid-sentence lower
    their article.
16. **"DAY 3 · DAY".** Fix: the day phase reads "daylight".
17. **The verb row jumped** when the give hint appeared. Fix: the hint takes
    the ribbon label's place.
18. **Portraits only as 40px circles.** Fix: examining someone shows their
    portrait in the card, the dreamer panel shows yours larger, and faces
    carry alt text.
19. **Clicked and typed examine/read rendered differently**, with mismatched
    labels and a doubled noun. Fix: the server marks examine and read lines,
    so both render as the same card, labelled "you examine the telescope" /
    "you read the repair ledger".
20. **Common words linked**, and words inside the player's own quoted line.
    Fix: a person's single-word alias links only as a name (capitalized),
    and chatter lines are not linked.
21. **The book's page scrolls without a cue.** Fix: the scroll rail.
22. **The takeover overlay.** Fix: "another window or device", a solid
    wash, and "dream here instead".
23. **The dreamer panel had no backdrop.** Fix: a scrim like the books'.

### Gameplay

24. **Your own words to villagers were not echoed.** Fix: a private echo of
    what you said or asked, like speech between players.
25. **Nothing tracked open threads.** Fix: authored threads (per arc, with
    conditions) listed in the book, with counts where there are counts; "what
    now" answers with them.
26. **Time-of-day contradictions** (the loft "holds the dusk" at noon; "the
    first night they come"; the loft "glances toward the tower"). Fix:
    authored lines.
27. **Tace's 17 topics.** Fix: asked topics read as asked, and a topic that
    just opened glows.
28. **"1 of 172 stray minutes".** Fix: the book counts what you found.
29. **Mood tags that contradict** (Pim's Nap "curious" while asleep). Fix:
    authored moods.
30. **"You are in the Winding Balcony".** Fix: rooms may say how you are
    there ("on the Winding Balcony").
31. **The first awake page** offered "make your dreamer" and "your dreamer"
    (the same thing), and explained resting before there was a dreamer.
    Fix: one way in, and the note only once there is a dreamer.
32. **The help's "← begin dreaming"** pointed back. Fix: it points on.

Not fixed: a local-model reply may invent a gesture (Tace "sets down the
loupe" while standing at the window). That is the small model's reach;
answers that matter are authored.

## Status

All 32 fixed in the pass, one commit per area, each with its tests:

| Area | Findings | Commit |
|---|---|---|
| Arrival order and greetings | 1 | a6598a0 |
| Dozing players | 8 | 7cbf248 |
| The guide on a first visit; typed help | 3, 7 | 4d3c3b4 |
| Scroll rail, margin index, resting fade | 12, 13, 14, 21 | 810524a, 307b8fd |
| Cards, portraits, links, drop cap, titles, hint, overlays, awake page, guide arrow, book count | 15, 17-20, 22, 23, 28, 31, 32 | 397e83f |
| Your words and asks told back | 24 | 8fa034f |
| Asked and new topics | 27 | da1d4ea |
| Parser: trailing phrases, "both" | 5, 6 | 809c57b |
| Dialogue echo guard | 4 | 6a40c2c |
| Journal window and hour | 11 | 53be38c |
| Things that go home; keepsake tags | 2 | d067558 |
| Authored lines, prepositions, the wound clock, "daylight" (1.6) | 9, 10, 16, 26, 29, 30 | 9198edb |
| Threads, and "what now" | 25 | 7e96b86 |

Two notes. A small clock wound before this pass keeps its old description
until it is wound once more (winding now rewrites it). The local model can
still invent a gesture in an improvised reply; that is its reach, and
answers that matter are authored.

The second playtest follows below once it has run.
