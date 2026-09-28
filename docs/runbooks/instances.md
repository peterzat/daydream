# Instances: several games behind one door

The design is [docs/INSTANCES.md](../INSTANCES.md). An instance is a complete
data dir (`/srv/daydream/data/instances/<name>/`: its world, accounts, art,
keep and backups); one is attached to the public URL at a time, through the
`active` link. Friends belong to an instance: an account exists only in the
instance it was invited to.

## Look

```sh
bin/game prod instance list          # every instance; * marks the attached one
bin/game prod status                 # the attached instance is the first line after the release
bin/game prod check                  # includes: the service answers as the attached instance
```

## Once: move a box to instances

A box set up before 2026-09-28 has one flat data dir. Move it into an
instance (the village keeps everything; everyone signs in once more, since the
session cookie is now per instance):

```sh
bin/game prod instance migrate village   # backup, stop, move, link, start, flag, keepsakes
bin/game prod check
```

## Make another instance

```sh
bin/game prod instance create zork --envelope worlds/zork1.json \
    --title "Zork I" --place "the Great Underground Empire" --operator "the Dungeon Master" \
    --lede "An old underground empire, kept for friends." \
    --invite-blurb "an old text adventure I keep for friends"
```

It loads the world from the release's own envelope, keyless, and is not
attached. Every word is optional and defaults to the village's; a door image
must be an asset the release ships (`--door-image assets/<file>.png`).

## Act on a detached instance

`--instance NAME`, as the last two arguments, acts on that instance instead
of the attached one: its accounts, invites, backups, world. Anywhere else it
is refused: the agent's permission rules match a verb as a prefix, and an
option inside the verb could walk around them. Only the verbs that act on
one instance's data take it (`world`, `dream`, `account`, `invite`,
`prebake`, `play`, `backup`); `sleep`, `wake`, `deploy`, `instance use` and
the rest act on the attached instance and refuse it.

```sh
bin/game prod invite create --for "A Friend" --json --instance zork
bin/game prod account list --instance zork
bin/game prod backup --instance zork
```

An invitation works only while its instance is attached (the link is the
same URL for every instance). Send it when you attach the instance, or say
so in the message.

## Swap (attach another instance)

```sh
bin/game prod status                          # who is playing on the attached one?
bin/game prod instance use zork [--grace 60] [--note "the village is closed for a game night"]
bin/game prod check
```

`use` preflights the target with the current release (a WORLD_VERSION MAJOR
gap refuses), backs up both instances, warns anyone playing, stops the
service, rests everyone and writes their journals, flips `active`, starts the
service, checks it answers as the target, then writes the flag with the
target's words and syncs its keepsakes to the edge. If the target does not
come up, `use` attaches the previous instance again and restarts it by
itself. To go back, `use` the other one; nothing is lost either way.

## What is per instance, what is per box

| Per instance | Per box |
|---|---|
| world, accounts, sessions, invites, throttles | the release and its venv |
| image cache and art keep | the GPU engines and their lock |
| backups (nightly: the attached one; `use` and `offsite`: every one) | the edge (Worker, KV flag, Access, tunnel) |
| instance.json (title, place, lede, door image, operator, invite blurb, envelope) | prod.env, the Cloudflare credentials |

`world reset` and `world refresh` default to the instance's own envelope, so
a bare reset of a Zork instance reseeds Zork, never the village.

## Changing an instance's words

`instance.json` lives in the instance dir and belongs to the service user.
Edit it as that user (`sudo -u daydream $EDITOR
/srv/daydream/data/instances/<name>/instance.json`); a malformed file makes
the service refuse to boot, so run `bin/game prod check` after the next
restart (or `use`).
