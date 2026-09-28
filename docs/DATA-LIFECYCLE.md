# Data lifecycle

Status: 2026-09-28, after the first prod reset. What daydream keeps, for how
long, and what may end it. Durable where the meaning lives (a painting and
what it was for, a friend's account while they have one, the backups);
disposable where it is a working copy (image caches); and every deletion
deliberate, scoped, and said out loud.

The operator's framing (2026-09-28): "not 'don't ever delete anything', more
'have a solid data lifecycle approach for daydream's purposes'", and "not
useful to have a cool pic of a stream if we don't remember what it was meant
to be used for."

## Principles

1. **Meaning travels with the bytes.** A painting is kept with what it was
   for: the world, the room or resident and its name, the prompt and the
   text it came from, the model, LoRA and workflow, when, where, and what
   happened to it.
2. **Working copies may be wiped; records may not be wiped by a routine
   verb.** An image cache is rebuilt from the keep; the keep, the backups
   and the accounts are records.
3. **Keep first, or wipe nothing.** Every verb that wipes art keeps it
   first and refuses to wipe when the keep cannot be written.
4. **A person's end is complete for their identity and private words**, not
   for the shared history others saw, and not for the art (retired, with its
   provenance).
5. **Deleting a record is a deliberate act**, with its own verb, scope and
   trace, never a side effect.

## Classes of data

| Data | Where (per env) | Kind | Kept | Ended by |
|---|---|---|---|---|
| The live world: rooms, dreamers, story state, events, the input log, `generated_assets` rows | `worlds-<env>/live.db` | record | while it is the live world; backups below | `world reset`, `world delete`, a restore (each after a backup) |
| Accounts, sessions, invites, throttles | `accounts-<env>.db` | record | while the person plays; sessions slide 30 days (180 at most), invites expire | `account delete` (the person), expiry |
| Paintings (bytes) | `keep/art/<sha256>.png` | record | indefinitely | a deliberate prune (not built; below) |
| Paintings' provenance | `keep/provenance.jsonl`, and a copy in every backup | record | indefinitely | never automatically |
| Image caches | `images/cache/<world>/<kind>/<id>/<key>.png` | working copy | while its world lives | `world reset`, `world delete` (after keeping) |
| Backups: world + accounts DBs + provenance | `backups/<ts>/` | record | every one from 14 days, never fewer than 14; offsite 60 days | age (the rule in `admin.cmd_backup`) |
| Snapshots, archives | `snapshots/`, `archives/` | record | until removed by hand | the operator |
| Prebake contact sheets | `prebake/<ts>/` | review aid | until removed by hand | the operator |
| Ephemeral renders (image-test, A/B) | `images/ephemeral/` | scratch | until overwritten | anyone |
| ComfyUI's own outputs | `external/ComfyUI/output/` (the shared engine, dev's tree) | engine scratch: a second copy of every render, without provenance | unmanaged today | nothing yet (below) |
| Server log lines | the systemd journal | operational | journald's retention | journald |
| Edge keepsakes | the Worker's KV | derived copy | until the next keepsakes sync | the next sync |

Dev (`~/data/daydream`) and prod (`/srv/daydream/data`) each have their own
of everything above; prod's art for the village's own rooms and residents is
the graded dev art, copied (`prod prebake --from-cache`) and recorded in
prod's keep as `adopted`.

## Art: the keep

`daydream/images/keep.py`. Every persistent render (a room, a portrait) is
also kept:

```
keep/art/<sha256[:2]>/<sha256>.png   the bytes, content-addressed, stored once
keep/provenance.jsonl                one line per event, append-only
```

The bytes are hard-linked from the cache when possible, so the keep costs no
extra disk. That is safe because nothing writes a cache file in place: a
repaint writes a temp file and renames it over the old name, so a kept
painting never changes under its hash.

Each provenance line carries `event`, `world_id`, `target_kind`,
`target_id`, `target_name` (the room's title or the resident's name, in
words), `source_text` (the seed or appearance text), `prompt` (the full
prompt sent), `model`, `lora`, `workflow_hash`, `cache_key` (seed text +
workflow, the cache file's name), `file`, `sha256`, `bytes`, `at`, `env` and
`build`. The events:

| Event | When |
|---|---|
| `rendered` | a painting made for its target |
| `repainted` | the admin repaint, over an earlier painting (both stay kept) |
| `adopted` | copied from another env's graded cache (prod from dev) |
| `restored` | put back into a new world's cache from the keep (after a reset) |
| `backfilled` | kept after the fact from a world's `generated_assets` rows (`keep-sync`) |
| `found` | a cache file with no record (`keep-sync`; its provenance is thin) |

Verbs:

- `bin/game world keep-sync [world]` keeps every painting the live world
  knows of. Idempotent. `world reset` and `world delete` run it first and
  refuse to wipe when it fails.
- `bin/game prebake --from-keep` puts each target's painting back into the
  cache from the keep, by its cache key. `world reset` runs it after
  loading, so a reset village has its art at once. (A brand-new box's keep
  is empty: it copies the graded dev art in once with `prod prebake
  --from-cache`, which keeps it, and every reset after that needs no copy.)
- `bin/game world backup` (and `bin/game prod backup`, the nightly timer)
  copies `provenance.jsonl` into each backup (the records travel offsite
  with the backups; the bytes do not yet, below).

## A person's end: `account delete`

`bin/game account delete <user> [--yes]` (without `--yes` it only says what
would go). It deletes:

- the account, its sessions, every invite tied to it, and its throttle
  counters (the accounts DB)
- its dreamers in the live world, their carried things left in the room
  (as `world delete-toon` does), with their journals and books, what they
  said to each resident, their relationships and their private finds
- everything those dreamers typed or clicked (the private input log)

It keeps the shared event history (what others saw happen in the village)
and each dreamer's portrait in the art keep, retired with its provenance
(which names the dreamer and the appearance text, never the account).
Backups made before the delete still hold the old records until they age
out (14 days local, 60 offsite).

## Not built yet (designed here, built when needed)

- **Pruning the keep.** A `bin/game art prune` would take a policy (for
  example: experimental repaints and `found` images older than N days that
  no world uses), print what it would remove, remove only with `--yes`, and
  write a `pruned` line for each image. The provenance line stays forever,
  even when the bytes go. Nothing adopted, restored or graded is a
  candidate.
- **ComfyUI's output folder.** It holds a second, provenance-free copy of
  every render (it is how the first prod reset's lost portraits came back).
  Once the keep has run a while, a prune of that folder (older than 30 days)
  is safe.
- **Art offsite.** The weekly offsite carries the provenance but not the
  bytes. The keep is tens of megabytes; adding `keep/art/` to the offsite
  bundle is the next step once the R2 bucket exists.
