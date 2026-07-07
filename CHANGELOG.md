# Changelog

Release history for daydream, newest first. Entries here are the condensed
record; the long-form narrative for each release (what was tried, what was
rejected, what was learned) lives in [README.md "Release notes"](README.md#release-notes)
and, for the GPU/model decisions, [docs/gpu-and-models.md](docs/gpu-and-models.md).
Versions follow the app's own semver (`daydream/version.py:APP_VERSION`);
`WORLD_VERSION` is the separate world-content compatibility stamp.

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
