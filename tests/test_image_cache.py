"""Image cache: deterministic combined key (seed + workflow), per-target
layout, hit/miss, seed and workflow edits both bust the cache. Pure
Python, no GPU, no network."""

from copy import deepcopy
from pathlib import Path

import pytest

from daydream.images import cache, client

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


# ---- seed_hash (building block) ----------------------------------------


def test_seed_hash_is_deterministic():
    assert cache.seed_hash("a meadow at dusk") == cache.seed_hash("a meadow at dusk")


def test_seed_hash_changes_with_seed():
    assert cache.seed_hash("a") != cache.seed_hash("b")


def test_seed_hash_is_short_hex():
    h = cache.seed_hash("anything")
    assert len(h) == 16
    int(h, 16)  # raises if not hex


# ---- workflow_hash -----------------------------------------------------


def test_workflow_hash_is_deterministic():
    wf = client.load_workflow()
    assert cache.workflow_hash(wf) == cache.workflow_hash(wf)


def test_workflow_hash_changes_with_lora():
    wf = client.load_workflow()
    wf2 = deepcopy(wf)
    wf2[client.LORA_NODE]["inputs"]["lora_name"] = "different.safetensors"
    assert cache.workflow_hash(wf) != cache.workflow_hash(wf2)


def test_workflow_hash_changes_with_ksampler_setting():
    wf = client.load_workflow()
    wf2 = deepcopy(wf)
    # bump steps; that's a real workflow-level edit
    for n in wf2.values():
        if n.get("class_type") == "KSampler":
            n["inputs"]["steps"] = n["inputs"].get("steps", 22) + 1
            break
    assert cache.workflow_hash(wf) != cache.workflow_hash(wf2)


def test_workflow_hash_ignores_meta():
    """The _meta key is documentation; editing it should NOT bust the cache."""
    wf = client.load_workflow()
    h_before = cache.workflow_hash(wf)
    wf_with_meta = dict(wf)
    wf_with_meta["_meta"] = {"random": "annotation"}
    # load_workflow already stripped _meta; verify the function strips again
    assert cache.workflow_hash(wf_with_meta) == h_before


# ---- combined_hash -----------------------------------------------------


def test_combined_hash_changes_with_seed():
    wf = client.load_workflow()
    assert cache.combined_hash("a", wf) != cache.combined_hash("b", wf)


def test_combined_hash_changes_with_workflow():
    wf = client.load_workflow()
    wf2 = deepcopy(wf)
    wf2[client.LORA_NODE]["inputs"]["lora_name"] = "different.safetensors"
    assert cache.combined_hash("seed", wf) != cache.combined_hash("seed", wf2)


# ---- cache_path / cache_url --------------------------------------------


def test_cache_path_lives_under_data_dir(tmp_path: Path):
    wf = client.load_workflow()
    p = cache.cache_path("w-1", "room", "r-1", "seed-text", wf)
    assert str(p).startswith(str(tmp_path))
    assert p.suffix == ".png"
    assert "w-1" in p.parts
    assert "room" in p.parts
    assert "r-1" in p.parts


def test_cache_path_segments_target_kind():
    """target_kind segment ('room', 'toon', etc.) prevents slug collision."""
    wf = client.load_workflow()
    p_room = cache.cache_path("w-1", "room", "x", "seed", wf)
    p_toon = cache.cache_path("w-1", "toon", "x", "seed", wf)
    assert p_room != p_toon
    assert p_room.parent.parent.name == "room"
    assert p_toon.parent.parent.name == "toon"


def test_cache_url_and_path_share_components():
    wf = client.load_workflow()
    p = cache.cache_path("w-1", "room", "r-1", "seed-text", wf)
    u = cache.cache_url("w-1", "room", "r-1", "seed-text", wf)
    assert u.startswith("/cache/w-1/room/r-1/")
    assert u.endswith("/" + p.name)


def test_url_for_cache_path_inverts_cache_path():
    wf = client.load_workflow()
    p = cache.cache_path("w-1", "room", "r-1", "seed", wf)
    u_via_inverse = cache.url_for_cache_path(p)
    u_via_direct = cache.cache_url("w-1", "room", "r-1", "seed", wf)
    assert u_via_inverse == u_via_direct


def test_is_cached_miss_on_empty_dir():
    wf = client.load_workflow()
    assert not cache.is_cached("w-1", "room", "r-1", "seed-text", wf)


def test_is_cached_hit_when_file_present():
    wf = client.load_workflow()
    p = cache.cache_path("w-1", "room", "r-1", "seed-text", wf)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    assert cache.is_cached("w-1", "room", "r-1", "seed-text", wf)


def test_seed_edit_invalidates_cache_non_destructively():
    """Editing the seed produces a new path; the old cached file is not
    deleted, so admin rollback can still serve it."""
    wf = client.load_workflow()
    p_old = cache.cache_path("w-1", "room", "r-1", "old seed", wf)
    p_new = cache.cache_path("w-1", "room", "r-1", "new seed", wf)
    assert p_old != p_new
    p_old.parent.mkdir(parents=True, exist_ok=True)
    p_old.write_bytes(b"\x89PNG\r\n\x1a\nold")
    assert cache.is_cached("w-1", "room", "r-1", "old seed", wf)
    assert not cache.is_cached("w-1", "room", "r-1", "new seed", wf)
    assert p_old.exists()


def test_workflow_edit_invalidates_cache_non_destructively():
    """Editing the workflow JSON (e.g. swapping LoRA) produces a new path
    without touching the previous file. This is the main reason we fold
    workflow_hash into the cache key."""
    wf1 = client.load_workflow()
    wf2 = deepcopy(wf1)
    wf2[client.LORA_NODE]["inputs"]["lora_name"] = "different.safetensors"
    p1 = cache.cache_path("w-1", "room", "r-1", "seed", wf1)
    p2 = cache.cache_path("w-1", "room", "r-1", "seed", wf2)
    assert p1 != p2
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_bytes(b"\x89PNG\r\n\x1a\nold")
    assert cache.is_cached("w-1", "room", "r-1", "seed", wf1)
    assert not cache.is_cached("w-1", "room", "r-1", "seed", wf2)


def test_ensure_cache_root_creates_dir():
    root = cache.ensure_cache_root()
    assert root.exists() and root.is_dir()


def test_world_room_isolation():
    """Same seed + workflow in different rooms produces different paths."""
    wf = client.load_workflow()
    p1 = cache.cache_path("w-1", "room", "r-meadow", "same seed", wf)
    p2 = cache.cache_path("w-1", "room", "r-forge", "same seed", wf)
    assert p1 != p2
    assert p1.parent != p2.parent
