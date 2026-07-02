"""Data skills: DB-loaded, LLM-driven skills that extend the registry.

A data skill's row in the `skills` table carries the fields the v0
schema already reserved:

- `name`, `kind='data'`, `ui_hint`, `description` — the registry
  interface fields, also surfaced to the LLM interpreter as candidates.
- `context_predicate_json` — which rooms the skill is available in.
  v1 format: `{}` (always) or `{"room_slug": "<slug>"}`. Unknown
  predicate keys fail closed (skill hidden) so a misauthored
  predicate cannot accidentally expose a skill everywhere.
- `prompt_template` — Jinja template rendered via the stdlib
  `SandboxedEnvironment` so the template itself cannot reach protected
  attributes. Receives `player_input` (already role-separator-wrapped),
  `actor_id`, and `room_id` as context variables.
- `effects_schema_json` — the shape the LLM is asked to produce.
  v1 uses this as documentation / provenance only; enforcement is by
  the effect allowlist in `daydream.skills.effects`. v2's full
  jsonschema pipeline lives in BACKLOG entry
  `skills-authoring-and-security`.
- `enabled` (0/1) — the operator switch; disabled rows are invisible
  to the registry.

Execution runs the full safety + effect pipeline (SPEC criteria 4-7):
1. banlist check on player args -> early narrate fallback
2. SandboxedEnvironment renders the template with `wrap_player_input`
3. LLM call (arbiter-wrapped in daydream.llm.client)
4. refusal parse (precedence over effects)
5. banlist check on narrative text fields of the response
6. dispatch_effects through the allowlist
"""

import json
import logging
from dataclasses import dataclass

from jinja2.sandbox import SandboxedEnvironment

from daydream import db, events, memories, objects, rooms
from daydream.llm import client as llm_client
from daydream.llm import safety
from daydream.skills import effects
from daydream.skills.registry import SkillSpec

logger = logging.getLogger(__name__)

_jinja = SandboxedEnvironment(autoescape=False)


@dataclass(frozen=True)
class DataSkillBody:
    """The DB-only fields a data skill needs at execution time.
    Kept separate from SkillSpec so the registry's read API stays
    uniform across core and data."""

    context_predicate: dict
    prompt_template: str
    effects_schema: dict


def _rows() -> list[dict]:
    """Fetch enabled data-skill rows. Degrades gracefully if the DB
    isn't initialized (returns empty)."""
    try:
        conn = db.get_conn()
    except RuntimeError:
        return []
    rows = conn.execute(
        "SELECT name, ui_hint, description, context_predicate_json, "
        "       prompt_template, effects_schema_json, enabled "
        "FROM skills WHERE kind = 'data' AND enabled = 1 "
        "ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def _parse_pair(row: dict) -> tuple[SkillSpec, DataSkillBody] | None:
    """Turn one DB row into a (SkillSpec, DataSkillBody) pair. Returns
    None on malformed JSON so list_all() can skip the row without
    poisoning the whole list."""
    try:
        predicate = json.loads(row["context_predicate_json"] or "{}")
        effects_schema = json.loads(row["effects_schema_json"] or "{}")
    except json.JSONDecodeError as e:
        logger.warning("skipping data skill %r: malformed JSON (%s)", row["name"], e)
        return None
    if not isinstance(predicate, dict):
        predicate = {}
    if not isinstance(effects_schema, dict):
        effects_schema = {}
    # Prefer the authored `description` column (added in migration 005)
    # so the interpreter sees the author's intent. Fall back to a
    # generic string only when the column is NULL / empty (pre-005 row
    # that hasn't been re-installed yet).
    stored_desc = row.get("description") if isinstance(row, dict) else None
    desc = stored_desc.strip() if isinstance(stored_desc, str) and stored_desc.strip() else f"A data skill: {row['name']}."
    spec = SkillSpec(
        name=row["name"],
        kind="data",
        handler=None,
        ui_hint=row["ui_hint"] or row["name"],
        description=desc,
    )
    body = DataSkillBody(
        context_predicate=predicate,
        prompt_template=row["prompt_template"] or "",
        effects_schema=effects_schema,
    )
    return (spec, body)


def list_all() -> list[tuple[SkillSpec, DataSkillBody]]:
    """Return every enabled data skill as (spec, body) pairs. Malformed
    rows are skipped with a log warning rather than raising, so one
    bad row can't hide the rest."""
    pairs: list[tuple[SkillSpec, DataSkillBody]] = []
    for row in _rows():
        pair = _parse_pair(row)
        if pair is not None:
            pairs.append(pair)
    return pairs


def available_for_room(room_id: str) -> list[tuple[SkillSpec, DataSkillBody]]:
    """List all enabled data skills whose predicate matches the given
    room. Resolves the room's slug once and passes it into the predicate
    matcher so each predicate is a pure dict-in-dict-out comparison.

    Degrades gracefully when the DB is not initialized (returns empty
    list), so the registry's contract of "core-only when DB is absent"
    holds even when list_available_for_room is called out-of-band
    (e.g., from interpreter unit tests that don't spin up a DB)."""
    try:
        db.get_conn()
    except RuntimeError:
        return []
    room = rooms.get_room(room_id)
    slug = room.slug if room else None
    return [
        (spec, body)
        for spec, body in list_all()
        if _matches_predicate(body.context_predicate, slug)
    ]


def find(name: str) -> tuple[SkillSpec, DataSkillBody] | None:
    """Look up a data skill by exact (lowercased) name. Returns the
    (spec, body) pair or None."""
    needle = name.strip().lower()
    for spec, body in list_all():
        if spec.name.lower() == needle:
            return (spec, body)
    return None


_ALLOWED_PREDICATE_KEYS = frozenset({"room_slug"})


def _matches_predicate(predicate: dict, room_slug: str | None) -> bool:
    """v1 predicate format:
       {} -> always available (every room)
       {"room_slug": "<slug>"} -> only in rooms with that slug

    Unknown predicate keys fail closed (skill hidden). This keeps a
    typoed or forward-compat predicate from leaking a skill into every
    room by accident — "the least surprising" failure mode."""
    if not predicate:
        return True
    if not set(predicate.keys()).issubset(_ALLOWED_PREDICATE_KEYS):
        logger.warning(
            "data skill has unknown predicate keys %s; treating as unavailable",
            sorted(k for k in predicate.keys() if k not in _ALLOWED_PREDICATE_KEYS),
        )
        return False
    wanted = predicate.get("room_slug")
    if wanted is None:
        return True
    return wanted == room_slug


_BANNED_FALLBACK_TEXT = "The dream won't hold that thought."
_FOGGY_FALLBACK_TEXT = "The dream is foggy right now; that thought slips away."
_RENDER_FAILURE_TEXT = "The dream loses the thread of that skill."

# System message for the data-skill dispatcher LLM call. Instructs SECOND
# PERSON for player-action narration so the player is always addressed as
# "you", never "the visitor" / third person (SPEC 2026-06-30). Built once at
# import; DEFAULT_KINDS is stable. (DEFAULT_KINDS, not ALLOWED_KINDS: the
# world-shaping kinds are per-verb opt-in and unreachable from a data skill's
# allowed=None dispatch, so advertising them here would only teach the model
# to emit effects the dispatcher then rejects.)
_DISPATCHER_SYSTEM = (
    "You are a skill dispatcher for a cozy watercolor text-adventure. "
    "Narrate the player's own actions in the SECOND PERSON: address the player "
    "as 'you', never as 'the visitor' or any third-person label. "
    "Return strict JSON with an 'effects' list; each effect has a 'kind' plus "
    "the fields that kind requires. Allowed kinds: "
    + ", ".join(sorted(effects.DEFAULT_KINDS))
    + '. If the request is off-tone or outside this skill, return '
    '{"refused": true, "reason": "<in-fiction gentle refusal>"}. '
    "Keep all narrative text tone-matched: cozy, soft, painterly."
)


def _resolve_npc_and_world(spec: SkillSpec, room_id: str) -> tuple[str | None, str | None]:
    """Bind a data skill to its backing NPC for memory scoping.

    Convention: skill name maps to ``f"t-{spec.name}"`` (Rook → t-rook,
    Iris → t-iris). This is the cheapest v0 path; an explicit ``npc_id``
    field on the skill schema lands when the convention ever ambiguates.
    Returns ``(None, None)`` for skills with no matching NPC row (e.g.,
    the room-anchored ``forge`` skill), so the caller can skip memory
    capture/retrieve cleanly without affecting the rest of the pipeline.

    Worlds that don't match the skill's room are also excluded — a row
    that exists in a different world than the conversation is happening
    in is treated as 'no NPC here', preserving the per-world scoping
    contract."""
    candidate_id = f"t-{spec.name.lower()}"
    try:
        db.get_conn()
    except RuntimeError:
        return (None, None)
    npc = objects.get(candidate_id)
    if npc is None or npc.kind != "toon":
        return (None, None)
    room = rooms.get_room(room_id)
    room_world_id = room.world_id if room else None
    if room_world_id and npc.world_id != room_world_id:
        return (None, None)
    return (npc.id, npc.world_id)


def _extract_narration(effects_list: list) -> str:
    """Concatenate all ``narrate`` effect texts so the memory capture
    has a single string to embed. Returns empty string if no narrate
    effects were emitted (e.g., a data skill that only mutates state)."""
    parts: list[str] = []
    for e in effects_list:
        if not isinstance(e, dict):
            continue
        if e.get("kind") != "narrate":
            continue
        text = e.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return " ".join(parts)


def _narrative_text(effects_list: list) -> str:
    """Concatenate text-ish fields across every effect in the LLM's
    response so the output-side banlist scan sees every narrative
    surface in one pass. Non-dict entries are skipped (the allowlist
    dispatcher already handles them).

    `mood` is included because `set_mood` writes the string through to
    `toons.mood`, which surfaces to the SPA as `${name} (${mood})` — a
    banned category there would bypass the output scan otherwise."""
    parts: list[str] = []
    for e in effects_list:
        if not isinstance(e, dict):
            continue
        for k in ("text", "seed", "name", "mood"):
            v = e.get(k)
            if isinstance(v, str):
                parts.append(v)
    return " ".join(parts)


def _emit_narrate(text: str, room_id: str) -> None:
    events.append("system", None, "narrate", {"text": text}, room_id=room_id)


async def execute(
    spec: SkillSpec,
    body: DataSkillBody,
    actor_id: str,
    room_id: str,
    args: str,
    allowed: "frozenset[str] | None" = None,
) -> None:
    """Run the full data-skill pipeline and emit events. No return
    value — the side effect is events in the log, matching the core
    skill convention.

    `allowed`, when given, is the per-verb effect allowlist forwarded to the
    effect dispatcher (e.g. the `talk` verb constrains an NPC's dialogue to
    narrate/set_property/set_mood/spawn_object). None = DEFAULT_KINDS, the
    standalone data-skill default (world-shaping kinds excluded)."""
    # (0) Bind the skill to its backing NPC (if any) and pull recent
    # memories. Both retrieval and capture are no-ops for skills that
    # don't have a matching NPC row (e.g., room-anchored skills like
    # ``forge``). The retrieve call itself is fail-closed: a missing
    # embedder, an uninitialized DB, or DAYDREAM_MEMORY_ENABLED=0 all
    # produce an empty list rather than raising.
    npc_id, world_id_for_mem = _resolve_npc_and_world(spec, room_id)
    retrieved_memories: list[memories.Memory] = []
    if npc_id is not None and world_id_for_mem is not None:
        retrieved_memories = memories.retrieve(npc_id, world_id_for_mem, args)

    # (1) Input banlist. A hit short-circuits before the LLM is called.
    if (hit := safety.first_banned(args)) is not None:
        logger.info("skill %r blocked on input banlist category=%s", spec.name, hit)
        _emit_narrate(_BANNED_FALLBACK_TEXT, room_id)
        return

    # (2) Render the template. SandboxedEnvironment protects against a
    # malicious template reaching __class__ / __globals__ etc. The
    # player's text is wrapped in role-separator tags before injection.
    # The ``memories`` context variable is always provided (possibly an
    # empty list); templates that don't reference it are unaffected.
    try:
        template = _jinja.from_string(body.prompt_template)
        prompt = template.render(
            player_input=safety.wrap_player_input(args),
            actor_id=actor_id,
            room_id=room_id,
            memories=retrieved_memories,
        )
    except Exception as e:
        logger.warning("skill %r template render failed: %s", spec.name, e)
        _emit_narrate(_RENDER_FAILURE_TEXT, room_id)
        return

    # (3) LLM call. Arbiter + error handling is inside acompletion_json.
    try:
        response = await llm_client.acompletion_json(
            system=_DISPATCHER_SYSTEM, user=prompt
        )
    except llm_client.LLMUnavailable as e:
        logger.warning("skill %r LLM unavailable: %s", spec.name, e)
        _emit_narrate(_FOGGY_FALLBACK_TEXT, room_id)
        return

    # (4) Refusal takes precedence over any effects in the same payload.
    refusal = safety.parse_refusal(response)
    if refusal is not None:
        _emit_narrate(refusal.reason, room_id)
        return

    effects_list = response.get("effects", []) if isinstance(response, dict) else []
    if not isinstance(effects_list, list):
        effects_list = []

    # (5) Output banlist: scan every narrative field in the effects
    # payload before mutating state.
    if (hit := safety.first_banned(_narrative_text(effects_list))) is not None:
        logger.info("skill %r blocked on output banlist category=%s", spec.name, hit)
        _emit_narrate(_BANNED_FALLBACK_TEXT, room_id)
        return

    # (6) Dispatch effects through the allowlist.
    room = rooms.get_room(room_id)
    world_id = room.world_id if room else ""
    applied = effects.dispatch_effects(
        effects_list,
        actor_id=actor_id,
        room_id=room_id,
        world_id=world_id,
        allowed=allowed,
    )
    # UX safety: if the LLM returned an empty / shape-less effects
    # list, the player would otherwise see nothing happen. Emit a soft
    # narrate so the input always has a visible outcome.
    if not any(a.event is not None for a in applied):
        _emit_narrate("The dream is quiet; nothing stirs just yet.", room_id)
        return

    # (7) Capture the exchange to NPC memory. Only fires for skills
    # bound to an NPC and only when normal effects ran (refusal /
    # banlist / empty-effects paths skipped via the early returns
    # above). Both calls are fail-closed inside daydream.memories;
    # capture failures never propagate back into the dialogue path.
    if npc_id is not None and world_id_for_mem is not None:
        narration = _extract_narration(effects_list)
        if narration:
            memories.capture(
                npc_id, world_id_for_mem, f"the visitor said: {args}"
            )
            speaker = spec.ui_hint or spec.name
            memories.capture(
                npc_id, world_id_for_mem, f"{speaker} said: {narration}"
            )


async def execute_by_name(
    name: str, actor_id: str, room_id: str, args: str
) -> bool:
    """Convenience for the WS layer: look up a data skill by name and
    run it. Returns True if a data skill was found and executed (so
    the caller knows the input was handled), False if no data skill
    matched (so the caller can fall back to the interpreter)."""
    pair = find(name)
    if pair is None:
        return False
    spec, body = pair
    await execute(spec, body, actor_id, room_id, args)
    return True
