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
| The raw input log and every event | Every painting and its provenance (the art keep; docs/DATA-LIFECYCLE.md) |
| The image cache (a working copy) | Each friend's keepsakes on the edge, until the next keepsakes sync |

A friend who signs in afterwards finds the awake page and "make your
dreamer": their account survives, their dreamer does not.

## Steps

```sh
bin/game prod status        # who is playing? a reset ends every dreamer, mid-sentence
bin/game prod backup        # the reset keeps no copy of the old village
bin/game prod world reset --yes
bin/game prod check
```

- `backup` is the undo point, so take it right before the reset. The reset
  prompts for approval, and on 2026-09-28 that prompt waited eight hours:
  if it waits, look at `prod status` again and take a fresh backup.
- `world reset --yes` stops the service, keeps every painting in the art
  keep (and resets nothing if it cannot), deletes the world database and its
  image cache, loads the current release's `worlds/lost-hours.json` (no
  model call), puts the new world's art back from the keep (`prebake
  --from-keep`), and starts the service. It prompts even under the standing
  grant (it replaces the world). Seconds.
- The first practice (2026-09-28, before the keep) wiped prod's art with the
  world, and `bin/game prod prebake --from-cache ~/data/daydream/images/cache`
  had to copy the graded dev art back (32 targets). That is still the way to
  bring in art graded in dev that prod's keep has never held.
- `check` should pass everything it passed before the reset.

## After

- If a `bin/game prod play` probe account exists from testing, disable it
  (`bin/game prod account disable agent-<name>`): its dreamer is gone, and
  its session file stays in the prod data dir.
- Note the reset in the instance record (`instance/NOTES.md`).

## Undo

Restore the backup taken first: `bin/game prod world restore-backup
/srv/daydream/data/backups/<ts>` ([backups.md](backups.md)). That also rolls
the accounts database back to that moment. The old village's paintings are
in the art keep; `bin/game prod prebake --from-keep` (service stopped by
prodctl) puts them back into the restored world's cache.
