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
   from a mood-bucketed pre-canned pool: the NPC's hand-authored
   per-NPC pool when one exists, else the name-templated
   `_GENERIC_DRIFT_POOL` (the safety net for bootstrapped NPCs). Falls
   back to the `default` bucket when the NPC's mood has no dedicated
   bucket. Selection is `random.choice` from the chosen bucket, with
   the toon's name substituted into any `{name}` token. NEVER calls the
   LLM, NEVER takes the arbiter.

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

from daydream import events, memories, toons
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


# Generic, name-templated drift pool. The safety net for any NPC without
# a hand-authored `_DRIFT_POOLS` entry — bootstrapped NPCs (ids shaped
# `t-<slug>-<uuid>`) in particular, whose per-character voice otherwise
# comes through the LLM path. Same dict-of-dicts shape and same bucket
# names as `_DRIFT_POOLS` so `_pick_canned_line` / `_maybe_transition_mood`
# treat it identically; the only difference is the literal `{name}` token,
# substituted at pick time via `str.replace` (never `str.format`, so a
# generated name containing `{` or `}` cannot crash the substitution).
#
# Voice-neutral by necessity: these beats carry no per-character imagery
# (no anvil, no letters) and use singular "they / their" so they read for
# any name and any gender. Tone is still WHIMSY-locked — soft, painterly,
# Spiritfarer / A Short Hike-adjacent, single-sentence third-person body
# language, no quoted dialogue, no urgency, no modern tech.
_GENERIC_DRIFT_POOL: dict[str, list[str]] = {
    "content": [
        "{name} hums a few notes under their breath, content with the quiet.",
        "{name} lets their shoulders settle and watches dust turn slow in a beam of light.",
        "{name} traces a small circle on a tabletop, in no hurry to be anywhere.",
        "{name} warms their hands and lets the moment sit, unhurried.",
    ],
    "thoughtful": [
        "{name} pauses to listen to the rafters, following a small sound to its end.",
        "{name} runs a thumb along the back of their hand, distracted by a thought.",
        "{name} gazes toward the window and lets a memory unspool at its own pace.",
        "{name} turns something over slowly in their mind, then lets it go.",
    ],
    "curious": [
        "{name} tilts their head at a shift in the light, quietly curious.",
        "{name} leans toward a small detail, half-smiling at what they find.",
        "{name} follows the drift of a dust mote with idle interest.",
        "{name} peers into a corner as if it might be hiding something kind.",
    ],
    "default": [
        "{name} draws a slow breath and lets the room go quiet around them.",
        "{name} shifts their weight from one foot to the other, settling in.",
        "{name} brushes a stray thread from their sleeve and lets it fall.",
        "{name} glances about the room, taking its small measure.",
    ],
}


_DEFAULT_IDLE_SECONDS = 300.0
_DEFAULT_BUSY_SECONDS = 1800.0
_DEFAULT_LLM_TOP_K = 3
_DEFAULT_MOOD_DRIFT_PROB = 0.2


# Per-NPC selection weight for the random tick draw. Higher weight = more
# often picked when a tick fires. Defaults are equal so v0 behavior is
# unchanged; tuning these is a soft lever for "Rook drifts more than
# Iris" or vice versa without restructuring the loop. NPCs missing from
# this dict default to weight 1.0; a weight of 0.0 excludes the NPC from
# selection entirely (eligible-but-suppressed). The mechanism survives
# adding new NPCs in v1+ — no migration, no schema change.
_NPC_DRIFT_WEIGHT: dict[str, float] = {
    "t-rook": 1.0,
    "t-iris": 1.0,
}


# Outcome counters for drift ticks. Process-local; reset on `bin/game up`.
# Mutually exclusive: every `_tick` call increments exactly one key.
# - `llm_emit`: LLM path returned a non-None narrate AND it was emitted.
# - `canned_fallback`: LLM path returned None (failure / banlist / empty)
#   AND the canned-pool fallback emitted a narrate.
# - `noop`: nothing emitted (no eligible NPCs, all-zero weights, all
#   rooms occupied, all pools empty, etc.).
# Surfaced via `bin/game status` when any value is non-zero. asyncio
# single-thread means no lock is needed.
_TICK_COUNTS: dict[str, int] = {
    "llm_emit": 0,
    "canned_fallback": 0,
    "noop": 0,
}


def tick_counts() -> dict[str, int]:
    """Return a copy of the drift outcome counters. Public accessor for
    `bin/game status` and tests."""
    return dict(_TICK_COUNTS)


def reset_tick_counts() -> None:
    """Test helper: zero all drift outcome counters."""
    for k in _TICK_COUNTS:
        _TICK_COUNTS[k] = 0


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


def _is_occupancy_suppression_enabled() -> bool:
    """Don't drift in a room a player is currently in (would feel
    intrusive). Default on in production; tests opt out per-test via
    monkeypatch when they need the legacy "drift anywhere" behavior."""
    return os.environ.get("DAYDREAM_DRIFT_SUPPRESS_OCCUPIED", "1") != "0"


def _is_mood_drift_enabled() -> bool:
    """Drift events occasionally nudge `toons.mood`. Default on in
    production; off in tests (`tests/conftest.py`) so the existing 19
    drift tests are unperturbed."""
    return os.environ.get("DAYDREAM_DRIFT_MOOD_DRIFT_ENABLED", "1") != "0"


def _mood_drift_prob() -> float:
    try:
        return float(os.environ.get("DAYDREAM_DRIFT_MOOD_DRIFT_PROB", _DEFAULT_MOOD_DRIFT_PROB))
    except ValueError:
        return _DEFAULT_MOOD_DRIFT_PROB


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
    return [
        {
            "id": t.id,
            "current_room_id": t.current_room_id,
            "world_id": t.world_id,
            "mood": t.mood,
            "name": t.name,
            "seed": t.seed,
        }
        for t in toons.get_npcs()
    ]


def _pick_canned_line(
    npc_id: str,
    mood: str | None,
    rng: random.Random | None = None,
    name: str | None = None,
) -> str | None:
    """Pick one canned drift line for `(npc_id, mood)`.

    Uses the NPC's hand-authored `_DRIFT_POOLS` entry when one exists;
    otherwise falls through to `_GENERIC_DRIFT_POOL` (the safety net for
    bootstrapped NPCs that have no per-NPC voice). Bucket selection is
    identical for either pool: prefer the bucket matching `mood` exactly
    when present and non-empty; otherwise fall back to `default`; if
    `default` is also empty, walk all buckets and pick from any non-empty
    one — this lets a future migration add a new mood bucket without
    `default` and still produce output.

    When `name` is provided, the chosen line's literal `{name}` token is
    substituted via `str.replace` (NOT `str.format`, so a generated name
    containing `{` or `}` cannot crash the call, and a line with no
    `{name}` token is left untouched). When `name` is None the
    substitution is skipped entirely.

    Returns the picked string, or None only when both the per-NPC pool
    and the generic pool yield no non-empty bucket — defense in depth,
    not reachable while `_GENERIC_DRIFT_POOL` ships non-empty buckets."""
    rng = rng if rng is not None else random
    buckets = _DRIFT_POOLS.get(npc_id) or _GENERIC_DRIFT_POOL
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
    line = rng.choice(chosen)
    if name is not None:
        line = line.replace("{name}", name)
    return line


def _occupied_room_ids() -> set[str]:
    """Rooms with at least one human-controlled, non-kicked toon
    present. Drift suppresses narrates in these rooms when occupancy
    suppression is enabled (default)."""
    try:
        return toons.occupied_room_ids()
    except Exception as e:
        logger.warning("drift: occupancy query failed: %s", e, exc_info=True)
        return set()


def _eligible_npcs(npcs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter NPC list to those eligible for a drift tick: every NPC
    (the `_list_npcs` query already restricts to `is_human_controlled=0`
    AND `kicked_at IS NULL`) whose current room has no human-controlled
    toon present when occupancy suppression is on.

    No per-NPC pool-membership check: bootstrapped NPCs with no
    `_DRIFT_POOLS` entry are eligible because `_pick_canned_line` falls
    through to `_GENERIC_DRIFT_POOL`, so eligibility no longer gates on
    having a hand-authored pool."""
    if _is_occupancy_suppression_enabled():
        occupied = _occupied_room_ids()
    else:
        occupied = set()
    return [n for n in npcs if n["current_room_id"] not in occupied]


def _pick_npc(
    eligible: list[dict[str, Any]], rng: random.Random | None = None
) -> dict[str, Any] | None:
    """Weighted random pick from eligible NPCs using `_NPC_DRIFT_WEIGHT`.
    NPCs missing from the dict default to weight 1.0; weight 0.0 excludes.
    Returns None when the eligible-set weights sum to 0 (all-zero edge
    case) — caller treats as a no-op tick."""
    if not eligible:
        return None
    rng = rng if rng is not None else random
    weights = [_NPC_DRIFT_WEIGHT.get(n["id"], 1.0) for n in eligible]
    if sum(weights) <= 0:
        return None
    return rng.choices(eligible, weights=weights, k=1)[0]


def _maybe_transition_mood(
    npc: dict[str, Any], rng: random.Random | None = None
) -> str | None:
    """Probabilistic mood transition. With probability
    `DAYDREAM_DRIFT_MOOD_DRIFT_PROB` (default 0.2) and at least one
    target bucket available (a pool key other than `default` and other
    than the current mood), pick a new mood and persist via
    `toons.set_mood`. The pool is the NPC's `_DRIFT_POOLS` entry when one
    exists, else `_GENERIC_DRIFT_POOL` — so bootstrapped NPCs draw their
    transition target from the generic bucket set. Returns the new mood
    string on transition, or None when no transition fired (toggle off,
    roll didn't land, no eligible target bucket, or persist failed).

    Persist failures are caught and logged at warning; the tick has
    already emitted its narrate by the time this runs and the loop
    continues regardless."""
    if not _is_mood_drift_enabled():
        return None
    rng = rng if rng is not None else random
    if rng.random() >= _mood_drift_prob():
        return None
    buckets = _DRIFT_POOLS.get(npc["id"]) or _GENERIC_DRIFT_POOL
    current_mood = npc.get("mood")
    targets = [
        m for m in buckets.keys() if m != "default" and m != current_mood
    ]
    if not targets:
        return None
    new_mood = rng.choice(targets)
    try:
        toons.set_mood(npc["id"], new_mood)
    except Exception as e:
        logger.warning(
            "drift: mood transition persist failed for %s -> %s: %s",
            npc["id"], new_mood, e,
        )
        return None
    return new_mood


def _render_drift_prompt(npc: dict[str, Any], retrieved_memories: list) -> str:
    """Render the drift LLM user prompt. Pure: takes any dict-shaped
    npc with `name`, `seed`, `mood` keys and an iterable of `Memory`-
    shaped objects (uses `.text`); returns the rendered prompt string.

    Extracted from `_llm_narrate` so the drift voice-bench harness
    (`daydream/drift_samples.py`) can render the same prompt the
    production code path would render, without DB state or memory
    retrieval coupling."""
    template = _jinja.from_string(_DRIFT_USER_TEMPLATE)
    return template.render(
        npc_name=npc["name"],
        npc_seed=npc["seed"],
        npc_mood=npc["mood"] or "calm",
        memories=retrieved_memories,
    )


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
        prompt = _render_drift_prompt(npc, retrieved)
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
    if the tick was a no-op (no NPCs, all pools empty, all rooms
    occupied, all weights zero, etc.).

    Async because the LLM-driven branch awaits `acompletion_json`. The
    canned branch could be sync but is awaited via the same coroutine
    so the loop body's contract stays uniform.

    Order of operations:
    1. List NPCs + filter for non-empty pool + room-occupancy suppression.
    2. Weighted-random select from eligible.
    3. Try LLM-driven narrate; on failure fall back to canned-pool.
    4. Emit narrate event.
    5. Probabilistically transition the chosen NPC's mood.

    `rng` injection lets tests seed selection deterministically."""
    rng = rng if rng is not None else random
    eligible = _eligible_npcs(_list_npcs())
    chosen = _pick_npc(eligible, rng=rng)
    if chosen is None:
        _TICK_COUNTS["noop"] += 1
        return False

    llm_text: str | None = None
    if _is_llm_enabled():
        llm_text = await _llm_narrate(chosen)
    text = llm_text if llm_text is not None else _pick_canned_line(
        chosen["id"], chosen["mood"], rng=rng, name=chosen["name"]
    )
    if text is None:
        _TICK_COUNTS["noop"] += 1
        return False
    events.append(
        actor_type="system",
        actor_id=None,
        kind="narrate",
        payload={"text": text},
        room_id=chosen["current_room_id"],
    )
    if llm_text is not None:
        _TICK_COUNTS["llm_emit"] += 1
    else:
        _TICK_COUNTS["canned_fallback"] += 1
    _maybe_transition_mood(chosen, rng=rng)
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


# Module-level handle to the running drift task. Tracked here (not only in
# the FastAPI lifespan local) so the in-process world hot-swap can stop and
# restart drift around a DB swap without the lifespan's handle in scope.
_handle: asyncio.Task | None = None


def start_drift_loop() -> asyncio.Task | None:
    """Spawn the drift task if enabled. Returns the task handle (for
    `stop_drift_loop`) or None if disabled. Records the handle module-side
    so `stop_drift_loop()` can be called with no argument (the hot-swap
    path). Safe to call once per FastAPI lifespan startup, and again after a
    `stop_drift_loop()` during a world swap."""
    global _handle
    if not _is_enabled():
        return None
    _handle = asyncio.create_task(_drift_loop(), name="daydream-drift")
    return _handle


async def stop_drift_loop(handle: asyncio.Task | None = None) -> None:
    """Cancel the drift task and await its cleanup. With no argument, stops
    the module-tracked task (the world-hot-swap path); an explicit handle is
    honored for the lifespan's existing call. No-op when there is no live
    task. Safe even if the task already completed for another reason."""
    global _handle
    target = handle if handle is not None else _handle
    if target is None or target.done():
        if target is _handle:
            _handle = None
        return
    target.cancel()
    try:
        await target
    except asyncio.CancelledError:
        pass
    if target is _handle:
        _handle = None
