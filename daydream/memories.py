"""NPC memory store: capture + retrieve dialogue exchanges so NPCs feel
remembered across turns.

v0 storage:
- One row per memory in the per-world ``memories`` SQLite table (added in
  migration 009). The embedding lives as raw float32 bytes in the BLOB
  column on the same row. No separate vector store. At single-user
  scale (one human, two NPCs, conversation depth in dozens) a linear
  scan over a per-(npc, world) slice is sub-millisecond. LanceDB is the
  v1 path once memory counts cross ~10K per NPC or a cross-NPC retrieval
  shape lands.

Embedder:
- BGE-small (``BAAI/bge-small-en-v1.5``, 384-dim) on CPU. Loaded lazily
  on first capture/retrieve call so server startup stays cheap.
  Configurable via ``DAYDREAM_MEMORY_MODEL``. The model file lives in
  the shared HuggingFace cache (``~/.cache/huggingface``); pre-download
  via ``bin/memory-bootstrap``. CPU-only by construction. Module DOES
  NOT take the GPU arbiter.

Failure modes (all logged at WARNING and swallowed; never raised):
- Embedder unavailable (``sentence-transformers`` not installed, model
  file missing, model load raises): ``capture`` returns ``None``,
  ``retrieve`` returns ``[]``.
- DB closed / not initialized: same fail-closed pattern.
- ``DAYDREAM_MEMORY_ENABLED=0``: short-circuits before any work; tests
  opt out via ``tests/conftest.py``.

Ranking (retrieve):
- ``score = cosine_similarity(query, memory) * exp(-age_hours / DECAY_HOURS)``
  with DECAY_HOURS=24 (override ``DAYDREAM_MEMORY_DECAY_HOURS``). The
  combined score collapses similarity + recency into one ordering: more
  similar wins; on similarity ties, more recent wins. Sorting is stable
  on ties.

Test seam:
- Tests monkeypatch ``daydream.memories._embed`` to return deterministic
  ``list[float]`` vectors so the suite never loads BGE-small.
"""

from __future__ import annotations

import logging
import math
import os
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from daydream import db
from daydream.llm import safety

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Memory:
    """One retrieved memory for the prompt template's ``memories`` context."""

    id: int
    text: str
    created_at: str
    source_event_seq: int | None
    age_seconds: float
    score: float


_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_DEFAULT_DECAY_HOURS = 24.0
_DEFAULT_TOP_K = 3


# Lazy-loaded embedder singleton. Re-loading is wasteful since the model
# is ~100 MB; ``_embedder`` is set on first successful load and never
# reset in production. Tests mock at the ``_embed`` boundary so they
# never touch this.
_embedder: Any = None


def _is_enabled() -> bool:
    """Memory is on by default in production; tests opt out via
    ``DAYDREAM_MEMORY_ENABLED=0`` (see ``tests/conftest.py``)."""
    return os.environ.get("DAYDREAM_MEMORY_ENABLED", "1") != "0"


def _model_name() -> str:
    return os.environ.get("DAYDREAM_MEMORY_MODEL", _DEFAULT_MODEL)


def _decay_hours() -> float:
    try:
        return float(os.environ.get("DAYDREAM_MEMORY_DECAY_HOURS", _DEFAULT_DECAY_HOURS))
    except ValueError:
        return _DEFAULT_DECAY_HOURS


def default_top_k() -> int:
    """Public accessor so the data-skill pipeline can read the same
    default the module uses internally."""
    try:
        return int(os.environ.get("DAYDREAM_MEMORY_TOP_K", _DEFAULT_TOP_K))
    except ValueError:
        return _DEFAULT_TOP_K


def _get_embedder():
    """Return the loaded SentenceTransformer model, lazy-initialized.
    Raises whatever the underlying load raises; callers wrap and log."""
    global _embedder
    if _embedder is not None:
        return _embedder
    from sentence_transformers import SentenceTransformer

    _embedder = SentenceTransformer(_model_name(), device="cpu")
    return _embedder


def _embed(text: str) -> list[float]:
    """Return the embedding as a plain Python ``list[float]``.

    Test seam: monkeypatch this function to inject deterministic vectors
    so the suite never loads BGE-small."""
    model = _get_embedder()
    vec = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vec.tolist()


def _bytes_from_vec(vec: list[float]) -> bytes:
    """Pack a float32 vector to raw bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(vec)}f", *vec)


def _vec_from_bytes(blob: bytes) -> list[float]:
    """Unpack raw float32 bytes back to a list. Returns ``[]`` for an
    empty/odd-length blob rather than raising."""
    n = len(blob) // 4
    if n == 0 or len(blob) % 4 != 0:
        return []
    return list(struct.unpack(f"{n}f", blob))


def _cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity. Returns 0.0 on dimension mismatch
    or zero-norm inputs. Inputs whose norms are pre-1 (BGE-small with
    ``normalize_embeddings=True``) collapse this to a dot product, which
    is fine."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _parse_age_seconds(created_at: str, now: datetime) -> float:
    """SQLite CURRENT_TIMESTAMP yields ``YYYY-MM-DD HH:MM:SS`` in UTC.
    Convert to age in seconds. Returns 0.0 on parse failure (so a
    malformed timestamp is treated as 'just happened' for ranking,
    which is the safest direction — never penalizes recall)."""
    try:
        dt = datetime.fromisoformat(created_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (now - dt).total_seconds())
    except Exception:
        return 0.0


def capture(
    npc_id: str,
    world_id: str,
    text: str,
    source_event_seq: int | None = None,
) -> int | None:
    """Persist one memory for ``(npc_id, world_id)``. Returns the new
    row id, or ``None`` if memory is disabled / embedder failed / DB
    unreachable. Never raises."""
    if not _is_enabled():
        return None
    if not text or not text.strip():
        return None
    # Defense-in-depth: skip capturing text that hits the WHIMSY banlist.
    # Memory rows are rendered into future prompts at the memory-block
    # position; never persist anything that already failed the
    # tone/safety filter. The output banlist + effect allowlist still
    # backstop downstream, but reducing the population of injected text
    # at the source is cheaper than scrubbing it on every retrieval.
    hit = safety.first_banned(text)
    if hit is not None:
        logger.warning("memory capture: banlist hit (%s); skipping persist", hit)
        return None
    try:
        vec = _embed(text)
    except Exception as e:
        logger.warning(
            "memory capture: embedder failed (%s): %s", type(e).__name__, e
        )
        return None
    try:
        conn = db.get_conn()
    except RuntimeError as e:
        logger.warning("memory capture: DB not initialized: %s", e)
        return None
    try:
        cur = conn.execute(
            "INSERT INTO memories(world_id, npc_id, text, embedding, source_event_seq) "
            "VALUES (?, ?, ?, ?, ?)",
            (world_id, npc_id, text, _bytes_from_vec(vec), source_event_seq),
        )
        return int(cur.lastrowid) if cur.lastrowid is not None else None
    except Exception as e:
        logger.warning("memory capture: DB write failed: %s", e)
        return None


def retrieve(
    npc_id: str,
    world_id: str,
    query_text: str,
    k: int | None = None,
) -> list[Memory]:
    """Return up to K memories for ``(npc_id, world_id)`` ranked by
    combined cosine similarity * recency decay. Empty list if memory is
    disabled, embedder fails, DB is unreachable, or no memories exist
    for this ``(npc, world)``. Never raises."""
    if not _is_enabled():
        return []
    if k is None:
        k = default_top_k()
    if k <= 0:
        return []
    if not query_text or not query_text.strip():
        return []
    try:
        qvec = _embed(query_text)
    except Exception as e:
        logger.warning(
            "memory retrieve: embedder failed (%s): %s", type(e).__name__, e
        )
        return []
    try:
        conn = db.get_conn()
    except RuntimeError as e:
        logger.warning("memory retrieve: DB not initialized: %s", e)
        return []
    try:
        rows = conn.execute(
            "SELECT id, text, embedding, created_at, source_event_seq "
            "FROM memories WHERE npc_id = ? AND world_id = ? "
            "ORDER BY created_at DESC",
            (npc_id, world_id),
        ).fetchall()
    except Exception as e:
        logger.warning("memory retrieve: DB read failed: %s", e)
        return []
    if not rows:
        return []
    decay_hours = _decay_hours()
    now = datetime.now(timezone.utc)
    scored: list[tuple[float, float, dict]] = []
    for r in rows:
        try:
            mvec = _vec_from_bytes(r["embedding"])
        except Exception:
            continue
        sim = _cosine(qvec, mvec)
        age_s = _parse_age_seconds(r["created_at"], now)
        weight = (
            math.exp(-(age_s / 3600.0) / decay_hours) if decay_hours > 0 else 1.0
        )
        score = sim * weight
        scored.append((score, age_s, dict(r)))
    # Sort: descending by score; ties broken by ascending age (more recent
    # wins). Using key=(-score, age) with default ascending sort.
    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[:k]
    return [
        Memory(
            id=int(d["id"]),
            text=d["text"],
            created_at=d["created_at"],
            source_event_seq=d["source_event_seq"],
            age_seconds=age_s,
            score=score,
        )
        for score, age_s, d in top
    ]


def reset_embedder() -> None:
    """Test helper: drop the cached embedder so tests can simulate a
    cold load or swap models. Never used in production."""
    global _embedder
    _embedder = None
