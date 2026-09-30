"""Jev (TypeSafe's hosted decision model), an optional second reflex beside
the local model (docs/EXTERNAL.md; the evaluation, docs/JEV-SPIKE.md).

Jev answers typed questions over a state: a Choice among named options, a
yes/no (Noul) or a rubric Score, each with calibrated probabilities. It
writes no text, so it stands in the running game only where the local
model decides: whether a draft keeps its promises (the promise judge), and
which authored topic a free line asks about (daydream/jev/runtime.py).

On exactly when a key is reachable, off otherwise; there is no other switch
(daydream/jev/settings.py). Dev reads `DAYDREAM_JEV_API_KEY` (or
`TYPESAFE_API_KEY`) from the repo's gitignored `.env`; prod holds no key
and calls through the egress gateway, which does. Removing the key turns
Jev off. Off, or with a bad key, an empty account (HTTP 402), a timeout or
any error, a surface runs exactly as it does without Jev: the local path
serves. On, the local path still runs beside it (daydream/jev/seam.py) and
each surface's rule chooses what serves.

Metrics are first-class: every call (tokens, cost, latency, outcome) and
every paired decision (both answers, which served, agreement, Jev's
confidence) goes to a ledger under the data dir, kept 30 days and read by
`bin/game jev report`.
"""
