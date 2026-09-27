# AFTER run: grounded dialogue on The Village of Lost Hours

SPEC 2026-09-26 criterion 10. Same suites as the BEFORE run
(`docs/model-eval/before-2026-09-26/`, committed before any dialogue change):
`bin/game model-eval run --label after-2026-09-26 --suites dialogue,canon,json`,
Qwen3.5 9B AWQ on vLLM 0.30.0, the game server down, on the finished world
(after both critic passes).

| Metric | Criterion | BEFORE | AFTER |
|---|---|---|---|
| Canon contradictions (34 replies) | 0 | 20 | 0 |
| Pronoun breaks (Tace, Bell are they/them) | | 8 | 0 |
| Max replies per NPC sharing their first six words | <= 2 | 6 (Tace) | 1 |
| JSON validity | >= 99% | 100% | 100% |
| Dialogue p50 / p95 | p50 <= 3.5 s | 3.15 / 3.63 s | 2.24 / 3.23 s |
| Mean output tokens per reply | | 123 | 68 |

## One raw flag, adjudicated

The raw run flagged 1 of 34 canon replies (Mott, "gear-seen"):

> Mott sets the tin back on the shelf and straightens it by a hair, so it
> sits just so. 'I have not seen a brass gear. I have never seen the
> escapement gear at all.'

The matched sentence is not the model's: it is one of Mott's authored drift
lines, spliced in by the dialogue's gesture swap (a worn opening gesture is
replaced by an authored one). "on the shelf" plus "it" (the tin) tripped the
location rule; the spoken line states canon correctly. The scorer now removes
the NPC's own authored lines before matching (`model_eval.authored_lines`,
tested in `tests/test_model_eval.py`), and both runs were rescored under that
one rule set: BEFORE is unchanged at 20/34, AFTER is 0/34. The files here are
the rescored results; the raw run lives at
`~/data/daydream/model-eval/after-2026-09-26/`.

## What the numbers do not say

Grounding makes the 9B honest, not eloquent. Several AFTER replies are correct
but clumsy: "Tace lists a small brass key on the workbench"; "You've got a warm
greeting, doesn't it smell like the stones are holding onto the day's heat?";
"You ask about the morning, and I tell you I sleep through it like a good
clock." This is the register drop `docs/REFLEXES.md` names as the main risk of
local improvisation; the agent playtest measures how often players meet it.
`dlg_brief` fell from 0.97 to 0.82 only because Bell's authored voice runs in
short exclamations (four sentences under 260 characters); replies got shorter
overall.
