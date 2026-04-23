"""GPU arbiter: in-process serialization of LLM and image-gen calls.

Daydream is the sole GPU consumer on this box (qwen-2.5-localreview's
warm server is off; see CLAUDE.md). The 20 GB VRAM ceiling makes it
unsafe to run vLLM and SDXL inference simultaneously, so every external
GPU-dependent call routes through this arbiter's lock and runs serially.

asyncio.Lock is sufficient because Daydream is one Python process with
one event loop. flock would be needed only if a second process ever
contended for the GPU; the pattern lives at
~/src/qwen-2.5-localreview/gpu_lock.py for that day."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


@asynccontextmanager
async def acquire() -> AsyncIterator[None]:
    """Async context manager for serialized GPU access.

    Usage:
        async with arbiter.acquire():
            await call_llm()  # or call_image_gen()
    """
    lock = _get_lock()
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()


def is_locked() -> bool:
    """Whether the arbiter lock is currently held. For tests and bin/game status."""
    return _lock is not None and _lock.locked()


def reset() -> None:
    """Test helper: drop the singleton so each test gets a fresh lock.
    Not for production paths."""
    global _lock
    _lock = None
