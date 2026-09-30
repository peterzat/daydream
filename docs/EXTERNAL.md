# External services: the policy's controlled exceptions

Status: 2026-09-30. The generation policy ([`CLAUDE.md`](../CLAUDE.md))
keeps the running game on the local GPU and the story with Opus at design
time. This document is the one place a hosted service can join the running
game: the rules it must meet, the registry of those that have, and how the
next one (an OpenRouter model, say) is added. It has one entry today, Jev.

## The rules

A hosted service may join the running game only when all of these hold:

1. **Optional, by key presence alone.** It is on exactly when its key is
   reachable (dev: the repo's gitignored `.env`; prod: the egress gateway
   has it). There is no other switch. Without the key, the game is the
   local game: the same code path, the same answers, no added wait.
2. **Beside a local reflex, never instead.** The local path always runs.
   The hosted answer serves only where the code says it may (a confidence
   floor, a rule over both answers), and any failure, timeout, refusal or
   empty account serves the local answer.
3. **A reflex, never the voice.** It may do what the local models do at
   runtime (decide, or answer what nobody wrote), never write what carries
   the story: that stays Opus's, at design time or in a dream ("Reflexes,
   not voice", [`docs/REFLEXES.md`](REFLEXES.md)).
4. **Measured, then pinned.** Adopted only when it is meaningfully more
   accurate on a held-out set (latency is not a reason), with an eval that
   reproduces the decision. The model is pinned to a version; a new
   version re-runs the eval before the pin moves.
5. **Observable.** One log line per call (never its text), a ledger with a
   stated retention, its state on every push, publish and `prod check`.
6. **What leaves the box is written down**, here, and the operator has
   accepted it.
7. **Keys stay out of git** (a tier_short test knows each key's shape), and
   **prod reaches it only through the egress gateway** (below).

## The registry

| Service | Gateway route | What it does in the game | Key | Since |
|---|---|---|---|---|
| Jev (TypeSafe) | `jev` | the promise judge; choosing an authored topic for a free line | `DAYDREAM_JEV_API_KEY` | 2026-09-30 |

## Jev

[Jev](https://typesafe.ai) is TypeSafe's hosted decision model. It is not an
LLM and writes no text: it answers typed questions over a state (a choice
among named options, a yes/no probability, or a score), each with a
confidence. The research notes are [`JEV-RESEARCH.md`](JEV-RESEARCH.md); the
evaluation, with every number below, is [`JEV-SPIKE.md`](JEV-SPIKE.md).

### What it buys

Two decisions the 9B makes badly enough for a player to notice:

- **The promise judge.** An improvised resident reply is checked before a
  player reads it for anything the game can't keep (the resident leaving
  with you, fetching, lending, meeting you later) or a name nothing gave.
  Every reply whose drafts all fail becomes a canned deflection. With Jev
  on, a draft passes when Jev is sure it only talks (P(ok) 0.8 or more), or
  when the local judge passes it and Jev leans that way (0.5 or more). On
  114 labeled drafts the rule was never tuned on, it passed no failing
  draft and held back 5 good ones, where the local judge alone held back
  14. Live, over 81 replies, the local judge let 6 failing drafts through;
  the rule, none.
- **Choosing an authored topic.** A free line to a resident that is about
  one of their topics should get the authored answer, not an improvised
  one. The word match catches a topic only when the line names it. With
  Jev on, Jev's pick serves at confidence 0.8 or more, else the word
  match's. On held-out lines: Jev 0.925, the word match 0.475. Live, Jev
  was right in 25 of 27 disagreements, and both of its errors fell below
  the floor, so neither reached a player. A line that names an open story
  beat is still matched by words, before Jev is asked.

Tried and not adopted: the parser and its triage (about as good as the
local model, and only about one line in six reaches a model at all).

Cost: about $0.00007 a judged reply and $0.00005 a topic choice ($0.042 per
million input tokens; output is free). A busy evening costs cents. The
wait: a topic choice adds Jev's answer (about 0.3 s, at most the 3 s
timeout) to a free line to a resident; the judge runs beside the local
judge, which takes about as long.

### What leaves the box

- For the judge: the drafts, and the parts of the dialogue prompt that
  bear on its rules (`dialogue.judge_view`): the resident's sheet; where
  they are (the place's name and description, the village's day and time
  of day); who is here, by name (the dreamer talking and every other
  resident and dreamer in the room); the village's people and places;
  what the resident knows, which includes deeds other dreamers did, by
  name; for any dreamer the player's line names, where and when they were
  last seen and whether they are awake, dozing or resting; the authored
  words of a topic the line mentions; and the player's words. Not the
  recent exchange, the resident's voice or wants, or their last lines.
- For a topic: the resident's name, the player's line, and the resident's
  topic names with the first words of each authored answer.

TypeSafe does not state its retention; zero retention is for its
enterprise customers. **The operator accepted this on 2026-09-30.** Friends'
typed lines to residents reach TypeSafe while Jev is on; the door does not
say so.

### On, off, and the key

- **Dev:** a line `DAYDREAM_JEV_API_KEY=<key>` in the repo's gitignored
  `.env` (`bin/game` loads it). Calls go straight to the API. Removing the
  line turns Jev off at the next `bin/game deploy`.
- **Prod:** the key is the egress gateway's, in `/etc/daydream/egress.env`
  (root 0600), set with
  `grep '^DAYDREAM_JEV_API_KEY=' .env | cut -d= -f2- | bin/game prod root egress set DAYDREAM_JEV_API_KEY`
  (the value on stdin, never the command line; it asks). The game asks the
  gateway at most once a minute whether its `jev` route has a key, so
  `bin/game prod root egress unset DAYDREAM_JEV_API_KEY` turns Jev off
  within a minute, with no restart.
- **Tests:** the suite runs keyless; `tests/conftest.py` clears the key and
  gives the client a transport that fails any test that reaches Jev.
- **The model** is `jev-1.13.0` (`daydream/jev/settings.py`). Before moving
  the pin, run `bin/game jev eval` against the new version and compare.

### Seeing it

- `bin/game jev status`: on or off, why, funded or empty (one question,
  about $0.00002), and what the ledger has recorded as spent. The pre-push
  hook, `bin/game status`, `bin/game prod plan` and the publish report
  print it; `bin/game prod check` fails when the gateway has a key and Jev
  is not answering, and reads "off" when it has none.
- `bin/game jev report [--disagreements N]`: calls, cost, latency, and the
  decisions where Jev and the local path differed, for adjudication.
- The log: one `daydream.jev` line per call (purpose, outcome, status,
  milliseconds, tokens, cost), never text. The gateway logs one line per
  request (route, path, status, bytes, milliseconds), never a body or a
  key.
- The ledger: `<data dir>/jev/calls.jsonl` (no text) and
  `decisions.jsonl` (both answers, which served, and the words the
  decision was about). 30 days, pruned by the server; `account delete`
  erases a person's decisions; never backed up
  ([`DATA-LIFECYCLE.md`](DATA-LIFECYCLE.md)).
- When the account runs dry, Jev answers HTTP 402; the client pauses calls
  for ten minutes and the local path serves. A refused key pauses the
  same way. A timeout, a network error, a rate limit (429) or a server
  error (5xx) pauses calls for a minute.

## The egress gateway

`daydream-prod.service` reaches loopback only: the kernel enforces the
generation policy. Its one way out is the egress gateway,
`daydream/egress.py`, a standard-library program installed by
`sudo ops/install-prod.sh` at `/usr/local/lib/daydream/egress.py` (so its
code changes only with the operator's password) and run as
`daydream-egress.service` on `127.0.0.1:54323`.

- **Routes are declared.** Each route in `ROUTES` names one host, the
  environment variable holding its key, and the exact method and path pairs
  it forwards. Anything else is a 404 or 405; a query string is refused; a
  body is at most 256 KB and a reply at most 2 MB.
- **It holds the keys.** It drops whatever `Authorization` the caller sends
  and adds the route's own. The game never sees a key. `GET /routes` says
  which routes have one, never the key; a route with none answers 503.
- **It sees nothing else.** A throwaway user (`DynamicUser=yes`), no
  writes, `/srv/daydream`, `/etc/daydream` and `/etc/cloudflared` hidden,
  the public internet only (the tailnet, the LAN and link-local are
  denied). The root helper's rules for this unit refuse a weaker one.
- **It wakes and sleeps with the village** (`prod wake` starts it before
  the service, `prod sleep` stops it); it is not enabled at boot.
- **Its keys** live in `/etc/daydream/egress.env`, root 0600, which systemd
  reads before starting it. `bin/game prod root egress show|set|unset`
  manages them (`set` takes the value on stdin, restarts the gateway if it
  is running, and never logs the value); `set` and `unset` ask.
  `bin/game prod root doctor` says whether the installed gateway is the
  deployed release's and which keys are set.

Dev has no gateway: its server is not sandboxed, and a key in `.env` is
used directly.

## Adding a service

For example, an OpenRouter model standing beside the local dialogue model:

1. **A route.** An entry in `ROUTES` in `daydream/egress.py`: the host, the
   key variable, the exact requests. A test in `tests/test_egress.py`.
2. **The key.** Its name in the root helper's `EGRESS_KEYS`
   (`ops/root/daydream-root`), with a validator and a test in
   `tests/test_root_helper.py`; its shape in `tests/test_no_cloud_keys.py`.
3. **A client** that reads its settings as `daydream/jev/settings.py` does
   (a key here in dev, the gateway in prod, on by key presence) and a seam
   that keeps the local path running beside it (`daydream/jev/seam.py`).
   Its log lines and ledger carry no text beyond what this document says.
4. **An eval** with a held-out set, run before it serves a player.
5. **A row** in the registry above, what leaves the box, and the
   operator's acceptance.
6. **Install.** The operator runs `sudo ops/install-prod.sh` (the new
   gateway code and helper), then `bin/game prod root egress set <KEY>`.
