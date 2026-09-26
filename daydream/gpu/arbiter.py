"""GPU arbiter v2: a shared/exclusive gate over the one 20 GB card.

Daydream is the sole GPU consumer on this box (qwen-2.5-localreview's
warm server is off; see CLAUDE.md). Two kinds of work contend:

- ``kind="llm"`` — a text call into vLLM. vLLM batches requests natively
  inside its preallocated memory slice (``--gpu-memory-utilization``), so
  LLM calls are VRAM-safe to run CONCURRENTLY with each other, capped at
  ``config.llm_concurrency()`` in flight.
- ``kind="exclusive"`` (the default, and every image render) — SDXL peaks
  several GB above its resident footprint, so an exclusive holder runs
  alone: no LLM call and no other exclusive may overlap it.

- ``kind="background"`` — a non-player LLM call (the story director ranking
  authored storylets, SPEC 2026-09-26 criterion 5). At most ONE runs at a
  time, it is admitted only when no render is active or queued AND no
  player-facing LLM call is queued, and it does NOT count against the LLM
  cap (vLLM's --max-num-seqs is 4 = the cap of 3 + this one slot), so it
  can never delay a player-facing call. A queued render waits for an active
  background call to finish but no new background call is admitted past it,
  so renders are never starved by background work.

Admission policy is TEXT-PRIORITY: an LLM waiter is admitted whenever no
exclusive is active (it barges past queued exclusives); an exclusive is
admitted only when nothing is active AND no LLM waiter is queued. A
sustained stream of text can therefore starve a queued render — accepted
by design (renders are lazy paint; text is a player waiting) and
observable via ``stats()``.

Implementation is a future-queue with fully SYNCHRONOUS wake/release
(atomic on the event loop, and a release in a ``finally`` can never be
interrupted by cancellation — the failure mode that rules out
``asyncio.Condition`` here). Granted-then-cancelled waiters hand their
slot back; cancelled-while-queued waiters are removed eagerly so a ghost
entry in the LLM queue can never block exclusives via the queue-empty
check.

asyncio-only because Daydream is one Python process with one event loop.
flock would be needed only if a second process ever contended for the
GPU; the pattern lives at ~/src/qwen-2.5-localreview/gpu_lock.py for
that day."""

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from daydream import config

_active_llm = 0
_active_exclusive = False
_active_bg = 0
BACKGROUND_CAP = 1
# Each queue entry is (future, enqueued_monotonic).
_llm_q: deque[tuple[asyncio.Future, float]] = deque()
_excl_q: deque[tuple[asyncio.Future, float]] = deque()
_bg_q: deque[tuple[asyncio.Future, float]] = deque()
_max_wait_ms = {"llm": 0, "exclusive": 0, "background": 0}


def _live(q: deque) -> bool:
    return any(not f.done() for f, _ in q)


def _wake() -> None:
    """Grant every currently-admissible waiter. Synchronous: runs to
    completion on the event loop, so check+grant is atomic."""
    global _active_llm, _active_exclusive, _active_bg
    while _llm_q and not _active_exclusive and _active_llm < config.llm_concurrency():
        fut, _ = _llm_q.popleft()
        if not fut.done():  # skip futures cancelled while queued
            _active_llm += 1  # grant BEFORE set_result
            fut.set_result(None)
    while (
        _excl_q and not _active_exclusive and _active_llm == 0
        and _active_bg == 0 and not _llm_q
    ):
        fut, _ = _excl_q.popleft()  # text priority: llm queue must be empty
        if not fut.done():
            _active_exclusive = True
            fut.set_result(None)
    # Background: lowest priority. Never past a queued render or a queued
    # player call, never alongside a render, at most BACKGROUND_CAP at once.
    while (
        _bg_q and not _active_exclusive and _active_bg < BACKGROUND_CAP
        and not _live(_excl_q) and not _live(_llm_q)
    ):
        fut, _ = _bg_q.popleft()
        if not fut.done():
            _active_bg += 1
            fut.set_result(None)


def _release(kind: str) -> None:
    """Synchronous release + wake — safe inside a ``finally`` even while
    the releasing task is itself being cancelled."""
    global _active_llm, _active_exclusive, _active_bg
    if kind == "llm":
        _active_llm -= 1
    elif kind == "background":
        _active_bg -= 1
    else:
        _active_exclusive = False
    _wake()


@asynccontextmanager
async def acquire(kind: str = "exclusive") -> AsyncIterator[None]:
    """Async context manager for gated GPU access.

    Usage:
        async with arbiter.acquire("llm"):        # shared text slot
            await call_llm()
        async with arbiter.acquire():             # exclusive (image gen)
            await call_image_gen()
    """
    if kind not in ("llm", "exclusive", "background"):
        raise ValueError(f"unknown arbiter kind {kind!r}")
    q = {"llm": _llm_q, "exclusive": _excl_q, "background": _bg_q}[kind]
    t0 = time.monotonic()
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    q.append((fut, t0))
    _wake()  # grants immediately when admissible
    try:
        await fut
    except asyncio.CancelledError:
        if fut.done() and not fut.cancelled():
            # Granted between the releaser's set_result and our resume,
            # then cancelled: hand the slot back or it leaks forever.
            _release(kind)
        else:
            # Still queued: drop the ghost entry (a lingering done-future
            # in _llm_q would spuriously block exclusives via `not _llm_q`).
            try:
                q.remove((fut, t0))
            except ValueError:
                pass
        raise
    waited_ms = int((time.monotonic() - t0) * 1000)
    if waited_ms > _max_wait_ms[kind]:
        _max_wait_ms[kind] = waited_ms
    try:
        yield
    finally:
        _release(kind)


def is_locked() -> bool:
    """Whether ANY gate activity is in flight (back-compat name: for tests
    and `bin/game status`, 'the GPU is busy')."""
    return _active_exclusive or _active_llm > 0 or _active_bg > 0


def exclusive_held() -> bool:
    """Whether an exclusive (image-gen) holder is active — the invariant
    the image tripwire asserts."""
    return _active_exclusive


def stats() -> dict:
    """Gate observability for /status/arbiter and the swarm harness."""
    now = time.monotonic()
    oldest_excl_wait_ms = 0
    live_excl = [(f, t) for f, t in _excl_q if not f.done()]
    if live_excl:
        oldest_excl_wait_ms = int((now - live_excl[0][1]) * 1000)
    return {
        "active_llm": _active_llm,
        "active_exclusive": _active_exclusive,
        "waiting_llm": sum(1 for f, _ in _llm_q if not f.done()),
        "waiting_exclusive": len(live_excl),
        "oldest_exclusive_wait_ms": oldest_excl_wait_ms,
        "max_wait_ms_llm": _max_wait_ms["llm"],
        "max_wait_ms_exclusive": _max_wait_ms["exclusive"],
        "llm_concurrency": config.llm_concurrency(),
        "active_background": _active_bg,
        "waiting_background": sum(1 for f, _ in _bg_q if not f.done()),
    }


def reset() -> None:
    """Test helper: drop all gate state so each test starts fresh.
    Not for production paths."""
    global _active_llm, _active_exclusive, _active_bg
    _active_llm = 0
    _active_exclusive = False
    _active_bg = 0
    _llm_q.clear()
    _excl_q.clear()
    _bg_q.clear()
    for k in _max_wait_ms:
        _max_wait_ms[k] = 0
