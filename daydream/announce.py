"""One line to everyone in the village, from the shell (SPEC 2026-09-27:
`bin/game prod sleep`'s warning before the lamps go out).

There is no web endpoint for this: the web can play, only the shell governs
(criterion 4). The operator's CLI writes `announce.json` ({"text": ...}) into
the data dir; this task notices it within a few seconds, tells every
connected player with a world-scoped narrate, and removes the file."""

from __future__ import annotations

import asyncio
import json
import logging

from daydream import config, events

logger = logging.getLogger(__name__)

POLL_SECONDS = 3.0
MAX_CHARS = 300
_task: asyncio.Task | None = None


def path():
    return config.data_dir() / "announce.json"


def check_once() -> str | None:
    """Deliver a pending announcement, if any; return its text."""
    p = path()
    if not p.exists():
        return None
    try:
        text = json.loads(p.read_text()).get("text")
    except (OSError, ValueError, AttributeError):
        text = None
    try:
        p.unlink()
    except OSError:
        pass
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()[:MAX_CHARS]
    # room_id None: world-scoped, so every connected player's room filter passes it.
    events.append("system", None, "narrate", {"text": text, "to": "everyone"}, room_id=None)
    return text


async def _loop() -> None:
    while True:
        try:
            check_once()
        except Exception:  # an announcement must never take the server down
            logger.exception("announce: delivery failed")
        await asyncio.sleep(POLL_SECONDS)


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="daydream-announce")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
        _task = None
