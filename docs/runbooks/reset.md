# A fresh village (world reset)

A reset replaces the live village with a new one: day 0, the great clock
stopped, no dreamers, no history. Use it only for a deliberate fresh start
(before the first friends, after a test run, or a WORLD_VERSION MAJOR bump
that refuses to boot). Content never ships this way; that is
[content.md](content.md).

First practiced in prod on 2026-09-28, after the operator's own test play:
seconds of downtime, and two things to know (below) that are now steps.

## What goes, what stays

| Goes (the world database) | Stays (elsewhere) |
|---|---|
| Every dreamer (toon), with its journal, book and satchel | Accounts, sessions and invites (`accounts-prod.db`) |
| Arcs, the village day, relationships, grown rooms, dream history | Backups (`/srv/daydream/data/backups/`) |
| The raw input log and every event | Each friend's keepsakes on the edge, until the next keepsakes sync |
| **Prod's art** (the reset wipes the world's image cache too) | The release, the engines, the edge flag |

A friend who signs in afterwards finds the awake page and "make your
dreamer": their account survives, their dreamer does not.

## Steps

```sh
bin/game prod status        # who is playing? a reset ends every dreamer, mid-sentence
bin/game prod backup        # the reset keeps no copy of the old village
bin/game prod world reset --yes
bin/game prod prebake --from-cache ~/data/daydream/images/cache
bin/game prod check
```

- `backup` is the undo point, so take it right before the reset. The reset
  prompts for approval, and on 2026-09-28 that prompt waited eight hours:
  if it waits, look at `prod status` again and take a fresh backup.
- `world reset --yes` stops the service, deletes the world database and its
  image cache, loads the current release's `worlds/lost-hours.json` (no
  model call), and starts the service. It prompts even under the standing
  grant (it replaces the world). About 4 seconds.
- `prebake --from-cache` puts the graded art back: the village's own rooms
  and residents (32 targets on 2026-09-28), copied, not painted. About 2
  seconds, with its own brief stop. Skip it and prod paints each room and
  face lazily on first entry instead, ungraded.
- `check` should pass everything it passed before the reset.

## After

- If a `bin/game prod play` probe account exists from testing, disable it
  (`bin/game prod account disable agent-<name>`): its dreamer is gone, and
  its session file stays in the prod data dir.
- Note the reset in the instance record (`instance/NOTES.md`).

## Undo

Restore the backup taken first: `bin/game prod world restore-backup
/srv/daydream/data/backups/<ts>` ([backups.md](backups.md)). That also rolls
the accounts database back to that moment. Art for the old village's own
dreamers is gone unless a dev cache holds it.
