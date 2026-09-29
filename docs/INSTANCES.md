# Instances: several villages behind one door

Status: 2026-09-28, built through the checklist's instance section except the prod steps; see the checklist at the end. The
operator's ask: swap prod between The Village of Lost Hours and a Zork I
playthrough (invite a friend, let them play, shelve it, go back), preserving
every instance's state (accounts, world, art, everything), all from the same
public URL, as the beginning of multi-tenancy. It is also the
moment for a deep, test-driven look at the internet-facing system, since
the Cloudflare side is new.

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

Accounts are per instance on purpose: a friend invited to Zork exists only in Zork, the
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
data dir (the engines' state is the box's). `bin/game prod <verb> ...
--instance zork` acts on an instance that is not attached (an invite before
Zork is up, a backup, a load). The option must be the last two arguments:
the agent's permission rules match a verb as a prefix, and anywhere else the
option could split a two-word verb past its rule, so prodctl refuses it.

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
with no file (dev, the tests) reads exactly as today. Under `instances/`, the
name is always the directory's: a file may leave `name` out, and one that
names another instance is refused. `envelope` is what
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
- `bin/game prod invite create --for "<a friend>" --instance zork`; the link works
  while Zork is attached (the invite message says so).

## Toward multi-tenancy

Several instances attached at once is one process per instance (module
state is per process: the DB connections, the event subscribers, the village
and drift loops): a templated unit `daydream-prod@<name>` with its own port
and `DAYDREAM_INSTANCE`, the Worker routing `/daydream/<name>/` (or a host)
to that instance's origin, KV keys namespaced by instance, and the cookie
already per instance. Nothing in this design has to be undone for that.

## The checklist

Status words: **done** (built, tested, deployed), **next** (in order),
**operator** (needs the operator's hands or decision), **later**. This
lists the engineering; what one instance has done with it (its migration,
its test accounts, its recovered art) lives in that instance's own record,
off GitHub.

### Found by the first evening in prod (2026-09-28)

- done: answers rest on a paragraph's top; scroll cues; the awake page; the
  dreamer panel's buttons
- done: server log lines reach the journal (no secrets, no typed words)
- done: arrivals replay only recent, non-ambient lines, and the cut holds
  for the rest of the visit
- done: the page fits iPad and iPhone Safari (dvh, the safe-area inset)
- done: a screen and engine layout matrix (Chromium, Firefox, WebKit)
- done: the door scrolls on a short window and no longer spills sideways
- done: a reset playbook, practiced in prod

### Data lifecycle (docs/DATA-LIFECYCLE.md)

- done: `account delete` (the end of a person: account, sessions, invites,
  dreamers, what they typed and said, their Book and finds)
- done: the art keep (every render, adoption and restore; keep-before-wipe;
  restore on a cache miss; read-only kept files; provenance in backups)
- later: art bytes offsite (after the R2 bucket); a `prune` verb; a prune of
  ComfyUI's output folder

### Root and the admin console (docs/ADMIN-ROOT.md)

- done: the validated helper (`ops/root/daydream-root`, its unit validator
  and tests), `bin/game prod root ...`, the installer and sudoers line, the
  ask rules (and a template for forks)
- operator: one `sudo ops/install-prod.sh` to install the helper on a box
- next, after that: `prod root doctor`, start the keepsakes job, `prod
  check` all green; later unit changes go through `prod root units --apply`

### Instances (this document)

- done: the core (resolution once per process, instance.json words, the
  per-instance cookie, envelopes), the prod verbs (`instance
  list|create|use|migrate` with the swap's guards and rollback; `--instance
  NAME` for the instance-scoped verbs, only as the last two arguments), the
  Worker's words, the runbook, a real swap rehearsal, `prod check`'s
  instance checks
- next (its own turn): a Zork instance in prod: `instance create`, its art
  (the dev archive's room paintings into its keep; a door image rendered and
  graded), `instance use zork`, invite a friend, play, swap back, and write
  down what the practice taught

### The internet-facing system (a deep, test-driven look)

- done: the uptime watch (a Worker cron trigger; debounced, closed by a
  sleep, written only on a change), shown by `edge status` and `prod status`
- done: the dreamer cap; a test that the Worker keeps the app's security
  headers; the dev refusal points at a tunnel
- done: a fresh-eyes review of the README, the setup docs and the runbooks
  as a newcomer who wants to fork and host (docs/FORKING.md came of it)
- next (its own turn): a capacity rehearsal in dev before twelve friends: N
  agent players (`bin/game play`) at once; LLM p50/p95 from the log lines,
  arbiter waits, render queueing; the numbers written down
- later: `prod check` on the keep (provenance present) and each instance's
  backup age; a push notification when an outage opens; a disaster-recovery
  drill (a new box: install, offsite restore, Cloudflare re-pointing)
- operator: HSTS in the Cloudflare dashboard (it is host-wide, so it binds
  the Pages site too); the R2 bucket and its lifecycle rule
  (CLOUDFLARE-SETUP step 13)
