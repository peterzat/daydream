# Reflexes, not voice: what the local GPU does

*Written 2026-09-26, during the pivot to The Village of Lost Hours, in answer to
the operator's question: once the story layer is built, how useful is the local
GPU to the player, and what does it generate that Opus could not do better up
front?*

**The local GPU is the game's reflexes, not its voice.** Almost nothing it
generates is better than what Opus can write ahead of time. What it offers is
the one thing prewritten text cannot: an answer, within seconds, to something no
author anticipated.

This is the working stance behind the generation policy in
[`CLAUDE.md`](../CLAUDE.md) ("local at runtime, Opus at design time") and the
pivot's rule that the 9B's job is narrow ([`PIVOT.md`](PIVOT.md)).

## What is authored up front (no GPU needed)

All of the story is written by Opus, at design time or in a dream, and runs
deterministically: every beat line, ending, fact, ritual and arrival, the 172
stray minutes, all room prose, the residents' ambient lines, and the art for
every room and resident portrait (rendered locally at design time from
Opus-written seeds, graded by the agent, and cached: `bin/game prebake`). The whole
world is completable with vLLM and ComfyUI both down; every arc ending has a
walkthrough the tests replay with zero model calls.

## What the GPU generates at runtime, ranked by honest value

**Useful, because the input comes from the player and cannot be prepared in
advance:**

1. **Player portraits and grown-room art (SDXL).** A player describes
   themselves, or plants a dreamseed with a phrase, and both need a picture
   now. This is SDXL's whole remaining runtime job, and it is a good one.
2. **The grown room itself (the 9B).** Planting writes one room inside
   Opus-authored limits, immediately. The next dream furnishes it at Opus
   quality. The local model supplies the moment; Opus polishes it overnight.
3. **Understanding typed commands.** It turns "could you hand the little gear
   to Tace" into `give(gear, Tace)`. Clicks, topic chips, and exact phrasings
   skip it entirely. It is what keeps typing forgiving instead of
   old-text-adventure strict.
4. **Off-script conversation.** When a player asks a resident something no
   topic covers, the 9B answers in that resident's voice, knowing the player's
   name, what the resident has heard (including gossip about that player), and
   their relationship. When the story moves, the words are Opus's: the 9B only
   chooses which authored beat fires. Grounding took canon contradictions from
   20 of 34 questions to 0 (`docs/model-eval/`). That shows the 9B can be kept
   honest, not that it is charming.

**Marginal, since Opus can do it better and mostly already has:**

5. **Rewording ambient lines** (`DAYDREAM_DRIFT_VARY_PROB`, default 0.3).
   Larger authored pools would beat it. Candidate for zero unless play shows
   ambient lines feeling samey.
6. **Dusk event ranking** (`DAYDREAM_DIRECTOR_LLM`). The 9B can rank which
   authored event happens at dusk; a player cannot tell it from the seeded,
   repeatable pick the game makes without it. Decorative.
7. **The journal written when a player leaves.** Same-day immediacy is nice;
   a dream could write a far better "morning page."
8. **Descriptions for objects the local model spawned.** Rare.

## The honest risk

Item 4 is the largest runtime surface and the weakest in quality. An
improvised 9B reply next to Opus lines reads as a drop in register. It costs
about two seconds per reply, and when vLLM is down, free text answers only
"the dream is foggy."

## How we decide what to do about it

The agent playtest day ([`docs/playtests/`](playtests/)) is the measurement:
every line the playtesters read is tagged authored or local, and the report
shows where the defects and the best moments cluster, with one persona pushing
off-script conversation on purpose.

If local improvisation proves to be the weak spot, the next step is **select,
don't write**: Opus authors a large reply bank per resident (small talk, each
other resident, each place, each time of day), the 9B picks the best authored
line, and it writes something short itself only when nothing fits. That takes
"keep the 9B's job narrow" one step further and puts nearly every word a
player reads at Opus quality.
