"""NPC drift loop: periodic soft-narrate emission so the world feels
inhabited even when the player is somewhere else.

Single asyncio.Task started by `start_drift_loop()` from the FastAPI
lifespan. Each tick picks one NPC at random, draws a drift line from
the NPC's pre-canned pool, and emits a `narrate` event addressed to
the NPC's current room. The existing WS broadcast machinery routes
the narrate to in-room subscribers; out-of-room subscribers are
filtered.

v0 design constraints (load-bearing — see SPEC 2026-05-07
"NPC drift loop"):

- Pre-canned text. NO LLM call. The drift loop never calls
  `daydream.gpu.arbiter.acquire()`, so player-input LLM calls and
  drift never contend for the GPU. The BACKLOG `npc-drift-loop`
  entry's "yield arbiter on player input" requirement is vacuously
  satisfied. When a future spec wants LLM-driven drift, the arbiter-
  yielding question reactivates.
- Single tick type (narrate emission). Weather and in-world
  calendar tick types from the BACKLOG entry are out of scope for
  v0; the schema doesn't model them yet.
- Single global cadence. All NPCs drift at the same interval.
  Per-NPC cadence overrides are out of scope.
- Pool location: a constant dict in this module. The cheapest
  authoring path for v0; if pools grow or need per-NPC ownership,
  migrate to a `toons.drift_lines_json` column or per-NPC
  `skills/<npc>-drift.json` files in a future spec.

Cadence: env-overridable. Default 300 s (5 min) when no WS
subscribers; 1800 s (30 min) when >=1 subscriber. Decision is made
at each wake-up, so a connection that arrives mid-sleep takes effect
on the next iteration.

Disable in tests via `DAYDREAM_DRIFT_ENABLED=0` (set in
`tests/conftest.py`); the default in production is `1`."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

from daydream import db, events

logger = logging.getLogger(__name__)


# Per-NPC drift pools. Each pool is a list of pre-canned narrate
# strings in the NPC's voice. All pools have >=3 entries; tests
# pin this floor (criterion 4 pool-quality check).
_DRIFT_POOLS: dict[str, list[str]] = {
    "t-rook": [
        "Rook hums something low and slow under the bellows.",
        "Rook brushes soot from the anvil's edge and lets it settle.",
        "Rook turns a bent nail between two fingers, considering it.",
        "A small bell on the forge door rocks once, gently, in the warm air.",
    ],
    "t-iris": [
        "Iris turns a postcard to the slanting light, smiling at something only she can see.",
        "Iris reads a sentence aloud to herself, then marks her page with a strip of pale ribbon.",
        "A trunk creaks faintly as Iris sets a small stack of letters atop it.",
        "Iris pauses with a hand on a tin of buttons, listening to the rafters.",
    ],
}


_DEFAULT_IDLE_SECONDS = 300.0
_DEFAULT_BUSY_SECONDS = 1800.0


def _is_enabled() -> bool:
    """Drift is on by default in production; tests opt out via
    DAYDREAM_DRIFT_ENABLED=0."""
    return os.environ.get("DAYDREAM_DRIFT_ENABLED", "1") != "0"


def _compute_next_interval(subscriber_count: int) -> float:
    """Cadence rule. Pure function: tests can call with synthetic
    subscriber counts to verify both branches."""
    if subscriber_count >= 1:
        return float(os.environ.get("DAYDREAM_DRIFT_BUSY_SECONDS", _DEFAULT_BUSY_SECONDS))
    return float(os.environ.get("DAYDREAM_DRIFT_IDLE_SECONDS", _DEFAULT_IDLE_SECONDS))


def _list_npcs() -> list[dict[str, Any]]:
    """Return all NPCs (toons with is_human_controlled=0, not kicked)
    with the fields the drift loop needs. Ordered by slot for
    deterministic iteration in tests; random selection happens
    in `_tick` after this returns."""
    rows = (
        db.get_conn()
        .execute(
            "SELECT id, current_room_id FROM toons "
            "WHERE is_human_controlled = 0 AND kicked_at IS NULL "
            "ORDER BY slot"
        )
        .fetchall()
    )
    return [{"id": r["id"], "current_room_id": r["current_room_id"]} for r in rows]


def _tick(rng: random.Random | None = None) -> bool:
    """One drift step. Returns True if a narrate was emitted, False
    if the tick was a no-op (no NPCs, all pools empty, etc.).

    `rng` injection lets tests seed the random selection deterministically."""
    rng = rng if rng is not None else random
    npcs = _list_npcs()
    # Filter to NPCs with non-empty pools; skip empty-pool entries
    # silently rather than emitting nothing.
    eligible = [n for n in npcs if _DRIFT_POOLS.get(n["id"])]
    if not eligible:
        return False
    chosen = rng.choice(eligible)
    line = rng.choice(_DRIFT_POOLS[chosen["id"]])
    events.append(
        actor_type="system",
        actor_id=None,
        kind="narrate",
        payload={"text": line},
        room_id=chosen["current_room_id"],
    )
    return True


async def _drift_loop() -> None:
    """The long-running task body. Sleeps for the cadence-appropriate
    interval, wakes, fires one tick, repeats. Per-tick exceptions are
    logged and swallowed so one bad tick does not kill the loop;
    `asyncio.CancelledError` propagates so cancellation exits cleanly."""
    while True:
        interval = _compute_next_interval(events.subscriber_count())
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        try:
            _tick()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("drift tick failed: %s", e, exc_info=True)


def start_drift_loop() -> asyncio.Task | None:
    """Spawn the drift task if enabled. Returns the task handle (for
    `stop_drift_loop`) or None if disabled. Safe to call once per
    FastAPI lifespan startup."""
    if not _is_enabled():
        return None
    return asyncio.create_task(_drift_loop(), name="daydream-drift")


async def stop_drift_loop(handle: asyncio.Task | None) -> None:
    """Cancel the drift task and await its cleanup. No-op if `handle`
    is None (drift was disabled at startup). Safe to call from the
    FastAPI lifespan shutdown branch even if the task has already
    completed for another reason."""
    if handle is None or handle.done():
        return
    handle.cancel()
    try:
        await handle
    except asyncio.CancelledError:
        pass
