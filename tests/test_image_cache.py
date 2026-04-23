"""Image cache: deterministic key, hit/miss, seed change invalidates without
destructive delete. Pure-Python, no GPU, no network."""

from pathlib import Path

import pytest

from daydream.images import cache


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


def test_seed_hash_is_deterministic():
    assert cache.seed_hash("a meadow at dusk") == cache.seed_hash("a meadow at dusk")


def test_seed_hash_changes_with_seed():
    assert cache.seed_hash("a") != cache.seed_hash("b")


def test_seed_hash_is_short_hex():
    h = cache.seed_hash("anything")
    assert len(h) == 16
    int(h, 16)  # raises if not hex


def test_cache_path_lives_under_data_dir(tmp_path: Path):
    p = cache.cache_path("w-1", "r-1", "seed-text")
    assert str(p).startswith(str(tmp_path))
    assert p.suffix == ".png"
    assert "w-1" in p.parts
    assert "r-1" in p.parts


def test_cache_url_and_path_share_components():
    p = cache.cache_path("w-1", "r-1", "seed-text")
    u = cache.cache_url("w-1", "r-1", "seed-text")
    assert u.startswith("/cache/w-1/r-1/")
    assert u.endswith("/" + p.name)


def test_is_cached_miss_on_empty_dir():
    assert not cache.is_cached("w-1", "r-1", "seed-text")


def test_is_cached_hit_when_file_present():
    p = cache.cache_path("w-1", "r-1", "seed-text")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    assert cache.is_cached("w-1", "r-1", "seed-text")


def test_seed_edit_invalidates_cache_non_destructively():
    """Editing the seed produces a new path; the old cached file is not
    deleted, so admin rollback can still serve it."""
    p_old = cache.cache_path("w-1", "r-1", "old seed")
    p_new = cache.cache_path("w-1", "r-1", "new seed")
    assert p_old != p_new
    p_old.parent.mkdir(parents=True, exist_ok=True)
    p_old.write_bytes(b"\x89PNG\r\n\x1a\nold")
    assert cache.is_cached("w-1", "r-1", "old seed")
    assert not cache.is_cached("w-1", "r-1", "new seed")
    # And the old file is still on disk.
    assert p_old.exists()


def test_ensure_cache_root_creates_dir():
    root = cache.ensure_cache_root()
    assert root.exists() and root.is_dir()


def test_world_room_isolation():
    """Same seed in different rooms produces different paths."""
    p1 = cache.cache_path("w-1", "r-meadow", "same seed")
    p2 = cache.cache_path("w-1", "r-forge", "same seed")
    assert p1 != p2
    assert p1.parent != p2.parent
