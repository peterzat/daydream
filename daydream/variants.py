"""Authored variants without verbatim repeats (SPEC 2026-09-26 criterion 11).

Every authored line that can be told more than once (an affordance, a topic
answer, a beat, an NPC's drift beat) may carry several variants. `pick`
chooses the next telling for a (key, room) pair so that no variant repeats
within the last `window` tellings there, deterministically: the choice is a
stable-seeded roll over the not-recently-told variants, keyed on the telling
count, so a replayed walkthrough tells the same lines in the same order.

State is one small worldstate row per (key, room): `told:<key>@<room>` =
{"n": tellings so far, "recent": [indices, newest last]}.
"""

from __future__ import annotations

import hashlib

from daydream import worldstate

TOLD_PREFIX = "told:"
DEFAULT_WINDOW = 3


def key_for(options: list[str]) -> str:
    """A stable key for an anonymous variant list (a narrate effect's
    `variants` with no authored key): a short hash of its text."""
    h = hashlib.sha1("\x1f".join(options).encode("utf-8")).hexdigest()
    return f"v{h[:12]}"


def pick(
    world_id: str,
    key: str,
    options: list[str],
    room_id: str | None = None,
    window: int = DEFAULT_WINDOW,
) -> str | None:
    """The next variant to tell for `key` in `room_id` (None = world-wide).
    With N options, the last min(window, N-1) tellings are excluded, so two
    options alternate and three or more never repeat within the window."""
    opts = [o for o in options if isinstance(o, str) and o.strip()]
    if not opts:
        return None
    if len(opts) == 1:
        return opts[0].strip()
    row_key = f"{TOLD_PREFIX}{key}@{room_id or '*'}"
    state = worldstate.get(world_id, row_key)
    if not isinstance(state, dict):
        state = {}
    n = state.get("n") if isinstance(state.get("n"), int) else 0
    recent = [i for i in state.get("recent", []) if isinstance(i, int)]
    span = max(0, min(window, len(opts) - 1))
    blocked = set(recent[-span:]) if span else set()
    fresh = [i for i in range(len(opts)) if i not in blocked]
    rng = worldstate.rng_stable(world_id, f"variant:{key}:{room_id}:{n}")
    idx = rng.choice(fresh)
    recent = (recent + [idx])[-max(span, 1):]
    worldstate.set(world_id, row_key, {"n": n + 1, "recent": recent})
    return opts[idx].strip()
