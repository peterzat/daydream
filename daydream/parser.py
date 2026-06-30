"""Grounded natural-language command parser — the local-LLM front door for
free text.

Maps a player's free text to one structured, grounded command
`{verb, dobj_id, iobj_id, args}`: the verb comes from the closed registry (plus
any in-scope room-affordance data skill), and the objects are resolved to
in-scope IDS — "grounded resolution", which plays to a 7B model's strict-JSON
strength. The deterministic engine, not the model, mutates state.

Three layers, cheapest first:
1. **Deterministic fast-path (NO LLM):** an exact exit direction, a bare verb
   word, "verb <in-scope-name>", or a first-word data-skill name (the legacy
   `rook hi` / `forge a ring` forms). Clicks bypass even this (the WS command
   frame).
2. **Grounded LLM call:** the model picks a verb from the enumerated set and a
   dobj/iobj id from the enumerated scope. `say hi to rook` / `talk to rook` /
   `greet rook` all ground to `talk(t-rook, "hi")`.
3. **Fail-safe:** an unknown verb or an out-of-scope/ambiguous object grounds to
   verb `none` (the caller narrates a gentle "don't understand"), mutating
   nothing. On LLM outage the parse carries an `error` so the caller narrates
   the "foggy" fallback — the LLM is a hard dependency for natural language.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from daydream import objects, rooms, verbs
from daydream.llm import client
from daydream.skills import registry

logger = logging.getLogger(__name__)

_LEADING_ARTICLES = ("the ", "a ", "an ")


def _strip_article(text: str) -> str:
    t = text.strip()
    low = t.lower()
    for art in _LEADING_ARTICLES:
        if low.startswith(art):
            return t[len(art):].strip()
    return t


@dataclass(frozen=True)
class Parse:
    """A resolved command. `verb` is a closed verb, a data-skill name, or
    'none' (chatter / ungroundable). `error` is set only when the LLM was
    unreachable (the caller narrates 'foggy')."""

    verb: str
    dobj_id: str | None = None
    iobj_id: str | None = None
    args: str = ""
    error: str | None = None


NONE = Parse("none")


SYSTEM = (
    "You translate a player's free text into ONE structured command for a cozy "
    "text adventure. Return STRICT JSON only:\n"
    '{"verb": <one verb name from the list>, "dobj_id": <an object id from '
    'scope or null>, "iobj_id": <id or null>, "args": <leftover text such as '
    'what to say, else "">}.\n'
    "Pick the verb whose meaning best fits the input. Resolve a target to an "
    "object id from the Scope list by matching its name or aliases; use null "
    "when the verb takes no target. Use the verb \"none\" when nothing fits or "
    "the input is idle chatter. Output JSON only, no prose."
)


async def parse(actor_id: str, text: str) -> Parse:
    """Resolve `text` to a grounded command for `actor_id`. Async because the
    LLM layer may be hit; the fast-path returns without any await (zero LLM
    calls)."""
    text = text.strip()
    if not text:
        return NONE
    actor = objects.get(actor_id)
    if actor is None:
        return NONE
    room = rooms.get_room(actor.location_id) if actor.location_id else None

    fp = _fast_path(actor_id, text, room)
    if fp is not None:
        return fp

    vocab = _verb_vocabulary(actor_id, room.id if room else "")
    scope = _scope_entries(actor_id)
    try:
        result = await client.acompletion_json(
            system=SYSTEM, user=_user_prompt(text, vocab, scope)
        )
    except client.LLMUnavailable as e:
        return Parse("none", error=str(e))

    if not isinstance(result, dict):
        return NONE
    verb = str(result.get("verb", "none")).strip().lower()
    if verb == "none" or verb not in {v["name"] for v in vocab}:
        return NONE
    args = result.get("args", "")
    args = args.strip() if isinstance(args, str) else ""
    scope_ids = {e["id"] for e in scope}
    raw_dobj = result.get("dobj_id")
    raw_iobj = result.get("iobj_id")
    dobj_id = raw_dobj if isinstance(raw_dobj, str) and raw_dobj in scope_ids else None
    iobj_id = raw_iobj if isinstance(raw_iobj, str) and raw_iobj in scope_ids else None
    # Fail safe: the model named a target that isn't in scope (hallucinated or
    # ambiguous) -> no command, a gentle "don't understand" (not a wrong action).
    if isinstance(raw_dobj, str) and raw_dobj and dobj_id is None:
        return NONE
    if isinstance(raw_iobj, str) and raw_iobj and iobj_id is None:
        return NONE
    return Parse(verb, dobj_id=dobj_id, iobj_id=iobj_id, args=args)


# ---- fast-path (deterministic, no LLM) ---------------------------------


def _fast_path(actor_id: str, text: str, room: rooms.Room | None) -> Parse | None:
    low = text.strip().lower()
    # Exact exit direction -> go.
    if room is not None and low in room.exits:
        return Parse("go", args=low)

    parts = text.split(None, 1)
    head = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    # A bare / explicit closed verb.
    spec = verbs.get(head)
    if spec is not None:
        # Free-text verbs (say/talk) with args may name a target ("say hi to
        # rook" -> talk); hand those to the LLM rather than claim them here.
        if rest and spec.free_text:
            return None
        if not spec.needs_dobj:
            return Parse(head, args=rest)
        if not rest:
            # "examine" alone -> let execute_command narrate "Examine what?".
            return Parse(head, args="")
        # "verb <name>": resolve the name deterministically against scope.
        obj = objects.find_in_scope_by_name(actor_id, _strip_article(rest))
        if obj is not None and head in objects.verbs_for(obj):
            return Parse(head, dobj_id=obj.id)
        # Unresolved by name (e.g. "take the glowing thing") -> let the LLM try.
        return None

    # Legacy first-word data-skill name (`rook hi`, `forge a ring`), gated on
    # the skill being available in the current room. Preserves the exact-name
    # dispatch while natural phrasings go through the LLM (talk verb).
    room_id = room.id if room is not None else ""
    if head in _room_data_skill_names(room_id):
        return Parse(head, args=rest)
    return None


# ---- vocabulary + scope for the LLM call -------------------------------


def _room_data_skill_names(room_id: str) -> set[str]:
    """Data-skill names available in this room (core skills excluded)."""
    if not room_id:
        return set()
    return {
        s.name for s in registry.list_available_for_room(room_id) if s.kind == "data"
    }


def _is_npc_bound(skill_name: str) -> bool:
    """A data skill is NPC-bound (reached via `talk`, not as its own verb) when
    a toon object exists under the `t-<name>` convention."""
    obj = objects.get(f"t-{skill_name}")
    return obj is not None and obj.kind == "toon"


def _verb_vocabulary(actor_id: str, room_id: str) -> list[dict]:
    """The verbs the model may choose from: the closed engine verbs plus any
    in-scope room-affordance (non-NPC) data skills. NPC dialogue is reached via
    `talk`, so NPC-bound skills are excluded here."""
    vocab = [
        {"name": v.name, "description": v.description}
        for v in verbs.VERBS.values()
    ]
    for name in sorted(_room_data_skill_names(room_id)):
        if not _is_npc_bound(name):
            spec = registry.find(name)
            desc = spec.description if spec else f"the {name} affordance"
            vocab.append({"name": name, "description": desc})
    return vocab


def _scope_entries(actor_id: str) -> list[dict]:
    """In-scope objects (excluding the actor + prototypes) as grounding rows."""
    out: list[dict] = []
    for o in objects.in_scope(actor_id):
        if o.id == actor_id or o.kind == "prototype":
            continue
        out.append(
            {"id": o.id, "name": o.name, "aliases": o.aliases, "kind": o.kind,
             "verbs": objects.verbs_for(o)}
        )
    return out


def _user_prompt(text: str, vocab: list[dict], scope: list[dict]) -> str:
    verb_lines = "\n".join(f"- {v['name']}: {v['description']}" for v in vocab)
    if scope:
        scope_lines = "\n".join(
            f"- {e['id']}: {e['name']} ({e['kind']})"
            + (f" [aliases: {', '.join(e['aliases'])}]" if e["aliases"] else "")
            for e in scope
        )
    else:
        scope_lines = "(nothing of note nearby)"
    return (
        f"Verbs:\n{verb_lines}\n\n"
        f"Scope (objects you can refer to):\n{scope_lines}\n\n"
        f"Player input: {text}\n\n"
        'Respond with JSON: {"verb": "...", "dobj_id": ..., "iobj_id": ..., "args": "..."}'
    )
