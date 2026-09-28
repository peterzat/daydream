# The first evening in prod (2026-09-28)

The operator's own first session in the live village, as a friend would
have it: invited through `/invite`, through the edge on Safari on a Mac,
a new dreamer made at the door, up the stairs to the Clockmaker's Loft, two
topics asked of Tace, back down, and out of the dream. About four minutes.
Read afterwards from the operator's notes, `bin/game prod logs`, and a
backup of the world and accounts databases.

## What the operator saw

| Note | Cause | Fix |
|---|---|---|
| "change password / sign out / close: buttons visually misaligned" | One blanket rule pushed every button in the dreamer panel to the right (`margin-left: auto`), which only a dreamer's row wants; the form's button went right, the others stacked left | The rule is scoped to dreamer rows; "change password" sits under its fields at their right edge; "sign out" and "close" share one row at the fields' two edges |
| "when I ask Tace about stuff the scrolling ... scrolls to the middle ... should be the top" | Every new line pinned the reading column to its bottom, so on a laptop-height window the column began with the tail of an older paragraph ("nod.") | A line that needs scrolling brings the view to rest on a paragraph's top, the whole answer in view; an answer taller than the column opens at its first line; a spacer under the log makes that resting place reachable; a reader scrolled back keeps their place unless they just acted |
| "scrolling works fine otherwise, but a bit undiscoverable" | Overlay scrollbars (macOS, phones) stay hidden until you scroll, and both columns scroll | A column holding more than it shows fades at that edge (a strong fade below, a light one above) |
| "left the dream, but I still see [the empty scene]" | Leaving opened the dreamer panel over a cleared scene; closing the panel showed "drifting...", empty margins and a live input box | Leaving wakes on a page of its own: the village seen from outside, "awake", where your dreamer is resting, and "step back in", "your dreamer", "sign out" |

The help leaf still told players about a "switch toon" control that accounts
retired; it now names "your dreamer".

## What the data showed

- **The path worked end to end.** The invitation was redeemed, a dreamer was
  made and painted in about six seconds, both topics were answered with
  authored lines (no model call), and the journal entry written on leaving
  reads well. The portrait turned "a scowling warrior" into a gentle cloaked
  figure, which is the whimsy suffix doing its job.
- **The log could not have told us any of that.** The prod journal held
  anonymous WebSocket open/close lines and nothing else: nothing configured
  the `daydream` loggers, so every INFO line (each model call's latency, each
  journal skip) was dropped, and nothing logged a sign-in, a dreamer or a
  session. `daydream/logs.py` now configures them in the lifespan, and the
  evening's lifecycle writes lines (docs/runbooks/incident.md "Reading the
  log"). They name accounts and dreamers, never a password, an invitation
  link or what anyone typed; a test holds that.
- **Walking into a room replayed hours-old lines.** A move re-snapshot
  replays the room's last 50 events, and in a quiet village that reached back
  to Tace's ambient lines from two and three hours before, read as happening
  now (and lengthening the column the answers landed in). Arrival now replays
  the last twenty minutes.
- **Ambient drift runs in empty rooms by design** (witnessed drift, SPEC
  2026-06-30): 33 lines in three hours with no one there, seven of them local
  variations. A few read awkwardly ("moving so softly it feels as though she
  might wake a sleeping object"); they are `src: "local"`, so the next dream's
  digest lists them as candidates for authored rewrites. Not changed.
- **The keepsakes job still fails** on the known cause: the installed unit
  keeps `NoNewPrivileges` until the operator re-runs `sudo
  ops/install-prod.sh`.

## Also

On a phone the log is a box above the margin and the topic chips sit below
it, so an answer landed out of sight; the page now brings the log into view
when it answers something you just did.

## How it was checked

A headless-browser harness took before and after screenshots at 1440x860,
1280x650 and a 390x844 phone. Three tests in `tests/test_browser_flow.py`
hold the fixes: leaving wakes on the page with the way back; each answer
rests on a paragraph's top with the whole answer in view and the columns
show their cues (the old SPA fails it on a mid-paragraph top); the panel's
buttons line up. `tests/test_ws_limits.py` holds the arrival window and
`tests/test_logs.py` the log lines.
