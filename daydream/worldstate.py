"""Per-world key-value state: the world clock, flags, counters, score, and
authored definition blocks (migration 013).

Two key families share the one `world_state` table:

- Authored definitions, written once by the world loader and read-only at
  runtime: ``def:verbs``, ``def:rules``, ``def:flags``, ``def:fuses``,
  ``def:daemons``, ``def:scoring``, ``config``, ``voice``.
- Runtime state, mutated by effects and the world clock: ``turn``, ``score``,
  ``rng_seed``, ``flag:<NAME>``, ``counter:<name>``, ``fuse:<name>``,
  ``daemon:<name>``.

Every read has a documented default (turn 0, score 0, flags false, counters
0), so a world with no rows — every pre-013 world — behaves exactly as
before. This module is the single read/write surface over the table.

Seeded RNG convention: ``rng(world_id, purpose)`` returns a ``random.Random``
seeded with ``f"{rng_seed}:{turn}:{purpose}"``. Deterministic per (seed,
turn, purpose) triple: replaying the same world seed through the same command
sequence reproduces every hazard roll, daemon move, and combat round, which
is what makes the walkthrough and combat tests pinnable.
"""

from __future__ import annotations

import json
import random
from typing import Any

from daydream import db

# Runtime key names / prefixes (one place, so effect handlers and the clock
# never drift on spelling).
KEY_TURN = "turn"
KEY_SCORE = "score"
KEY_RNG_SEED = "rng_seed"
FLAG_PREFIX = "flag:"
COUNTER_PREFIX = "counter:"
FUSE_PREFIX = "fuse:"
DAEMON_PREFIX = "daemon:"

# Default RNG seed for worlds that never authored one. A constant (not
# world_id-derived) so tests get determinism without setup; the format-2
# loader stamps a per-world seed from the envelope config.
DEFAULT_RNG_SEED = "0"


# ---- generic KV ----------------------------------------------------------


def get(world_id: str, key: str, default: Any = None) -> Any:
    """Read one key's JSON value, or `default` if absent or unparseable."""
    row = db.get_conn().execute(
        "SELECT value_json FROM world_state WHERE world_id = ? AND key = ?",
        (world_id, key),
    ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value_json"])
    except (json.JSONDecodeError, TypeError):
        return default


def set(world_id: str, key: str, value: Any) -> None:  # noqa: A001 - KV verb
    """Upsert one key. `value` must be JSON-serializable."""
    db.get_conn().execute(
        "INSERT INTO world_state (world_id, key, value_json) VALUES (?, ?, ?) "
        "ON CONFLICT (world_id, key) DO UPDATE SET "
        "value_json = excluded.value_json, updated_at = CURRENT_TIMESTAMP",
        (world_id, key, json.dumps(value)),
    )


def delete(world_id: str, key: str) -> None:
    db.get_conn().execute(
        "DELETE FROM world_state WHERE world_id = ? AND key = ?", (world_id, key)
    )


def keys(world_id: str, prefix: str = "") -> list[str]:
    """All keys for a world, optionally filtered by prefix, sorted. The
    clock uses this to enumerate active `fuse:` / `daemon:` entries."""
    rows = db.get_conn().execute(
        "SELECT key FROM world_state WHERE world_id = ? ORDER BY key", (world_id,)
    ).fetchall()
    return [r["key"] for r in rows if r["key"].startswith(prefix)]


def delete_world_state(world_id: str) -> None:
    """Remove every state row for a world (admin world-delete cascade)."""
    db.get_conn().execute("DELETE FROM world_state WHERE world_id = ?", (world_id,))


# ---- turn clock ----------------------------------------------------------


def turn(world_id: str) -> int:
    v = get(world_id, KEY_TURN, 0)
    return v if isinstance(v, int) else 0


def advance_turn(world_id: str) -> int:
    """Advance the world clock by one and return the new turn number."""
    t = turn(world_id) + 1
    set(world_id, KEY_TURN, t)
    return t


# ---- score ---------------------------------------------------------------


def score(world_id: str) -> int:
    v = get(world_id, KEY_SCORE, 0)
    return v if isinstance(v, int) else 0


def adjust_score(world_id: str, delta: int) -> int:
    """Add `delta` (may be negative) to the world score; returns the new
    score. Scores are world-shared (fidelity relaxation R1: co-op scoring;
    a solo playthrough is bit-identical to the single-player game)."""
    s = score(world_id) + delta
    set(world_id, KEY_SCORE, s)
    return s


# ---- flags ---------------------------------------------------------------


def get_flag(world_id: str, name: str, default: bool = False) -> bool:
    v = get(world_id, FLAG_PREFIX + name, default)
    return bool(v)


def set_flag(world_id: str, name: str, value: bool) -> None:
    set(world_id, FLAG_PREFIX + name, bool(value))


# ---- counters ------------------------------------------------------------


def counter(world_id: str, name: str) -> int:
    v = get(world_id, COUNTER_PREFIX + name, 0)
    return v if isinstance(v, int) else 0


def adjust_counter(world_id: str, name: str, delta: int) -> int:
    c = counter(world_id, name) + delta
    set(world_id, COUNTER_PREFIX + name, c)
    return c


def set_counter(world_id: str, name: str, value: int) -> None:
    set(world_id, COUNTER_PREFIX + name, int(value))


# ---- seeded RNG ----------------------------------------------------------


def rng_seed(world_id: str) -> str:
    v = get(world_id, KEY_RNG_SEED, DEFAULT_RNG_SEED)
    return v if isinstance(v, str) else DEFAULT_RNG_SEED


def rng(world_id: str, purpose: str) -> random.Random:
    """A deterministic RNG for one decision point. Seeded with
    (world rng_seed, current turn, purpose) so distinct purposes on the same
    turn are independent streams, and the same world seed replayed through
    the same commands reproduces every roll."""
    return random.Random(f"{rng_seed(world_id)}:{turn(world_id)}:{purpose}")


# ---- rank + snapshot status ----------------------------------------------


def rank_for(world_id: str, score_value: int) -> str | None:
    """Resolve a score to its authored rank name from `def:scoring`'s
    `ranks` ladder (`[{"min": 0, "name": ...}, ...]`). Highest qualifying
    `min` wins. None when the world authors no ladder."""
    scoring = get(world_id, "def:scoring")
    if not isinstance(scoring, dict):
        return None
    ranks = scoring.get("ranks")
    if not isinstance(ranks, list):
        return None
    best: tuple[int, str] | None = None
    for r in ranks:
        if not isinstance(r, dict):
            continue
        m, name = r.get("min"), r.get("name")
        if not isinstance(m, int) or not isinstance(name, str):
            continue
        if m <= score_value and (best is None or m > best[0]):
            best = (m, name)
    return best[1] if best else None


def status_block(world_id: str) -> dict:
    """The snapshot `status` payload: world-shared score / rank / moves /
    deaths. `lit` is filled by the WS layer once lighting lands (until then
    every room is lit and the field is constant true)."""
    s = score(world_id)
    return {
        "score": s,
        "rank": rank_for(world_id, s),
        "moves": turn(world_id),
        "deaths": counter(world_id, "deaths"),
        "lit": True,
    }
