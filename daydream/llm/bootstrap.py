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

from daydream import config, db, version

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
    {"slot": <int>, "name": <single word>, "seed": <one-sentence persona>, "appearance_seed": <one-sentence appearance>, "current_room_slug": <slug from rooms[]>, "is_human_controlled": 0 | 1, "mood": <one word like 'curious'/'content'/'thoughtful'>, "presence_text": <one-sentence greeting that fires when the player enters the room, OR null>, "properties": <OPTIONAL quest state, e.g. {"wants": <item name>, "gives": {"name": <reward>, "seed": <desc>, "aliases": [<...>], "verbs": ["use"]}, "gives_text": <line when the gift is accepted>, "gives_mood": <the NPC's new one-word mood>}>}
    /* exactly 4 toons. Slots 1-5 for human-controllable toons; slots 100+ for NPCs. Typically 1 human-claimable in slot 1 + 3 NPCs in slots 100, 101, 102. */
  ],
  "items": [
    {"room_slug": <slug from rooms[]>, "name": <noun phrase>, "seed": <one-sentence description, painterly>, "aliases": <OPTIONAL [other names]>, "readable": <OPTIONAL true if it has words>, "text": <OPTIONAL the words to read>, "fixture": <OPTIONAL true if immovable furniture — examine only, no take>, "verbs": <OPTIONAL per-object affordances like ["open"] or ["use"]>, "properties": <OPTIONAL stateful-object block, e.g. {"state": "locked", "state_text": {"locked": <look>, "unlocked": <look>, "open": <look>}, "locked_text": <refusal>, "open_text": <payoff>, "use": {"with": <item name>, "from_state": "locked", "to_state": "unlocked", "text": <transition line>}, "contains": {"name": <reward>, "seed": <desc>}}>}
    /* zero or more, distributed across rooms. The optional blocks author stateful interactive objects (a lockable case, a readable ledger). Cross-references (use.with, a toon's wants) are BY NAME. */
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
    # Format-2 envelopes (platform turn, SPEC 2026-07-02) take the new loader;
    # this v1 path stays byte-identical for existing worlds.
    if isinstance(envelope, dict) and envelope.get("format") == 2:
        from daydream.llm import format2

        return format2.load_world2(envelope, output_path, force=force)
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


def _validate_aliases(aliases: object, where: str) -> None:
    """Optional `aliases`: when present, a list of non-empty strings."""
    if aliases is None:
        return
    if not isinstance(aliases, list) or not all(
        isinstance(a, str) and a.strip() for a in aliases
    ):
        raise BootstrapValidationError(f"{where} must be a list of non-empty strings")


def _validate_optional_verbs(verbs: object, where: str) -> None:
    """Optional per-object `verbs`: when present, a list of non-empty strings
    (per-object affordance additions like `open` / `use` / `read`)."""
    if verbs is None:
        return
    if not isinstance(verbs, list) or not all(
        isinstance(v, str) and v.strip() for v in verbs
    ):
        raise BootstrapValidationError(f"{where} must be a list of non-empty strings")


def _validate_contains(contains: object, where: str) -> None:
    """Optional `contains` on a stateful thing: the payload `open` reveals.
    A single object or a list of them (SPEC 2026-07-02). Each entry requires
    non-empty `name` + `seed`; optional `aliases` / `verbs` / `readable` /
    `properties` (whose nested growth-relevant keys validate recursively, so a
    dreamseed inside a clock case fails loudly at load, not at plant time)."""
    if contains is None:
        return
    if not isinstance(contains, (dict, list)):
        raise BootstrapValidationError(
            f"{where} must be an object or a list of objects"
        )
    entries = contains if isinstance(contains, list) else [contains]
    for j, entry in enumerate(entries):
        w = f"{where}[{j}]" if isinstance(contains, list) else where
        if not isinstance(entry, dict):
            raise BootstrapValidationError(f"{w} must be an object")
        for k in ("name", "seed"):
            if not isinstance(entry.get(k), str) or not entry[k].strip():
                raise BootstrapValidationError(f"{w}.{k} must be a non-empty string")
        _validate_aliases(entry.get("aliases"), f"{w}.aliases")
        _validate_optional_verbs(entry.get("verbs"), f"{w}.verbs")
        if "readable" in entry and not isinstance(entry["readable"], bool):
            raise BootstrapValidationError(f"{w}.readable must be a boolean")
        if "properties" in entry:
            if not isinstance(entry["properties"], dict):
                raise BootstrapValidationError(f"{w}.properties must be an object")
            _validate_growth_keys(entry["properties"], w)


def _validate_exemplar_rooms(value: object, where: str, lo: int, hi: int) -> None:
    """A list of `lo`-`hi` exemplar/skeleton rooms, each with non-empty
    title / seed / description strings."""
    if not isinstance(value, list) or not (lo <= len(value) <= hi):
        raise BootstrapValidationError(
            f"{where} must be a list of {lo}-{hi} rooms"
        )
    for j, ex in enumerate(value):
        if not isinstance(ex, dict):
            raise BootstrapValidationError(f"{where}[{j}] must be an object")
        for k in ("title", "seed", "description"):
            if not isinstance(ex.get(k), str) or not ex[k].strip():
                raise BootstrapValidationError(
                    f"{where}[{j}].{k} must be a non-empty string"
                )


def _validate_growth(growth: object, where: str) -> None:
    """A dreamseed's authored growth boundaries (SPEC 2026-07-02), fail-loudly
    validated at load so a malformed seed never reaches the runtime. Required:
    `question` (str), `theme` (1-8 strings), `palette` (str), `exemplars` (1-3
    rooms of title/seed/description). Optional: `motifs` (0-8 strings),
    `skeletons` (0-3 rooms — the rung-(b) select-and-fill templates, validated
    from day one so flipping rungs never touches the loader). Unknown keys are
    tolerated (a future `depth`)."""
    if not isinstance(growth, dict):
        raise BootstrapValidationError(f"{where} must be an object")
    if not isinstance(growth.get("question"), str) or not growth["question"].strip():
        raise BootstrapValidationError(f"{where}.question must be a non-empty string")
    theme = growth.get("theme")
    if not isinstance(theme, list) or not (1 <= len(theme) <= 8) or not all(
        isinstance(t, str) and t.strip() for t in theme
    ):
        raise BootstrapValidationError(
            f"{where}.theme must be a list of 1-8 non-empty strings"
        )
    if not isinstance(growth.get("palette"), str) or not growth["palette"].strip():
        raise BootstrapValidationError(f"{where}.palette must be a non-empty string")
    motifs = growth.get("motifs")
    if motifs is not None and (
        not isinstance(motifs, list) or len(motifs) > 8
        or not all(isinstance(m, str) and m.strip() for m in motifs)
    ):
        raise BootstrapValidationError(
            f"{where}.motifs must be a list of 0-8 non-empty strings"
        )
    _validate_exemplar_rooms(growth.get("exemplars"), f"{where}.exemplars", 1, 3)
    if growth.get("skeletons") is not None:
        _validate_exemplar_rooms(growth["skeletons"], f"{where}.skeletons", 0, 3)


def _validate_growth_keys(props: dict, where: str) -> None:
    """Validate the growth-relevant keys of an authored `properties` dict:
    `contains` (a reveal payload, recursively) and `growth` (a dreamseed's
    boundaries). Other property keys stay free-form."""
    if "contains" in props:
        _validate_contains(props["contains"], f"{where}.properties.contains")
    if "growth" in props:
        _validate_growth(props["growth"], f"{where}.properties.growth")


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
        _validate_aliases(t.get("aliases"), f"toons[{i}].aliases")
        # Optional NPC quest-state passthrough (wants / gives / gives_text / ...).
        if "properties" in t and not isinstance(t["properties"], dict):
            raise BootstrapValidationError(f"toons[{i}].properties must be an object")
        # Optional per-NPC `talk` dialogue binding: a {prompt_template, ...}
        # the loader installs as a data skill and references from the object.
        dlg = t.get("dialogue")
        if dlg is not None:
            if not isinstance(dlg, dict) or not isinstance(dlg.get("prompt_template"), str) \
                    or not dlg["prompt_template"].strip():
                raise BootstrapValidationError(
                    f"toons[{i}].dialogue must be an object with a non-empty 'prompt_template'"
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
        _validate_aliases(it.get("aliases"), f"items[{i}].aliases")
        # Optional stateful-interactive-object fields (SPEC 2026-07-01): a
        # `properties` passthrough, per-object `verbs`, readable `text`, and the
        # `fixture` / `readable` prototype flags. A malformed field fails loudly.
        if "properties" in it and not isinstance(it["properties"], dict):
            raise BootstrapValidationError(f"items[{i}].properties must be an object")
        if isinstance(it.get("properties"), dict):
            # Growth-relevant property keys (`contains` payloads, a dreamseed's
            # `growth` block) fail loudly at load (SPEC 2026-07-02).
            _validate_growth_keys(it["properties"], f"items[{i}]")
        _validate_optional_verbs(it.get("verbs"), f"items[{i}].verbs")
        if "text" in it and not isinstance(it["text"], str):
            raise BootstrapValidationError(f"items[{i}].text must be a string")
        for flag in ("fixture", "readable"):
            if flag in it and not isinstance(it[flag], bool):
                raise BootstrapValidationError(f"items[{i}].{flag} must be a boolean")

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


def _proto_id(kind: str) -> str:
    """Prototype id for an archetype name. Single-world-per-DB at v0, so the
    bare ids do not collide (mirrors migration 011)."""
    return f"proto-{kind}"


# Default verb sets per archetype. `give` rides on every takeable thing (you can
# hand anything you carry to someone); `read` on readables (words on a page); a
# `fixture` is immovable (examine only) — you can't pocket a town clock. Stateful
# affordances (`open`, `use`) stay per-object so an object's offered verbs remain
# a meaningful hint, not noise on every thing.
_PROTOTYPES: tuple[tuple[str, list[str]], ...] = (
    ("room", ["look"]),
    ("npc", ["examine", "talk"]),
    ("thing", ["examine", "take", "drop", "give", "put"]),
    ("readable", ["examine", "take", "drop", "give", "put", "read"]),
    ("fixture", ["examine"]),
)


def _write_db(output_path: Path, spec: WorldSpec, world_display_name: str) -> None:
    """Apply migrations to a fresh DB at ``output_path``, delete the seeded
    w-bunny content, and INSERT the bootstrapped spec onto the unified
    ``objects`` schema (migration 011) under world_id='w-bunny'. Closes the
    connection before returning."""
    conn = db.open_db(output_path)
    try:
        db.init_schema(conn, config.MIGRATIONS_DIR)

        # Wipe the seeded w-bunny content. `objects` holds rooms / toons /
        # things / prototypes; deleting the whole world clears them in one
        # statement (the self-referential FKs are satisfied because the
        # entire world goes at once). generated_assets + memories cascade via
        # world_id; skills are global, cleared wholesale.
        cur = conn.cursor()
        cur.execute("DELETE FROM memories WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM generated_assets WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM objects WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM skills")  # data skills are global; clear any pre-installed
        cur.execute("DELETE FROM worlds WHERE id = 'w-bunny'")

        # Insert the new world record. Slug derived from the operator's
        # NAME (which is already kebab-case via the CLI contract).
        slug = re.sub(r"[^a-z0-9-]+", "-", world_display_name.lower()).strip("-")
        # Stamp the world with THIS code's WORLD_VERSION at load time, so the
        # freshly loaded world matches the running code and the boot gate
        # (version.check_world_compat) only fires once the code's version later
        # moves ahead of it.
        cur.execute(
            "INSERT INTO worlds (id, name, slug, aesthetic_seed, world_version) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "w-bunny", spec.world_name, slug or "bootstrapped",
                spec.aesthetic_seed, version.WORLD_VERSION,
            ),
        )

        # Prototypes first (FK targets for prototype_id on every concrete
        # object below).
        for kind, verbs in _PROTOTYPES:
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, properties_json) "
                "VALUES (?, 'w-bunny', 'prototype', ?, ?)",
                (_proto_id(kind), kind, json.dumps({"verbs": verbs})),
            )

        # Rooms -> objects. Build slug→id map first so exits can reference ids.
        slug_to_room_id: dict[str, str] = {
            r["slug"]: f"r-{r['slug']}" for r in spec.rooms
        }
        for r in spec.rooms:
            exits_with_ids = {
                d: slug_to_room_id[target] for d, target in r["exits"].items()
            }
            props = {
                "slug": r["slug"],
                "title": r["title"],
                "seed": r["seed"],
                "description_cached": None,
                "exits": exits_with_ids,
                "parent_id": None,
            }
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, location_id, "
                "prototype_id, properties_json) "
                "VALUES (?, 'w-bunny', 'room', ?, NULL, ?, ?)",
                (slug_to_room_id[r["slug"]], r["title"], _proto_id("room"),
                 json.dumps(props)),
            )

        # Toons -> objects (kind='toon'; location = current room; promoted
        # slot/controller/human columns; persona fields into properties).
        for t in spec.toons:
            toon_slug = re.sub(r"[^a-z0-9-]+", "-", t["name"].lower()).strip("-") or "toon"
            toon_id = f"t-{toon_slug}-{_short_uuid()}"
            props = {
                "seed": t["seed"],
                "appearance_seed": t["appearance_seed"],
                "mood": t["mood"],
                "presence_text": t.get("presence_text"),
            }
            # Merge an authored `properties` dict so an NPC can carry quest state
            # (`wants` / `gives` / `gives_text` / `gives_mood` / `declines_text`).
            # The four core persona fields above win over any collision.
            extra = t.get("properties")
            if isinstance(extra, dict):
                for k, v in extra.items():
                    props.setdefault(k, v)
            aliases = t.get("aliases") if isinstance(t.get("aliases"), list) else []
            # Per-NPC `talk` dialogue binding: install the dialogue as a data
            # skill (hidden from room-affordance lists via a sentinel predicate
            # so it is reached ONLY via the talk verb) and reference it from the
            # object's properties.dialogue, which `verbs._bound_dialogue_skill`
            # consults first.
            dlg = t.get("dialogue") if isinstance(t.get("dialogue"), dict) else None
            if dlg is not None:
                dlg_skill = f"dlg-{toon_slug}"
                props["dialogue"] = dlg_skill
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, aliases_json, "
                "location_id, prototype_id, properties_json, slot, "
                "controller_session, is_human_controlled, kicked_at) "
                "VALUES (?, 'w-bunny', 'toon', ?, ?, ?, ?, ?, ?, NULL, ?, NULL)",
                (
                    toon_id,
                    t["name"],
                    json.dumps(aliases),
                    slug_to_room_id[t["current_room_slug"]],
                    _proto_id("npc"),
                    json.dumps(props),
                    t["slot"],
                    int(t["is_human_controlled"]),
                ),
            )
            if dlg is not None:
                cur.execute(
                    "INSERT INTO skills (id, name, kind, context_predicate_json, "
                    "prompt_template, ui_hint, description, effects_schema_json, "
                    "author, enabled) "
                    "VALUES (?, ?, 'data', '{\"room_slug\": \"__npc_dialogue__\"}', "
                    "?, ?, ?, ?, 'opus-load', 1)",
                    (
                        f"skill-{dlg_skill}",
                        dlg_skill,
                        dlg["prompt_template"],
                        dlg.get("ui_hint") or "Talk",
                        dlg.get("description") or f"Talk to {t['name']}.",
                        json.dumps(dlg.get("effects_schema") or {}),
                    ),
                )

        # Designate the starting room (where toons wake after a rest): the
        # first human-controllable toon's room, else the first room.
        _human = next(
            (t for t in spec.toons if int(t.get("is_human_controlled", 0)) == 1), None
        )
        _start_slug = _human["current_room_slug"] if _human else spec.rooms[0]["slug"]
        cur.execute(
            "UPDATE worlds SET starting_room_id = ? WHERE id = 'w-bunny'",
            (slug_to_room_id[_start_slug],),
        )

        # Items -> thing objects (located in their room). Prototype selection:
        # `fixture` (immovable) beats `readable` beats plain `thing`. An authored
        # `properties` dict (state, state_text, use rule, contains, locked_text /
        # open_text, ...) is merged in so the world can express stateful
        # interactive objects; top-level seed / text / verbs override it.
        for it in spec.items:
            if it.get("fixture"):
                proto = "fixture"
            elif it.get("readable"):
                proto = "readable"
            else:
                proto = "thing"
            aliases = it.get("aliases") if isinstance(it.get("aliases"), list) else []
            props: dict = {}
            extra = it.get("properties")
            if isinstance(extra, dict):
                props.update(extra)
            props["seed"] = it["seed"]
            props["is_unique"] = int(bool(it.get("is_unique", 0)))
            if isinstance(it.get("text"), str) and it["text"].strip():
                props["text"] = it["text"].strip()
            if isinstance(it.get("verbs"), list):
                cleaned = [v for v in it["verbs"] if isinstance(v, str) and v.strip()]
                if cleaned:
                    props["verbs"] = cleaned
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, aliases_json, "
                "location_id, prototype_id, properties_json) "
                "VALUES (?, 'w-bunny', 'thing', ?, ?, ?, ?, ?)",
                (
                    f"o-{_short_uuid()}",
                    it["name"],
                    json.dumps(aliases),
                    slug_to_room_id[it["room_slug"]],
                    _proto_id(proto),
                    json.dumps(props),
                ),
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
