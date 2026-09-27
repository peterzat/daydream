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

Across processes (SPEC 2026-09-27 criterion 21): dev, prod, and a tier_long
run each have their own in-process gate, so the same shared/exclusive rule is
mirrored onto an flock on one lock file both users can open
(`config.gpu_lock_path()`, set up by ops/install-prod.sh):

- **Shared lock.** Held while THIS process has any LLM or background call in
  flight (refcounted, taken on 0 -> 1 and dropped on -> 0).
- **Exclusive lock.** Held for a render. In-process admission already
  guarantees a process never holds its shared lock while asking for the
  exclusive one, so it cannot deadlock against itself.
- **Cancellable.** Taken by LOCK_NB polling, so a cancelled waiter never ends
  up holding the lock.
- **Bounded for renders.** A render that cannot get the exclusive lock within
  XP_RENDER_WAIT_S gives up (GpuBusyElsewhere): its in-process slot would
  otherwise stall this process's own text calls behind it. Renders are lazy
  paint; the caller keeps the placeholder and paints later.

No lock path means no cross-process layer (tests, CI, a box without prod)."""

import asyncio
import fcntl
import os
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


# ---- the cross-process layer (flock) ------------------------------------------

XP_POLL_S = 0.05
XP_RENDER_WAIT_S = 20.0
_xp_fd: int | None = None
_xp_fd_path: str | None = None
_xp_shared = 0
_xp_mutex: asyncio.Lock | None = None


class GpuBusyElsewhere(RuntimeError):
    """Another daydream process held the GPU too long for this render."""


def _xp_file() -> int | None:
    global _xp_fd, _xp_fd_path
    path = config.gpu_lock_path()
    if path is None:
        return None
    if _xp_fd is None or _xp_fd_path != str(path):
        if _xp_fd is not None:
            os.close(_xp_fd)
        _xp_fd = os.open(str(path), os.O_RDONLY | os.O_CREAT, 0o660)
        _xp_fd_path = str(path)
    return _xp_fd


async def _xp_poll(fd: int, op: int, timeout: float | None) -> None:
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, op | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if deadline is not None and time.monotonic() >= deadline:
                raise GpuBusyElsewhere("another daydream process holds the GPU") from None
            await asyncio.sleep(XP_POLL_S)


async def _xp_enter(kind: str) -> None:
    global _xp_shared, _xp_mutex
    fd = _xp_file()
    if fd is None:
        return
    if kind == "exclusive":
        await _xp_poll(fd, fcntl.LOCK_EX, XP_RENDER_WAIT_S)
        return
    if _xp_mutex is None:
        _xp_mutex = asyncio.Lock()
    async with _xp_mutex:
        if _xp_shared == 0:
            await _xp_poll(fd, fcntl.LOCK_SH, None)
        _xp_shared += 1


def _xp_exit(kind: str) -> None:
    """Synchronous (flock unlock never blocks), so safe in a `finally`."""
    global _xp_shared
    if _xp_fd is None or config.gpu_lock_path() is None:
        return
    if kind == "exclusive":
        fcntl.flock(_xp_fd, fcntl.LOCK_UN)
        return
    _xp_shared = max(0, _xp_shared - 1)
    if _xp_shared == 0:
        fcntl.flock(_xp_fd, fcntl.LOCK_UN)


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
    # In-process slot granted; now the same rule across processes. On any
    # failure here (cancelled, or a render timing out) the in-process slot
    # goes back before the exception leaves.
    try:
        await _xp_enter(kind)
    except BaseException:
        _release(kind)
        raise
    waited_ms = int((time.monotonic() - t0) * 1000)
    if waited_ms > _max_wait_ms[kind]:
        _max_wait_ms[kind] = waited_ms
    try:
        yield
    finally:
        _xp_exit(kind)
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
    global _active_llm, _active_exclusive, _active_bg, _xp_fd, _xp_fd_path, _xp_shared, _xp_mutex
    if _xp_fd is not None:
        try:
            fcntl.flock(_xp_fd, fcntl.LOCK_UN)
            os.close(_xp_fd)
        except OSError:
            pass
    _xp_fd = _xp_fd_path = None
    _xp_shared = 0
    _xp_mutex = None
    _active_llm = 0
    _active_exclusive = False
    _active_bg = 0
    _llm_q.clear()
    _excl_q.clear()
    _bg_q.clear()
    for k in _max_wait_ms:
        _max_wait_ms[k] = 0
