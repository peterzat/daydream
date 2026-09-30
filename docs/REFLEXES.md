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

## Pictures: the local GPU paints everything

There is no cloud image model, and Opus does not paint. Every image in the
game is rendered by SDXL on the local GPU; what differs is when. The world's
rooms and resident portraits are rendered at design time (Opus writes each
prompt and grades the result against WHIMSY.md, `bin/game prebake`), and so
is anything a dream adds. Only what players create is painted live. For
pictures, the local GPU is the painter and Opus is the art director; the
"reflexes, not voice" split is about words.

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
   topic covers (a line that names a topic gets the authored answer instead), the 9B answers in that resident's voice, knowing the player's
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
9. **Why a thing the prose names can't be handled** (playtest 2026-09-29b;
   `daydream/glimpse.py`). "Get the jar" used to read "You don't see the jar
   here" right after the shelf's look said a jar glinted there. The reason
   is authored where it matters (an object's `glimpsed` list, per verb and
   per story state), a look reads the prose itself, and only the rest (the
   lantern by the stair, the reeds) gets one short 9B line drawn from the
   sentence that names it, validated and cached. Measured 11 of 11 valid
   (`bin/game model-eval --suites glimpse`): storybook enough, sometimes a
   little purple. Each is tagged local, so the digest turns the ones players
   meet into authored reasons.

## Limitations

Item 4 is the largest runtime surface and the weakest in quality. An
improvised 9B reply next to Opus lines reads as a drop in register. The
measured p50 is about 2.2 seconds, but four players at once saw 7 to 9 second
replies before the fixes below, and a canon suite that scored 0 of 34
contradictions did not stop Mott from inventing "I gave the hush to Pim" in
play. When vLLM is down, free text answers only "the dream is foggy".

## What the measurement said (the first agent playtest, 2026-09-26)

Every narration is now tagged by source (`src: "local"` in the event
payload). Four agent playtesters played the live village at once
(docs/playtests/2026-09-26/SUMMARY.md): 77 of 510 narrations (15%) were
local-model lines. The best moments were all authored (the clock case
opening, Pim's Nap's red kite, Tock, the Ledger naming who helped, the chip
answers); nearly every worst line was local (robotic "I do not know"
denials, an invented thread-closing fact, "Of course one!", a resident
naming themself). A few local lines landed: Fen's "That is a question for
the inside of a letter, not the front", and Linden chalking a player's name
on a saucer, which the first dream then made canon.

The stance held, and the decisions followed from it:

- **Select, don't write, first step (shipped).** A free-form line that names
  one of a resident's topics or open beats gets the authored answer with no
  model call. The prompt turns unknowns gently and takes in what the player
  says; one candidate when the GPU is busy.
- **Dreams convert improvisation into authorship (shipped).** Each dream's
  digest lists the recent local lines; a wrong or frequent one becomes an
  authored topic or fact (the first dream's "no baker" fact is the model).
- **Reply banks (next).** Opus authors a large bank per resident, the 9B
  selects (BACKLOG `reply-banks-select-dont-write`).

The marginal surfaces each have a switch, for when play shows they are not
missed: `DAYDREAM_DRIFT_VARY_PROB` (default 0.3), `DAYDREAM_DIRECTOR_LLM`
(default on), `DAYDREAM_JOURNAL_ENABLED` (default on), `DAYDREAM_GLIMPSE_LLM`
(default on; off reads a plain "out of reach" line), `DAYDREAM_PARSER_TRIAGE`
(default on; off, the parser's call returns one command and no kind),
`DAYDREAM_PROMISE_GUARD` (default on; off shows the best draft unjudged),
and `DAYDREAM_RETELL_ENABLED` (Zork only). Jev (below) has no switch: it is
on exactly when a key is reachable.

One caveat on pictures: "only what players create is painted live" holds
with the repaint tool off. `DAYDREAM_REGEN_UI` defaults on for the operator;
set it to 0 before friends play so the graded art stays as graded.

## Prompting the reflexes (2026-09-30)

What the parser triage and the promise judge taught about asking a 9B model
for a reflex, and what every local surface should follow:

- **Examples are input; answers are latency.** Prompt tokens are prefilled
  in bulk and cost little; every token the model writes costs about 25 ms on
  this card. So teach with a few examples instead of long rules, and ask for
  the shortest answer that carries the decision. The parser writes only the
  fields that have a value (about 24 tokens instead of 40) and its call got
  faster while doing more; the judge answers one short verdict per draft
  from a trimmed view of the drafting prompt (p50 0.4 s).
- **Examples come from another story.** An example must share no words with
  the eval's cases and name nothing in the world. The first triage examples
  echoed the case set (a moon, a teapot, a resident's alias) and scored 0.94
  on it; clean ones scored 0.82 until each confused category had an example
  of its own, and then 0.94 again. A **held-out set**, written after the
  prompt and never used to tune it, is how to tell the two apart: the
  triage prompt scores 16/16 on its held-out lines.
- **Score what the game does.** An eval reads the model's reply through the
  runtime's own function (`parser.interpret`, the real talk path), never a
  hand-copied mirror of it, so the score is the player's experience.
- **Deterministic first, the model last, even inside a guard.** The promise
  guard reads a name nothing gave and a first-person commitment shape before
  the judge sees a draft; the judge catches the rest. A 9B judge alone let
  invented places and some promises through.
- **Give the model the closed lists.** Drafts and judge both see the
  village's people, places and the ways between them; canon contradictions
  in the canon suite went from 2 to 0.

## A second reader: Jev (2026-09-30)

Two of the reflexes above are decisions, not writing: the promise judge
(does an improvised reply only talk?) and, since "select, don't write",
which authored topic a free line is about. For those two, the village can
ask a second reader: Jev, TypeSafe's hosted decision model
([`EXTERNAL.md`](EXTERNAL.md); the evaluation, [`JEV-SPIKE.md`](JEV-SPIKE.md)).
It fits the stance rather than bending it: Jev writes no text, so every word
a player reads is still authored or the 9B's; it only chooses among
authored answers and checks the 9B's improvisation.

- **How it runs: a lookaside, not a replacement.** The local path always
  runs, and Jev answers beside it (`daydream/jev/seam.py`). The judge serves
  a rule over both verdicts: a draft passes when Jev is sure it only talks
  (P(ok) 0.8 or more), or when the local judge passes it and Jev leans that
  way (0.5 or more). A topic choice serves Jev's pick at confidence 0.8 or
  more, else the word match's. A timeout (3 s), an error, an empty account
  or no key serves the local answer. With no key the code takes the local
  path and nothing else: the no-key game is the game this document
  describes.
- **What it measured.** The judge alone: 0.980 against the 9B's 0.857 on 98
  labeled drafts (0.974 against 0.868 held out), and every 9B error was a
  good reply held back, which a player meets as a canned deflection. The
  combined rule, on 114 drafts it was never tuned on: no failing draft
  passed, 5 good ones held (the 9B alone, 14). Topics, on a clean held-out
  set: Jev 0.925, the 9B asked the same question 0.750, the word match
  0.475; live, Jev was right in 25 of 27 disagreements with the word
  match, and both of its errors fell below the 0.8 floor.
- **What it did not earn.** The parser and its triage: about as good as the
  9B on lines that reach the model (0.975 against 0.900 held out, not
  significant), and only about one line in six reaches a model at all.
  Latency was never a reason to adopt anything; Jev is about 0.3 s from
  this box, the 9B judge about the same.
- **What the numbers say about the 9B.** Its failures on these two
  decisions were caution (holding back good replies) and literalness
  (missing a paraphrase), not invention. Where a second reader is
  calibrated, a confidence floor turns its disagreements into safe
  improvements: every live Jev error on topics sat below the floor.
- **Watching it.** `bin/game jev report --disagreements 20` lists the
  decisions where the two readers differed, with both answers, for the
  same adjudication the spike did. The dream digest's local-line list is
  unchanged: a topic Jev picked is an authored answer, not a local line.

Next experiments, in the spike's order: beat advance (a wrong `advance`
moves the story, and a calibrated reader could gate it), and asking the
player which they meant when the two readers disagree on a command.
