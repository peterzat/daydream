# Roadmap

The direction after the pivot to The Village of Lost Hours (2026-09-26;
design record [`PIVOT.md`](PIVOT.md), contract [`SPEC.md`](../SPEC.md)). This
file is the shape of what comes next, not a promise of order; durable
deferred items keep their long-form entries in [`BACKLOG.md`](../BACKLOG.md).

**The direction in one sentence:** move words from the 9B to Opus (dreams
that turn each digest's local lines into authored topics, then reply banks),
keep the 9B for parsing and the unanticipated, and zero the marginal
surfaces (drift variation, director ranking) unless play misses them
([`REFLEXES.md`](REFLEXES.md)).

## Now: the village in use

- **The operator's playtest and a dream cadence.** The first dream is live;
  the operator plays the morning after (SPEC criterion 22). Then a steady
  rhythm: play, digest, dream, observe. Each dream's digest lists the local
  model's recent lines; every wrong or frequent one becomes an authored topic
  or fact.
- **Reply banks** (BACKLOG `reply-banks-select-dont-write`): Opus writes a
  large bank of lines per resident; the 9B selects and writes only when
  nothing fits.
- **Being remembered** (BACKLOG `npc-memory-of-player-disclosures`): the
  lowest rubric score on the first day; residents should keep what a player
  told them about themself.
- **Small experience fixes from the first playtest**: a quiet "considers..."
  while a reply is coming (`thinking-indicator`), scenery nouns that answer
  (`scenery-nouns`), more threads for latecomers on a busy day
  (`shared-thread-contention`), a real-dusk beat after the early first dusk
  (`dusk-after-an-early-first-dusk`).
- **Zero the marginal reflexes** if play does not miss them:
  `DAYDREAM_DRIFT_VARY_PROB=0`, `DAYDREAM_DIRECTOR_LLM=0`.

## Next: what the pivot promised and has not built

From PIVOT.md, recorded so they are not lost:

- **Memory as compression** (PIVOT section 3.3): per-player, per-NPC summaries
  written by dreams, not embeddings.
- **Simulated weeks** (section 5.3): a fake-clock soak of the village over
  many days with scripted players, to see arcs open, close, and time out.
- **An agent playtest inside rehearsal** (section 9): today a rehearsal replays
  walkthroughs with zero model calls; a persona session on the side copy
  would catch experience regressions before install.
- **Named save-state fixtures and a day-0 golden archive** (section 9):
  archived village states to start tests and rehearsals from.
- **Replay-diff of real sessions** (section 9): `bin/game dream export` turns
  a session into a walkthrough; the diff against a later build does not
  exist yet.
- **Revisit the growth cap and propagation** (section 6) once players plant
  more than a room a day.

## Later: the shared world (v2)

- **Multi-user hardening.** Single-writer drain for SQLite, reconnect tokens,
  a bot soak gate, nightly snapshots. The friend-scope posture (shared
  password, bounded event queues, slot guards) is honest for a handful of
  friends, not for strangers.
- **Player-authored verbs and a world-authoring surface**, bounded like
  dreamseed growth (BACKLOG `user-authored-llm-driven-world-building-verbs`).
- **Performance** (`in_scope` query collapse, delta snapshots) before bots.
- **Ops**: multi-env layout (dev/preview/prod ports and data dirs), a mypy
  gate, staging and prod probes for `bin/game test`.

## Parked

The Zork I turn's follow-ups (retell rung, postgame, fidelity relaxations)
are parked with Zork frozen as the engine's regression net (BACKLOG, "Zork
turn deferrals"). The forge-legibility and LoRA A/B items belong to the
retired loft art and wait for a need.
