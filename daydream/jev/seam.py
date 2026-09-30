"""The seam every Jev surface goes through: the local path, with Jev beside
it (docs/EXTERNAL.md).

    value = await seam.decide("judge", local=..., remote=..., agree=..., ...)

Off (no key reachable: settings.enabled), `local()` runs alone: the game is
exactly what it is without Jev. On, both run at once, and one rule chooses
what serves:

- `combine(local_value, answer)`: a rule over both answers (the judge);
- otherwise Jev's answer serves when its confidence reaches `min_conf`,
  and the local answer when it doesn't, or when Jev is silent.

Every decision made on is one ledger row (daydream/jev/ledger.py): both
answers, which served, their agreement, Jev's confidence, the dreamer it
was for, and what it was about, so a disagreement can be read later."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from daydream.jev import ledger, settings

logger = logging.getLogger(__name__)


@dataclass
class Answer:
    value: Any
    confidence: float
    detail: dict = field(default_factory=dict)


async def _safe(fn: Callable[[], Awaitable[Any]]):
    try:
        return await fn()
    except Exception:  # noqa: BLE001 - Jev never breaks play
        logger.exception("jev seam: the Jev path raised")
        return None


async def decide(surface: str, *, local: Callable[[], Awaitable[Any]],
                 remote: Callable[[], Awaitable[Answer | None]],
                 agree: Callable[[Any, Any], bool], about: dict, toon: str | None = None,
                 show: Callable[[Any], Any] = lambda v: v,
                 combine: Callable[[Any, Answer], Any] | None = None,
                 min_conf: float = 0.8) -> Any:
    if not settings.enabled():
        return await local()
    value, answer = await asyncio.gather(local(), _safe(remote))
    if answer is None:
        served, by = value, "local"
    elif combine is not None:
        served, by = combine(value, answer), "combined"
    elif answer.confidence >= min_conf:
        served, by = answer.value, "jev"
    else:
        served, by = value, "local"
    row: dict = {"surface": surface, "toon": toon, "served": by, "about": about,
                 "local": show(value), "served_value": show(served)}
    if answer is None:
        row.update(jev=None, agree=None)
    else:
        try:
            same = bool(agree(value, answer.value))
        except Exception:  # noqa: BLE001
            same = None
        row.update(jev=show(answer.value), confidence=round(answer.confidence, 4),
                   detail=answer.detail, agree=same)
    ledger.record_decision(row)
    return served
