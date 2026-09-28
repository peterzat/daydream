# Backups and restores

| Copy | When | Where | Kept |
|---|---|---|---|
| Nightly | 04:30 (timer) | `/srv/daydream/data/backups/<ts>/` (world + accounts DBs) | every one from the last 14 days, and never fewer than the newest 14 |
| Before a deploy, a pull, an offsite | automatically | the same pool | the same rule |
| Offsite | Sundays 05:15 (timer) | the private R2 bucket `daydream-backups`, encrypted with `age` | 60 days (bucket lifecycle rule) |
| By hand | `bin/game prod backup` | the same pool | the same rule |

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
ls /srv/daydream/data/backups/                         # pick one
bin/game prod world restore-backup /srv/daydream/data/backups/<ts>   # prompts; stops and restarts the service
bin/game prod check
```

This puts back the world AND the accounts DB of that moment: sessions,
invites and accounts made since are gone, so friends may need to sign in
again. Prefer restoring only after a bad migration or a bad dream.

## Offsite: set up, prove, restore

Not set up yet on this instance until the R2 bucket exists
([`CLOUDFLARE-SETUP.md`](../CLOUDFLARE-SETUP.md) step 13). Then prove the
round trip once, on the box (`offsite-restore` decrypts with the box's own
key and needs `~/.config/daydream/cloudflare.env` and wrangler):

```sh
bin/game prod offsite
bin/game prod offsite-restore prod-<stamp>.tar.gz.age /tmp/daydream-restore-check
```

From another machine holding one of the SSH keys, fetch the object from the
`daydream-backups` bucket (the dashboard, or `wrangler r2 object get
daydream-backups/<name> --file <name> --remote`), then decrypt and unpack it:
`age -d -i <your ssh key> -o backup.tar.gz <name>` and `tar -xzf backup.tar.gz`.

The job finds node under `~/.nvm` itself (a timer's PATH has none).
