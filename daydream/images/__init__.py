"""Image generation and caching.

cache.py owns the deterministic (world, room, seed) -> file path mapping.
client.py (lands in Inc 4) talks to ComfyUI over HTTP and writes results
into the cache."""
