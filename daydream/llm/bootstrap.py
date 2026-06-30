"""World-bootstrap: author a fresh daydream world via Claude Opus 4.7.

Implements the SPEC 2026-05-07 world-bootstrap-opus contract. The
operator runs ``bin/game world bootstrap NAME --aesthetic "..."``;
this module calls Anthropic Opus 4.7 via litellm with a tight prompt
that produces a strict-JSON envelope describing 5 rooms, 4 toons,
items per room, and 2 starter data skills. The envelope is validated
against the criterion 3 schema and then INSERTed into a fresh SQLite
file at the chosen output path.

The bootstrapped DB REPLACES the seeded ``w-bunny`` content (the
canonical world id stays ``w-bunny`` so existing hardcoded references
in ``daydream/api/ws.py`` etc. continue to work; only the
human-readable ``worlds.name`` changes). Activation is operator-manual
at v1: copy the file over ``live.db`` after ``bin/game down``.

API key: reads ``ANTHROPIC_API_KEY`` from env (litellm convention).
No ``api_base`` override; litellm picks Anthropic's default endpoint.
Cost is ~$0.40-$0.80 per bootstrap at Opus 4.7 pricing.

Tests mock ``litellm.acompletion`` at the module boundary; no real
network call ever happens in the suite."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from daydream import config, db

logger = logging.getLogger(__name__)


# ---- exceptions --------------------------------------------------------


class BootstrapError(Exception):
    """Base for bootstrap failures."""


class BootstrapLLMError(BootstrapError):
    """LLM call failed: missing API key, network error, rate limit,
    timeout, or any other backend failure. Mapped to CLI exit code 2."""


class BootstrapValidationError(BootstrapError):
    """Parsed JSON didn't match the criterion 3 schema. Mapped to CLI
    exit code 3."""


class BootstrapOutputExistsError(BootstrapError):
    """Output path exists and ``force=False``. Mapped to CLI exit
    code 4."""


# ---- prompt ------------------------------------------------------------

_SYSTEM_PROMPT = """You are an authoring assistant for a cozy multiplayer text-adventure called daydream. Your job is to design a small new world the operator will play in.

Aesthetic anchor: cozy, soft, painterly. Spiritfarer / A Short Hike-adjacent. Warm late-day light. Watercolor edges. NEVER pixel art, NEVER 8-bit, NEVER grimdark, NEVER urgent, NEVER modern tech, NEVER violence, NEVER sexual content, NEVER sarcasm at the player.

Return STRICT JSON matching this schema (no prose, no markdown, no commentary — just the JSON object):

{
  "world": {"name": <human-readable name>, "aesthetic_seed": <one-sentence aesthetic description>},
  "rooms": [
    {"slug": <kebab-case>, "title": <Title Case>, "seed": <one-paragraph room description, painterly>, "exits": {<direction>: <other room slug>, ...}}
    /* exactly 5 rooms; bidirectional exits — every exit must have a return path from the destination room back to the source */
  ],
  "toons": [
    {"slot": <int>, "name": <single word>, "seed": <one-sentence persona>, "appearance_seed": <one-sentence appearance>, "current_room_slug": <slug from rooms[]>, "is_human_controlled": 0 | 1, "mood": <one word like 'curious'/'content'/'thoughtful'>, "presence_text": <one-sentence greeting that fires when the player enters the room, OR null>}
    /* exactly 4 toons. Slots 1-5 for human-controllable toons; slots 100+ for NPCs. Typically 1 human-claimable in slot 1 + 3 NPCs in slots 100, 101, 102. */
  ],
  "items": [
    {"room_slug": <slug from rooms[]>, "name": <noun phrase>, "seed": <one-sentence description, painterly>}
    /* zero or more, distributed across rooms */
  ],
  "skills": [
    {"name": <kebab-case>, "ui_hint": <Title Case verb>, "description": <one-sentence affordance>, "context_predicate": {"room_slug": <slug>}, "prompt_template": <Jinja template with {{ player_input }} role-separator and ambient grounding>, "effects_schema": {"allowed_kinds": ["narrate"], "note": <optional>}}
    /* exactly 2 starter data skills. Each is room-anchored via context_predicate.room_slug. Templates should match the watercolor tone and end with a refusal branch. */
  ]
}

Constraints:
- Slot uniqueness: every toon's slot is distinct.
- Room uniqueness: every slug is distinct.
- Exits: every "north"/"south"/"east"/"west"/"up"/"down" key in a room's exits points to a slug present in rooms[]. For every (A → direction → B) edge, B must have SOME exit direction back to A (need not be the geometric inverse).
- Tone: every text field is on-aesthetic. No urgency, no modern tech, no harsh edges.
- Concision: rooms.seed is 1-2 sentences; toons.seed is one sentence; items.seed is one sentence.

Output ONLY the JSON object. No prose before or after."""


_USER_PROMPT_TEMPLATE = """Aesthetic for the new world: {aesthetic}

World name: {name}

Author the JSON envelope per the schema."""


# ---- the public function ----------------------------------------------


def bootstrap_world(
    name: str,
    aesthetic: str,
    output_path: Path,
    *,
    model: str = "anthropic/claude-opus-4-7",
    force: bool = False,
) -> Path:
    """Author a new daydream world via Opus 4.7 and write a fresh SQLite
    file at ``output_path``. Returns the output path on success.

    Raises:
    - ``BootstrapOutputExistsError`` if ``output_path`` exists and
      ``force=False``.
    - ``BootstrapLLMError`` if the LLM call fails (no API key, network
      error, malformed model name).
    - ``BootstrapValidationError`` if the LLM returned invalid JSON or
      the JSON didn't match the criterion 3 schema.

    The output DB has the full migration chain applied, the seeded
    ``w-bunny`` content removed, and the bootstrapped content INSERTed
    under ``world_id='w-bunny'``. Connection is closed before return."""
    output_path = Path(output_path).expanduser().resolve()
    if output_path.exists() and not force:
        raise BootstrapOutputExistsError(
            f"output path exists: {output_path} (pass --force to overwrite)"
        )
    envelope = _call_llm(name, aesthetic, model)
    # Reuse the keyless validate + write path. The exists-check already ran
    # above (before spending the LLM call), so force here.
    return load_world(name, envelope, output_path, force=True)


def load_world(
    name: str, envelope: dict, output_path: Path, *, force: bool = False
) -> Path:
    """Build a fresh daydream world DB from an already-authored JSON envelope
    (the same schema bootstrap_world's LLM produces). NO LLM call, NO API key,
    NO network: this is the keyless authoring path — Opus authors the envelope
    inside a Claude Code session, this writes it to a SQLite file. Returns the
    output path.

    Raises BootstrapOutputExistsError (output exists and not force) and
    BootstrapValidationError (envelope fails the schema)."""
    output_path = Path(output_path).expanduser().resolve()
    if output_path.exists() and not force:
        raise BootstrapOutputExistsError(
            f"output path exists: {output_path} (pass --force to overwrite)"
        )
    spec = _validate_envelope(envelope)
    if output_path.exists():
        output_path.unlink()
    _write_db(output_path, spec, name)
    return output_path


def _call_llm(name: str, aesthetic: str, model: str) -> dict:
    """Run the LLM call synchronously (wraps async litellm) and return
    the parsed JSON envelope. Raises BootstrapLLMError on backend
    failures and BootstrapValidationError on parse failures."""
    try:
        text = asyncio.run(_async_call_llm(name, aesthetic, model))
    except BootstrapError:
        raise
    except Exception as e:
        raise BootstrapLLMError(f"LLM call failed: {e}") from e
    text = _strip_code_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise BootstrapValidationError(
            f"LLM returned non-JSON: {e}; first 200 chars: {text[:200]!r}"
        ) from e


async def _async_call_llm(name: str, aesthetic: str, model: str) -> str:
    """Async wrapper around ``litellm.acompletion`` so the public
    surface stays sync. Imports litellm lazily so a missing dep doesn't
    crash the module's import (relevant during test collection on a
    no-litellm dev box, though daydream pins litellm in pyproject)."""
    import litellm

    user = _USER_PROMPT_TEMPLATE.format(aesthetic=aesthetic, name=name)
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            max_tokens=8192,
        )
    except Exception as e:
        raise BootstrapLLMError(f"litellm.acompletion failed: {e}") from e
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError) as e:
        raise BootstrapLLMError(f"LLM response missing message content: {e}") from e


_FENCE_RE = re.compile(r"^```(?:json)?\s*(.+?)\s*```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Some Anthropic responses wrap JSON in a ```json ... ``` fence
    despite the system prompt saying not to. Strip leading/trailing
    fences before json.loads. Pass-through on non-fenced content."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    return text


# ---- validator ---------------------------------------------------------


@dataclass(frozen=True)
class WorldSpec:
    """Validated world content ready for INSERT. Mirrors the LLM
    envelope but with normalized types + downstream-ready ids."""

    world_name: str
    aesthetic_seed: str
    rooms: list[dict]
    toons: list[dict]
    items: list[dict]
    skills: list[dict]


def _validate_envelope(env: dict) -> WorldSpec:
    """Strict validation of the LLM's JSON envelope. Raises
    BootstrapValidationError with a one-line operator-facing message
    on the first violation."""
    if not isinstance(env, dict):
        raise BootstrapValidationError(
            f"envelope must be a JSON object, got {type(env).__name__}"
        )
    for top in ("world", "rooms", "toons", "items", "skills"):
        if top not in env:
            raise BootstrapValidationError(f"envelope missing top-level key: {top!r}")

    world = env["world"]
    if not isinstance(world, dict) or not isinstance(world.get("name"), str) \
            or not isinstance(world.get("aesthetic_seed"), str):
        raise BootstrapValidationError(
            "world must be an object with string 'name' and 'aesthetic_seed'"
        )

    rooms = env["rooms"]
    if not isinstance(rooms, list) or len(rooms) != 5:
        raise BootstrapValidationError(
            f"rooms must be a list of exactly 5 entries (got {len(rooms) if isinstance(rooms, list) else type(rooms).__name__})"
        )
    seen_slugs: set[str] = set()
    for i, r in enumerate(rooms):
        if not isinstance(r, dict):
            raise BootstrapValidationError(f"rooms[{i}] is not an object")
        for k in ("slug", "title", "seed"):
            if not isinstance(r.get(k), str) or not r[k].strip():
                raise BootstrapValidationError(f"rooms[{i}].{k} must be a non-empty string")
        if r["slug"] in seen_slugs:
            raise BootstrapValidationError(f"rooms[{i}].slug duplicate: {r['slug']!r}")
        seen_slugs.add(r["slug"])
        exits = r.get("exits", {})
        if not isinstance(exits, dict):
            raise BootstrapValidationError(f"rooms[{i}].exits must be an object")
        for d, target in exits.items():
            if not isinstance(d, str) or not isinstance(target, str):
                raise BootstrapValidationError(
                    f"rooms[{i}].exits has non-string direction or target"
                )
    # Exit consistency: every exit's target is a known slug, and every
    # (A → B) edge has at least one (B → A) edge somewhere.
    by_slug = {r["slug"]: r for r in rooms}
    edges: set[tuple[str, str]] = set()
    for r in rooms:
        for d, target in r["exits"].items():
            if target not in by_slug:
                raise BootstrapValidationError(
                    f"room {r['slug']!r} exit {d!r} points to unknown slug {target!r}"
                )
            edges.add((r["slug"], target))
    for src, dst in edges:
        if (dst, src) not in edges:
            raise BootstrapValidationError(
                f"room {src!r} → {dst!r} has no return path"
            )

    toons = env["toons"]
    if not isinstance(toons, list) or len(toons) != 4:
        raise BootstrapValidationError(
            f"toons must be a list of exactly 4 entries (got {len(toons) if isinstance(toons, list) else type(toons).__name__})"
        )
    seen_slots: set[int] = set()
    for i, t in enumerate(toons):
        if not isinstance(t, dict):
            raise BootstrapValidationError(f"toons[{i}] is not an object")
        slot = t.get("slot")
        if not isinstance(slot, int) or not (1 <= slot <= 5 or slot >= 100):
            raise BootstrapValidationError(
                f"toons[{i}].slot must be int in 1..5 or 100+; got {slot!r}"
            )
        if slot in seen_slots:
            raise BootstrapValidationError(f"toons[{i}].slot duplicate: {slot}")
        seen_slots.add(slot)
        for k in ("name", "seed", "appearance_seed", "current_room_slug", "mood"):
            if not isinstance(t.get(k), str) or not t[k].strip():
                raise BootstrapValidationError(f"toons[{i}].{k} must be a non-empty string")
        if t["current_room_slug"] not in by_slug:
            raise BootstrapValidationError(
                f"toons[{i}].current_room_slug {t['current_room_slug']!r} not in rooms"
            )
        if t.get("is_human_controlled") not in (0, 1):
            raise BootstrapValidationError(
                f"toons[{i}].is_human_controlled must be 0 or 1; got {t.get('is_human_controlled')!r}"
            )
        # presence_text is optional (None or str)
        pres = t.get("presence_text")
        if pres is not None and not isinstance(pres, str):
            raise BootstrapValidationError(
                f"toons[{i}].presence_text must be string or null"
            )

    items = env["items"]
    if not isinstance(items, list):
        raise BootstrapValidationError("items must be a list")
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise BootstrapValidationError(f"items[{i}] is not an object")
        for k in ("room_slug", "name", "seed"):
            if not isinstance(it.get(k), str) or not it[k].strip():
                raise BootstrapValidationError(f"items[{i}].{k} must be a non-empty string")
        if it["room_slug"] not in by_slug:
            raise BootstrapValidationError(
                f"items[{i}].room_slug {it['room_slug']!r} not in rooms"
            )

    skills = env["skills"]
    if not isinstance(skills, list) or len(skills) != 2:
        raise BootstrapValidationError(
            f"skills must be a list of exactly 2 entries (got {len(skills) if isinstance(skills, list) else type(skills).__name__})"
        )
    seen_skill_names: set[str] = set()
    for i, s in enumerate(skills):
        if not isinstance(s, dict):
            raise BootstrapValidationError(f"skills[{i}] is not an object")
        for k in ("name", "ui_hint", "description", "prompt_template"):
            if not isinstance(s.get(k), str) or not s[k].strip():
                raise BootstrapValidationError(f"skills[{i}].{k} must be a non-empty string")
        if s["name"] in seen_skill_names:
            raise BootstrapValidationError(f"skills[{i}].name duplicate: {s['name']!r}")
        seen_skill_names.add(s["name"])
        if not isinstance(s.get("context_predicate"), dict):
            raise BootstrapValidationError(
                f"skills[{i}].context_predicate must be an object"
            )
        if not isinstance(s.get("effects_schema"), dict):
            raise BootstrapValidationError(
                f"skills[{i}].effects_schema must be an object"
            )

    return WorldSpec(
        world_name=world["name"],
        aesthetic_seed=world["aesthetic_seed"],
        rooms=rooms,
        toons=toons,
        items=items,
        skills=skills,
    )


# ---- DB writer ---------------------------------------------------------


def _short_uuid() -> str:
    return uuid.uuid4().hex[:8]


def _write_db(output_path: Path, spec: WorldSpec, world_display_name: str) -> None:
    """Apply migrations to a fresh DB at ``output_path``, delete the
    seeded w-bunny content, and INSERT the bootstrapped spec under
    world_id='w-bunny'. Closes the connection before returning."""
    conn = db.open_db(output_path)
    try:
        db.init_schema(conn, config.MIGRATIONS_DIR)

        # Wipe the seeded w-bunny content. Order matters for FK
        # integrity (children before parents). The toons table FK
        # references rooms; items reference rooms (and optionally
        # toons via inventory_json — but that's JSON, not FK); skills
        # are not FK-bound to world but are filtered by world via
        # context_predicate's room_slug, so deletion is wholesale.
        # generated_assets and memories cascade via world_id.
        cur = conn.cursor()
        cur.execute("DELETE FROM memories WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM generated_assets WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM items WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM toons WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM rooms WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM skills")  # data skills are global; clear any pre-installed
        cur.execute("DELETE FROM worlds WHERE id = 'w-bunny'")

        # Insert the new world record. Slug derived from the operator's
        # NAME (which is already kebab-case via the CLI contract).
        slug = re.sub(r"[^a-z0-9-]+", "-", world_display_name.lower()).strip("-")
        cur.execute(
            "INSERT INTO worlds (id, name, slug, aesthetic_seed) VALUES (?, ?, ?, ?)",
            ("w-bunny", spec.world_name, slug or "bootstrapped", spec.aesthetic_seed),
        )

        # Build slug→id map first so exits_json can reference room ids.
        slug_to_room_id: dict[str, str] = {
            r["slug"]: f"r-{r['slug']}" for r in spec.rooms
        }
        for r in spec.rooms:
            # Translate exits {direction: slug} → {direction: room_id}
            # to match the existing schema convention (migration 004
            # stores exits_json keyed by room id, e.g. 'r-forge').
            exits_with_ids = {
                d: slug_to_room_id[target] for d, target in r["exits"].items()
            }
            cur.execute(
                "INSERT INTO rooms (id, world_id, slug, title, seed, description_cached, exits_json) "
                "VALUES (?, 'w-bunny', ?, ?, ?, NULL, ?)",
                (
                    slug_to_room_id[r["slug"]],
                    r["slug"],
                    r["title"],
                    r["seed"],
                    json.dumps(exits_with_ids),
                ),
            )

        # Toons. Convert exits_json sluggraph to room_id graph in
        # update steps below.
        for t in spec.toons:
            toon_slug = re.sub(r"[^a-z0-9-]+", "-", t["name"].lower()).strip("-") or "toon"
            toon_id = f"t-{toon_slug}-{_short_uuid()}"
            cur.execute(
                "INSERT INTO toons (id, world_id, slot, name, seed, appearance_seed, "
                "current_room_id, is_human_controlled, controller_session, "
                "inventory_json, mood, kicked_at, presence_text) "
                "VALUES (?, 'w-bunny', ?, ?, ?, ?, ?, ?, NULL, '[]', ?, NULL, ?)",
                (
                    toon_id,
                    t["slot"],
                    t["name"],
                    t["seed"],
                    t["appearance_seed"],
                    slug_to_room_id[t["current_room_slug"]],
                    int(t["is_human_controlled"]),
                    t["mood"],
                    t.get("presence_text"),
                ),
            )

        # Items.
        for it in spec.items:
            cur.execute(
                "INSERT INTO items (id, world_id, name, seed, room_id, properties_json, is_unique) "
                "VALUES (?, 'w-bunny', ?, ?, ?, '{}', 0)",
                (f"i-{_short_uuid()}", it["name"], it["seed"], slug_to_room_id[it["room_slug"]]),
            )

        # Data skills. id convention mirrors admin.cmd_skill_add
        # (`skill-<name>`); author tagged 'opus-bootstrap' so an
        # operator can later distinguish bootstrapped skills from
        # hand-authored ones.
        for s in spec.skills:
            cur.execute(
                "INSERT INTO skills (id, name, kind, context_predicate_json, "
                "prompt_template, ui_hint, description, effects_schema_json, "
                "author, enabled) "
                "VALUES (?, ?, 'data', ?, ?, ?, ?, ?, ?, 1)",
                (
                    f"skill-{s['name']}",
                    s["name"],
                    json.dumps(s["context_predicate"]),
                    s["prompt_template"],
                    s["ui_hint"],
                    s["description"],
                    json.dumps(s["effects_schema"]),
                    "opus-bootstrap",
                ),
            )
    finally:
        conn.close()
