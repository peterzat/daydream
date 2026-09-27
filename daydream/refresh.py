"""`bin/game world refresh`: deploy authored content to a live world without
losing play (the playtest-day gap, 2026-09-26).

A reset is a new village; a dream patch is additive only. Neither can carry
a fixed line, a gated topic, or a new refusal into a world people have
already played. A refresh can: it loads the canonical envelope (plus every
applied dream's `add`) into a scratch DB, then, in ONE transaction on the live
DB:

- every authored object that exists live takes the fresh authored
  definition, EXCEPT what play wrote: keys the running world set (recorded
  `property_set` / `mood_set` events, plus the runtime keys below), a name a
  rename gave it, its current location, and exits grown or dreamed onto it
  (exits are merged; a room's text keeps "A new way opens ..." sentences);
- authored objects new to the envelope are inserted where authored;
- live-only objects (players, finds, keepsakes, grown rooms, dream
  furnishings) are untouched;
- every `def:*` story definition is replaced by the fresh one, and applied
  dreams' `live` facts and cast additions are re-applied on top; every other
  world-state key (arc progress, relationships, per-player state, deeds,
  flags, the clock) is kept.

`--check` runs the same merge and rolls it back, printing what would change.
The server must be down (bin/game world refresh handles the snapshot, the
down, and the up)."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

from daydream import db, objects, worldclock, worldstate

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Keys only play writes (or that play has already merged): never taken from
# the envelope when the live object has them.
RUNTIME_KEYS = frozenset({
    "state", "examined_text", "examined_src", "journal", "journal_last_seq", "mood",
    "furnished_by", "grown", "generated_by", "private_to", "collectible", "fuel",
    "lit", "burned_out", "flame", "glow_level", "combat_strength",
})
_NEW_WAY = re.compile(r"\s*A new way opens [^.]*\.")


def _played_keys(conn) -> dict[str, set[str]]:
    """Object id -> the property keys the running world has written."""
    out: dict[str, set[str]] = {}
    for kind, payload in conn.execute(
            "SELECT kind, payload_json FROM events WHERE kind IN ('property_set', 'mood_set')"):
        try:
            p = json.loads(payload or "{}")
        except ValueError:
            continue
        oid = p.get("target_id") or p.get("toon_id")
        key = p.get("key") if kind == "property_set" else "mood"
        if isinstance(oid, str) and isinstance(key, str):
            out.setdefault(oid, set()).add(key)
    return out


def _renamed(conn) -> set[str]:
    out = set()
    for (payload,) in conn.execute("SELECT payload_json FROM events WHERE kind = 'object_renamed'"):
        try:
            oid = json.loads(payload or "{}").get("object_id")
        except ValueError:
            continue
        if isinstance(oid, str):
            out.add(oid)
    return out


def fresh_envelope(envelope_path: Path, world_id: str) -> dict:
    """The canonical envelope plus every applied dream's `add`, exactly as a
    dream rehearsal builds its fresh twin."""
    from daydream import dream

    env = json.loads(envelope_path.read_text())
    for i, a in enumerate(dream.applied(world_id)):
        env = dream.merge(env, a.get("add") or {}, where=f"add[{i}]")
    return env


def _merge_props(live: dict, fresh: dict, played: set[str]) -> dict:
    keep = RUNTIME_KEYS | played
    merged = dict(live)
    for k, v in fresh.items():
        if k in keep and k in live:
            continue
        if v is None and live.get(k) is not None:
            continue  # an unset authored field never erases what the world has
        merged[k] = copy.deepcopy(v)
    lx, fx = live.get("exits"), fresh.get("exits")
    if isinstance(lx, dict) or isinstance(fx, dict):
        ex = dict(fx or {})
        for d, to in (lx or {}).items():
            ex.setdefault(d, to)
        merged["exits"] = ex
    ld, fd = live.get("description_cached"), fresh.get("description_cached")
    if isinstance(fd, str) and "description_cached" not in played:
        if live.get("furnished_by"):
            merged["description_cached"] = ld
        else:
            grown = "".join(m.group(0) for m in _NEW_WAY.finditer(ld or "")
                            if m.group(0).strip() not in fd)
            merged["description_cached"] = fd.rstrip() + grown
    return merged


def refresh(envelope_path: Path, *, check: bool = False) -> dict:
    """Merge the envelope's authored content into the live DB (see module
    doc). Returns a report; with check=True nothing is written."""
    from daydream import dream
    from daydream.llm import bootstrap

    conn = db.get_conn()
    world_id = dream._live_world_id()
    env = fresh_envelope(envelope_path, world_id)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "fresh.db"
        bootstrap.load_world("refresh", copy.deepcopy(env), scratch, force=True)
        f = sqlite3.connect(scratch)
        f.row_factory = sqlite3.Row
        fresh_world = f.execute("SELECT id, starting_room_id FROM worlds").fetchone()
        if fresh_world is None or fresh_world["id"] != world_id:
            raise SystemExit(f"envelope world {fresh_world and fresh_world['id']!r} "
                             f"is not the live world {world_id!r}")
        fresh_rows = [dict(r) for r in f.execute(
            "SELECT * FROM objects WHERE world_id = ?", (world_id,))]
        fresh_state = {r["key"]: json.loads(r["value_json"]) for r in f.execute(
            "SELECT key, value_json FROM world_state WHERE world_id = ?", (world_id,))}
        f.close()

    played = _played_keys(conn)
    renamed = _renamed(conn)
    report = {"world": world_id, "updated": [], "inserted": [], "kept_keys": {},
              "defs": [], "at": worldclock.iso(), "check": check}
    conn.execute("BEGIN")
    try:
        live_ids = {r[0] for r in conn.execute(
            "SELECT id FROM objects WHERE world_id = ?", (world_id,))}
        pending_locations = []
        for row in fresh_rows:
            fprops = json.loads(row["properties_json"] or "{}")
            if row["id"] in live_ids:
                live = objects.get(row["id"])
                merged = _merge_props(live.properties, fprops, played.get(row["id"], set()))
                name, aliases = live.name, live.aliases
                if row["id"] not in renamed:
                    name, aliases = row["name"], json.loads(row["aliases_json"] or "[]")
                if merged != live.properties or name != live.name or aliases != live.aliases \
                        or row["prototype_id"] != live.prototype_id:
                    conn.execute(
                        "UPDATE objects SET name = ?, aliases_json = ?, prototype_id = ?, "
                        "properties_json = ? WHERE id = ?",
                        (name, json.dumps(aliases), row["prototype_id"],
                         json.dumps(merged), row["id"]))
                    report["updated"].append(row["id"])
                kept = sorted((RUNTIME_KEYS | played.get(row["id"], set()))
                              & set(live.properties) & set(fprops))
                if kept:
                    report["kept_keys"][row["id"]] = kept
            else:
                conn.execute(
                    "INSERT INTO objects (id, world_id, kind, name, aliases_json, location_id, "
                    "prototype_id, properties_json, slot, controller_session, "
                    "is_human_controlled, kicked_at) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, 0, NULL)",
                    (row["id"], world_id, row["kind"], row["name"], row["aliases_json"],
                     row["prototype_id"], row["properties_json"], row["slot"]))
                pending_locations.append((row["id"], row["location_id"]))
                report["inserted"].append(row["id"])
        for oid, loc in pending_locations:
            if loc is not None:
                conn.execute("UPDATE objects SET location_id = ? WHERE id = ?", (loc, oid))
        # Story definitions: the fresh ones, with applied dreams' live
        # additions on top; every other key is play and stays.
        for key, value in fresh_state.items():
            if key.startswith("def:"):
                if worldstate.get(world_id, key) != value:
                    report["defs"].append(key)
                worldstate.set(world_id, key, value)
            elif worldstate.get(world_id, key) is None:
                worldstate.set(world_id, key, value)
        for a in dream.applied(world_id):
            live_part = a.get("live") or {}
            if live_part.get("facts"):
                facts = dict(worldstate.get(world_id, "def:facts") or {})
                facts.update(copy.deepcopy(live_part["facts"]))
                worldstate.set(world_id, "def:facts", facts)
            for tid, spec in (live_part.get("cast_add") or {}).items():
                if row_ok := objects.get(tid):
                    dream.cast_add(row_ok, spec)
        if fresh_world["starting_room_id"]:
            conn.execute("UPDATE worlds SET starting_room_id = ? WHERE id = ?",
                         (fresh_world["starting_room_id"], world_id))
        if check:
            conn.execute("ROLLBACK")
        else:
            worldstate.set(world_id, "refresh:last", {
                "at": report["at"], "updated": len(report["updated"]),
                "inserted": len(report["inserted"]), "defs": report["defs"]})
            conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return report


def main(argv: list[str] | None = None) -> int:
    from daydream import config

    ap = argparse.ArgumentParser(prog="bin/game world refresh", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("envelope", nargs="?", default=str(PROJECT_ROOT / "worlds/lost-hours.json"))
    ap.add_argument("--db", help="live DB (default: the configured live DB)")
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args(argv)
    path = Path(args.db) if args.db else None
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    try:
        report = refresh(Path(args.envelope), check=args.check)
    finally:
        db.close_db()
    verb = "would update" if args.check else "updated"
    print(f"refresh {report['world']}: {verb} {len(report['updated'])} objects, "
          f"{'would insert' if args.check else 'inserted'} {len(report['inserted'])}, "
          f"{len(report['defs'])} story definitions changed")
    if report["inserted"]:
        print("  new: " + ", ".join(report["inserted"]))
    if report["defs"]:
        print("  defs: " + ", ".join(report["defs"]))
    held = {k: v for k, v in report["kept_keys"].items() if v}
    if held:
        print("  kept from play: " + "; ".join(f"{k} ({', '.join(v)})" for k, v in sorted(held.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
