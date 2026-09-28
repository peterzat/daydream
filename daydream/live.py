"""Transient frames to one player's open page (beta rehearsal 2026-09-28).

Some things are worth telling a player at once and never worth logging: an
improvised reply is on its way (three to eight seconds of silence read as a
lost line), a seed is composing. The WebSocket layer registers a sender for
each connected player's toon; engine code that is about to wait on a model
calls `notify`. No sender (a walkthrough, a tool, a test) means nothing is
sent; a failed send is ignored. Never an event, never persisted.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

_senders: dict[str, Callable[[dict], Awaitable[None]]] = {}


def register(toon_id: str, send: Callable[[dict], Awaitable[None]]) -> None:
    _senders[toon_id] = send


def unregister(toon_id: str, send: Callable[[dict], Awaitable[None]] | None = None) -> None:
    if send is None or _senders.get(toon_id) is send:
        _senders.pop(toon_id, None)


async def notify(toon_id: str | None, frame: dict) -> None:
    """Send a transient frame to this player's page, if one is open."""
    if not toon_id:
        return
    send = _senders.get(toon_id)
    if send is None:
        return
    try:
        await send(frame)
    except Exception:  # a closed socket; the broadcast loop handles the rest
        logger.debug("live frame not sent", exc_info=True)


async def thinking(toon_id: str | None, who: str | None = None, text: str | None = None) -> None:
    """"<who> considers..." while a reply composes, or a bespoke line."""
    await notify(toon_id, {"kind": "thinking", "who": who, "text": text})
