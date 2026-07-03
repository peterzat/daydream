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


# ---- arbiter v2: shared llm / exclusive image, text priority --------------


@pytest.mark.asyncio
async def test_llm_slots_run_concurrently_up_to_cap(monkeypatch):
    """kind="llm" admits up to config.llm_concurrency() at once; the
    cap+1th waits."""
    monkeypatch.setenv("DAYDREAM_LLM_CONCURRENCY", "3")
    in_flight = 0
    max_concurrent = 0

    async def llm_task():
        nonlocal in_flight, max_concurrent
        async with arbiter.acquire("llm"):
            in_flight += 1
            max_concurrent = max(max_concurrent, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1

    await asyncio.gather(*[llm_task() for _ in range(6)])
    assert max_concurrent == 3, f"expected cap 3, saw {max_concurrent}"


@pytest.mark.asyncio
async def test_exclusive_blocks_llm_and_vice_versa():
    """Mutual exclusion both directions: an active exclusive holds out an
    llm arrival; an active llm holds out an exclusive arrival."""
    order: list[str] = []

    async def exclusive_then_llm():
        async def excl():
            async with arbiter.acquire():
                order.append("excl-in")
                await asyncio.sleep(0.03)
                order.append("excl-out")

        async def llm():
            await asyncio.sleep(0.01)
            async with arbiter.acquire("llm"):
                order.append("llm-in")

        await asyncio.gather(excl(), llm())

    await exclusive_then_llm()
    assert order == ["excl-in", "excl-out", "llm-in"]

    arbiter.reset()
    order.clear()

    async def llm_then_exclusive():
        async def llm():
            async with arbiter.acquire("llm"):
                order.append("llm-in")
                await asyncio.sleep(0.03)
                order.append("llm-out")

        async def excl():
            await asyncio.sleep(0.01)
            async with arbiter.acquire():
                order.append("excl-in")

        await asyncio.gather(llm(), excl())

    await llm_then_exclusive()
    assert order == ["llm-in", "llm-out", "excl-in"]


@pytest.mark.asyncio
async def test_text_priority_llm_barges_past_queued_exclusive():
    """A queued llm waiter is admitted before a queued exclusive, even if
    the exclusive queued first (renders are lazy paint; text is a player
    waiting)."""
    order: list[str] = []

    async def excl_holder():
        async with arbiter.acquire():
            order.append("excl1-in")
            await asyncio.sleep(0.03)

    async def excl_waiter():
        await asyncio.sleep(0.005)  # queues while excl1 holds
        async with arbiter.acquire():
            order.append("excl2-in")

    async def llm_waiter():
        await asyncio.sleep(0.015)  # queues AFTER excl2
        async with arbiter.acquire("llm"):
            order.append("llm-in")

    await asyncio.gather(excl_holder(), excl_waiter(), llm_waiter())
    assert order == ["excl1-in", "llm-in", "excl2-in"]


@pytest.mark.asyncio
async def test_cancelled_while_queued_does_not_wedge_exclusives():
    """A cancelled queued llm waiter is removed eagerly; a ghost entry in
    the llm queue must not block exclusives via the queue-empty check."""

    async def excl_holder():
        async with arbiter.acquire():
            await asyncio.sleep(0.03)

    holder = asyncio.create_task(excl_holder())
    await asyncio.sleep(0.005)

    async def llm_waiter():
        async with arbiter.acquire("llm"):
            pass

    waiter = asyncio.create_task(llm_waiter())
    await asyncio.sleep(0.005)  # llm now queued behind the exclusive
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    async def excl_after():
        async with arbiter.acquire():
            return True

    await holder
    assert await asyncio.wait_for(excl_after(), timeout=1.0)
    assert not arbiter.is_locked()


@pytest.mark.asyncio
async def test_granted_then_cancelled_returns_the_slot():
    """A waiter cancelled after its future resolved (granted) but before it
    resumed must hand the slot back, or the gate leaks closed forever."""

    async def excl_holder():
        async with arbiter.acquire():
            await asyncio.sleep(0.02)

    holder = asyncio.create_task(excl_holder())
    await asyncio.sleep(0.005)

    async def llm_waiter():
        async with arbiter.acquire("llm"):
            await asyncio.sleep(1.0)  # never reached if cancelled at grant

    waiter = asyncio.create_task(llm_waiter())
    await asyncio.sleep(0.005)  # queued behind the exclusive
    await holder  # release grants the llm future synchronously...
    waiter.cancel()  # ...and we cancel before the waiter task resumes
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert not arbiter.is_locked(), "granted-then-cancelled leaked its slot"

    async def excl_after():
        async with arbiter.acquire():
            return True

    assert await asyncio.wait_for(excl_after(), timeout=1.0)


@pytest.mark.asyncio
async def test_stats_shape_and_counters():
    """stats() exposes actives, waiting counts, and max-wait buckets."""
    idle = arbiter.stats()
    assert idle["active_llm"] == 0
    assert idle["active_exclusive"] is False
    assert idle["waiting_llm"] == 0
    assert idle["waiting_exclusive"] == 0
    assert idle["llm_concurrency"] >= 1

    async with arbiter.acquire("llm"):
        busy = arbiter.stats()
        assert busy["active_llm"] == 1
        assert arbiter.is_locked()
        assert not arbiter.exclusive_held()

    async with arbiter.acquire():
        assert arbiter.exclusive_held()
        assert arbiter.stats()["active_exclusive"] is True

    assert arbiter.stats()["max_wait_ms_llm"] >= 0


@pytest.mark.asyncio
async def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        async with arbiter.acquire("video"):
            pass


@pytest.mark.tier_medium
def test_status_arbiter_endpoint():
    """`/status/arbiter` returns the one-line gate summary (always
    non-empty, unlike /status/drift's silent zero state)."""
    from fastapi.testclient import TestClient

    from daydream.server import app

    with TestClient(app) as client:
        r = client.get("/status/arbiter")
        assert r.status_code == 200
        assert r.text.startswith("arbiter: llm 0/")
        assert "image idle" in r.text
        assert "events dropped 0" in r.text
