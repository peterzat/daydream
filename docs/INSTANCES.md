# Instances: several villages behind one door

Status: design, 2026-09-28; building from the checklist at the end. The
operator's ask: swap prod between The Village of Lost Hours and a Zork I
playthrough (invite a friend, let them play, shelve it, go back), preserving
every instance's state (accounts, world, art, everything), all from the same
`www.eidolon.com/daydream`, as the beginning of multi-tenancy. It is also the
moment for a deep, test-driven look at the internet-facing system, since
Cloudflare and eidolon.com are new.

## What an instance is

A complete data dir. Everything a game is lives inside it; everything the box
is lives outside it.

```
/srv/daydream/data/
  gpu.lock                    box: every daydream process shares the card
  .local/ .cache/             box: HOME and XDG dirs for the service user
  active -> instances/village the attached instance (a symlink)
  instances/
    village/                  one instance: its own everything
      instance.json           its identity and its words (below)
      worlds-prod/live.db     the world
      accounts-prod.db        who may play HERE (accounts are per instance)
      images/cache/           the working copy of its art
      keep/                   its art keep (docs/DATA-LIFECYCLE.md)
      backups/ snapshots/ prebake/ play/ announce.json .cli-cookie
    zork/
      ...
/srv/daydream/{releases,venvs,current,previous,etc,incoming-art}   box
```

Per box, shared by every instance: the release (one engine serves them all),
the GPU engines and their lock, the edge (Worker, KV, Access, tunnel), the
Cloudflare credentials, prod.env's boot-guard settings. Per instance:
everything a friend could tell apart.

Accounts are per instance on purpose: a friend exists only in Zork, the
village's friends only in the village. That is the isolation multi-tenancy
needs, and it costs nothing today.

## Which instance a process serves

`config.data_dir()` resolves, once per process:

1. `DAYDREAM_INSTANCE=<name>`: `<DAYDREAM_DATA_DIR>/instances/<name>`
2. else, when `<DAYDREAM_DATA_DIR>/active` exists: its resolved target
3. else `DAYDREAM_DATA_DIR` itself (dev, the tests, and today's layout)

Once per process, because a swap under a running server would split it
(open SQLite handles on one instance, new files on the other). A swap stops
the service first, always.

`bin/game prod` passes the resolved instance dir as `DAYDREAM_DATA_DIR` to
every command it runs as the service user (so `bin/game`'s own bash paths,
`world reset` included, agree with Python), and keeps `HOME` at the box's
data dir (the engines' state is the box's). `bin/game prod --instance zork
<verb>` acts on an instance that is not attached (an invite for a friend before
Zork is up, a backup, a load).

## instance.json: identity and words

```json
{
  "name": "zork",
  "title": "Zork I",
  "envelope": "worlds/zork1.json",
  "place": "the Great Underground Empire",
  "operator": "the Dungeon Master",
  "lede": "An old underground empire, kept for friends.",
  "door_image": "assets/door-zork.png",
  "invite_blurb": "an old text adventure I keep for friends"
}
```

Every key is optional; the defaults are the village's words, so an instance
with no file (dev, the tests) reads exactly as today. `envelope` is what
`world reset` and `world refresh` load when not told otherwise (without it, a
bare reset of a Zork instance would seed Lost Hours). The words reach:

- the door: the server fills `door.html` (lede, plate image, title) the way
  it already fills `<base href>`; door.js reads `place` for its sentences
- the game page: `index.html` carries the same values for main.js (the awake
  page, the asleep note, the help leaf's "village" lines)
- server text: "the village is full", invites resting, the sleep warning
- the invite message (`accounts_cli.invite_message`)
- the edge: the flag in KV carries `title`, `place` and `operator`, and the
  asleep page and keepsakes page use them
- `tests/test_no_world_literals.py` keeps world names out of engine code;
  these words are data, in the instance, never literals

## The session cookie

`dd_session_<env>_<instance>` when instances are in use (today's
`dd_session_prod` otherwise). A browser keeps a village session and a Zork
session side by side, and a swap back finds the friend still signed in. The
Worker learns the attached instance's cookie name from the flag.

## Swap: `bin/game prod instance use <name>`

1. Refuse an unknown instance; show who is playing on the attached one.
2. Preflight the target with the current release (WORLD_VERSION MAJOR gap
   refuses; pending migrations are reported) and back it up.
3. Warn anyone playing (the sleep grace), back up the attached instance.
4. Stop the service. Flip `active` (as the service user, one atomic rename).
5. Start the service, wait for health, check the served instance is the
   target (`/status/build` names it).
6. Write the flag with the target's words; sync the target's keepsakes and
   passes to the edge (the published-keys manifest is the box's mirror of
   KV, so the previous instance's keys are withdrawn; they come back when it
   is attached again).
7. `prod check`.

If any step after the stop fails, flip back and start the previous instance.

Also: `instance list` (name, title, attached, world, accounts, size, last
played), `instance create <name> --envelope ... [--title ...]` (a new
instance dir, the world loaded, an empty accounts DB, instance.json written),
and `instance migrate` (the one-time move of today's flat layout into
`instances/village`, service stopped, with a backup first).

## Zork in prod

- `bin/game prod instance create zork --envelope worlds/zork1.json --title
  "Zork I" --place "the Great Underground Empire" --operator "the Dungeon
  Master"` (the words above).
- Art: the 92 room paintings from the dev archive
  (`~/data/daydream/archives/w-zork1-*.tar.gz`) imported into Zork's keep
  with provenance `found` (their seeds are the rooms'); then `prebake
  --from-keep`. A door image rendered once in dev (West of House in the
  house style) and graded like the rest.
- Zork is frozen (CLAUDE.md): nothing in `worlds/zork1*` changes. Its
  WORLD_VERSION gap is MINOR, so it boots with a warning; a fresh load stamps
  the current version.
- `bin/game prod --instance zork invite create --for "a friend"`; the link works
  while Zork is attached (the invite message says so).

## Toward multi-tenancy

Several instances attached at once is one process per instance (module
state is per process: the DB connections, the event subscribers, the village
and drift loops): a templated unit `daydream-prod@<name>` with its own port
and `DAYDREAM_INSTANCE`, the Worker routing `/daydream/<name>/` (or a host)
to that instance's origin, KV keys namespaced by instance, and the cookie
already per instance. Nothing in this design has to be undone for that.

## The checklist

Status words: **done** (built, tested, committed), **next** (this initiative,
in order), **operator** (needs the operator's hands or decision), **later**.

### Found by the first evening in prod (2026-09-28)

- done: answers rest on a paragraph's top; scroll cues; the awake page; the
  dreamer panel's buttons
- done: server log lines reach the journal (no secrets, no typed words)
- done: arrivals replay only recent, non-ambient lines, and the cut holds
- done: the page fits iPad and iPhone Safari (dvh, the safe-area inset)
- done: a screen and engine layout matrix (Chromium, Firefox, WebKit)
- done: the door scrolls on a short window and no longer spills sideways
- done: a reset playbook, practiced in prod

### Data lifecycle (docs/DATA-LIFECYCLE.md)

- done: `account delete` (the end of a person)
- done: the art keep, keep-before-wipe, restore-from-keep, provenance in
  backups
- next: deploy, then `keep-sync` prod; import the two recovered portraits
  (from the engine's own output folder) with provenance from the pre-reset backup
- next: delete the early test accounts in prod (`account delete --yes`)
- later: art bytes offsite (after the R2 bucket); a `prune` verb; a prune of
  ComfyUI's output folder

### Root and the admin console (docs/ADMIN-ROOT.md)

- operator: decide on the helper (or another shape)
- next, once decided: build `ops/root/daydream-root` with its unit validator
  and tests; `bin/game prod root ...`; ask rules for `--apply` and `env set`
- operator: one last `sudo ops/install-prod.sh` (installs the helper, and
  with it today's pending keepsakes/offsite unit fix)
- next: `prod root units --apply`, start the keepsakes job, `prod check`
  all green

### Instances (this document)

- next: `config.data_dir()` resolution (`DAYDREAM_INSTANCE`, `active`),
  once per process; instance.json with village defaults; tests
- next: prodctl passes the instance dir to every command, `HOME` stays the
  box's; `--instance NAME`; per-instance `.cli-cookie`; `prod status` and
  `/status/build` name the instance
- next: `bin/game world reset|refresh` default to the instance's envelope
- next: the words: door, game page, server text, invite message, sleep
  warning; tests that a Zork-worded instance reads as Zork and the default
  reads exactly as today
- next: the per-instance cookie name, and the Worker reading it from the flag
- next: `prod instance list|create|use|migrate`, with the swap's rollback;
  tests against a fake box (tmp dirs, a fake systemctl)
- next: the Worker: the flag's words on the asleep and keepsakes pages;
  node tests; `bin/game edge deploy`
- next: a runbook (docs/runbooks/instances.md), and the /village and
  /invite skills learn `--instance`
- next: in dev, a full rehearsal: two instances, swap, invite, play, swap
  back, everything intact
- next: prod: `instance migrate` (the village becomes `instances/village`),
  `prod check`
- next (its own turn if long): prod: `instance create zork`, the art import,
  swap, invite a friend, play, swap back

### The internet-facing system (a deep, test-driven look)

- next: `prod check` learns the attached instance (served vs `active` vs
  the flag), the keep (provenance present), per-instance backup age
- next: a capacity rehearsal in dev before twelve friends: N agent players
  (`bin/game play`) at once; LLM p50/p95 from the new log lines, arbiter
  waits, render queueing; the numbers written down
- next: dreamer creation is rate-limited per account (each one costs a
  portrait render on the shared GPU)
- next: an uptime record: a Worker cron trigger (free plan) probes the
  origin while the flag says awake and records unplanned outages in KV;
  `edge status` and `prod status` show them (a friend's "it's down" should
  never be the first signal)
- next: the edge's response headers for /daydream: HSTS, Referrer-Policy,
  and a test that the Worker keeps the app's CSP intact
- later: a disaster-recovery drill written down (a new box: install,
  offsite restore, Cloudflare re-pointing), once offsite exists
- operator: the R2 bucket and its lifecycle rule (CLOUDFLARE-SETUP step 13)
- operator (optional): leave the `docker` group (docs/ADMIN-ROOT.md)
- operator (not daydream): the anonymous `/generate` Worker on eidolon.com
