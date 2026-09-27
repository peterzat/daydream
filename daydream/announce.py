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


def main(argv: list[str] | None = None) -> int:
    """`python -m daydream.announce send TEXT`: leave a line for the running
    server to tell everyone. `bin/game prod sleep` runs this as the service
    user; the operator never writes into the data dir."""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "send" or not args[1].strip():
        print("usage: python -m daydream.announce send TEXT", file=sys.stderr)
        return 2
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"text": args[1].strip()[:MAX_CHARS]}))
    tmp.replace(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
