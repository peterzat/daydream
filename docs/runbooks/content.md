# Content: authored fixes, dreams, art

The live village keeps what players did. Content reaches it additively; a
world reset (a NEW village) is never the way to ship content.

## An authored fix (a line, a topic, a rule)

Edit the sources under `worlds/lost-hours/`, re-assemble
(`tools/assemble_world.py --source worlds/lost-hours`), run the tests, commit,
then:

```sh
bin/game prod deploy                     # the release carries the new envelope
bin/game prod world refresh --check      # what would change; writes nothing, no restart
bin/game prod world refresh              # snapshot, stop, merge, start
bin/game prod check
```

`refresh` carries every authored definition into the live DB and keeps
everything play wrote (see CLAUDE.md "world refresh"). If the change is a
MINOR `WORLD_VERSION` bump, refresh re-stamps the world.

## A dream

Dreams are written in-session, never scheduled (docs/DREAM-RUNBOOK.md is the
full procedure). In prod the service user cannot read the dev checkout, so a
patch reaches prod committed and deployed:

1. `bin/game prod dream digest` (what friends did; read it, don't paste it anywhere public).
2. Iterate on the patch in dev against a copy of prod: `bin/game prod pull`
   (the dev server down first), then `bin/game dream check|rehearse` there.
3. Commit the dream folder, `bin/game prod deploy`.
4. `bin/game prod dream rehearse worlds/lost-hours/dreams/<id>/patch.json`
5. `bin/game prod backup` (the undo point: note the `backups/<ts>` it prints), then
   `bin/game prod dream install worlds/lost-hours/dreams/<id>/patch.json`
6. `bin/game prod check`; then look for a callback in play.

Paths are relative to the release (the repo layout). An absolute path under
the operator's home is refused with this explanation. Undo a bad dream with
`bin/game prod world restore-backup /srv/daydream/data/backups/<that ts>`,
which also rolls the accounts DB back to that moment ([backups.md](backups.md)).
The pre-dream snapshot `dream install` prints cannot be restored in prod:
`world snapshot-restore` refuses while a live DB exists.

## Art

Prod doesn't prebake: it copies the graded dev art. A room or resident
missing from the copy (`prebake --from-cache` lists it as `missing`) is
painted by prod itself, ungraded, the first time a player comes across it;
render and grade it in dev, then copy again.

```sh
bin/game prebake                                                   # in dev, then grade it (docs/art/)
bin/game prod prebake --from-cache ~/data/daydream/images/cache    # copy what matches; renders nothing
```

Player portraits and grown rooms are painted live by prod's own ComfyUI
calls. A render that cannot get the card within 20 s keeps its placeholder
and paints later.
