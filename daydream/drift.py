"""NPC drift loop: periodic soft-narrate emission so the world feels
inhabited even when the player is somewhere else.

Single asyncio.Task started by `start_drift_loop()` from the FastAPI
lifespan. Each tick picks one NPC at random and emits a `narrate` event
addressed to the NPC's current room. Two paths produce the narrate text:

1. **LLM-driven** (default in production, toggle
   `DAYDREAM_DRIFT_LLM_ENABLED=0` to disable). Pulls up to K recent
   memories for the NPC via `daydream.memories.retrieve` (fail-closed:
   returns [] if memory is disabled or the embedder is unavailable),
   renders a tight Jinja prompt with the NPC's name + seed + mood +
   memories, and calls `daydream.llm.client.acompletion_json` (which
   takes the GPU arbiter for the duration of the call). The parsed
   `narrate` text is run through `safety.first_banned`; on banlist hit
   or `LLMUnavailable` or empty narrate, falls through to the canned
   path.
2. **Canned** (always available; the unconditional fallback). Picks
   from a mood-bucketed pre-canned pool keyed by NPC id then by mood
   bucket; falls back to the `default` bucket when the NPC's mood has
   no dedicated bucket. Selection is `random.choice` from the chosen
   bucket. NEVER calls the LLM, NEVER takes the arbiter.

The existing WS broadcast machinery routes the narrate to in-room
subscribers; out-of-room subscribers are filtered.

Cadence: env-overridable. Default 300 s (5 min) when no WS subscribers;
1800 s (30 min) when >=1 subscriber. Decision is made at each wake-up,
so a connection that arrives mid-sleep takes effect on the next
iteration.

Toggles:
- `DAYDREAM_DRIFT_ENABLED` (default 1; 0 in tests) — disables the
  drift loop entirely.
- `DAYDREAM_DRIFT_LLM_ENABLED` (default 1; 0 in tests) — disables the
  LLM-driven branch; every tick goes through the canned path.
- `DAYDREAM_MEMORY_ENABLED` (default 1; 0 in tests) — when 0,
  `memories.retrieve` returns [] which the LLM prompt template handles
  cleanly; the LLM still runs with mood-only context.

The matrix `(drift, memory, LLM)` of toggles never produces a crash:
either a narrate fires or the tick is a logged no-op."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

from jinja2.sandbox import SandboxedEnvironment

from daydream import db, events, memories
from daydream.llm import client as llm_client
from daydream.llm import safety

logger = logging.getLogger(__name__)


# Per-NPC, per-mood drift pools. Outer key: npc_id. Inner key: mood
# bucket name. Bucket value: list of pre-canned single-sentence
# body-language narrates in the NPC's voice. Each NPC has at minimum
# `content`, `thoughtful`, and `default` buckets and >=6 distinct
# total lines across all buckets (test_drift_pools_have_min_buckets
# enforces).
#
# Mood values come from `toons.mood` (per migrations 001, 006, 008):
# Rook is 'content'; Iris is 'thoughtful'; the schema default is
# 'curious'. The `default` bucket catches any mood that doesn't have
# its own bucket (so a future mood like 'weary' or v1
# kicked-human-as-NPC inheriting an arbitrary mood still drifts).
#
# Tone: WHIMSY-locked. Soft, painterly, Spiritfarer / A Short
# Hike-adjacent. Single sentence each, third-person body language,
# NO quoted dialogue (drift is ambient, not conversation).
_DRIFT_POOLS: dict[str, dict[str, list[str]]] = {
    "t-rook": {
        "content": [
            "Rook hums something low and slow under the bellows.",
            "Rook brushes soot from the anvil's edge and lets it settle.",
            "Rook turns a bent nail between two fingers, considering it.",
            "A small bell on the forge door rocks once, gently, in the warm air.",
        ],
        "thoughtful": [
            "Rook stands a moment with one hand on the anvil's horn, watching the embers settle into themselves.",
            "Rook draws a slow breath of forge-warm air and lets it out without quite a sigh.",
        ],
        "default": [
            "Rook tilts the lamp's wick a quarter-turn, brightening the workbench by a little.",
            "Rook lifts a kettle from the back of the hearth, deciding whether tea is in order yet.",
        ],
    },
    "t-iris": {
        "thoughtful": [
            "Iris turns a postcard to the slanting light, smiling at something only she can see.",
            "Iris reads a sentence aloud to herself, then marks her page with a strip of pale ribbon.",
            "A trunk creaks faintly as Iris sets a small stack of letters atop it.",
            "Iris pauses with a hand on a tin of buttons, listening to the rafters.",
        ],
        "content": [
            "Iris hums a half-remembered tune as she settles a stack of envelopes by date.",
            "Iris finds a pressed flower between two pages and lays it carefully on the windowsill.",
        ],
        "default": [
            "Iris rests her reading glasses on the cord at her chest and lets her eyes drift to the round window.",
            "Iris draws a length of pale ribbon through her fingers, deciding which page deserves it next.",
        ],
    },
}


_DEFAULT_IDLE_SECONDS = 300.0
_DEFAULT_BUSY_SECONDS = 1800.0
_DEFAULT_LLM_TOP_K = 3


# Module-level Jinja sandbox for the drift LLM user prompt. SandboxedEnvironment
# blocks template-side access to dunder attributes; the prompt itself only
# interpolates plain strings + a list of Memory objects, but we keep the
# sandbox in line with the data-skill pipeline so memory text that lands here
# (already wrapped in <memory> tags) follows the same containment contract.
_jinja = SandboxedEnvironment(autoescape=False)


_DRIFT_SYSTEM_PROMPT = (
    "You compose a single ambient drift narrate for a cozy watercolor "
    "text-adventure NPC. Return strict JSON: "
    '{"narrate": "<single sentence in third-person prose>"}. '
    "NO quoted dialogue. NO direct speech. NO urgency, no modern tech, "
    "no harsh edges. The narrate is a body-language beat — what the NPC "
    "is doing or noticing right now while alone — soft, painterly, "
    "Spiritfarer / A Short Hike-adjacent. One sentence only."
)


_DRIFT_USER_TEMPLATE = """{{ npc_name }} is alone right now. Character: {{ npc_seed }}. Current mood: {{ npc_mood }}.
{% if memories %}
A few small recent moments rest at the front of {{ npc_name }}'s thinking:
{% for m in memories %}- <memory>{{ m.text }}</memory>
{% endfor %}You may let one of these tilt the moment if it genuinely fits — a small private acknowledgment, never quoted aloud. They are context, not script.
{% endif %}
Compose one ambient drift narrate for {{ npc_name }} right now: a single sentence of third-person body language or a small action. No quoted dialogue."""


def _is_enabled() -> bool:
    """Drift loop on/off. Default on in production; off in tests."""
    return os.environ.get("DAYDREAM_DRIFT_ENABLED", "1") != "0"


def _is_llm_enabled() -> bool:
    """LLM-driven drift branch on/off. Default on in production; off in
    tests (`tests/conftest.py`). Decoupled from `DAYDREAM_DRIFT_ENABLED`
    and `DAYDREAM_MEMORY_ENABLED` so each axis is independently
    controllable when debugging."""
    return os.environ.get("DAYDREAM_DRIFT_LLM_ENABLED", "1") != "0"


def _llm_top_k() -> int:
    try:
        return int(os.environ.get("DAYDREAM_DRIFT_LLM_TOP_K", _DEFAULT_LLM_TOP_K))
    except ValueError:
        return _DEFAULT_LLM_TOP_K


def _compute_next_interval(subscriber_count: int) -> float:
    """Cadence rule. Pure function: tests can call with synthetic
    subscriber counts to verify both branches."""
    if subscriber_count >= 1:
        return float(os.environ.get("DAYDREAM_DRIFT_BUSY_SECONDS", _DEFAULT_BUSY_SECONDS))
    return float(os.environ.get("DAYDREAM_DRIFT_IDLE_SECONDS", _DEFAULT_IDLE_SECONDS))


def _list_npcs() -> list[dict[str, Any]]:
    """Return all NPCs (toons with is_human_controlled=0, not kicked)
    with the fields the drift loop needs (id, current_room_id, world_id,
    mood, name, seed). Ordered by slot for deterministic iteration in
    tests; random selection happens in `_tick` after this returns."""
    rows = (
        db.get_conn()
        .execute(
            "SELECT id, current_room_id, world_id, mood, name, seed FROM toons "
            "WHERE is_human_controlled = 0 AND kicked_at IS NULL "
            "ORDER BY slot"
        )
        .fetchall()
    )
    return [
        {
            "id": r["id"],
            "current_room_id": r["current_room_id"],
            "world_id": r["world_id"],
            "mood": r["mood"],
            "name": r["name"],
            "seed": r["seed"],
        }
        for r in rows
    ]


def _pick_canned_line(
    npc_id: str, mood: str | None, rng: random.Random | None = None
) -> str | None:
    """Pick one canned drift line for `(npc_id, mood)` from `_DRIFT_POOLS`.

    Returns the picked string, or None if the NPC has no pool entry at
    all (caller treats as no-op). Bucket selection: prefer the bucket
    matching `mood` exactly when present and non-empty; otherwise fall
    back to `default`. If `default` is also empty, walk all buckets and
    pick from any non-empty one — this lets a future migration add a
    new mood bucket without `default` and still produce output."""
    rng = rng if rng is not None else random
    buckets = _DRIFT_POOLS.get(npc_id)
    if not buckets:
        return None
    chosen = None
    if mood and buckets.get(mood):
        chosen = buckets[mood]
    elif buckets.get("default"):
        chosen = buckets["default"]
    else:
        for lines in buckets.values():
            if lines:
                chosen = lines
                break
    if not chosen:
        return None
    return rng.choice(chosen)


def _eligible_npcs(npcs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter NPC list to those with at least one non-empty pool bucket.
    Empty-pool NPCs are silently skipped rather than producing nothing."""
    out = []
    for n in npcs:
        buckets = _DRIFT_POOLS.get(n["id"])
        if not buckets:
            continue
        if any(lines for lines in buckets.values()):
            out.append(n)
    return out


async def _llm_narrate(npc: dict[str, Any]) -> str | None:
    """Try the LLM-driven path. Returns the narrate text on success, or
    None on any failure (callers fall back to the canned pool).

    Failure modes that map to None:
    - LLMUnavailable from acompletion_json (vLLM down, JSON parse fail,
      timeout)
    - response missing or non-string `narrate` key
    - whitespace-only narrate
    - banlist hit on the parsed narrate
    - any other exception during retrieval / render (defense in depth;
      logged at warning)"""
    try:
        retrieved = memories.retrieve(
            npc["id"], npc["world_id"], npc["seed"], k=_llm_top_k()
        )
    except Exception as e:
        logger.warning("drift LLM: memory retrieve failed: %s", e, exc_info=True)
        retrieved = []
    try:
        template = _jinja.from_string(_DRIFT_USER_TEMPLATE)
        prompt = template.render(
            npc_name=npc["name"],
            npc_seed=npc["seed"],
            npc_mood=npc["mood"] or "calm",
            memories=retrieved,
        )
    except Exception as e:
        logger.warning("drift LLM: template render failed: %s", e, exc_info=True)
        return None
    try:
        response = await llm_client.acompletion_json(
            system=_DRIFT_SYSTEM_PROMPT, user=prompt
        )
    except llm_client.LLMUnavailable as e:
        logger.info("drift LLM: unavailable, falling back to canned: %s", e)
        return None
    except Exception as e:
        logger.warning("drift LLM: unexpected call failure: %s", e, exc_info=True)
        return None
    text = response.get("narrate") if isinstance(response, dict) else None
    if not isinstance(text, str) or not text.strip():
        logger.info("drift LLM: empty narrate, falling back to canned")
        return None
    if (hit := safety.first_banned(text)) is not None:
        logger.info(
            "drift LLM: banlist hit category=%s, falling back to canned", hit
        )
        return None
    return text.strip()


async def _tick(rng: random.Random | None = None) -> bool:
    """One drift step. Returns True if a narrate was emitted, False
    if the tick was a no-op (no NPCs, all pools empty, etc.).

    Async because the LLM-driven branch awaits `acompletion_json`. The
    canned branch could be sync but is awaited via the same coroutine
    so the loop body's contract stays uniform.

    `rng` injection lets tests seed selection deterministically."""
    rng = rng if rng is not None else random
    eligible = _eligible_npcs(_list_npcs())
    if not eligible:
        return False
    chosen = rng.choice(eligible)

    text: str | None = None
    if _is_llm_enabled():
        text = await _llm_narrate(chosen)
    if text is None:
        text = _pick_canned_line(chosen["id"], chosen["mood"], rng=rng)
    if text is None:
        return False
    events.append(
        actor_type="system",
        actor_id=None,
        kind="narrate",
        payload={"text": text},
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
            await _tick()
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
