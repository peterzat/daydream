# Agent playtest brief

The brief each agent playtester receives (SPEC 2026-09-26 criterion 17).
Playtesters play the LIVE game blind, through the same WebSocket path a
browser uses, and critique it as players against the rubric below. They do
not read world data or source code: the point is to meet the game the way a
person does.

## How to play

All play goes through `bin/game play` from the repo root
(`/home/peter/src/daydream`):

```
bin/game play start <Name> --look "<how your character looks>"
bin/game play look <Name>                  # where am I, who and what is here, ways out
bin/game play do <Name> "<anything you would type>"
bin/game play ask <Name> <npc> "<topic>"   # the clickable ask-about chips
bin/game play click <Name> <verb> <thing> [--with <other>] [--text "..."]
bin/game play book <Name>                  # your Book of Stray Minutes
bin/game play leave <Name>                 # rest your character (end of session)
```

Each call prints what happened since your previous call ("meanwhile"), then
what your input caused, and the scene when it changes. Type as a player
would: directions (`north`, `up`), `look`, `examine X`, `take X`,
`give X to Y`, `use X on Y`, `read X`, `talk to X about Y`, `ask X about Y`,
`say ...`, or plain sentences. Other dreamers may be playing at the same
time: that is intended.

## Rules

- Play blind: do NOT read files under `worlds/`, `daydream/`, `docs/canon/`,
  or tests. Everything you know comes from playing.
- Play for real: 50 to 90 commands, at a human pace (think between moves),
  for about 20 to 30 minutes of wall time. The village keeps a real clock
  (dusk is 18:00 Pacific); if a dusk passes while you play, notice what it
  brings.
- Stay in your persona (below), but play honestly: if something delights
  you, follow it.
- Do not start or stop the server, and do not touch the GPU.

## The rubric

Score each 1 to 5 with a sentence of evidence:

1. **Surprise**: did anything happen that you did not expect and enjoyed?
2. **Consequence**: did anything you did matter later (a person reacting, a
   thread moving, the world changing)?
3. **Being remembered**: did anyone remember you, your name, or what you
   did?
4. **Reason to return**: would you come back tomorrow for a coffee break?
   Why or why not?

Then list **defects**: every bug, confusing moment, dead end, tone break,
line that repeated verbatim, invented fact, slow reply, or place where you
did not know what to do. For each: the exact command, what happened, and
what you expected. Then your **three best moments**.

Write your critique to `docs/playtests/<date>/<persona>.md` (create the
folder) with: a short session summary (where you went, what you did, what
threads you found), the rubric, the defects, the best moments.
