"""Jev (TypeSafe's hosted decision model), an optional second reflex beside
the local model: a spike, on the `spike/jev` branch (docs/JEV-SPIKE.md).

Jev answers typed questions over a state: a Choice among named options, a
yes/no (Noul) or a rubric Score, each with calibrated probabilities. It
writes no text, so it can stand in only where the local model decides:
which command a line means, whether a draft keeps its promises, which
authored topic a line asks about.

Always optional. With no key, a bad key, an empty account (HTTP 402), a
timeout or any error, a surface runs exactly as it does without Jev: the
local path serves. Every surface has three modes (`DAYDREAM_JEV`, or
`DAYDREAM_JEV_<SURFACE>` for one surface):

- `off`: the local path only (the default).
- `shadow`: the local path serves; Jev answers the same question in the
  background, and both answers are recorded side by side.
- `on`: Jev serves when it answers with enough confidence
  (`DAYDREAM_JEV_<SURFACE>_MIN`), else the local path does; the local
  answer is recorded beside it either way.

Metrics are first-class: every call (tokens, cost, latency, outcome) and
every paired decision (both answers, agreement, Jev's confidence) goes to
an append-only ledger under the data dir, read by `bin/game jev report`.
"""
