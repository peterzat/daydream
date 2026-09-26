"""Wall-clock time for the living world (SPEC 2026-09-26 criterion 4).

Distinct from `daydream.clock`, which counts COMMANDS (the world turn that
drives fuses, daemons, fuel). This module owns real time: the one `now()`
every story surface reads, so tests can pin or advance it with a fake clock
(`set_fake_now`, or `DAYDREAM_FAKE_NOW=<iso>` for a subprocess).

Story state that depends on time is evaluated against `now()` lazily where it
can be (gossip spread, arc deadlines), and processed by the catch-up pass
where it must fire exactly once (dusk events). See `daydream.village`.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

_fake_now: datetime | None = None


def _parse(text: str) -> datetime:
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def now() -> datetime:
    """The current instant (timezone-aware UTC unless faked with a zone)."""
    if _fake_now is not None:
        return _fake_now
    env = os.environ.get("DAYDREAM_FAKE_NOW")
    if env:
        try:
            return _parse(env)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def set_fake_now(value: datetime | str | None) -> None:
    """Pin the clock (tests, walkthrough `clock` steps). None unpins."""
    global _fake_now
    if value is None:
        _fake_now = None
        return
    _fake_now = _parse(value) if isinstance(value, str) else value
    if _fake_now.tzinfo is None:
        _fake_now = _fake_now.replace(tzinfo=timezone.utc)


def advance(**delta) -> datetime:
    """Move a pinned clock forward (`advance(minutes=30)`); pins it first at
    the real now if it was not pinned."""
    set_fake_now(now() + timedelta(**delta))
    return now()


def iso(dt: datetime | None = None) -> str:
    """ISO-8601 UTC with seconds, the one timestamp format story state uses."""
    dt = dt or now()
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse(text: str) -> datetime:
    """Parse a stored `iso()` timestamp back to an aware datetime."""
    return _parse(text)
