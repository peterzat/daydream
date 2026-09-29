# Changelog

Release history for daydream, newest first. Entries here are the condensed
record; the long-form narrative for each release (what was tried, what was
rejected, what was learned) lives in [docs/RELEASES.md](docs/RELEASES.md)
and, for the GPU/model decisions, [docs/gpu-and-models.md](docs/gpu-and-models.md).
Versions follow the app's own semver (`daydream/version.py:APP_VERSION`);
`WORLD_VERSION` is the separate world-content compatibility stamp.

## Unreleased

- **A first friend's ten minutes** (2026-09-28; docs/playtests/2026-09-28-first-friend.md). An agent played the village the way a new friend would, in the browser, and the pass fixed all 32 findings. Scrolling is discoverable: every scrolling column draws a slim storybook rail and the margin's foot names what is below the fold ("↓ you carry · 2"). A resident's welcome follows the arrival line instead of reading as an old, dimmed line, and they don't greet you twice. Your satchel lists the **threads** you are in the middle of (authored per arc, "two of five letters home"), and "what now" reads them. Your words and questions to residents are told back; typed and clicked looks read as the same card; looking at someone shows their painted portrait; asked topics read as asked and new ones glow; another player with no one at the page dozes. A thing that goes home while you rest says so, and only what stays is a keepsake. The guide opens only on a first visit, and typing "help" opens it. The parser takes "both letters" and looks past "for Linden"; a reply that hands your words back is never chosen; the journal reads the whole session and knows the hour. Time-neutral lines, rooms you are "on", and a wound clock that says so (`WORLD_VERSION` 1.6).
- **Going live** (SPEC 2026-09-27; docs/GOING-LIVE.md). The author's village opened to invited players on 2026-09-28. Invite-only accounts replace the shared password: argon2id passwords, hashed session tokens re-checked on every request and WebSocket frame, a sign-in gate a test proves covers every route, and two roles where the shell, not the browser, is the admin console. Prod is a second environment on the same box: a sandboxed `daydream` system user with loopback-only egress, pinned and reversible releases (`bin/game prod deploy|rollback`), nightly and offsite backups, and shared GPU engines behind a cross-process lock. A Cloudflare Worker proxies to an Access-guarded tunnel (no inbound port) and shows a storybook "the village is asleep" page, with each friend's keepsakes, whenever the box sleeps. Players know the operator only as the Night Warden. One-time setup: docs/CLOUDFLARE-SETUP.md.
- **Operating it** (2026-09-28). `bin/game prod check` verifies the live edge and prod invariants on demand; `prod status` shows each timer job's last result; playbooks for sleep and wake, maintenance windows, deploy and rollback, content, friends, backups, incidents and the edge live in docs/runbooks/, written for an agent to follow, and the `/village` skill gains `check` and `maintenance`. A headless-browser test walks a new friend from an invitation to the start room; the ops files and the playbooks are tested against the code. The pre-push review of going live found three BLOCKs (the Worker leaked Access's cookie on WebSocket answers, the front door sent empty credentials, "rest" re-entered the dream), all fixed before friends were invited; the lessons are in docs/GOING-LIVE.md section 11.
- **The first evening in prod** (2026-09-28; docs/playtests/2026-09-28-first-evening.md). The operator's own first session, read back from the log, a backup and their notes. Answers now come to rest on a paragraph's top instead of pinning the column to its bottom, scrollable columns fade at an edge that holds more, leaving the dream wakes on a page with the way back in rather than an empty scene, and the dreamer panel's buttons line up. The server's own log lines reach the journal at last (sign-ins, invitations, dreamers, sessions with their length, model calls, paintings, journal entries, session errors; never passwords, links or typed words), and walking into a room replays only its last twenty minutes, never a resident's ambient beats. The page fits iPad and iPhone Safari (dvh and the safe-area inset), the front door scrolls on a short window, and a screen and engine matrix (Chromium, Firefox, WebKit) checks the layout rules on every deploy.
- **The Village of Lost Hours** (the pivot, 2026-09-26; docs/PIVOT.md, SPEC.md 21/22). Daydream becomes a story world: 17 places, 9 residents with voice sheets, wants, secrets and schedules, 11 arcs (a prologue, six guest arcs, three keeper arcs, one village arc) with 29 endings, and 172 stray minutes on 12 pages of a per-player Book. Every ending ships a walkthrough replayed with zero model calls; a static analyzer proves every room reachable and every arc solvable. The Clockmaker's Loft is retired (the prologue is its quest), Zork I is frozen off the live server as the engine's regression net, and `WORLD_VERSION` is 1.5.
- **The story layer.** A real wall-clock village day with restart-safe catch-up and NPC schedules; arcs, beats, and endings with per-player relationships and state; a director that picks among authored storylets; facts and gossip that name players; rules that follow a verb (`after`); `ask` topics as the deterministic producer for every story beat.
- **Grounded dialogue.** The dialogue prompt carries the resident's voice sheet, what they know, their relationship with this player, and recent exchanges; the model picks at most one open beat from an enumerated list, and an advanced beat speaks its authored line. Canon contradictions on the canon suite went from 20 of 34 to 0, pronoun breaks from 8 to 0, and repeated openers from 6 to 1 (docs/model-eval/after-2026-09-26/).
- **Reflexes, not voice** (docs/REFLEXES.md). A line naming a resident's topic gets the authored answer; only the rest is improvised. Every local-model line is tagged `src: "local"`, and dream digests count them.
- **Dreams.** `bin/game dream digest | check | rehearse | install`: Opus writes the village forward in-session from what players did, proven on a side copy and a fresh twin with zero model calls, installed with a few seconds' pause; returning players see a once-only "while you slept" note. The first dream (dream-2026-09-26) calls back to four players by name.
- **`bin/game world refresh`**: deploy authored content to a played world without losing play.
- **Agent playtesters.** `bin/game play` drives the live game over its WebSocket from a shell; four persona agents played the first day at once (docs/playtests/2026-09-26/), and their findings reshaped how a shared room reads (private "you" lines with third-person lines for others, private conversations, greetings once) and how the parser keeps an utterance whole.
- **Every word kept**: a raw input log (private, digested by dreams, exportable as a walkthrough).
- **Security**: an LLM-originated `spawn_object` can no longer carry authored-only properties, and room data skills honor their declared effect allowlist (SECURITY.md).
- **Soft stakes**: WHIMSY.md gains a stories section and the banlist matches it; art for every room and portrait is prebaked and graded (`bin/game prebake`).
- **A better local dreamer.** The runtime LLM moves from Qwen 2.5 7B Instruct AWQ to Qwen3.5 9B AWQ 4-bit on vLLM 0.30.0, in the same VRAM slice beside SDXL. Blind-graded prose +0.69/5, parser grounding 41 to 47 of 48, no more NPC replies narrated as the player's body; dialogue took ~2.7 s instead of ~1.6 s in the bake-off (the grounded dialogue of the pivot runs at a 2.2 s p50). The retell rules gain one line so the new model varies repeat tellings instead of echoing them.
- **`bin/game model-eval`**, a bake-off harness that drives every runtime LLM surface through the production prompts and validators, plus a blinded prose sheet for in-session grading. The benign-refusal probe now measures the real `talk` prompt.
- Full record: [docs/model-evals/2026-09-26-bakeoff.md](docs/model-evals/2026-09-26-bakeoff.md).

## v1.0.0 — the release turn (2026-07-07)

The four flagship features that close the product's own promises, plus the
repo's public release identity.

- **Dreamseeds propagate.** A seed's authored `growth.propagation` block
  (chance, max_generation, child seed text) can, on a successful plant,
  yield a fresh plantable dreamseed inside the newly grown room — the
  growing-world loop. Seeded-deterministic roll, generation ceiling,
  grown-room-cap suppression, zero new LLM surface.
- **The cast has faces.** Toons with an appearance seed lazily get a
  watercolor portrait (new `painterly_portrait.json` workflow, 640×768,
  face-aware negatives) through the existing persistent-image pipeline as
  `target_kind='toon'`: cached, recorded, arbiter-gated, re-snapshot on
  paint completion. Faces appear in the scene margin, the WHO YOU ARE
  block, and the slot picker (cached-only; the picker never renders), with
  a quiet placeholder until painted. Room-art cache keys stayed
  byte-identical (regression-tested).
- **The book remembers.** Leaving the dream writes a 2–3 sentence
  past-tense second-person journal recap of the toon's own events (one
  local-LLM call, validated, FIFO-capped, sequence-idempotent,
  fail-closed; `DAYDREAM_JOURNAL_ENABLED` kill switch). Returning shows a
  "previously, in your dream" beat; the satchel's collection page renders
  the real journal, and keepsake cards caption with each item's own
  examined/authored detail.
- **Winning is visible & newcomers are welcomed.** `game_won` is
  world-scoped (every connected player sees The End storybook page, with
  score + rank; dismissible; the world keeps running; late joiners get a
  reopenable marker from snapshot status). A first-visit "How to Dream"
  leaf covers speaking, verbs/objects, exits, the satchel, and
  leaving/picking a toon — once per browser, reopenable from a persistent
  `?` affordance.
- **The loft learns the batch (WORLD_VERSION 1.4).** Authored drift pools
  for Tace/Bell/Mott (the drift loop prefers a toon's own pools), the
  dreamseed's propagation config, and a one-time authored first-planting
  chapter close (narrated in-room + written to the planter's journal).
- **Verification.** The benign-refusal mystery closed with a
  layer-attributing live probe (0/21 fallbacks; deterministic regression
  corpus in `tests/security/`); portrait dHash goldens ratified; a journal
  quality probe (5 live recaps, agent-graded, one attribution fix) keeps
  the journal default-on; tier_long green end-to-end.
- **Release identity.** `APP_VERSION`/pyproject at 1.0.0 with a drift
  guard and an `app:` line on `GET /status/build`; MIT `LICENSE`; this
  CHANGELOG; README overhaul; `docs/ROADMAP.md`; groomed BACKLOG;
  `.env.example` completeness pass; backfilled release tags.

## v0.6.0 — Zork I on daydream: the platform turn (2026-07-02)

The complete *Zork I: The Great Underground Empire* hosted as a swappable
world of pure DATA on new Zork-agnostic engine primitives (a no-literals
test convicts any engine file naming a Zork noun). Platform half: per-world
state KV with seeded turn-keyed RNG, actor-private events, a declarative
rule engine with world-declared verbs, real containers, a world clock with
fuses/daemons, lighting + the seeded darkness hazard, conditional/secret
exits and vehicles, seeded outcome-faithful combat, a wide deterministic
parser (ALL/EXCEPT, IT, AGAIN, THEN, GWIM, clarify), and matching Reading
Room affordances. World half: 110 rooms, 19 treasures, 350 points,
transcribed from the MIT-licensed ZIL source with all prose freshly
authored. The ~380-command walkthrough replays under a zero-LLM spy and
live over WebSocket to 350/Master Adventurer; a dfrotz differential oracle
replays it against the real 1980 game (ratified GREEN 2026-07-07). The
retell layer ships ON for Zork at the scoped rung. `WORLD_VERSION` → 1.3.

## v0.5.0 — dreamseeds: the world grows from the inside (2026-07-02)

Play can permanently grow the shared world: the quest-earned dreamseed +
the `plant` verb, one boundary-scaffolded local-LLM composition inside
Opus-authored seed boundaries, strict validation (schema windows, WHIMSY
banlist, anti-copy, refusal escape), and a synchronous race-rechecked
commit block dispatching `spawn_room`/`link_exit` — the world-shaping
effects only `plant` may emit. Grown rooms are first-class and persistent
with provenance; every failure path preserves the seed. `WORLD_VERSION` → 1.2.

## v0.4.0 — a playable quest (2026-07-01)

The first complete play loop: two-object verbs (`give X to Y`,
`use X on Y`), state-gated `open`/`read`, free-form object state, NPC
`wants`/`gives`, and a brand-new canonical world — The Clockmaker's Loft —
hosting the ledger → gear → case-key → clock-case quest. A deterministic
golden playthrough becomes the durable regression guard. `WORLD_VERSION` → 1.1.

## v0.3.0 — a world of objects (2026-06-30)

The MOO-style object/verb refactor: one `objects` table (containment by
location, verbs by prototype), a closed verb set on one `execute_command`
bus fed by UI clicks (structured commands, no LLM) and free text (a
grounded local-LLM parser), an allowlisted world-mutation effect API, and
explicit-only generative object spawns with lazy-cached examine.

## v0.2.0 — second inhabited dream (2026-05-07)

LLM-driven drift narrates composed from NPC memories + mood (canned pool
as the offline fallback), per-NPC selection weights, probabilistic mood
transitions, the drift voice-bench harness, and drift outcome counters.

## v0.1.0 — first inhabited dream (2026-05-06)

Multi-room world, two hand-authored NPCs with dialogue memory (BGE-small
CPU embeddings, salience-decayed retrieval), the data-skill safety
baseline (banlists, role-separator wrapping, refusal schema, effect
allowlist), the drift loop, the voice-bench audit trail, and world admin
(archive/restore/verify/delete).

## Pre-0.1.0 milestones

- **image-gen pipeline** — SDXL base + watercolor LoRA via ComfyUI and
  Qwen 2.5 7B Instruct AWQ via vLLM, coexisting on one 20 GB card behind
  the in-process GPU arbiter; `tools/arbiter-smoke.py` as the live-stack
  canary.
- **the smallest dream** — one toon, one meadow, FastAPI + websockets +
  SQLite with an append-only event log as the spine, snapshot
  reconstruction, and friend-scope shared-password auth.
