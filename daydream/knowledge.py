"""NPC knowledge as data, and gossip (SPEC 2026-09-26 criterion 7).

Two kinds of fact:

- **Authored facts** (worldstate `def:facts`): `{"<id>": {"text",
  "known_by": [npc ids] | "all", "if"?: [conditions]}}`. The `if` gates
  relevance on world state ("the gear is still lost"), evaluated for the
  player in the conversation.
- **Deed facts**, created at runtime by the rule effect `add_fact`, naming
  the player who did the deed: `{"id", "text": "{actor} carried the gear
  home", "known_by": [npc ids], "spread": [{"to": [npc ids] | "all",
  "after_minutes": N}, ...]}`. Stored as worldstate `fact:<id>:<actor>`
  (one per deed per player; a repeat never resets the clock).

Knowing is evaluated LAZILY against the wall clock: an NPC knows a deed fact
if it is in `known_by`, or in a spread stage whose `after_minutes` have
passed since the deed. So gossip needs no background task, survives
restarts, and is driven in tests by the fake clock.
"""

from __future__ import annotations

from datetime import timedelta

from daydream import events, objects, toons, worldclock, worldstate

FACT_PREFIX = "fact:"


def facts_def(world_id: str) -> dict:
    d = worldstate.get(world_id, "def:facts")
    return d if isinstance(d, dict) else {}


def _in(npc_id: str, who) -> bool:
    if who == "all":
        return True
    return isinstance(who, list) and npc_id in who


def add_fact(world_id: str, fact_id: str, text: str, actor_id: str | None,
             known_by, spread, room_id: str | None = None) -> events.Event | None:
    """Record one deed fact about `actor_id` (the doer). The first telling
    wins: a repeated deed keeps its original timestamp and spread."""
    if not isinstance(fact_id, str) or not fact_id.strip():
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    actor = objects.get(actor_id) if actor_id else None
    key = f"{FACT_PREFIX}{fact_id.strip()}:{actor_id or '-'}"
    if worldstate.get(world_id, key) is not None:
        return None
    # A name made before names were bounded never carries past the cap into
    # the stored fact (it reaches every resident's prompt).
    who = actor.name[:toons.MAX_NAME_CHARS] if actor else None
    rendered = text.replace("{actor}", who or "someone")
    stages = []
    for st in spread if isinstance(spread, list) else []:
        if isinstance(st, dict) and isinstance(st.get("after_minutes"), (int, float)):
            stages.append({"to": st.get("to"), "after_minutes": st["after_minutes"]})
    worldstate.set(world_id, key, {
        "id": fact_id.strip(), "text": rendered.strip(), "about": actor_id,
        "about_name": who, "at": worldclock.iso(),
        "known_by": known_by if (known_by == "all" or isinstance(known_by, list)) else [],
        "spread": stages,
    })
    return events.append("system", None, "fact_added",
                         {"fact": fact_id.strip(), "about": actor_id},
                         room_id=room_id)


def deed_facts(world_id: str) -> list[dict]:
    out = []
    for k in worldstate.keys(world_id, FACT_PREFIX):
        v = worldstate.get(world_id, k)
        if isinstance(v, dict):
            out.append(v)
    out.sort(key=lambda f: f.get("at") or "")
    return out


def deed_known_by(fact: dict, npc_id: str, now=None) -> bool:
    if _in(npc_id, fact.get("known_by")):
        return True
    now = now or worldclock.now()
    try:
        at = worldclock.parse(fact["at"])
    except (KeyError, ValueError, TypeError):
        return False
    for st in fact.get("spread") or []:
        if _in(npc_id, st.get("to")) and now >= at + timedelta(minutes=st["after_minutes"]):
            return True
    return False


_CHECKING: set[str] = set()


def npc_knows(world_id: str, npc_id: str, fact_id: str,
              about: str | None = None, now=None, ctx: dict | None = None) -> bool:
    """The `knows` rule condition: does this NPC know the fact (an authored
    fact id, or any deed fact with that id, optionally about one player)?
    An authored fact is known only while its own `if` holds (the same test
    the dialogue context applies), evaluated in the caller's rule context
    when given, else the world's."""
    auth = facts_def(world_id).get(fact_id)
    if isinstance(auth, dict) and about is None and _in(npc_id, auth.get("known_by")):
        if not auth.get("if"):
            return True
        if fact_id not in _CHECKING:  # a fact gated on knowing itself is not known
            from daydream import rules

            _CHECKING.add(fact_id)
            try:
                if rules.conditions_hold(auth["if"], ctx or rules.world_ctx(world_id, None, "facts")):
                    return True
            finally:
                _CHECKING.discard(fact_id)
    for f in deed_facts(world_id):
        if f.get("id") != fact_id:
            continue
        if about is not None and f.get("about") != about:
            continue
        if deed_known_by(f, npc_id, now):
            return True
    return False


def known_facts(npc: objects.Object, actor_id: str | None = None,
                limit: int = 10, now=None) -> list[dict]:
    """What this NPC knows right now, for its dialogue context, ordered by
    relevance: deeds by the player in the conversation, then other players'
    deeds (newest first), then authored facts whose conditions hold.
    Each entry: {"text", "kind": "deed"|"fact", "about"?}."""
    from daydream import rules

    world_id = npc.world_id
    now = now or worldclock.now()
    mine, others, authored = [], [], []
    for f in reversed(deed_facts(world_id)):
        if not deed_known_by(f, npc.id, now):
            continue
        entry = {"text": f["text"], "kind": "deed", "about": f.get("about"),
                 "about_name": f.get("about_name")}
        (mine if actor_id and f.get("about") == actor_id else others).append(entry)
    actor = objects.get(actor_id) if actor_id else None
    ctx = (rules._build_ctx(actor, None, None, actor.location_id or "", npc, "facts")
           if actor is not None else rules.world_ctx(world_id, None, "facts"))
    ranked = []
    for order, (fid, f) in enumerate(facts_def(world_id).items()):
        if not isinstance(f, dict) or not _in(npc.id, f.get("known_by")):
            continue
        if not rules.conditions_hold(f.get("if"), ctx):
            continue
        if isinstance(f.get("text"), str) and f["text"].strip():
            # Relevance: a situational fact (gated on an open arc, the clock,
            # a beat) is news and outranks standing lore; lore this NPC
            # specifically knows outranks what the whole village knows.
            rank = (0 if f.get("if") else 1, 0 if f.get("known_by") != "all" else 1, order)
            ranked.append((rank, {"text": f["text"].strip(), "kind": "fact", "id": fid}))
    authored = [e for _, e in sorted(ranked, key=lambda x: x[0])]
    return (mine + others + authored)[:limit]
