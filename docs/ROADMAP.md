# Roadmap

The post-1.0 direction, split into near polish (v1.x, single-box friend
scope stays the deployment model) and the larger v2 arc (a genuinely shared
world). Durable deferred items keep their long-form entries in
[`BACKLOG.md`](../BACKLOG.md); this file is the shape of what comes next,
not a promise of order. The v1.0 acceptance record is the closed
SPEC (2026-07-07) and [`CHANGELOG.md`](../CHANGELOG.md).

## v1.x — polish within the current shape

- **Drift variety metric + richer beats.** The v0 mitigation (laconic
  prompt, consecutive-duplicate suppressor) hides repeats; a
  "distinctness over N ticks" metric plus per-NPC rotation or a
  recently-noticed exclusion would reduce them (BACKLOG
  `drift-variety-richer-beats`).
- **Remaining snapshot enrichments for the Reading Room.** The inventory
  detail field landed with the journal turn; the rest of the
  enrichment list (richer toon cards, room mood hints) is still open.
- **Forge legibility.** The forge anchor passes at its ratified bar but
  the anvil/bellows read soft; a curated hero render pinned via the
  first real `assets.pin_asset` caller is the intended fix.
- **Retell rung revisit.** The Zork retell layer ships at the scoped
  rung (repeat tellings only). Re-probe whether a wider rung holds up
  under the same validation once more transcripts exist.
- **Zork postgame polish.** The barrow ending is faithful; the postgame
  niceties (sacred-word behaviors, endgame flourishes) are open data
  work — and any walkthrough edit upstream of the fights re-derives the
  thief-fight RNG windows, so batch such edits deliberately.

## v2 — the shared world

- **Multi-user hardening.** Single-writer drain for SQLite, reconnect
  tokens, a 10-bot soak gate, nightly snapshot cron. The current
  friend-scope posture (shared password, bounded event queues, slot
  ownership guards) is honest for a handful of friends, not for
  strangers.
- **Skills/world authoring UI.** The in-game authoring surface over the
  effect-allowlist substrate (jsonschema validation, content-safety
  classifier, audit/undo) — the "wizard standing" permission model from
  the README's thesis.
- **Player-authored verbs.** The headline: let earned standing author
  new verbs (bounded like dreamseed growth) so grown areas can carry
  real mechanics.
- **Map view, ambient audio.** Presentation depth once the world is
  worth surveying.
- **Performance.** `in_scope` N-query collapse, delta snapshots instead
  of full-snapshot broadcasts, one-connection-per-request SQLite
  review — none of it binds at friend scale; all of it binds before
  bots.
- **Ops.** litellm proxy for engine failover, multi-env layout
  (dev/preview/prod ports + data dirs), a mypy gate, staging/prod
  probes for `bin/game test`.
