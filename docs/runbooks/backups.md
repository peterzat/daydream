# Backups and restores

| Copy | When | Where | Kept |
|---|---|---|---|
| Nightly | 04:30 (timer) | the attached instance's `backups/<ts>/` (world + accounts DBs) | every one from the last 14 days, and never fewer than the newest 14 |
| Before a deploy, a pull, an offsite | automatically | the same pool | the same rule |
| Offsite | Sundays 05:15 (timer) | the private R2 bucket `daydream-backups`, encrypted with `age` | the bucket's expiry rule: 60 days on a bucket `offsite-bucket --create` made (`bin/game prod offsite-bucket` says) |
| By hand | `bin/game prod backup` | the same pool | the same rule |

Each instance's backups live in its own data dir,
`/srv/daydream/data/instances/<name>/backups/<ts>/`
(`/srv/daydream/data/backups/<ts>/` on a box without instances);
`bin/game prod backup` prints the path it wrote.

`bin/game prod status` and `bin/game prod check` show each timer job's last
result. A failed offsite or keepsakes job says why in
`journalctl -u daydream-<job>.service`.

## Restore into dev (reproduce a friend's bug)

```sh
bin/game down
bin/game prod pull        # a fresh prod backup becomes the dev world; dev's is kept in snapshots/
bin/game up
```

The pulled toons are unowned in dev (prod's account ids mean nothing here); a
dev account adopts one with `POST api/slots/<slot>/claim`.

## Restore prod from a local backup

```sh
bin/game prod status                                   # sure? who is playing?
ls /srv/daydream/data/instances/<name>/backups/        # pick one (the attached instance's)
bin/game prod world restore-backup /srv/daydream/data/instances/<name>/backups/<ts>   # prompts; stops and restarts the service
bin/game prod check
```

This puts back the world AND the accounts DB of that moment: sessions,
invites and accounts made since are gone, so friends may need to sign in
again. Prefer restoring only after a bad migration or a bad dream.

## Offsite: set up, prove, restore

The weekly job fails until the R2 bucket exists, and it says so before it
backs anything up. Check the bucket, and make it if it is missing:

```sh
bin/game prod offsite-bucket            # exists? private? how long copies stay (read-only)
bin/game prod offsite-bucket --create   # makes a missing bucket with its 60-day expiry rule
```

`sudo ops/install-prod.sh` runs the `--create` form, and
[`CLOUDFLARE-SETUP.md`](../CLOUDFLARE-SETUP.md) step 13 has the by-hand way.
This instance's bucket was missing from 2026-10-04 to 2026-11-22, and all
seven weekly runs failed; the failures showed in `prod status` and `prod
check`, but nothing sent them to anyone. With instances, each one is sealed
under its own name (`prod-<instance>-<ts>.tar.gz.age`).

An offsite copy counts only once a restore has been tried. Prove the round
trip once, on the box (`offsite-restore` decrypts with the box's own key and
needs `~/.config/daydream/cloudflare.env` and wrangler; it always prompts):

```sh
bin/game prod offsite
bin/game prod offsite-restore prod-<stamp>.tar.gz.age /tmp/daydream-restore-check
```

Then open what it unpacked: `PRAGMA integrity_check` on each `.db` (read-only),
and compare it with the local backup of the same stamp, which the offsite run
made (`backups/<ts>/`). Delete the restored copy afterwards: it holds the
accounts DB. The first tried restore (2026-11-26) matched byte for byte.

From another machine holding one of the SSH keys, fetch the object from the
`daydream-backups` bucket (the dashboard, or `wrangler r2 object get
daydream-backups/<name> --file <name> --remote`), then decrypt and unpack it:
`age -d -i <your ssh key> -o backup.tar.gz <name>` and `tar -xzf backup.tar.gz`.

The job finds node under `~/.nvm` itself (a timer's PATH has none).
