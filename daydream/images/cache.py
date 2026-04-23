"""Image cache: per-(world, room, seed) deterministic file paths.

Cache key is the SHA-256 hex prefix of the room's seed text. The cached
file lives under ~/data/daydream/images/cache/{world}/{room}/{hash}.png.

Editing the room's seed produces a different hash, misses the cache, and
triggers regeneration. Old files stay on disk (no destructive deletes)
until the operator chooses to clean them; this is intentional so admin
rollback still has the prior asset to re-serve."""

import hashlib
from pathlib import Path

from daydream import config


def seed_hash(seed: str) -> str:
    """16-char hex prefix of SHA-256(seed). Stable across runs and processes."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def cache_dir() -> Path:
    return config.data_dir() / "images" / "cache"


def cache_path(world_id: str, room_id: str, room_seed: str) -> Path:
    """Deterministic file path for a room background."""
    h = seed_hash(room_seed)
    return cache_dir() / world_id / room_id / f"{h}.png"


def cache_url(world_id: str, room_id: str, room_seed: str) -> str:
    """URL path the SPA fetches the cached image from. Mirrors cache_path()'s
    {world}/{room}/{hash}.png shape so the StaticFiles mount in server.py can
    serve it without translation."""
    h = seed_hash(room_seed)
    return f"/cache/{world_id}/{room_id}/{h}.png"


def is_cached(world_id: str, room_id: str, room_seed: str) -> bool:
    return cache_path(world_id, room_id, room_seed).exists()


def ensure_cache_root() -> Path:
    """Create the cache root if absent. Returns the root."""
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root
