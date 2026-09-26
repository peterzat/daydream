# The dream runbook

How to run a **dream**: the in-session step where Opus (the Claude Code
agent) reads what players did in The Village of Lost Hours and writes the
village forward (SPEC 2026-09-26 criterion 14; design in docs/PIVOT.md
sections 3.1 and 9). Dreams run **in-session only**: the operator triggers
one by name in a Claude Code session, and the agent follows this file.
Nothing here is scheduled or headless, and there is no API key anywhere.

## Trigger

The operator says something like "dream", "run a dream", or "let the
village dream". The agent then does every step below without further
prompting, and reports at the end (what changed, the callbacks, the
rehearsal result, the install).

## 0. Before you start

- Read `docs/canon/LOST-HOURS.md` (canon: who, where, secrets, the arc
  library, the long mystery) and `docs/canon/AUTHORING.md` (format). The
  dream must stay consistent with both, and must update the canon bible in
  the same commit if it adds canon.
- `bin/game status`: the server should be up (players may be playing), vLLM
  and ComfyUI state does not matter for a dream.
- Pick the dream's id: `dream-YYYY-MM-DD` (append `-b` for a second dream
  the same day). Its folder is `worlds/lost-hours/dreams/<id>/`.

## 1. Digest

```sh
bin/game dream digest --out worlds/lost-hours/dreams/<id>/
```

Writes `digest.json` and `digest.md`: every player's raw inputs since the
last dream (what they typed and clicked, where), their relationships and
minutes, every arc's status and who advanced which beat, grown rooms (with
the planter's phrase and whether a dream has furnished them), deeds (the
gossip facts naming players), and the chronicle. Read `digest.md` closely:
it is the only thing you know about what happened.

## 2. Author the patch

Write `worlds/lost-hours/dreams/<id>/patch.json` (shape in the
`daydream/dream.py` docstring). A good dream does most of these, in this
order of importance:

1. **Calls back to specific player deeds**, by name. At least one per
   dream (criterion 18). The main tools: `live.facts` (authored facts the
   residents now know: "Wren sang Pim's nap home; Bell has been humming the
   lullaby ever since"), `live.cast_add` topics that answer a deed ("ask
   Tace about the lullaby clock" once it was mended), and new storylets.
2. **Furnishes every grown room** a player planted since the last dream
   (`live.furnish`): a description pass at canon quality that keeps the
   player's own phrase's spirit (the planter's `grown.phrase` is kept
   verbatim by the engine; do not try to change it), plus a resident, a
   hook (a thing with a small story), or a stray minute's worth of wonder.
3. **Moves threads**: new facts that advance open arcs' soft stakes, a
   keeper's small change of heart, a new guest arc when the village is
   quiet (`add.arcs` + its guest in `add.toons`, with walkthroughs).
4. **The note**: `while_you_slept`, the leaf every returning player sees
   once. Two to five short sentences in the village's voice: who arrived,
   what someone did (by name), what changed. Warm, specific, no urgency.

Rules: additive only (the engine refuses anything else); namespace new ids
with the dream id (`o-<id>-...`, `t-...`, facts `<id>-...`); never reveal
the long mystery's answer outright (section 6 of the bible) unless the
operator asks for that chapter; keep WHIMSY.

Walkthroughs: add `walkthroughs.fresh` for anything in `add` (it must be
playable in a brand-new village: start from the prologue, as in
`worlds/lost-hours/walkthroughs/`), and `walkthroughs.live` for things in
`live` (they run on a copy of the live world with a fresh rehearsal
player, so use only relative clocks such as `+1h` and `@dusk`, and walk to
what the patch added).

## 3. Check

```sh
bin/game dream check worlds/lost-hours/dreams/<id>/patch.json
```

Merges the patch into a synthesis of the LIVE world and runs the loader's
validator and the static analyzer; names every problem; writes nothing. Fix
and repeat until it says the patch is sound.

## 4. Rehearse

```sh
bin/game dream rehearse worlds/lost-hours/dreams/<id>/patch.json
```

Snapshots the live world, applies the patch to a side copy, replays the
patch's `live` walkthroughs there, then builds a fresh twin (the canonical
world plus every applied dream's `add` plus this one) and replays EVERY
committed walkthrough and the patch's `fresh` ones. Zero LLM calls. Writes
`rehearsal.json` next to the patch. A failed rehearsal installs nothing:
fix the patch and rehearse again.

## 5. Install

```sh
bin/game dream install worlds/lost-hours/dreams/<id>/patch.json
```

Refuses unless `rehearsal.json` passed for exactly this patch. Then: a
pre-dream snapshot (`~/data/daydream/snapshots/`), `bin/game down` (players
see the calm "the dream is sleeping" overlay for a few seconds), apply the
proven patch to the CURRENT live database (so nothing a player did after
the rehearsal is lost), record the digest mark, `bin/game up`.

To undo a bad night: `bin/game down`, then
`bin/game world snapshot-restore <the pre-dream snapshot> --yes` (move the
live DB aside first; the command refuses to overwrite), then `bin/game up`.

## 6. Commit and verify

- Commit `worlds/lost-hours/dreams/<id>/` (digest, patch, rehearsal) and
  any canon-bible update, e.g. `dream <id>: <one-line summary>`.
- Verify in play: `bin/game play start Dreamer` then walk to one callback
  and see it (`bin/game play ask Dreamer tace "<topic>"`), and confirm the
  while-you-slept note on a returning session. Record what you observed in
  the dream's folder (`observed.md`).
- Tell the operator: the callbacks, what was furnished, the note's text,
  and anything left for the next dream.
