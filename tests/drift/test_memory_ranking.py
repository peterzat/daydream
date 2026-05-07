"""Memory salience-formula drift probe.

The retrieval ranking score is ``cosine_similarity * exp(-age_hours / DECAY_HOURS)``
where ``DECAY_HOURS = 24`` by default (env override ``DAYDREAM_MEMORY_DECAY_HOURS``).
The formula and the constant together ARE the contract for how NPCs select
which past memories to recall. This probe pins both:

- The ordering returned for a fixed (similarity, age) corpus. Catches
  sort-key flips, decay-direction sign errors, and similarity-vs-recency
  weighting bugs.
- The per-item score, rounded to 4 decimals as a formatted string. Catches
  ``DECAY_HOURS`` drift, formula tweaks (e.g. linear decay swapped for
  exponential), and similarity-pipeline bugs.

Tier: ``tier_short``. CPU-only, no real engines, deterministic mocked
embeddings injected via ``monkeypatch.setattr(memories, "_embed", ...)``.
The DB is a tmp_path SQLite with the full migration set applied — well
under the 2 s tier budget.

The corpus is five memories with crafted (similarity, age) pairs that
exercise three orthogonal regimes:

- Pure similarity (high-sim recent vs low-sim recent at the same age).
- Recency dominates (high-sim 20-h-old loses to med-sim recent).
- Age annihilates similarity (highest-sim 72-h-old falls to last).

Drift loop:

- First run: no golden → fail with ``.latest`` written and ratify
  instructions.
- Match: pass; ``.latest`` refreshed.
- Diverge: fail with a field-level diff; operator decides "fix the
  regression" vs "ratify the new baseline".
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from daydream import db, memories

from .conftest import assert_against_baseline

pytestmark = pytest.mark.tier_short


PROBE_ID = "memory_ranking"
SCORE_FMT = "{:.4f}"  # 4-decimal string fingerprint absorbs FP jitter


# Crafted corpus: (text, similarity_to_query, age_hours).
# Keep stable text labels so the diff in a baseline-divergence message
# is human-readable.
_CORPUS: list[tuple[str, float, float]] = [
    ("high-sim recent", 0.9, 1.0),
    ("high-sim old", 0.9, 20.0),
    ("med-sim recent", 0.7, 1.0),
    ("low-sim recent", 0.4, 1.0),
    ("high-sim ancient", 0.95, 72.0),
]
_QUERY = "test query"


def _vec_at_angle(sim: float) -> list[float]:
    """2-D unit vector whose dot with (1, 0) equals ``sim``."""
    return [sim, math.sqrt(max(0.0, 1.0 - sim * sim))]


@pytest.fixture
def memdb(tmp_path: Path):
    """Isolated DB at tmp_path with full migrations applied. Mirrors
    the fixture in tests/test_memories.py."""
    p = tmp_path / "live.db"
    conn = db.open_db(p)
    db.init_schema(conn, Path("migrations"))
    db._conn = conn
    yield conn
    db.close_db()


@pytest.fixture
def memory_enabled(monkeypatch):
    """Memory is off by default in tests (conftest); turn it on and pin
    the decay constant so a stray env override can't silently shift the
    baseline."""
    monkeypatch.setenv("DAYDREAM_MEMORY_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_MEMORY_DECAY_HOURS", "24")


@pytest.fixture
def mock_embed(monkeypatch):
    """Deterministic 2-D embeddings: each corpus text → unit vector at
    its configured similarity-angle to the query (1, 0)."""
    mapping: dict[str, list[float]] = {_QUERY: [1.0, 0.0]}
    for text, sim, _age in _CORPUS:
        mapping[text] = _vec_at_angle(sim)

    def fake_embed(text: str) -> list[float]:
        if text not in mapping:
            raise KeyError(f"unmapped text in drift probe: {text!r}")
        return list(mapping[text])

    monkeypatch.setattr(memories, "_embed", fake_embed)


def _seed_corpus(conn) -> None:
    """Insert each corpus row with a backdated ``created_at`` so
    ``retrieve()`` sees the configured age. ``CURRENT_TIMESTAMP`` would
    stamp 'now' on every row, which would erase the age axis."""
    now = datetime.now(timezone.utc)
    for text, sim, age_h in _CORPUS:
        ts = (now - timedelta(hours=age_h)).strftime("%Y-%m-%d %H:%M:%S")
        blob = memories._bytes_from_vec(_vec_at_angle(sim))
        conn.execute(
            "INSERT INTO memories(world_id, npc_id, text, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("w-bunny", "t-rook", text, blob, ts),
        )


def test_memory_ranking_drift(memdb, memory_enabled, mock_embed):
    """Pin the salience formula's ordering and per-item scores against
    the committed golden baseline."""
    _seed_corpus(memdb)
    results = memories.retrieve("t-rook", "w-bunny", _QUERY, k=len(_CORPUS))
    assert len(results) == len(_CORPUS), (
        f"expected {len(_CORPUS)} retrieved memories, got {len(results)}"
    )
    observed = {
        "decay_hours": memories._decay_hours(),
        "ranked": [
            {"text": m.text, "score": SCORE_FMT.format(m.score)} for m in results
        ],
    }
    assert_against_baseline(
        PROBE_ID, observed, compare_keys=["decay_hours", "ranked"]
    )
