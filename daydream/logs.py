"""The app's own log lines (first prod evening, 2026-09-28: the journal held
only anonymous WebSocket open/close lines, because nothing configured the
`daydream` loggers and Python drops INFO by default).

`configure()` runs in the server lifespan: one handler on the `daydream`
logger, at `DAYDREAM_LOG_LEVEL` (default INFO), writing to stderr, where
systemd's journal keeps it in prod (`bin/game prod logs`) and the run-dir log
file keeps it in dev (`bin/game logs`). Under systemd the journal stamps each
line, so the format carries no time of its own there.

What a line may say: account usernames, dreamer names, ids, rooms, counts,
timings, outcomes. Never a password, a session token, an invite slug, or
what a player typed (that lives, private, in the world's input log)."""

from __future__ import annotations

import logging
import os
import sys


class _Stderr(logging.StreamHandler):
    """Writes to whatever sys.stderr is at the moment of writing, so a test
    runner that swaps stderr per test never leaves the handler holding a
    closed stream."""

    def __init__(self) -> None:
        super().__init__(sys.stderr)

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, value) -> None:
        pass


def configure() -> None:
    """Idempotent: a second lifespan (tests, a world swap) adds nothing."""
    level = logging.getLevelName(os.environ.get("DAYDREAM_LOG_LEVEL", "INFO").upper())
    if not isinstance(level, int):
        level = logging.INFO
    root = logging.getLogger("daydream")
    root.setLevel(level)
    if any(isinstance(h, _Stderr) for h in root.handlers):
        return
    handler = _Stderr()
    stamp = "" if os.environ.get("JOURNAL_STREAM") else "%(asctime)s "
    handler.setFormatter(logging.Formatter(stamp + "%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
