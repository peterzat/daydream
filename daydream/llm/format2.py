"""Format-2 world envelopes: the Zork-scale keyless loader (SPEC 2026-07-02).

An envelope with `"format": 2` routes here from `bootstrap.load_world`; the
v1 path stays byte-identical for existing worlds. Format 2 relaxes v1's
fixed counts (rooms 1..400, toons 0..64), takes STABLE AUTHORED IDS for
every object, allows one-way exits (reciprocity becomes a lint), gives
things a location union ({"room": id} | {"in": thing-id} | {"toon": id} |
"offstage"), and adds the authored definition sections the platform now
executes: verbs / flags / rules / fuses / daemons / scoring / voice /
config, all validated fail-loud with named errors and ZERO writes on any
failure (closed vocabularies, full cross-reference closure, flags declared
before use, every rule's `on` naming a declared verb or `enter`, every
effect kind inside RULE_KINDS).

Top-level shape:

    {"format": 2,
     "world": {"name", "slug", "aesthetic_seed", "rng_seed"?},
     "start_room": "<room id>",
     "config": {...}, "voice": {...}, "scoring": {"ranks": [...]},
     "flags": ["TRAP-OPEN", ...],
     "verbs": {<name>: {...verb spec...}},
     "rules": [...world rules...],
     "fuses": {<name>: {"turns": N, "do": [...]}},
     "daemons": {<name>: {"kind": "script"|"wanderer"|"conveyor", ...}},
     "rooms": [{"id", "slug", "title", "seed", "description"?, "dark"?,
                "exits": {dir: <exit value>}, "enter_if"?,
                "enter_blocked_text"?, "rules"?, "properties"?}],
     "toons": [{"id", "name", "slot", "room", "appearance_seed"?, "seed"?,
                "mood"?, "aliases"?, "presence_text"?, "dialogue"?,
                "is_human_controlled"?, "properties"?}],
     "things": [{"id", "name", "location", "seed"?, "aliases"?, "verbs"?,
                 "text"?, "readable"?, "fixture"?, "rules"?, "properties"?}]}
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from daydream import config, db, rules, version, worldstate, worldverbs
from daydream.verbs import VERBS

logger = logging.getLogger(__name__)

MAX_ERRORS_SHOWN = 12

_EXIT_VALUE_KEYS = frozenset({"to", "if", "blocked_text", "on_traverse", "secret", "text"})
_DAEMON_KINDS = frozenset({"script", "wanderer", "conveyor", "glow"})


class Format2ValidationError(Exception):
    """Raised with the named error list joined; zero writes have happened."""


def _err(errors: list[str]) -> None:
    shown = errors[:MAX_ERRORS_SHOWN]
    more = f" (+{len(errors) - len(shown)} more)" if len(errors) > len(shown) else ""
    raise Format2ValidationError("; ".join(shown) + more)


# ---- validation ------------------------------------------------------------


def _known_verb_names(env: dict) -> set[str]:
    """Canonical names rules may fire on: engine specs + declared world
    verbs (canonical names only — rules fire on spec.name)."""
    names = set(VERBS.keys())
    verbs_block = env.get("verbs")
    if isinstance(verbs_block, dict):
        names.update(k for k in verbs_block.keys() if isinstance(k, str))
    return names


def validate_envelope2(env: dict) -> list[str]:
    """Full fail-loud validation. Returns lint warnings (one-way exits);
    raises Format2ValidationError on any hard error."""
    errors: list[str] = []
    lints: list[str] = []

    world = env.get("world")
    if not isinstance(world, dict):
        _err(["world must be an object"])
    for k in ("name", "slug", "aesthetic_seed"):
        if not isinstance(world.get(k), str) or not world[k].strip():
            errors.append(f"world.{k} must be a non-empty string")
    if "rng_seed" in world and not isinstance(world["rng_seed"], str):
        errors.append("world.rng_seed must be a string")

    rooms_ = env.get("rooms")
    toons_ = env.get("toons", [])
    things_ = env.get("things", [])
    if not isinstance(rooms_, list) or not (1 <= len(rooms_) <= 400):
        _err(errors + ["rooms must be a list of 1..400 entries"])
    if not isinstance(toons_, list) or len(toons_) > 64:
        _err(errors + ["toons must be a list of 0..64 entries"])
    if not isinstance(things_, list):
        _err(errors + ["things must be a list"])

    # Pass 1: collect ids (cross-reference closure needs the full universe).
    all_ids: set[str] = set()
    room_ids: set[str] = set()
    toon_ids: set[str] = set()
    thing_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for i, r in enumerate(rooms_):
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not r["id"].strip():
            errors.append(f"rooms[{i}]: missing string id")
            continue
        rid = r["id"]
        if rid in all_ids:
            errors.append(f"rooms[{i}]: duplicate id {rid!r}")
        all_ids.add(rid)
        room_ids.add(rid)
    for i, t in enumerate(toons_):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"].strip():
            errors.append(f"toons[{i}]: missing string id")
            continue
        tid = t["id"]
        if tid in all_ids:
            errors.append(f"toons[{i}]: duplicate id {tid!r}")
        all_ids.add(tid)
        toon_ids.add(tid)
    for i, th in enumerate(things_):
        if not isinstance(th, dict) or not isinstance(th.get("id"), str) or not th["id"].strip():
            errors.append(f"things[{i}]: missing string id")
            continue
        oid = th["id"]
        if oid in all_ids:
            errors.append(f"things[{i}]: duplicate id {oid!r}")
        all_ids.add(oid)
        thing_ids.add(oid)
    if errors:
        _err(errors)

    # Declared vocabularies.
    flags = env.get("flags", [])
    if not isinstance(flags, list) or not all(
        isinstance(f, str) and f.strip() for f in flags
    ):
        errors.append("flags must be a list of non-empty strings")
        flags = []
    known_flags = set(flags)
    fuses = env.get("fuses", {})
    if not isinstance(fuses, dict):
        errors.append("fuses must be an object")
        fuses = {}
    daemons = env.get("daemons", {})
    if not isinstance(daemons, dict):
        errors.append("daemons must be an object")
        daemons = {}
    known = dict(
        known_flags=known_flags, known_ids=all_ids,
        known_fuses=set(fuses.keys()), known_daemons=set(daemons.keys()),
    )
    known_verbs = _known_verb_names(env)

    # Verbs block.
    if "verbs" in env:
        errors.extend(worldverbs.validate_verb_defs(env["verbs"]))

    # World rules.
    if "rules" in env:
        errors.extend(rules.validate_rules(
            env["rules"], source="rules", known_verbs=known_verbs, **known,
        ))

    # Fuses: {name: {turns, do}}.
    for name, d in fuses.items():
        where = f"fuses.{name}"
        if not isinstance(d, dict):
            errors.append(f"{where}: must be an object")
            continue
        if not isinstance(d.get("turns"), int) or d["turns"] < 1:
            errors.append(f"{where}.turns must be an int >= 1")
        errors.extend(rules.validate_effect_list(
            d.get("do"), f"{where}.do", require_nonempty=True, **known,
        ))
        unknown = set(d) - {"turns", "do"}
        if unknown:
            errors.append(f"{where}: unknown field(s) {sorted(unknown)}")

    # Daemons: {name: {kind, ...}}. Script kind fully validated; wanderer /
    # conveyor shapes land with the hostiles increment (kind must be known).
    for name, d in daemons.items():
        where = f"daemons.{name}"
        if not isinstance(d, dict):
            errors.append(f"{where}: must be an object")
            continue
        kind = d.get("kind", "script")
        if kind not in _DAEMON_KINDS:
            errors.append(f"{where}.kind must be one of {sorted(_DAEMON_KINDS)}")
            continue
        if kind == "script":
            errors.extend(rules.validate_condition_list(
                d.get("if"), f"{where}.if",
                known_flags=known_flags, known_ids=all_ids,
            ))
            errors.extend(rules.validate_effect_list(
                d.get("do"), f"{where}.do", require_nonempty=True, **known,
            ))
        elif kind == "wanderer":
            if not isinstance(d.get("toon"), str) or d["toon"] not in all_ids:
                errors.append(f"{where}.toon must name a declared toon id")
            for rid in d.get("rooms", []):
                if rid not in all_ids:
                    errors.append(f"{where}.rooms: unknown room {rid!r}")
            dep = d.get("deposit_room")
            if dep is not None and dep not in all_ids:
                errors.append(f"{where}.deposit_room: unknown room {dep!r}")
        elif kind == "conveyor":
            if not isinstance(d.get("vehicle"), str) or d["vehicle"] not in all_ids:
                errors.append(f"{where}.vehicle must name a declared thing id")
            path = d.get("path")
            if not isinstance(path, list) or len(path) < 2:
                errors.append(f"{where}.path must list at least two rooms")
            else:
                for rid in path:
                    if rid not in all_ids:
                        errors.append(f"{where}.path: unknown room {rid!r}")
        elif kind == "glow":
            if not isinstance(d.get("item"), str) or d["item"] not in all_ids:
                errors.append(f"{where}.item must name a declared thing id")
            for hid in d.get("hostiles", []):
                if hid not in all_ids:
                    errors.append(f"{where}.hostiles: unknown toon {hid!r}")

    # Scoring.
    scoring = env.get("scoring")
    if scoring is not None:
        if not isinstance(scoring, dict):
            errors.append("scoring must be an object")
        else:
            ranks = scoring.get("ranks")
            if ranks is not None:
                if not isinstance(ranks, list):
                    errors.append("scoring.ranks must be a list")
                else:
                    for i, rk in enumerate(ranks):
                        if not (isinstance(rk, dict) and isinstance(rk.get("min"), int)
                                and isinstance(rk.get("name"), str)):
                            errors.append(
                                f"scoring.ranks[{i}] must be {{min: int, name: str}}"
                            )

    for section in ("config", "voice"):
        if section in env and not isinstance(env[section], dict):
            errors.append(f"{section} must be an object")

    start_room = env.get("start_room")
    if not isinstance(start_room, str) or start_room not in room_ids:
        errors.append("start_room must name a declared room id")

    # Pass 2: rooms in detail.
    edges: set[tuple[str, str]] = set()
    for i, r in enumerate(rooms_):
        where = f"rooms[{i}]({r.get('id')})"
        for k in ("slug", "title", "seed"):
            if not isinstance(r.get(k), str) or not r[k].strip():
                errors.append(f"{where}.{k} must be a non-empty string")
        slug = r.get("slug")
        if isinstance(slug, str):
            if slug in seen_slugs:
                errors.append(f"{where}: duplicate slug {slug!r}")
            seen_slugs.add(slug)
        if "description" in r and not isinstance(r["description"], str):
            errors.append(f"{where}.description must be a string")
        if "dark" in r and not isinstance(r["dark"], bool):
            errors.append(f"{where}.dark must be a boolean")
        exits = r.get("exits", {})
        if not isinstance(exits, dict):
            errors.append(f"{where}.exits must be an object")
            exits = {}
        for direction, value in exits.items():
            ewhere = f"{where}.exits.{direction}"
            if isinstance(value, str):
                if value not in room_ids:
                    errors.append(f"{ewhere}: unknown room {value!r}")
                else:
                    edges.add((r["id"], value))
                continue
            if not isinstance(value, dict):
                errors.append(f"{ewhere}: must be a room id or an object")
                continue
            unknown = set(value) - _EXIT_VALUE_KEYS
            if unknown:
                errors.append(f"{ewhere}: unknown key(s) {sorted(unknown)}")
            if "to" in value:
                if value["to"] not in room_ids:
                    errors.append(f"{ewhere}.to: unknown room {value['to']!r}")
                else:
                    edges.add((r["id"], value["to"]))
                errors.extend(rules.validate_condition_list(
                    value.get("if"), f"{ewhere}.if",
                    known_flags=known_flags, known_ids=all_ids,
                ))
                if "on_traverse" in value:
                    errors.extend(rules.validate_effect_list(
                        value["on_traverse"], f"{ewhere}.on_traverse",
                        allow_inline_if=True, **known,
                    ))
                for tk in ("blocked_text",):
                    if tk in value and not isinstance(value[tk], str):
                        errors.append(f"{ewhere}.{tk} must be a string")
                if "secret" in value and not isinstance(value["secret"], bool):
                    errors.append(f"{ewhere}.secret must be a boolean")
            elif "text" in value:
                if not isinstance(value["text"], str) or not value["text"].strip():
                    errors.append(f"{ewhere}.text must be a non-empty string")
                extra = set(value) - {"text"}
                if extra:
                    errors.append(f"{ewhere}: message-only exit allows only 'text'")
            else:
                errors.append(f"{ewhere}: needs 'to' or 'text'")
        if "enter_if" in r:
            errors.extend(rules.validate_condition_list(
                r["enter_if"], f"{where}.enter_if",
                known_flags=known_flags, known_ids=all_ids,
            ))
        if "enter_blocked_text" in r and not isinstance(r["enter_blocked_text"], str):
            errors.append(f"{where}.enter_blocked_text must be a string")
        if "rules" in r:
            errors.extend(rules.validate_rules(
                r["rules"], source=f"{where}.rules",
                known_verbs=known_verbs, **known,
            ))
        if "properties" in r and not isinstance(r["properties"], dict):
            errors.append(f"{where}.properties must be an object")
    # One-way exits are legal in format 2 (Zork's slide, the chimney):
    # reciprocity is a LINT, not an error.
    for src, dst in sorted(edges):
        if (dst, src) not in edges:
            lints.append(f"one-way exit: {src} -> {dst}")

    # Pass 3: toons.
    seen_slots: set[int] = set()
    for i, t in enumerate(toons_):
        where = f"toons[{i}]({t.get('id')})"
        if not isinstance(t.get("name"), str) or not t["name"].strip():
            errors.append(f"{where}.name must be a non-empty string")
        slot = t.get("slot")
        if not isinstance(slot, int) or not (1 <= slot <= 8 or slot >= 100):
            errors.append(f"{where}.slot must be int in 1..8 or 100+")
        elif slot in seen_slots:
            errors.append(f"{where}: duplicate slot {slot}")
        else:
            seen_slots.add(slot)
        if t.get("room") not in room_ids:
            errors.append(f"{where}.room must name a declared room id")
        if t.get("is_human_controlled") not in (None, 0, 1):
            errors.append(f"{where}.is_human_controlled must be 0 or 1")
        dlg = t.get("dialogue")
        if dlg is not None and (
            not isinstance(dlg, dict)
            or not isinstance(dlg.get("prompt_template"), str)
            or not dlg["prompt_template"].strip()
        ):
            errors.append(f"{where}.dialogue needs a non-empty prompt_template")
        if "rules" in t:
            errors.extend(rules.validate_rules(
                t["rules"], source=f"{where}.rules",
                known_verbs=known_verbs, **known,
            ))
        if "properties" in t and not isinstance(t["properties"], dict):
            errors.append(f"{where}.properties must be an object")

    # Pass 4: things.
    for i, th in enumerate(things_):
        where = f"things[{i}]({th.get('id')})"
        if not isinstance(th.get("name"), str) or not th["name"].strip():
            errors.append(f"{where}.name must be a non-empty string")
        loc = th.get("location")
        if loc == "offstage":
            pass
        elif isinstance(loc, dict) and len(loc) == 1:
            (kind, ref), = loc.items()
            if kind == "room" and ref not in room_ids:
                errors.append(f"{where}.location.room: unknown room {ref!r}")
            elif kind == "in" and ref not in thing_ids:
                errors.append(f"{where}.location.in: unknown thing {ref!r}")
            elif kind == "toon" and ref not in toon_ids:
                errors.append(f"{where}.location.toon: unknown toon {ref!r}")
            elif kind not in ("room", "in", "toon"):
                errors.append(f"{where}.location: unknown kind {kind!r}")
        else:
            errors.append(
                f"{where}.location must be {{room|in|toon: id}} or \"offstage\""
            )
        if "rules" in th:
            errors.extend(rules.validate_rules(
                th["rules"], source=f"{where}.rules",
                known_verbs=known_verbs, **known,
            ))
        if "properties" in th and not isinstance(th["properties"], dict):
            errors.append(f"{where}.properties must be an object")
        if "verbs" in th and not (
            isinstance(th["verbs"], list)
            and all(isinstance(v, str) for v in th["verbs"])
        ):
            errors.append(f"{where}.verbs must be a list of strings")
        for flag in ("readable", "fixture"):
            if flag in th and not isinstance(th[flag], bool):
                errors.append(f"{where}.{flag} must be a boolean")

    if errors:
        _err(errors)
    return lints


# ---- writer -----------------------------------------------------------------

# Default per-archetype verb sets, mirroring bootstrap._PROTOTYPES (kept in
# sync by tests/test_format2.py::test_prototypes_match_v1_loader).
_PROTOTYPES: tuple[tuple[str, list[str]], ...] = (
    ("room", ["look"]),
    ("npc", ["examine", "talk"]),
    ("thing", ["examine", "take", "drop", "give", "put"]),
    ("readable", ["examine", "take", "drop", "give", "put", "read"]),
    ("fixture", ["examine"]),
)


def load_world2(env: dict, output_path: Path, *, force: bool = False) -> Path:
    """Validate + write a format-2 envelope to a fresh DB. Mirrors
    bootstrap.load_world's contract (raises on existing output unless
    force). Lint warnings (one-way exits) log at info."""
    from daydream.llm.bootstrap import BootstrapOutputExistsError

    output_path = Path(output_path).expanduser().resolve()
    if output_path.exists() and not force:
        raise BootstrapOutputExistsError(
            f"output path exists: {output_path} (pass --force to overwrite)"
        )
    lints = validate_envelope2(env)
    for lint in lints:
        logger.info("format2 lint: %s", lint)
    if output_path.exists():
        output_path.unlink()
    _write_db2(env, output_path)
    return output_path


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")


def _write_db2(env: dict, output_path: Path) -> None:
    world = env["world"]
    world_id = f"w-{_slugify(world['slug'])}"
    conn = db.open_db(output_path)
    try:
        db.init_schema(conn, config.MIGRATIONS_DIR)
        cur = conn.cursor()
        # Wipe the migration-seeded starter world; this DB holds ONE world.
        cur.execute("DELETE FROM memories WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM generated_assets WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM world_state WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM objects WHERE world_id = 'w-bunny'")
        cur.execute("DELETE FROM skills")
        cur.execute("DELETE FROM worlds WHERE id = 'w-bunny'")

        cur.execute(
            "INSERT INTO worlds (id, name, slug, aesthetic_seed, world_version, "
            "starting_room_id) VALUES (?, ?, ?, ?, ?, ?)",
            (world_id, world["name"], world["slug"], world["aesthetic_seed"],
             version.WORLD_VERSION, env["start_room"]),
        )

        for kind, verb_list in _PROTOTYPES:
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, properties_json) "
                "VALUES (?, ?, 'prototype', ?, ?)",
                (f"proto-{kind}", world_id, kind,
                 json.dumps({"verbs": verb_list})),
            )

        for r in env["rooms"]:
            props: dict = {}
            extra = r.get("properties")
            if isinstance(extra, dict):
                props.update(extra)
            props.update({
                "slug": r["slug"],
                "title": r["title"],
                "seed": r["seed"],
                "description_cached": (
                    r["description"].strip()
                    if isinstance(r.get("description"), str) and r["description"].strip()
                    else None
                ),
                "exits": r.get("exits", {}),
                "parent_id": None,
            })
            if r.get("dark"):
                props["dark"] = True
            for k in ("enter_if", "enter_blocked_text", "rules"):
                if k in r:
                    props[k] = r[k]
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, location_id, "
                "prototype_id, properties_json) VALUES (?, ?, 'room', ?, NULL, ?, ?)",
                (r["id"], world_id, r["title"], "proto-room", json.dumps(props)),
            )

        for t in env.get("toons", []):
            props = {}
            extra = t.get("properties")
            if isinstance(extra, dict):
                props.update(extra)
            props.setdefault("seed", t.get("seed") or t.get("appearance_seed") or "")
            props.setdefault("appearance_seed", t.get("appearance_seed") or "")
            props.setdefault("mood", t.get("mood") or "calm")
            props.setdefault("presence_text", t.get("presence_text"))
            if "rules" in t:
                props["rules"] = t["rules"]
            dlg = t.get("dialogue") if isinstance(t.get("dialogue"), dict) else None
            dlg_skill = None
            if dlg is not None:
                dlg_skill = f"dlg-{_slugify(t['name']) or 'npc'}"
                props["dialogue"] = dlg_skill
            aliases = t.get("aliases") if isinstance(t.get("aliases"), list) else []
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, aliases_json, "
                "location_id, prototype_id, properties_json, slot, "
                "controller_session, is_human_controlled, kicked_at) "
                "VALUES (?, ?, 'toon', ?, ?, ?, ?, ?, ?, NULL, ?, NULL)",
                (t["id"], world_id, t["name"], json.dumps(aliases), t["room"],
                 "proto-npc", json.dumps(props), t["slot"],
                 int(t.get("is_human_controlled") or 0)),
            )
            if dlg is not None:
                cur.execute(
                    "INSERT INTO skills (id, name, kind, context_predicate_json, "
                    "prompt_template, ui_hint, description, effects_schema_json, "
                    "author, enabled) "
                    "VALUES (?, ?, 'data', '{\"room_slug\": \"__npc_dialogue__\"}', "
                    "?, ?, ?, ?, 'opus-load', 1)",
                    (f"skill-{dlg_skill}", dlg_skill, dlg["prompt_template"],
                     dlg.get("ui_hint") or "Talk",
                     dlg.get("description") or f"Talk to {t['name']}.",
                     json.dumps(dlg.get("effects_schema") or {})),
                )

        # Things: two-pass so containment order never fights the FK — insert
        # every row locationless, then point locations at the now-existing
        # rows ("offstage" stays NULL).
        for th in env.get("things", []):
            proto = "thing"
            if th.get("fixture"):
                proto = "fixture"
            elif th.get("readable"):
                proto = "readable"
            props = {}
            extra = th.get("properties")
            if isinstance(extra, dict):
                props.update(extra)
            props["seed"] = th.get("seed") or ""
            props["is_unique"] = 1
            if isinstance(th.get("text"), str) and th["text"].strip():
                props["text"] = th["text"].strip()
            if isinstance(th.get("verbs"), list):
                cleaned = [v for v in th["verbs"] if isinstance(v, str) and v.strip()]
                if cleaned:
                    props["verbs"] = cleaned
            if "rules" in th:
                props["rules"] = th["rules"]
            aliases = th.get("aliases") if isinstance(th.get("aliases"), list) else []
            cur.execute(
                "INSERT INTO objects (id, world_id, kind, name, aliases_json, "
                "location_id, prototype_id, properties_json) "
                "VALUES (?, ?, 'thing', ?, ?, NULL, ?, ?)",
                (th["id"], world_id, th["name"], json.dumps(aliases),
                 f"proto-{proto}", json.dumps(props)),
            )
        for th in env.get("things", []):
            loc = th.get("location")
            if loc == "offstage" or not isinstance(loc, dict):
                continue
            (_, ref), = loc.items()
            cur.execute(
                "UPDATE objects SET location_id = ? WHERE id = ?", (ref, th["id"]),
            )

        # Authored definition blocks -> world_state (the runtime reads them
        # through daydream.worldstate).
        defs: dict = {}
        if isinstance(env.get("verbs"), dict):
            defs["def:verbs"] = env["verbs"]
        if isinstance(env.get("rules"), list):
            defs["def:rules"] = env["rules"]
        if isinstance(env.get("flags"), list):
            defs["def:flags"] = env["flags"]
        if isinstance(env.get("fuses"), dict):
            defs["def:fuses"] = env["fuses"]
        if isinstance(env.get("daemons"), dict):
            defs["def:daemons"] = env["daemons"]
        if isinstance(env.get("scoring"), dict):
            defs["def:scoring"] = env["scoring"]
        if isinstance(env.get("config"), dict):
            defs["config"] = env["config"]
        if isinstance(env.get("voice"), dict):
            defs["voice"] = env["voice"]
        defs["rng_seed"] = (
            world.get("rng_seed") if isinstance(world.get("rng_seed"), str)
            else world["slug"]
        )
        worldstate.write_rows(conn, world_id, defs)
    finally:
        conn.close()
