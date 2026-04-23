"""GPU arbiter and (eventually) GPU-related utilities.

v1 ships only the in-process arbiter. flock-based cross-process
coordination is unnecessary while Daydream is the sole GPU consumer on
the box (per CLAUDE.md); the qwen-2.5-localreview/gpu_lock.py pattern is
still cited as a clean code template if that assumption ever changes."""
