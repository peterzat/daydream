"""Dreams: the in-session authoring loop (SPEC 2026-09-26 criteria 13-15, 18;
the operator's runbook is docs/DREAM-RUNBOOK.md).

A dream is how the world keeps being written after launch. The operator
triggers one by name in a Claude Code session; the agent follows the
runbook: `digest` what players did since the last dream, author a PATCH,
`check` it, `rehearse` it, and `install` it. Dreams run in-session only:
nothing here is scheduled or headless, and nothing here calls a model (the
author is the agent in the session; the rehearsal forbids LLM calls).

Patch shape (`worlds/lost-hours/dreams/<id>/patch.json`):

    {"format": "dream-patch", "id": "dream-2026-09-27",
     "title": "The First Dream", "world": "w-lost-hours",
     "while_you_slept": "the note each returning player sees once",
     "add":  {portable world content, format-2 sections: rooms, toons,
              things, arcs, facts, storylets, rules, collectibles, pages,
              verbs, flags, player_flags, player_counters},
     "live": {"furnish": [{"room": <grown room id>, "description"?,
                           "things"?: [...], "toons"?: [...]}],
              "facts": {id: fact},                 # e.g. callbacks to real deeds
              "exits": [{"from", "direction", "to", "reverse"}],
              "cast_add": {npc id: {"topics"?, "samples"?, "wants"?,
                                    "drift_pools"?}}},
     "walkthroughs": {"fresh": [dataset, ...], "live": [dataset, ...]}}

`add` must stand on its own in a fresh village (the rehearsal's fresh
twin); `live` may reference the live world's own objects (a grown room,
a real player's deed). Validation merges the patch into a synthesis of the
LIVE world and runs the same format-2 validator and static analyzer the
world passed, with zero writes on any error. Apply is additive only: it
inserts new rows and merges new definitions; it never deletes or rewrites a
player-created object or any per-player state (the one sanctioned touch on
a grown room is `furnish`: a description pass and new contents, with the
planter's `grown` provenance, phrase included, left verbatim). A patch id
applies once (idempotent), and id collisions are refused.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import logging
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from daydream import db, events, inputs, objects, worldclock, worldstate

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LATEST_KEY = "dream:latest"
APPLIED_PREFIX = "dream:applied:"
MARK_KEY = "dream:last_mark"

_LIST_SECTIONS = ("rooms", "toons", "things", "rules", "storylets", "collectibles")
_DICT_SECTIONS = ("arcs", "facts", "pages", "verbs", "fuses", "daemons")
_NAME_SECTIONS = ("flags", "player_flags", "player_counters")
_DEF_KEYS = {
    "verbs": "def:verbs", "rules": "def:rules", "flags": "def:flags",
    "fuses": "def:fuses", "daemons": "def:daemons", "scoring": "def:scoring",
    "config": "config", "voice": "voice", "arcs": "def:arcs", "facts": "def:facts",
    "storylets": "def:storylets", "collectibles": "def:collectibles",
    "pages": "def:pages", "time": "def:time", "player_flags": "def:player_flags",
    "player_counters": "def:player_counters",
}


class PatchError(Exception):
    """A patch failed validation; nothing was written."""


# ---- while you slept -------------------------------------------------------


def latest(world_id: str) -> dict | None:
    v = worldstate.get(world_id, LATEST_KEY)
    return v if isinstance(v, dict) and v.get("id") else None


def note_for(toon_id: str) -> dict | None:
    """The latest dream's note for a PLAYER toon, exactly once: returned on
    the first call after the dream (and marked seen), None thereafter. A
    toon's very first call records the current dream as its baseline, so a
    newcomer is never shown a night they did not sleep through."""
    from daydream import story

    toon = objects.get(toon_id)
    if toon is None or toon.kind != "toon" or not toon.is_human_controlled:
        return None
    world_id = toon.world_id
    cur = latest(world_id)
    cur_id = cur["id"] if cur else ""
    seen = story.pget(world_id, toon_id, "dream_seen")
    if seen is None:
        story.pset(world_id, toon_id, "dream_seen", cur_id)
        return None
    if seen == cur_id or cur is None:
        return None
    story.pset(world_id, toon_id, "dream_seen", cur_id)
    return {"id": cur["id"], "title": cur.get("title") or "While you slept",
            "text": cur.get("text") or ""}


# ---- the live world as an envelope --------------------------------------------


def _live_world_id() -> str:
    from daydream import toons

    return toons.live_world_id()


def synthesize_envelope(world_id: str) -> dict:
    """The live world rebuilt as a format-2 envelope (rooms incl. grown ones,
    NPCs, every thing, every definition block), so a patch is validated and
    analyzed against the world as it IS. Things a player carries are placed
    in that player's room for analysis (players themselves are not part of
    the envelope)."""
    conn = db.get_conn()
    w = conn.execute("SELECT * FROM worlds WHERE id = ?", (world_id,)).fetchone()
    env: dict = {
        "format": 2,
        "world": {"name": w["name"], "slug": w["slug"], "aesthetic_seed": w["aesthetic_seed"],
                  "rng_seed": worldstate.rng_seed(world_id)},
        "start_room": w["starting_room_id"],
    }
    for section, key in _DEF_KEYS.items():
        v = worldstate.get(world_id, key)
        if v is not None:
            env[section] = v
    rows = [objects.Object.from_row(r) for r in conn.execute(
        "SELECT * FROM objects WHERE world_id = ? AND kind != 'prototype' ORDER BY id",
        (world_id,))]
    by_id = {o.id: o for o in rows}
    rooms, toons_, things = [], [], []
    room_keys = {"slug", "title", "seed", "description_cached", "exits", "parent_id",
                 "rules", "enter_if", "enter_blocked_text", "dark"}
    for o in rows:
        p = dict(o.properties)
        if o.kind == "room":
            r = {"id": o.id, "slug": p.get("slug") or o.id, "title": p.get("title") or o.name,
                 "seed": p.get("seed") or o.name, "exits": p.get("exits") or {}}
            if isinstance(p.get("description_cached"), str):
                r["description"] = p["description_cached"]
            for k in ("rules", "enter_if", "enter_blocked_text"):
                if k in p:
                    r[k] = p[k]
            if p.get("dark"):
                r["dark"] = True
            extra = {k: v for k, v in p.items() if k not in room_keys}
            if extra:
                r["properties"] = extra
            rooms.append(r)
        elif o.kind == "toon" and not o.is_player:
            t = {"id": o.id, "name": o.name, "slot": o.slot if o.slot is not None else 100,
                 "room": o.location_id or "offstage", "aliases": o.aliases}
            for k in ("seed", "appearance_seed", "mood", "presence_text"):
                if isinstance(p.get(k), str):
                    t[k] = p.pop(k)
                else:
                    p.pop(k, None)
            if "rules" in p:
                t["rules"] = p.pop("rules")
            p.pop("dialogue", None)
            if p:
                t["properties"] = p
            toons_.append(t)
        elif o.kind == "thing":
            loc = o.location_id
            holder = by_id.get(loc) if loc else None
            if holder is None:
                location = "offstage"
            elif holder.kind == "room":
                location = {"room": holder.id}
            elif holder.kind == "thing":
                location = {"in": holder.id}
            elif holder.kind == "toon" and not holder.is_player:
                location = {"toon": holder.id}
            else:
                location = ({"room": holder.location_id}
                            if holder.location_id in by_id else "offstage")
            th = {"id": o.id, "name": o.name, "location": location, "aliases": o.aliases,
                  "seed": p.pop("seed", "") or ""}
            if o.prototype_id == objects.PROTO_FIXTURE:
                th["fixture"] = True
            elif o.prototype_id == objects.PROTO_READABLE:
                th["readable"] = True
            for k in ("text", "verbs", "rules"):
                if k in p:
                    th[k] = p.pop(k)
            p.pop("is_unique", None)
            if p:
                th["properties"] = p
            things.append(th)
    env["rooms"], env["toons"], env["things"] = rooms, toons_, things
    return env


def merge(base: dict, add: dict, where: str = "add") -> dict:
    """base + a patch's additive sections (lists append; dicts merge and a
    key defined twice is an error; name lists union)."""
    env = copy.deepcopy(base)
    errors: list[str] = []
    for sec in _LIST_SECTIONS:
        if add.get(sec):
            env.setdefault(sec, []).extend(copy.deepcopy(add[sec]))
    for sec in _DICT_SECTIONS:
        for k, v in (add.get(sec) or {}).items():
            target = env.setdefault(sec, {})
            if k in target:
                errors.append(f"{where}.{sec}.{k}: already defined in the world")
            target[k] = copy.deepcopy(v)
    for sec in _NAME_SECTIONS:
        for name in add.get(sec) or []:
            names = env.setdefault(sec, [])
            if name not in names:
                names.append(name)
    unknown = set(add) - set(_LIST_SECTIONS) - set(_DICT_SECTIONS) - set(_NAME_SECTIONS)
    if unknown:
        errors.append(f"{where}: unknown section(s) {sorted(unknown)}")
    if errors:
        raise PatchError("; ".join(errors))
    return env


def _live_additions(env: dict, live: dict, world_id: str) -> tuple[dict, list[str]]:
    """Fold the `live` part into a synthesized envelope for validation."""
    errors: list[str] = []
    env = copy.deepcopy(env)
    rooms = {r["id"]: r for r in env["rooms"]}
    for i, f in enumerate(live.get("furnish") or []):
        rid = f.get("room") if isinstance(f, dict) else None
        room = rooms.get(rid)
        if room is None:
            errors.append(f"live.furnish[{i}]: unknown room {rid!r}")
            continue
        if not isinstance((room.get("properties") or {}).get("grown"), dict):
            errors.append(f"live.furnish[{i}]: {rid} is not a grown room")
        if "description" in f and not (isinstance(f["description"], str)
                                       and f["description"].strip()):
            errors.append(f"live.furnish[{i}].description must be a non-empty string")
        env["things"].extend(copy.deepcopy(f.get("things") or []))
        env["toons"].extend(copy.deepcopy(f.get("toons") or []))
        if isinstance(f.get("description"), str):
            room["description"] = f["description"]
    for k, v in (live.get("facts") or {}).items():
        if k in env.setdefault("facts", {}):
            errors.append(f"live.facts.{k}: already defined in the world")
        env["facts"][k] = copy.deepcopy(v)
    for i, x in enumerate(live.get("exits") or []):
        a, b = rooms.get(x.get("from")), rooms.get(x.get("to"))
        if a is None or b is None:
            errors.append(f"live.exits[{i}]: unknown room")
            continue
        if x.get("direction") in a.get("exits", {}) or x.get("reverse") in b.get("exits", {}):
            errors.append(f"live.exits[{i}]: that direction is already taken")
            continue
        a.setdefault("exits", {})[x["direction"]] = b["id"]
        b.setdefault("exits", {})[x["reverse"]] = a["id"]
    npcs = {t["id"] for t in env["toons"]}
    for tid, spec in (live.get("cast_add") or {}).items():
        if tid not in npcs:
            errors.append(f"live.cast_add.{tid}: no such NPC")
            continue
        extra = set(spec) - {"topics", "samples", "wants", "drift_pools"}
        if extra:
            errors.append(f"live.cast_add.{tid}: unknown key(s) {sorted(extra)}")
        t = next(x for x in env["toons"] if x["id"] == tid)
        props = t.setdefault("properties", {})
        props.setdefault("topics", []).extend(copy.deepcopy(spec.get("topics") or []))
        if spec.get("samples") or spec.get("wants"):
            voice = props.setdefault("voice", {})
            voice.setdefault("samples", []).extend(spec.get("samples") or [])
            voice.setdefault("wants", []).extend(spec.get("wants") or [])
    unknown = set(live) - {"furnish", "facts", "exits", "cast_add"}
    if unknown:
        errors.append(f"live: unknown section(s) {sorted(unknown)}")
    return env, errors


def _new_ids(patch: dict) -> list[str]:
    add, live = patch.get("add") or {}, patch.get("live") or {}
    ids = [x.get("id") for sec in ("rooms", "toons", "things") for x in add.get(sec) or []]
    for f in live.get("furnish") or []:
        ids += [x.get("id") for x in (f.get("things") or []) + (f.get("toons") or [])]
    return [i for i in ids if i]


def check_patch(patch: dict, world_id: str | None = None) -> list[str]:
    """Every problem with applying `patch` to the live world (empty = sound).
    Pure: reads only."""
    from daydream import analyzer
    from daydream.llm import format2

    world_id = world_id or _live_world_id()
    errors: list[str] = []
    if patch.get("format") != "dream-patch":
        errors.append("format must be 'dream-patch'")
    if not isinstance(patch.get("id"), str) or not patch["id"].strip():
        errors.append("id must be a non-empty string")
    if patch.get("world") not in (None, world_id):
        errors.append(f"patch is for {patch.get('world')!r}, the live world is {world_id!r}")
    note = patch.get("while_you_slept")
    if note is not None and not (isinstance(note, str) and note.strip()):
        errors.append("while_you_slept must be a non-empty string")
    if errors:
        return errors
    base = synthesize_envelope(world_id)
    existing = {x["id"] for sec in ("rooms", "toons", "things") for x in base[sec]}
    existing |= {r["id"] for r in db.get_conn().execute(
        "SELECT id FROM objects WHERE world_id = ?", (world_id,))}
    for nid in _new_ids(patch):
        if nid in existing:
            errors.append(f"id collision: {nid!r} already exists in the live world")
    try:
        merged = merge(base, patch.get("add") or {})
    except PatchError as e:
        return errors + [str(e)]
    merged, live_errors = _live_additions(merged, patch.get("live") or {}, world_id)
    errors += live_errors
    if errors:
        return errors
    try:
        format2.validate_envelope2(merged)
    except format2.Format2ValidationError as e:
        return [f"validation: {e}"]
    return [f"analyzer: {p}" for p in analyzer.analyze(merged)]


# ---- apply -------------------------------------------------------------------


@contextmanager
def _transaction():
    conn = db.get_conn()
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def apply_patch(patch: dict, world_id: str | None = None) -> str:
    """Validate, then apply additively in ONE transaction. Returns "applied"
    or "already-applied". Raises PatchError (nothing written) when invalid."""
    from daydream.llm import format2

    world_id = world_id or _live_world_id()
    if worldstate.get(world_id, APPLIED_PREFIX + str(patch.get("id"))):
        return "already-applied"
    problems = check_patch(patch, world_id)
    if problems:
        raise PatchError("; ".join(problems[:12]))
    add, live = patch.get("add") or {}, patch.get("live") or {}
    furnish = live.get("furnish") or []
    with _transaction() as conn:
        cur = conn.cursor()
        entities = {
            "rooms": add.get("rooms") or [],
            "toons": (add.get("toons") or []) + [t for f in furnish for t in f.get("toons") or []],
            "things": (add.get("things") or []) + [t for f in furnish for t in f.get("things") or []],
        }
        format2.insert_entities(cur, world_id, entities)
        for sec in _DICT_SECTIONS:
            items = dict(add.get(sec) or {})
            if sec == "facts":
                items.update(live.get("facts") or {})
            if items:
                key = _DEF_KEYS[sec]
                cur_v = worldstate.get(world_id, key)
                cur_v = cur_v if isinstance(cur_v, dict) else {}
                cur_v.update(copy.deepcopy(items))
                worldstate.set(world_id, key, cur_v)
        for sec in ("rules", "storylets", "collectibles"):
            if add.get(sec):
                key = _DEF_KEYS[sec]
                cur_v = worldstate.get(world_id, key)
                cur_v = cur_v if isinstance(cur_v, list) else []
                worldstate.set(world_id, key, cur_v + copy.deepcopy(add[sec]))
        for sec in _NAME_SECTIONS:
            if add.get(sec):
                key = _DEF_KEYS.get(sec, f"def:{sec}")
                cur_v = worldstate.get(world_id, key)
                cur_v = list(cur_v) if isinstance(cur_v, list) else []
                worldstate.set(world_id, key, cur_v + [n for n in add[sec] if n not in cur_v])
        for arc_id, arc in (add.get("arcs") or {}).items():
            if isinstance(arc, dict) and arc.get("opens") == "start":
                worldstate.set(world_id, f"arc:{arc_id}", {
                    "status": "open", "opened_day": 0, "beats": {}, "helpers": []})
        for x in live.get("exits") or []:
            for rid, d, to in ((x["from"], x["direction"], x["to"]),
                               (x["to"], x["reverse"], x["from"])):
                ex = dict(objects.get_property(rid, "exits") or {})
                ex[d] = to
                objects.set_property(rid, "exits", ex)
        for f in furnish:
            if isinstance(f.get("description"), str):
                objects.set_property(f["room"], "description_cached", f["description"].strip())
            objects.set_property(f["room"], "furnished_by", patch["id"])
        for tid, spec in (live.get("cast_add") or {}).items():
            cast_add(objects.get(tid), spec)
        if isinstance(patch.get("while_you_slept"), str):
            worldstate.set(world_id, LATEST_KEY, {
                "id": patch["id"], "title": patch.get("title") or "While you slept",
                "text": patch["while_you_slept"].strip(), "at": worldclock.iso()})
        worldstate.set(world_id, APPLIED_PREFIX + patch["id"], {
            "at": worldclock.iso(), "title": patch.get("title"),
            "sha": patch_sha(patch), "add": add,
            # Kept so a content refresh (daydream/refresh.py) can re-apply
            # this dream's facts and cast additions on top of fresh defs.
            "live": {"facts": live.get("facts") or {},
                     "cast_add": live.get("cast_add") or {}}})
    events.append("system", None, "dream_installed", {"id": patch["id"]}, room_id=None)
    return "applied"


def cast_add(t: objects.Object | None, spec: dict) -> None:
    """Append a dream's additions (topics, voice samples and wants, drift
    lines) to one resident, writing only the keys that change."""
    if t is None or not isinstance(spec, dict):
        return
    props = dict(t.properties)
    if spec.get("topics"):
        props["topics"] = list(props.get("topics") or []) + copy.deepcopy(spec["topics"])
    if spec.get("samples") or spec.get("wants"):
        voice = dict(props.get("voice") or {})
        voice["samples"] = list(voice.get("samples") or []) + list(spec.get("samples") or [])
        voice["wants"] = list(voice.get("wants") or []) + list(spec.get("wants") or [])
        props["voice"] = voice
    for mood, lines in (spec.get("drift_pools") or {}).items():
        pools = dict(props.get("drift_pools") or {})
        pools[mood] = list(pools.get(mood) or []) + list(lines)
        props["drift_pools"] = pools
    for k, v in props.items():
        if t.properties.get(k) != v:
            objects.set_property(t.id, k, v)


def patch_sha(patch: dict) -> str:
    return hashlib.sha256(json.dumps(patch, sort_keys=True).encode()).hexdigest()[:16]


def applied(world_id: str) -> list[dict]:
    out = []
    for k in worldstate.keys(world_id, APPLIED_PREFIX):
        v = worldstate.get(world_id, k)
        if isinstance(v, dict):
            out.append({"id": k[len(APPLIED_PREFIX):], **v})
    out.sort(key=lambda r: r.get("at") or "")
    return out


# ---- digest -------------------------------------------------------------------


def mark(world_id: str) -> dict:
    """Record the digest high-water mark (after an install)."""
    m = {"event_seq": events.max_seq(), "input_seq": inputs.max_seq(), "at": worldclock.iso()}
    worldstate.set(world_id, MARK_KEY, m)
    return m


def digest(world_id: str | None = None) -> dict:
    """A deterministic summary of play since the last dream: raw inputs per
    player, deeds (facts naming players), beats advanced and arcs opened or
    closed (with who), grown rooms (and whether a dream has furnished them),
    the chronicle, relationships, and the village's time."""
    from daydream import collect, knowledge, story, village

    world_id = world_id or _live_world_id()
    m = worldstate.get(world_id, MARK_KEY)
    m = m if isinstance(m, dict) else {"event_seq": 0, "input_seq": 0, "at": None}
    conn = db.get_conn()
    toons_all = [objects.Object.from_row(r) for r in conn.execute(
        "SELECT * FROM objects WHERE world_id = ? AND kind = 'toon' ORDER BY slot",
        (world_id,))]
    # Players who left the dream are still players (their day is what the
    # dream reads): is_player, not is_human_controlled.
    players = [t for t in toons_all if t.is_player]
    names = {p.id: p.name for p in players}
    npcs = [t for t in toons_all if not t.is_player]
    since_events = [e for e in events.fetch_since(m.get("event_seq", 0))]
    by_player = {}
    for p in players:
        rows = inputs.fetch(since=m.get("input_seq", 0), toon_id=p.id)
        by_player[p.name] = {
            "toon_id": p.id,
            "inputs": [{"at": r.created_at, "room": r.room_id,
                        "typed": r.text if r.source == "text" else None,
                        "clicked": ({"verb": r.verb, "dobj": r.dobj_id, "iobj": r.iobj_id,
                                     "args": r.args} if r.source == "command" else None)}
                       for r in rows],
            "relationships": {n.name: story.rel(world_id, n.id, p.id) for n in npcs
                              if story.rel(world_id, n.id, p.id)},
            "collected": collect.count(world_id, p.id),
            "room": p.location_id,
        }
    arcs = {}
    for arc_id, st in story.all_states(world_id).items():
        arc = story.arc_def(world_id, arc_id) or {}
        arcs[arc_id] = {
            "title": arc.get("title"), "kind": arc.get("kind"), "status": st["status"],
            "ending": st.get("ending"),
            "beats": {b: names.get((v or {}).get("by"), (v or {}).get("by"))
                      for b, v in st["beats"].items()},
            "helpers": [names.get(h, h) for h in st["helpers"]],
            "opened_day": st.get("opened_day"), "closed_day": st.get("closed_day"),
        }
    grown = []
    for r in conn.execute("SELECT * FROM objects WHERE world_id = ? AND kind = 'room'",
                          (world_id,)):
        o = objects.Object.from_row(r)
        g = o.properties.get("grown")
        if isinstance(g, dict):
            grown.append({"room": o.id, "title": o.properties.get("title"),
                          "phrase": g.get("phrase"), "planter": names.get(g.get("planter_id"),
                                                                           g.get("planter_id")),
                          "at": g.get("at"), "furnished_by": o.properties.get("furnished_by"),
                          "contents": [t.name for t in objects.contents(o.id)]})
    deeds = [{"text": f["text"], "about": f.get("about_name"), "at": f.get("at")}
             for f in knowledge.deed_facts(world_id)
             if not m.get("at") or (f.get("at") or "") >= m["at"]]
    kinds = {}
    for e in since_events:
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    # Reflexes, not voice (docs/REFLEXES.md): how much of what players read
    # the local model wrote, and a sample of its lines for the dreamer to read.
    told = [e for e in since_events if e.kind == "narrate"]
    local = [e for e in told if e.payload.get("src") == "local"]
    voice = {"narrations": len(told), "local": len(local),
             "local_lines": [e.payload.get("text") for e in local[-40:]]}
    return {
        "world": world_id, "since": m, "now": worldclock.iso(),
        "village": village.status(world_id) if village.time_def(world_id) else None,
        "players": by_player, "arcs": arcs, "grown_rooms": grown, "deeds": deeds,
        "chronicle": story.chronicle(world_id), "event_counts": kinds, "voice": voice,
        "dreams_applied": [a["id"] for a in applied(world_id)],
    }


def render_digest(d: dict) -> str:
    lines = [f"# Dream digest: {d['world']}", "",
             f"Since {d['since'].get('at') or 'the beginning'}; now {d['now']}.", ""]
    if d.get("village"):
        v = d["village"]
        lines += [f"Village: day {v['day']}, {v['phase']}.", ""]
    lines.append("## Players")
    for name, p in d["players"].items():
        lines.append(f"### {name} ({len(p['inputs'])} inputs, {p['collected']} minutes, "
                     f"in {p['room']})")
        if p["relationships"]:
            lines.append("Relationships: " + ", ".join(f"{k} {v}" for k, v in p["relationships"].items()))
        for i in p["inputs"]:
            what = i["typed"] if i["typed"] is not None else json.dumps(i["clicked"])
            lines.append(f"- {i['at']} [{i['room']}] {what}")
        lines.append("")
    lines.append("## Arcs")
    for aid, a in d["arcs"].items():
        lines.append(f"- **{a['title']}** ({aid}, {a['kind']}): {a['status']}"
                     + (f", ending {a['ending']}" if a["ending"] else "")
                     + (f"; beats {a['beats']}" if a["beats"] else "")
                     + (f"; helpers {a['helpers']}" if a["helpers"] else ""))
    lines += ["", "## Grown rooms"]
    for g in d["grown_rooms"] or [{"room": "(none)"}]:
        lines.append(f"- {g}")
    lines += ["", "## Deeds (gossip)"]
    for x in d["deeds"] or [{"text": "(none)"}]:
        lines.append(f"- {x['text']}")
    lines += ["", "## Chronicle"]
    for c in d["chronicle"] or [{"text": "(nothing yet)"}]:
        lines.append(f"- {c.get('text')}")
    v = d.get("voice") or {}
    if v:
        lines += ["", "## Voice (authored vs local)",
                  f"{v['local']} of {v['narrations']} narrations were written by the local "
                  "model; the rest were authored or engine text. Recent local lines "
                  "(candidates for an authored rewrite):"]
        lines += [f"- {t}" for t in v["local_lines"]] or ["- (none)"]
    return "\n".join(lines) + "\n"


# ---- rehearse + install -------------------------------------------------------


@contextmanager
def _no_llm():
    """The rehearsal proves the patch deterministically: any LLM call fails
    it outright (never a silent degrade)."""
    from daydream.llm import client

    real = client.acompletion_json

    async def refuse(*a, **kw):
        raise RuntimeError("the rehearsal makes zero LLM calls")

    client.acompletion_json = refuse
    try:
        yield
    finally:
        client.acompletion_json = real


def backup_db(src: Path, dest: Path) -> None:
    """A consistent copy of a (possibly live, WAL-mode) SQLite DB."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    s = sqlite3.connect(str(src))
    d = sqlite3.connect(str(dest))
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _walkthrough_files() -> list[Path]:
    return sorted((PROJECT_ROOT / "worlds/lost-hours/walkthroughs").glob("*.json"))


async def rehearse(patch: dict, live_db: Path, work_dir: Path,
                   base_env_path: Path | None = None,
                   walkthrough_dir: Path | None = None) -> dict:
    """Prove a patch before it touches the live world:

    1. snapshot the live DB (kept as the pre-dream snapshot);
    2. a SIDE COPY of it: check, apply, and replay the patch's own `live`
       walkthroughs there (fresh rehearsal players, relative clocks);
    3. a FRESH TWIN: the canonical world + every previously applied patch's
       `add` + this one's, replaying every committed walkthrough and the
       patch's `fresh` walkthroughs.

    Zero LLM calls. Writes work_dir/rehearsal.json and returns the report;
    `ok` is true only if every step passed. Touches the live DB only to
    read it."""
    from daydream import config, walkthrough
    from daydream.llm import bootstrap

    base_env_path = base_env_path or PROJECT_ROOT / "worlds/lost-hours.json"
    work_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"patch": patch.get("id"), "sha": patch_sha(patch),
                    "at": worldclock.iso(), "steps": [], "ok": False}

    def step(name: str, ok: bool, detail: str = "") -> bool:
        report["steps"].append({"step": name, "ok": ok, "detail": detail[:2000]})
        return ok

    pre = work_dir / "pre-dream.db"
    side = work_dir / "side.db"
    backup_db(live_db, pre)
    shutil.copyfile(pre, side)
    step("snapshot", True, str(pre))
    saved_clock = worldclock._fake_now
    prior_adds: list[dict] = []
    all_ok = True
    with _no_llm():
        try:
            db.close_db()
            events.reset_subscribers()
            db.init_live(path=side, migrations_dir=config.MIGRATIONS_DIR)
            world_id = _live_world_id()
            prior_adds = [a.get("add") or {} for a in applied(world_id)
                          if a["id"] != patch.get("id")]
            problems = check_patch(patch, world_id)
            all_ok &= step("check (side copy)", not problems, "; ".join(problems))
            if not problems:
                try:
                    all_ok &= step("apply (side copy)", apply_patch(patch, world_id) == "applied")
                except Exception as e:  # noqa: BLE001 - reported, never raised
                    all_ok &= step("apply (side copy)", False, repr(e))
                for ds in (patch.get("walkthroughs") or {}).get("live") or []:
                    try:
                        await walkthrough.replay(ds, on_live_copy=True)
                        all_ok &= step(f"live walkthrough {ds.get('name')}", True)
                    except Exception as e:  # noqa: BLE001
                        all_ok &= step(f"live walkthrough {ds.get('name')}", False, repr(e))
            db.close_db()
            events.reset_subscribers()
            # The fresh twin.
            env = json.loads(base_env_path.read_text())
            try:
                for i, add in enumerate(prior_adds + [patch.get("add") or {}]):
                    env = merge(env, add, where=f"add[{i}]")
                from daydream import analyzer
                from daydream.llm import format2

                format2.validate_envelope2(copy.deepcopy(env))
                probs = analyzer.analyze(env)
                all_ok &= step("fresh twin validates", not probs, "; ".join(probs))
            except Exception as e:  # noqa: BLE001
                all_ok &= step("fresh twin validates", False, repr(e))
                env = None
            if env is not None:
                files = (sorted(walkthrough_dir.glob("*.json")) if walkthrough_dir
                         else _walkthrough_files())
                datasets = [json.loads(p.read_text()) for p in files]
                datasets += (patch.get("walkthroughs") or {}).get("fresh") or []
                for ds in datasets:
                    path = work_dir / "fresh.db"
                    try:
                        bootstrap.load_world("fresh-twin", copy.deepcopy(env), path, force=True)
                        db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
                        await walkthrough.replay(ds)
                        all_ok &= step(f"fresh walkthrough {ds.get('name')}", True)
                    except Exception as e:  # noqa: BLE001
                        all_ok &= step(f"fresh walkthrough {ds.get('name')}", False, repr(e))
                    finally:
                        db.close_db()
                        events.reset_subscribers()
        finally:
            db.close_db()
            events.reset_subscribers()
            worldclock._fake_now = saved_clock
    report["ok"] = bool(all_ok)
    (work_dir / "rehearsal.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def install_ready(patch: dict, work_dir: Path) -> str | None:
    """None when a passing rehearsal of exactly this patch exists in
    work_dir; otherwise the reason the install must not proceed."""
    rp = work_dir / "rehearsal.json"
    if not rp.exists():
        return "no rehearsal found; run `bin/game dream rehearse` first"
    r = json.loads(rp.read_text())
    if r.get("sha") != patch_sha(patch):
        return "the rehearsal was of a different version of this patch; rehearse again"
    if not r.get("ok"):
        failed = [s["step"] for s in r.get("steps", []) if not s.get("ok")]
        return f"the rehearsal failed ({', '.join(failed)}); nothing may be installed"
    return None


# ---- CLI (bin/game dream ...) -------------------------------------------------


def _patch_arg(path: str) -> tuple[dict, Path]:
    p = Path(path).expanduser().resolve()
    return json.loads(p.read_text()), p.parent


def main(argv: list[str] | None = None) -> int:
    from daydream import config

    ap = argparse.ArgumentParser(prog="daydream.dream")
    sub = ap.add_subparsers(dest="cmd", required=True)
    dg = sub.add_parser("digest", help="summarize play since the last dream")
    dg.add_argument("--out", help="directory for digest.json + digest.md")
    dg.add_argument("--db", help="DB to read (default: the live DB)")
    ck = sub.add_parser("check", help="validate a patch against the live world (no writes)")
    ck.add_argument("patch")
    ck.add_argument("--db")
    ap_ = sub.add_parser("apply", help="apply a patch to a DB (default: the live DB)")
    ap_.add_argument("patch")
    ap_.add_argument("--db")
    rh = sub.add_parser("rehearse", help="snapshot, side-copy apply, replay everything")
    rh.add_argument("patch")
    rh.add_argument("--db")
    ir = sub.add_parser("install-check", help="exit 0 iff a passing rehearsal exists")
    ir.add_argument("patch")
    mk = sub.add_parser("mark", help="record the digest mark (after an install)")
    mk.add_argument("--db")
    ex = sub.add_parser("export", help="a player's recorded session as a walkthrough dataset")
    ex.add_argument("--toon", required=True, help="the player's name or toon id")
    ex.add_argument("--since", type=int, default=0, help="input seq to start after")
    ex.add_argument("--out", help="write the dataset here (default: stdout)")
    ex.add_argument("--db")
    args = ap.parse_args(argv)
    db_path = Path(getattr(args, "db", None) or config.live_db_path()).expanduser()

    if args.cmd == "install-check":
        patch, pdir = _patch_arg(args.patch)
        why = install_ready(patch, pdir)
        print(why or f"ready: {patch['id']} passed its rehearsal")
        return 0 if why is None else 1
    if args.cmd == "rehearse":
        patch, pdir = _patch_arg(args.patch)
        report = asyncio.run(rehearse(patch, db_path, pdir))
        for s in report["steps"]:
            print(("ok   " if s["ok"] else "FAIL ") + s["step"]
                  + (f": {s['detail'][:300]}" if s["detail"] and not s["ok"] else ""))
        print(f"rehearsal {'PASSED' if report['ok'] else 'FAILED'} -> {pdir / 'rehearsal.json'}")
        return 0 if report["ok"] else 1

    db.init_live(path=db_path, migrations_dir=config.MIGRATIONS_DIR)
    try:
        if args.cmd == "digest":
            d = digest()
            text = render_digest(d)
            if args.out:
                out = Path(args.out).expanduser()
                out.mkdir(parents=True, exist_ok=True)
                (out / "digest.json").write_text(json.dumps(d, indent=2) + "\n")
                (out / "digest.md").write_text(text)
                print(f"wrote {out}/digest.json and digest.md")
            else:
                print(text)
            return 0
        if args.cmd == "check":
            patch, _ = _patch_arg(args.patch)
            problems = check_patch(patch)
            for p in problems:
                print(f"- {p}")
            print("ok: the patch is sound" if not problems else f"{len(problems)} problem(s)")
            return 0 if not problems else 1
        if args.cmd == "apply":
            patch, _ = _patch_arg(args.patch)
            try:
                result = apply_patch(patch)
            except PatchError as e:
                print(f"refused (nothing written): {e}", file=sys.stderr)
                return 1
            print(f"{patch['id']}: {result}")
            return 0
        if args.cmd == "mark":
            print(json.dumps(mark(_live_world_id())))
            return 0
        if args.cmd == "export":
            row = db.get_conn().execute(
                "SELECT id FROM objects WHERE kind = 'toon' AND (id = ? OR name = ?) "
                "ORDER BY is_human_controlled DESC LIMIT 1", (args.toon, args.toon)).fetchone()
            if row is None:
                print(f"no toon {args.toon!r}", file=sys.stderr)
                return 1
            data = inputs.export_walkthrough(row["id"], since=args.since,
                                             name=f"session-{args.toon}")
            text = json.dumps(data, indent=2) + "\n"
            if args.out:
                Path(args.out).expanduser().write_text(text)
                print(f"wrote {args.out} ({len(data['segments'][0]['commands'])} steps)")
            else:
                print(text)
            return 0
    finally:
        db.close_db()
    return 2


if __name__ == "__main__":
    sys.exit(main())
