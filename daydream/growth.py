"""Dreamseed growth: the `plant` verb's pipeline (SPEC 2026-07-02).

A player plants a quest-earned dreamseed and answers one in-character question
with a short vision phrase; ONE local-LLM call composes a small new room
inside the seed's Opus-authored boundaries (`properties.growth`), and a
synchronous commit block grows it for everyone, forever: a persistent room, a
bidirectional exit, 0-2 resting objects, the seed consumed into a husk, and an
in-character payoff naming the new way.

Shape of the pipeline (each stage preserves the seed on failure):

  gates      carried -> not spent -> has growth -> cap -> free direction ->
             non-empty vision (else narrate the seed's authored question) ->
             phrase length cap -> input banlist. All pre-LLM; a refusal here
             costs nothing.
  compose    one `acompletion_json` call (temp 0, ~450 max tokens, ~30 s
             timeout; the GPU arbiter is internal to the client). The LLM
             never sees object ids or directions — it composes only title,
             prose, and 0-2 objects.
  validate   refusal escape hatch -> strict schema (length windows, 0-2
             objects, reject-not-truncate) -> WHIMSY banlist over every text
             field -> anti-copy check against the seed's authored exemplars.
  commit     a SYNCHRONOUS block (no awaits, so no interleaving under
             asyncio's cooperative model): re-check every gate the LLM await
             could have raced (seed dropped, cap reached, a rival plant taking
             the direction or slug), pick a unique slug + `r-<slug>` id, then
             dispatch one ordered effect batch through the verb's allowlist —
             spawn_room -> link_exit -> spawn_object(s) -> seed set_property
             (state/examined_text/verbs) -> move_object husk -> narrate. A
             structural checkpoint after spawn_room+link_exit guarantees the
             seed is never consumed against a half-built room.

Every failure path narrates in character and mutates NOTHING; the seed stays
carried, unspent, and plantable. Per the generation policy this runs ONLY
against the local model; there is no cloud fallback."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from daydream import config, events, objects, rooms
from daydream.llm import client, safety
from daydream.skills import effects

logger = logging.getLogger(__name__)

# The engine picks the exit direction; the LLM never sees directions or ids.
# First free wins, in this fixed order; the reverse is the compass involution.
_DIRECTIONS = ("north", "east", "south", "west", "up", "down")
_REVERSE = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "up": "down", "down": "up",
}

# The player's vision phrase is a short answer, not an essay: length-capped
# before it ever reaches a prompt (SPEC 2026-07-02, criterion 2).
MAX_PHRASE_CHARS = 120

# In-character failure lines. Every one leaves the seed carried, unspent, and
# plantable, and mutates nothing.
_NOT_CARRIED = "The dreamseed needs to rest in your hands before it will take root."
_SPENT = "The husk is quiet now; whatever it held has already grown."
_NO_GROWTH = "You press it into the earth, but nothing in it wants to grow."
_CAP_REACHED = "The dream holds all the new places it can for now; let them settle a while."
_NO_DIRECTION = "Every way out of this place is already taken; the seed has nowhere to open."
_PHRASE_TOO_LONG = "The seed trembles under so many words; hold a smaller vision."
_OFF_TONE = "The seed stirs, but the dream won't hold that shape."
_WONT_HOLD_YET = "The seed stirs, but the dream won't hold that shape yet."
_FOGGY = "The dream is foggy right now; that thought slips away."
_HUSK_DEFAULT = "a spent dreamseed, its light gone soft; something of it lives on in this place"

# ---- the growth prompt (rung a: exemplar-scaffolded free composition) ---
#
# The mitigation ladder (SPEC 2026-07-02, criterion 7): rung (a) ships this
# prompt; rung (b) would flip to select-and-fill over the seed's authored
# `skeletons` (validated by the loader from day one); rung (c) is a
# deterministic skeleton fill. The tier_long probe + agent ratification
# against WHIMSY.md decides the rung before the golden baseline is committed.

GROWTH_SYSTEM = (
    "You are the dream-gardener of a cozy watercolor world. A player has "
    "planted a dreamseed and spoken a short vision; you compose ONE small new "
    "place that grows from it, inside the seed's authored boundaries.\n"
    "Return STRICT JSON only:\n"
    '{"title": "...", "room_seed": "...", "description": "...", '
    '"objects": [{"name": "...", "seed": "..."}]}\n'
    "- title: 1-5 words, 3-40 characters, evocative, Title Case.\n"
    "- room_seed: 30-300 characters; one painterly sentence of what the place "
    "IS, concrete and visual (it will be painted from this).\n"
    "- description: 60-500 characters; 2-4 soft sentences a player reads on "
    "arriving there, present tense.\n"
    "- objects: 0-2 small resting things found in the place, each "
    '{"name": 3-30 chars, "seed": 15-200 chars}. Things only — no creatures, '
    "no people.\n"
    "Weave the player's vision into the place so they can feel it was heard. "
    "Stay inside the seed's theme and palette; echo its motifs gently. Do NOT "
    "copy the example rooms; grow something new in their spirit.\n"
    "Tone: cozy, soft, painterly, Spiritfarer / A Short Hike. No urgency, no "
    "modern tech, no harsh edges, no violence, no darkness.\n"
    "If the vision is off-tone or impossible to hold gently, refuse with "
    '{"refused": true, "reason": "<one soft in-character sentence>"}.\n'
    "Output ONLY the JSON object."
)


def _growth_shape_ok(growth: object) -> bool:
    """True when a growth block has the shape `_user_prompt` (and the
    exemplar checks in `validate_growth_output`) rely on. Loader-authored
    seeds are validated at load (`bootstrap._validate_growth`), but a
    runtime-created seed can carry an arbitrary `growth` dict (e.g. via a
    `spawn_object` effect's properties passthrough); a malformed one must
    refuse in character, never raise."""
    if not isinstance(growth, dict):
        return False
    exemplars = growth.get("exemplars")
    if not isinstance(exemplars, list) or not exemplars:
        return False
    for ex in exemplars:
        if not isinstance(ex, dict) or not all(
            isinstance(ex.get(k), str) and ex[k].strip()
            for k in ("title", "seed", "description")
        ):
            return False
    for key in ("theme", "motifs"):
        value = growth.get(key)
        if value is not None and (
            not isinstance(value, list)
            or not all(isinstance(item, str) for item in value)
        ):
            return False
    for key in ("palette", "question"):
        value = growth.get(key)
        if value is not None and not isinstance(value, str):
            return False
    return True


def _user_prompt(growth: dict, room: "rooms.Room", phrase: str) -> str:
    """The per-plant user block: the seed's authored boundaries + exemplars,
    the room being grown from (title + seed only — never ids), and the
    player's phrase inside role-separator wrapping."""
    lines = ["Seed boundaries:"]
    theme = growth.get("theme") or []
    lines.append(f"- theme: {', '.join(theme)}")
    lines.append(f"- palette: {growth.get('palette', '')}")
    motifs = growth.get("motifs") or []
    if motifs:
        lines.append(f"- motifs: {', '.join(motifs)}")
    lines.append("")
    lines.append("Example rooms in this seed's voice (for spirit, never to copy):")
    for ex in growth.get("exemplars") or []:
        lines.append(
            f"- title: {ex['title']} | seed: {ex['seed']} | "
            f"description: {ex['description']}"
        )
    lines.append("")
    lines.append(f"The place it is planted in: {room.title} — {room.seed}")
    lines.append("")
    question = growth.get("question", "Where does the new way lead?")
    lines.append(
        f'The planter\'s vision (their answer to "{question}"): '
        f"{safety.wrap_player_input(phrase)}"
    )
    lines.append("")
    lines.append("Respond with the JSON object now.")
    return "\n".join(lines)


# ---- validation ----------------------------------------------------------


def _norm(text: str) -> str:
    """Normalization for the anti-copy check: lowercase, collapsed whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _check_len(value: object, lo: int, hi: int) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if lo <= len(v) <= hi else None


def validate_growth_output(result: object, growth: dict) -> dict | None:
    """Strict validation of the LLM's composition (SPEC 2026-07-02,
    criterion 2). Returns the cleaned {title, room_seed, description, objects}
    dict, or None on ANY violation — schema windows, more than 2 objects
    (reject, not truncate), a WHIMSY banlist hit in any text field, or an
    anti-copy match against the seed's authored exemplars. Callers treat None
    as "mutate nothing"."""
    if not isinstance(result, dict):
        return None
    title = _check_len(result.get("title"), 3, 40)
    if title is None or not (1 <= len(title.split()) <= 5):
        return None
    room_seed = _check_len(result.get("room_seed"), 30, 300)
    description = _check_len(result.get("description"), 60, 500)
    if room_seed is None or description is None:
        return None
    raw_objects = result.get("objects", [])
    if raw_objects is None:
        raw_objects = []
    if not isinstance(raw_objects, list) or len(raw_objects) > 2:
        return None  # >2 rejects; a trimmed list would hide a drifting model
    cleaned_objects: list[dict] = []
    for entry in raw_objects:
        if not isinstance(entry, dict):
            return None
        name = _check_len(entry.get("name"), 3, 30)
        seed = _check_len(entry.get("seed"), 15, 200)
        if name is None or seed is None:
            return None
        cleaned_objects.append({"name": name, "seed": seed})
    # WHIMSY banlist over every text field.
    all_text = " ".join(
        [title, room_seed, description]
        + [f"{o['name']} {o['seed']}" for o in cleaned_objects]
    )
    if safety.first_banned(all_text) is not None:
        return None
    # Anti-copy tripwire: the composition must not BE an exemplar. Exact
    # normalized match on any exemplar's title / seed / description; the
    # softer "how distinct is it" measure lives in the tier_long probe.
    for ex in growth.get("exemplars") or []:
        if _norm(title) == _norm(ex.get("title", "")):
            return None
        if _norm(room_seed) == _norm(ex.get("seed", "")):
            return None
        if _norm(description) == _norm(ex.get("description", "")):
            return None
    return {
        "title": title, "room_seed": room_seed,
        "description": description, "objects": cleaned_objects,
    }


# ---- helpers -------------------------------------------------------------


def _narrate(room_id: str, text: str) -> None:
    events.append("system", None, "narrate", {"text": text}, room_id=room_id)


def _free_direction(room: "rooms.Room") -> str | None:
    for d in _DIRECTIONS:
        if d not in room.exits:
            return d
    return None


def _direction_phrase(direction: str) -> str:
    return {"up": "above you", "down": "below you"}.get(
        direction, f"to the {direction}"
    )


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "grown-place"


def _unique_slug_and_id(world_id: str, title: str) -> tuple[str, str]:
    """A slug (and its `r-<slug>` id) free in BOTH namespaces — room slugs and
    object ids — suffixing -2, -3, ... on collision, so a rival plant landing
    the same title mid-await never collides at commit."""
    base = _slugify(title)
    slug = base
    n = 2
    while (
        objects.by_slug(world_id, slug) is not None
        or objects.get(f"r-{slug}") is not None
    ):
        slug = f"{base}-{n}"
        n += 1
    return slug, f"r-{slug}"


def _husk_text(growth: dict) -> str:
    husk = growth.get("husk_text")
    if isinstance(husk, str) and husk.strip():
        return husk.strip()
    return _HUSK_DEFAULT


# ---- the pipeline ---------------------------------------------------------


async def execute_plant(
    actor: "objects.Object",
    room_id: str,
    seed: "objects.Object",
    args: str,
    allowed: frozenset[str],
) -> None:
    """Run the full plant pipeline for `actor` planting `seed` in `room_id`
    with vision phrase `args`, dispatching effects through the verb's
    `allowed` set. Emits events as its only side effects."""
    world_id = actor.world_id
    phrase = args.strip()

    # ---- gates (pre-LLM; every refusal is free and mutates nothing) ----
    if seed.location_id != actor.id:
        _narrate(room_id, _NOT_CARRIED)
        return
    if seed.properties.get("state") == "spent":
        _narrate(room_id, _SPENT)
        return
    growth = seed.properties.get("growth")
    if not _growth_shape_ok(growth):
        _narrate(room_id, _NO_GROWTH)
        return
    if rooms.grown_room_count(world_id) >= config.growth_max_rooms():
        _narrate(room_id, _CAP_REACHED)
        return
    room = rooms.get_room(room_id)
    if room is None:
        _narrate(room_id, _WONT_HOLD_YET)
        return
    if _free_direction(room) is None:
        _narrate(room_id, _NO_DIRECTION)
        return
    if not phrase:
        # The typed two-turn path: ask the seed's authored question and wait
        # for the player's next input. No session state; the next `plant ...`
        # carries the answer.
        question = growth.get("question")
        _narrate(
            room_id,
            question if isinstance(question, str) and question.strip()
            else "Where does the new way lead?",
        )
        return
    if len(phrase) > MAX_PHRASE_CHARS:
        _narrate(room_id, _PHRASE_TOO_LONG)
        return
    if safety.first_banned(phrase) is not None:
        _narrate(room_id, _OFF_TONE)
        return

    # ---- compose: the single LLM call ----
    try:
        result = await client.acompletion_json(
            system=GROWTH_SYSTEM,
            user=_user_prompt(growth, room, phrase),
            max_tokens=450,
            timeout=30.0,
        )
    except client.LLMUnavailable as e:
        logger.warning("plant: LLM unavailable: %s", e)
        _narrate(room_id, _FOGGY)
        return

    refusal = safety.parse_refusal(result)
    if refusal is not None:
        _narrate(room_id, refusal.reason)
        return

    composition = validate_growth_output(result, growth)
    if composition is None:
        logger.info("plant: composition rejected by validation")
        _narrate(room_id, _WONT_HOLD_YET)
        return

    _commit_growth(actor.id, seed.id, phrase, composition, allowed)


def _commit_growth(
    actor_id: str,
    seed_id: str,
    phrase: str,
    composition: dict,
    allowed: frozenset[str],
) -> None:
    """The post-LLM synchronous commit block: NO awaits from the first
    re-check to the last effect, so nothing can interleave (asyncio is
    cooperative). Re-checks every gate the LLM await could have raced —
    a re-check failure narrates in character and mutates nothing."""
    actor = objects.get(actor_id)
    if actor is None:
        return
    world_id = actor.world_id
    current_room_id = actor.location_id or ""
    seed = objects.get(seed_id)  # re-read: the await may have moved/spent it
    if seed is None or seed.location_id != actor_id:
        _narrate(current_room_id, _NOT_CARRIED)
        return
    if seed.properties.get("state") == "spent":
        _narrate(current_room_id, _SPENT)
        return
    growth = seed.properties.get("growth")
    if not isinstance(growth, dict):
        _narrate(current_room_id, _NO_GROWTH)
        return
    if rooms.grown_room_count(world_id) >= config.growth_max_rooms():
        _narrate(current_room_id, _CAP_REACHED)
        return
    room = rooms.get_room(current_room_id)
    if room is None:
        _narrate(current_room_id, _WONT_HOLD_YET)
        return
    direction = _free_direction(room)  # re-pick: a rival plant may have won ours
    if direction is None:
        _narrate(current_room_id, _NO_DIRECTION)
        return

    slug, new_room_id = _unique_slug_and_id(world_id, composition["title"])
    provenance = f"plant:{seed_id}"
    grown = {
        "seed_id": seed_id,
        "planter_id": actor_id,
        "phrase": phrase,
        "at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }

    # One ordered effect batch, with a structural checkpoint: the room + exit
    # pair must both land before anything consumes the seed, so a programming
    # bug can never leave a spent-but-roomless seed or a half-linked exit.
    structural: list[dict] = [
        {"kind": "spawn_room", "room_id": new_room_id, "slug": slug,
         "title": composition["title"], "seed": composition["room_seed"],
         "description": composition["description"],
         "properties": {"generated_by": provenance, "grown": grown}},
        {"kind": "link_exit", "from_room_id": current_room_id,
         "to_room_id": new_room_id, "direction": direction,
         "reverse_direction": _REVERSE[direction]},
    ]
    applied = effects.dispatch_effects(
        structural, actor_id=actor_id, room_id=current_room_id,
        world_id=world_id, allowed=allowed,
    )
    if any(
        a.event is None or a.event.kind not in ("room_grown", "exit_linked")
        for a in applied
    ):
        logger.error(
            "plant: structural effects failed post-recheck (room=%s slug=%s); "
            "seed preserved", new_room_id, slug,
        )
        _narrate(current_room_id, _WONT_HOLD_YET)
        return

    consume: list[dict] = []
    for obj in composition["objects"]:
        consume.append({
            "kind": "spawn_object", "name": obj["name"], "seed": obj["seed"],
            "location_id": new_room_id, "generated_by": provenance,
        })
    consume.extend([
        {"kind": "set_property", "target_id": seed_id, "key": "state",
         "value": "spent"},
        {"kind": "set_property", "target_id": seed_id, "key": "examined_text",
         "value": _husk_text(growth)},
        # Drop the per-object `plant` grant; the husk keeps its prototype
        # verbs (examine / take / drop / give) but is no longer plantable.
        {"kind": "set_property", "target_id": seed_id, "key": "verbs",
         "value": []},
        {"kind": "move_object", "object_id": seed_id, "dest_id": new_room_id},
        {"kind": "narrate", "text": (
            f"The dreamseed takes root, and the dream makes room. A new way "
            f"opens {_direction_phrase(direction)}: {composition['title']}."
        )},
    ])
    effects.dispatch_effects(
        consume, actor_id=actor_id, room_id=current_room_id,
        world_id=world_id, allowed=allowed,
    )
