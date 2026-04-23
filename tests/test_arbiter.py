"""GPU arbiter contract: acquire/release, serialization under contention,
exception safety, double-acquire blocks. Pure-asyncio, no GPU."""

import asyncio

import pytest

from daydream.gpu import arbiter

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_arbiter():
    arbiter.reset()
    yield
    arbiter.reset()


@pytest.mark.asyncio
async def test_acquire_releases_in_context_manager():
    assert not arbiter.is_locked()
    async with arbiter.acquire():
        assert arbiter.is_locked()
    assert not arbiter.is_locked()


@pytest.mark.asyncio
async def test_double_acquire_serializes():
    """A second acquirer must wait until the first releases."""
    order: list[str] = []

    async def first():
        async with arbiter.acquire():
            order.append("first-in")
            await asyncio.sleep(0.05)
            order.append("first-out")

    async def second():
        await asyncio.sleep(0.01)  # ensure first acquires the lock first
        async with arbiter.acquire():
            order.append("second-in")

    await asyncio.gather(first(), second())
    assert order == ["first-in", "first-out", "second-in"]


@pytest.mark.asyncio
async def test_release_on_exception():
    """If the body raises, the lock must still release."""
    with pytest.raises(ValueError):
        async with arbiter.acquire():
            assert arbiter.is_locked()
            raise ValueError("boom in critical section")
    assert not arbiter.is_locked()


@pytest.mark.asyncio
async def test_serializes_under_contention():
    """N concurrent acquirers run serially, never overlap inside the lock."""
    in_critical = 0
    max_concurrent = 0

    async def task():
        nonlocal in_critical, max_concurrent
        async with arbiter.acquire():
            in_critical += 1
            max_concurrent = max(max_concurrent, in_critical)
            await asyncio.sleep(0.005)
            in_critical -= 1

    await asyncio.gather(*[task() for _ in range(8)])
    assert max_concurrent == 1, f"arbiter let {max_concurrent} tasks into the critical section"


@pytest.mark.asyncio
async def test_reset_drops_singleton():
    """reset() returns the module to a fresh state so tests don't share locks."""
    async with arbiter.acquire():
        pass
    arbiter.reset()
    assert not arbiter.is_locked()
    async with arbiter.acquire():
        assert arbiter.is_locked()


@pytest.mark.asyncio
async def test_is_locked_before_init():
    """is_locked is False when the singleton has not been initialized."""
    arbiter.reset()
    assert not arbiter.is_locked()
