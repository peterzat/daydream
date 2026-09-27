"""The GPU gate across processes (SPEC 2026-09-27 criterion 21): a render in
one daydream process never overlaps an LLM call or a render in another, and
a cancelled waiter never leaves the lock held. Real OS processes contend on a
temporary lock file."""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from daydream.gpu import arbiter

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent

HOLDER = """
import asyncio, sys, time
sys.path.insert(0, {root!r})
from daydream.gpu import arbiter
async def main():
    async with arbiter.acquire({kind!r}):
        print("held", time.monotonic(), flush=True)
        await asyncio.sleep({hold})
    print("released", time.monotonic(), flush=True)
asyncio.run(main())
"""


def _holder(lock: Path, kind: str, hold: float) -> subprocess.Popen:
    env = {**os.environ, "DAYDREAM_GPU_LOCK": str(lock)}
    p = subprocess.Popen([sys.executable, "-c", HOLDER.format(root=str(ROOT), kind=kind, hold=hold)],
                         env=env, stdout=subprocess.PIPE, text=True)
    line = p.stdout.readline()
    assert line.startswith("held"), line
    return p


@pytest.fixture
def lock(tmp_path, monkeypatch):
    path = tmp_path / "gpu.lock"
    monkeypatch.setenv("DAYDREAM_GPU_LOCK", str(path))
    arbiter.reset()
    yield path
    arbiter.reset()


async def test_an_llm_call_waits_for_another_process_render(lock):
    other = _holder(lock, "exclusive", 0.8)
    t0 = time.monotonic()
    async with arbiter.acquire("llm"):
        waited = time.monotonic() - t0
    other.wait(timeout=10)
    assert waited >= 0.5


async def test_a_render_waits_for_another_process_llm_call(lock):
    other = _holder(lock, "llm", 0.8)
    t0 = time.monotonic()
    async with arbiter.acquire("exclusive"):
        waited = time.monotonic() - t0
    other.wait(timeout=10)
    assert waited >= 0.5


async def test_llm_calls_in_two_processes_run_together(lock):
    other = _holder(lock, "llm", 1.0)
    t0 = time.monotonic()
    async with arbiter.acquire("llm"):
        waited = time.monotonic() - t0
    other.wait(timeout=10)
    assert waited < 0.3


async def test_a_render_gives_up_rather_than_stall_text(lock, monkeypatch):
    monkeypatch.setattr(arbiter, "XP_RENDER_WAIT_S", 0.3)
    other = _holder(lock, "llm", 2.0)
    with pytest.raises(arbiter.GpuBusyElsewhere):
        async with arbiter.acquire("exclusive"):
            pass
    # Its in-process slot went back: this process's text is not stuck.
    async with arbiter.acquire("llm"):
        pass
    other.kill()


async def test_a_cancelled_waiter_leaves_the_lock_free(lock):
    other = _holder(lock, "exclusive", 0.6)
    task = asyncio.create_task(_render_once())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    other.wait(timeout=10)
    # A third process gets the exclusive lock at once: nobody kept it.
    t0 = time.monotonic()
    third = _holder(lock, "exclusive", 0.0)
    third.wait(timeout=10)
    assert time.monotonic() - t0 < 2.0
    assert not arbiter.is_locked()


async def _render_once():
    async with arbiter.acquire("exclusive"):
        await asyncio.sleep(0)


def test_without_a_lock_path_there_is_no_cross_process_layer(monkeypatch):
    from daydream import config

    monkeypatch.setenv("DAYDREAM_GPU_LOCK", "")
    assert config.gpu_lock_path() is None
    monkeypatch.delenv("DAYDREAM_GPU_LOCK")
    monkeypatch.setattr(config, "PROD_GPU_LOCK", Path("/nonexistent/gpu.lock"))
    assert config.gpu_lock_path() is None
