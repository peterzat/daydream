# Deploy and roll back

Prod runs commits, never a working tree. A deploy is safe to run with friends
online: they see a few seconds of "the dream is sleeping..." and their tabs
reload themselves into the new build.

## Deploy

```sh
git status                         # clean; commit first
bin/game prod status               # current release, who is playing
git log --oneline <current>..HEAD  # what is going out
bin/game prod deploy               # or: bin/game prod deploy <ref>
bin/game prod check
```

What `deploy` does, in order, stopping at the first failure:

1. Refuses a dirty tree when deploying HEAD.
2. Runs the short and medium tiers at that exact commit, in a throwaway git
   worktree that borrows the dev venv (the same ~1700 tests CI runs).
3. Builds `/srv/daydream/releases/<sha>` (a read-only `git archive`) and its
   venv from `ops/requirements-prod.lock` (reused when the lock is unchanged).
4. Preflight, as the service user with the NEW release's code against prod
   data: refuses a WORLD_VERSION MAJOR mismatch; reports pending migrations.
5. Backs up the prod world and accounts DBs (`backups/<ts>/`).
6. Points `current` at the new release (`previous` at the old one).
7. If the village is awake: restarts the service, waits for health, and
   checks the served build is the new one. If not healthy, it rolls back by
   itself (and restores the backup if migrations ran), then reports it.
   If asleep: the next `wake` runs the new release.

`--skip-tests` exists only to re-deploy a ref that just passed.

## Roll back by hand

```sh
bin/game prod rollback     # current <-> previous, restart if awake
bin/game prod check
```

`rollback` swaps code only; it does not undo migrations. If the bad release
migrated the world, restore the pre-deploy backup the deploy printed
([backups.md](backups.md), "Restore prod").

## After changing ops files

A deploy ships code, not the box's own config. When a change touches
`ops/systemd/*`, `ops/sudoers.d/*` or `ops/install-prod.sh`, the operator
re-runs `sudo ops/install-prod.sh` (idempotent; it keeps `prod.env` and the
tunnel token). A change to `ops/prod.env.example` does not reach
`/srv/daydream/etc/prod.env`: the operator edits that with sudo. A change to
`edge/` ships with `bin/game edge deploy` ([edge.md](edge.md)).

## If the deploy gate fails

Read the failing test. The gate runs in a fresh worktree with a scrubbed
environment, so a test that depends on the dev box's state (a running
server, an awake prod, `~/.config`) fails there and nowhere else: fix the
test's isolation, not the gate. (Both of the gate's first failures on the
real box, 2026-09-28, were that.)
