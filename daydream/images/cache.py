"""Image cache: per-(world, target_kind, target_id, seed, workflow) deterministic
file paths.

The cache key folds three things together:
- the seed text (the room/toon/item's prompt source),
- the workflow JSON (so workflow edits — sampler tweaks, LoRA strength,
  resolution — actually bust the cache rather than silently serving the
  prior image),
- and the (target_kind, target_id) tuple (so two rooms with the same seed
  text get different files instead of accidentally aliasing each other on
  disk).

Layout: ~/data/daydream/images/cache/{world}/{target_kind}/{target_id}/{combined_hash}.png

Editing the seed OR the workflow JSON produces a different combined_hash,
misses the cache, and triggers regeneration. Old files stay on disk (no
destructive deletes) until the operator chooses to clean them; this is
intentional so admin rollback still has the prior asset to re-serve.
"""

import hashlib
import json
from pathlib import Path

from daydream import config


def seed_hash(seed: str) -> str:
    """16-char hex prefix of SHA-256(seed). Stable across runs and processes.
    Building block for combined_hash; also still stored in the
    generated_assets row as the natural-key seed component."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def workflow_hash(workflow: dict) -> str:
    """16-char hex prefix of SHA-256(canonical JSON of workflow minus _meta).

    The _meta key is stripped because it's documentation only (operator
    notes, node-id annotations) and editing it should not bust the cache.
    Canonical JSON via sort_keys=True so dict insertion order doesn't
    affect the hash."""
    stripped = {k: v for k, v in workflow.items() if not k.startswith("_")}
    canonical = json.dumps(stripped, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def combined_hash(seed: str, workflow: dict) -> str:
    """16-char hex prefix of SHA-256(seed_hash + workflow_hash). Composing
    the two component hashes (rather than re-hashing the raw inputs) means
    debug output can show seed_hash and workflow_hash side-by-side and they
    still combine to the cache key."""
    raw = seed_hash(seed) + workflow_hash(workflow)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cache_dir() -> Path:
    return config.data_dir() / "images" / "cache"


def cache_path(
    world_id: str, target_kind: str, target_id: str, seed: str, workflow: dict
) -> Path:
    """Deterministic file path for a generated asset. The {target_kind}
    segment ('room' for v1; 'toon' / 'item' later) prevents slug collision
    when NPC portraits land alongside room backgrounds."""
    h = combined_hash(seed, workflow)
    return cache_dir() / world_id / target_kind / target_id / f"{h}.png"


def cache_url(
    world_id: str, target_kind: str, target_id: str, seed: str, workflow: dict
) -> str:
    """URL path the SPA fetches the cached image from. Mirrors cache_path()'s
    {world}/{kind}/{id}/{hash}.png shape so the StaticFiles mount in
    server.py can serve it without translation."""
    h = combined_hash(seed, workflow)
    return f"/cache/{world_id}/{target_kind}/{target_id}/{h}.png"


def is_cached(
    world_id: str, target_kind: str, target_id: str, seed: str, workflow: dict
) -> bool:
    return cache_path(world_id, target_kind, target_id, seed, workflow).exists()


def url_for_cache_path(path: Path) -> str:
    """Inverse of cache_path: derive the SPA-served URL from an absolute
    cache path. Used by callers that already hold the path returned by
    generate_image and don't want to recompute the hash via cache_url()."""
    rel = path.relative_to(cache_dir())
    return "/cache/" + rel.as_posix()


def ensure_cache_root() -> Path:
    """Create the cache root if absent. Returns the root."""
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root
