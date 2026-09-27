---
name: village
description: Check on or operate the prod village (www.eidolon.com/daydream). Subcommands - status, wake, sleep "<note>", deploy [ref]. Use when the operator types /village, or asks whether the village is up, to wake it, put it to sleep (e.g. to use the GPU for something else), or ship the current code to prod.
---

# /village status | wake | sleep "<note>" | deploy [ref]

Operate daydream prod (SPEC 2026-09-27 criterion 18). Background: CLAUDE.md
"Prod"; docs/GOING-LIVE.md.

## status (default when no subcommand)

Run `bin/game prod status` and `bin/game edge status`. Summarize in a few
lines:
- awake or asleep, with the note
- the release vs HEAD (commits behind)
- engines up or down
- who is playing

## wake

Ask-first unless the operator's message already says to wake it. Run
`bin/game prod wake`, then `bin/game prod status`. The engines take 30-60 s.
If the release is behind HEAD, mention it; do not deploy unasked.

## sleep "<note>"

Ask-first unless the operator's message already says to put it to sleep. The
note is what friends read on the asleep page (e.g. "lent to a training run
until Sunday"); if the operator gave none, propose one and use it only once
they agree, or use an empty note.

Run `bin/game prod sleep --note "<note>"` (the default 60 s grace warns anyone
playing). It:
1. rests everyone and writes their journals
2. flips the edge to asleep
3. stops the tunnel, the service and the engines, freeing the GPU

Use `--keep-engines` only if the operator wants the GPU engines left running.

## deploy [ref]

Always ask-first, and confirm what is going out:
`git log --oneline <current>..<ref>` (the current release name is in
`bin/game prod status`). Then run `bin/game prod deploy <ref>` (default HEAD).
It tests that exact commit, builds a release, backs up prod, switches, and
rolls back by itself if the new release is unhealthy.

Report:
- which release is live
- whether migrations ran
- whether players' sessions were dropped (a restart drops them briefly;
  open tabs reload themselves)

If the village is asleep, the deploy just stages the release for the next
wake.

## Never

- Never `bin/game prod world reset` from this skill: a reset is a NEW village
  (day 0, no toons). It needs its own explicit request.
- Never force a deploy past failing tests (`--skip-tests` is for re-deploying
  a ref that just passed).
