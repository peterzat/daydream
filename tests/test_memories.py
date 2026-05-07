"""Unit and integration tests for daydream.memories.

The full BGE-small embedder is never loaded in this suite. Tests opt in
to the memory subsystem via DAYDREAM_MEMORY_ENABLED=1 and mock
``daydream.memories._embed`` so the cosine + recency math is exercised
deterministically without a 100 MB model download.

Test tiers:
- tier_short: pure-Python helpers (cosine, byte-pack, age parse) and
  fail-closed branches (disabled, embedder raises) that don't touch
  the DB.
- tier_medium: capture + retrieve roundtrip and scoping checks against
  a real sqlite TestClient-style DB.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from daydream import db, memories


# ---- helpers -----------------------------------------------------------


def _vec(x: float, y: float, z: float = 0.0) -> list[float]:
    """Make a 3-dim float vector for similarity tests."""
    return [float(x), float(y), float(z)]


def _normed(*xs: float) -> list[float]:
    """Return a unit-norm vector; saves ``[1.0, 0.0, ...]`` style writes
    in tests where we want pure dot-product equality."""
    n = math.sqrt(sum(x * x for x in xs))
    if n == 0.0:
        return list(xs)
    return [x / n for x in xs]


@pytest.fixture
def memdb(tmp_path: Path):
    """Open an isolated DB at tmp_path/live.db with all migrations
    applied. Yields the connection. Closes it on teardown so the next
    test gets a clean module-level _conn slot."""
    p = tmp_path / "live.db"
    conn = db.open_db(p)
    db.init_schema(conn, Path("migrations"))
    # Bind to the module global so memories.py can call db.get_conn().
    db._conn = conn
    yield conn
    db.close_db()


@pytest.fixture
def enabled(monkeypatch):
    """Turn memory on for this test (conftest disables it by default)."""
    monkeypatch.setenv("DAYDREAM_MEMORY_ENABLED", "1")
    monkeypatch.setenv("DAYDREAM_MEMORY_DECAY_HOURS", "24")


@pytest.fixture
def mock_embed(monkeypatch):
    """Install a deterministic embedder that maps known query/text
    strings to specific vectors so similarity ranking is predictable.
    Tests that need a different mapping override this fixture's
    ``mapping`` dict via ``mock_embed.mapping[text] = [...]``."""

    class _Stub:
        mapping: dict[str, list[float]] = {}
        default: list[float] = _normed(0.5, 0.5)

        @classmethod
        def embed(cls, text: str) -> list[float]:
            return cls.mapping.get(text, list(cls.default))

    monkeypatch.setattr(memories, "_embed", _Stub.embed)
    return _Stub


# ---- tier_short: pure helpers ------------------------------------------


@pytest.mark.tier_short
def test_cosine_dot_product_for_unit_vectors():
    a = _normed(1.0, 0.0)
    b = _normed(1.0, 0.0)
    assert memories._cosine(a, b) == pytest.approx(1.0)
    c = _normed(0.0, 1.0)
    assert memories._cosine(a, c) == pytest.approx(0.0)
    d = _normed(-1.0, 0.0)
    assert memories._cosine(a, d) == pytest.approx(-1.0)


@pytest.mark.tier_short
def test_cosine_returns_zero_on_empty_or_length_mismatch():
    assert memories._cosine([], [1.0]) == 0.0
    assert memories._cosine([1.0], []) == 0.0
    assert memories._cosine([1.0, 0.0], [1.0]) == 0.0


@pytest.mark.tier_short
def test_cosine_returns_zero_on_zero_norm():
    assert memories._cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert memories._cosine([1.0, 0.0], [0.0, 0.0]) == 0.0


@pytest.mark.tier_short
def test_byte_packing_roundtrips():
    v = [0.1, -0.5, 1.25, 0.0, 1e-7]
    blob = memories._bytes_from_vec(v)
    assert len(blob) == len(v) * 4
    out = memories._vec_from_bytes(blob)
    assert out == pytest.approx(v, rel=1e-6)


@pytest.mark.tier_short
def test_unpack_handles_malformed_blob():
    assert memories._vec_from_bytes(b"") == []
    assert memories._vec_from_bytes(b"abc") == []  # length not div by 4


@pytest.mark.tier_short
def test_age_seconds_from_sqlite_timestamp():
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    ts = "2026-05-07 11:00:00"
    assert memories._parse_age_seconds(ts, now) == pytest.approx(3600.0)


@pytest.mark.tier_short
def test_age_seconds_unparseable_falls_back_to_zero():
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    assert memories._parse_age_seconds("not-a-timestamp", now) == 0.0


@pytest.mark.tier_short
def test_default_top_k_reads_env(monkeypatch):
    monkeypatch.delenv("DAYDREAM_MEMORY_TOP_K", raising=False)
    assert memories.default_top_k() == 3
    monkeypatch.setenv("DAYDREAM_MEMORY_TOP_K", "5")
    assert memories.default_top_k() == 5
    monkeypatch.setenv("DAYDREAM_MEMORY_TOP_K", "garbage")
    assert memories.default_top_k() == 3


@pytest.mark.tier_short
def test_disabled_short_circuits_capture_and_retrieve(monkeypatch):
    # conftest sets DAYDREAM_MEMORY_ENABLED=0; assert that holds and the
    # public API is well-behaved without ever hitting the DB.
    assert memories.capture("t-rook", "w-bunny", "hello") is None
    assert memories.retrieve("t-rook", "w-bunny", "hello") == []


@pytest.mark.tier_short
def test_capture_swallows_embedder_failure(monkeypatch, enabled):
    def boom(_text: str):
        raise RuntimeError("embedder unavailable")

    monkeypatch.setattr(memories, "_embed", boom)
    assert memories.capture("t-rook", "w-bunny", "hello") is None


@pytest.mark.tier_short
def test_retrieve_swallows_embedder_failure(monkeypatch, enabled):
    def boom(_text: str):
        raise RuntimeError("embedder unavailable")

    monkeypatch.setattr(memories, "_embed", boom)
    assert memories.retrieve("t-rook", "w-bunny", "hello") == []


@pytest.mark.tier_short
def test_capture_swallows_db_not_initialized(monkeypatch, enabled, mock_embed):
    # Module-level _conn is None outside a memdb fixture; capture must
    # log + return None rather than raising.
    db._conn = None
    assert memories.capture("t-rook", "w-bunny", "hello") is None


@pytest.mark.tier_short
def test_retrieve_swallows_db_not_initialized(monkeypatch, enabled, mock_embed):
    db._conn = None
    assert memories.retrieve("t-rook", "w-bunny", "hello") == []


# ---- tier_medium: DB-backed roundtrips ---------------------------------


@pytest.mark.tier_medium
def test_capture_then_retrieve_roundtrip(memdb, enabled, mock_embed):
    mock_embed.mapping["the visitor said: hello"] = _normed(1.0, 0.0)
    mock_embed.mapping["hello"] = _normed(1.0, 0.0)
    rid = memories.capture("t-rook", "w-bunny", "the visitor said: hello")
    assert isinstance(rid, int) and rid > 0
    out = memories.retrieve("t-rook", "w-bunny", "hello")
    assert len(out) == 1
    assert out[0].text == "the visitor said: hello"
    assert out[0].score == pytest.approx(1.0, abs=0.05)


@pytest.mark.tier_medium
def test_per_npc_scoping_isolates_memories(memdb, enabled, mock_embed):
    mock_embed.mapping["rook said: warmth"] = _normed(1.0, 0.0)
    mock_embed.mapping["iris said: a postcard"] = _normed(0.0, 1.0)
    mock_embed.mapping["any query"] = _normed(0.7, 0.7)
    memories.capture("t-rook", "w-bunny", "rook said: warmth")
    memories.capture("t-iris", "w-bunny", "iris said: a postcard")

    rook_results = memories.retrieve("t-rook", "w-bunny", "any query")
    iris_results = memories.retrieve("t-iris", "w-bunny", "any query")
    assert [m.text for m in rook_results] == ["rook said: warmth"]
    assert [m.text for m in iris_results] == ["iris said: a postcard"]


@pytest.mark.tier_medium
def test_per_world_scoping_isolates_memories(memdb, enabled, mock_embed):
    # Seed a second world so per-world memory rows have somewhere to live.
    memdb.execute(
        "INSERT INTO worlds(id, name, slug, aesthetic_seed) "
        "VALUES ('w-other', 'other', 'other', 'seed')"
    )
    mock_embed.mapping["bunny memory"] = _normed(1.0, 0.0)
    mock_embed.mapping["other memory"] = _normed(0.0, 1.0)
    mock_embed.mapping["query"] = _normed(0.5, 0.5)

    memories.capture("t-rook", "w-bunny", "bunny memory")
    memories.capture("t-rook", "w-other", "other memory")

    bunny = memories.retrieve("t-rook", "w-bunny", "query")
    other = memories.retrieve("t-rook", "w-other", "query")
    assert [m.text for m in bunny] == ["bunny memory"]
    assert [m.text for m in other] == ["other memory"]


@pytest.mark.tier_medium
def test_top_k_honored(memdb, enabled, mock_embed):
    # Five memories with descending similarity to the query.
    for i, sim in enumerate([0.9, 0.8, 0.7, 0.6, 0.5]):
        text = f"memory-{i}"
        # Embed at varying angles so cosine reflects the chosen sim.
        # cos(theta) = sim → vec at (sim, sqrt(1-sim^2)) gives that
        # similarity against (1, 0).
        mock_embed.mapping[text] = [sim, math.sqrt(max(0.0, 1.0 - sim * sim))]
        memories.capture("t-rook", "w-bunny", text)

    mock_embed.mapping["query"] = _normed(1.0, 0.0)
    top = memories.retrieve("t-rook", "w-bunny", "query", k=2)
    assert len(top) == 2
    assert top[0].text == "memory-0"
    assert top[1].text == "memory-1"


@pytest.mark.tier_medium
def test_recency_tiebreaker(memdb, enabled, mock_embed, monkeypatch):
    # Two identical-similarity memories, one older than the other.
    # The recency decay is multiplicative: equal similarity → older
    # memory's score is strictly smaller.
    same = _normed(1.0, 0.0)
    mock_embed.mapping["older memory"] = list(same)
    mock_embed.mapping["newer memory"] = list(same)
    mock_embed.mapping["query"] = list(same)

    # Insert older row directly with a backdated created_at; capture()
    # would stamp 'now' which makes the tiebreaker invisible.
    blob = memories._bytes_from_vec(same)
    older_ts = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    memdb.execute(
        "INSERT INTO memories(world_id, npc_id, text, embedding, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("w-bunny", "t-rook", "older memory", blob, older_ts),
    )
    memories.capture("t-rook", "w-bunny", "newer memory")

    top = memories.retrieve("t-rook", "w-bunny", "query", k=2)
    assert [m.text for m in top] == ["newer memory", "older memory"]
    assert top[0].score > top[1].score


@pytest.mark.tier_medium
def test_empty_store_returns_empty_list(memdb, enabled, mock_embed):
    mock_embed.mapping["query"] = _normed(1.0, 0.0)
    assert memories.retrieve("t-rook", "w-bunny", "query") == []


@pytest.mark.tier_medium
def test_capture_records_source_event_seq(memdb, enabled, mock_embed):
    mock_embed.mapping["traced"] = _normed(1.0, 0.0)
    mock_embed.mapping["q"] = _normed(1.0, 0.0)
    rid = memories.capture("t-rook", "w-bunny", "traced", source_event_seq=42)
    assert rid is not None
    out = memories.retrieve("t-rook", "w-bunny", "q")
    assert out and out[0].source_event_seq == 42


@pytest.mark.tier_medium
def test_blank_text_does_not_capture(memdb, enabled, mock_embed):
    assert memories.capture("t-rook", "w-bunny", "") is None
    assert memories.capture("t-rook", "w-bunny", "   ") is None
    out = memories.retrieve("t-rook", "w-bunny", "anything")
    assert out == []


@pytest.mark.tier_medium
def test_blank_query_returns_empty(memdb, enabled, mock_embed):
    mock_embed.mapping["seeded"] = _normed(1.0, 0.0)
    memories.capture("t-rook", "w-bunny", "seeded")
    assert memories.retrieve("t-rook", "w-bunny", "") == []
    assert memories.retrieve("t-rook", "w-bunny", "  ") == []
