#!/usr/bin/env python3
"""Assemble a region-sourced world into one committed format-2 envelope.

Design-time only, stdlib only, deterministic: the committed artifact
byte-matches a re-assembly from its sources (a tier_short drift guard
enforces this for zork1). Layout:

    worlds/<name>/world.json      format-2 top level (world/config/voice/
                                  verbs/flags/rules/fuses/daemons/scoring/
                                  start_room), no rooms/toons/things
    worlds/<name>/regions/*.json  {"rooms": [...], "toons": [...],
                                  "things": [...]} merged in filename order

Authoring sugar expanded here (the loader never sees it):

    thing.treasure: {"take": N, "case": M}
        -> properties.treasure = true, score_take = N, score_case = M
           (the engine awards them once, on successful take / case deposit)
    room.bonus: N
        -> a prepended non-consuming enter rule awarding N once per room
    room.zork_name / thing.zork_name / toon.zork_name
        -> stripped into <name>/oracle_map.json (the differential oracle's
           id <-> original-name mapping; never shipped in the envelope)

Usage: tools/assemble_world.py [--source worlds/zork1] [--check]
    --check: assemble to memory and diff against the committed envelope
             (exit 1 on drift) instead of writing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _expand_thing(thing: dict, oracle_things: dict) -> dict:
    out = dict(thing)
    zork_name = out.pop("zork_name", None)
    if isinstance(zork_name, str) and zork_name.strip():
        oracle_things[out["id"]] = zork_name.strip()
    treasure = out.pop("treasure", None)
    if isinstance(treasure, dict):
        props = dict(out.get("properties") or {})
        props["treasure"] = True
        take = treasure.get("take")
        case = treasure.get("case")
        if isinstance(take, int) and take:
            props["score_take"] = take
        if isinstance(case, int) and case:
            props["score_case"] = case
        out["properties"] = props
    return out


def _expand_room(room: dict, oracle_rooms: dict) -> dict:
    out = dict(room)
    zork_name = out.pop("zork_name", None)
    if isinstance(zork_name, str) and zork_name.strip():
        oracle_rooms[out["id"]] = zork_name.strip()
    bonus = out.pop("bonus", None)
    if isinstance(bonus, int) and bonus:
        rule = {
            "on": "enter", "stop": False,
            "do": [{"kind": "adjust_score", "delta": bonus,
                    "once": f"room:{out['id']}"}],
        }
        out["rules"] = [rule] + list(out.get("rules") or [])
    return out


def _expand_toon(toon: dict, oracle_toons: dict) -> dict:
    out = dict(toon)
    zork_name = out.pop("zork_name", None)
    if isinstance(zork_name, str) and zork_name.strip():
        oracle_toons[out["id"]] = zork_name.strip()
    return out


def assemble(source: Path) -> tuple[dict, dict]:
    """Returns (envelope, oracle_map)."""
    world_path = source / "world.json"
    env = json.loads(world_path.read_text())
    for section in ("rooms", "toons", "things"):
        if section in env:
            raise SystemExit(
                f"{world_path}: {section} belongs in regions/, not world.json"
            )
    env.setdefault("format", 2)
    rooms: list = []
    toons: list = []
    things: list = []
    oracle = {"rooms": {}, "toons": {}, "things": {}}
    region_dir = source / "regions"
    region_files = sorted(region_dir.glob("*.json"))
    if not region_files:
        raise SystemExit(f"no region files under {region_dir}")
    for rf in region_files:
        region = json.loads(rf.read_text())
        unknown = set(region) - {"rooms", "toons", "things", "comment"}
        if unknown:
            raise SystemExit(f"{rf}: unknown section(s) {sorted(unknown)}")
        for r in region.get("rooms", []):
            rooms.append(_expand_room(r, oracle["rooms"]))
        for t in region.get("toons", []):
            toons.append(_expand_toon(t, oracle["toons"]))
        for th in region.get("things", []):
            things.append(_expand_thing(th, oracle["things"]))
    env["rooms"] = rooms
    env["toons"] = toons
    env["things"] = things
    return env, oracle


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="worlds/zork1", type=Path)
    ap.add_argument("--output", default=None, type=Path,
                    help="default: worlds/<source-name>.json")
    ap.add_argument("--check", action="store_true",
                    help="diff against the committed artifact; write nothing")
    args = ap.parse_args(argv)
    source: Path = args.source
    output: Path = args.output or source.parent / f"{source.name}.json"
    oracle_path = source / "oracle_map.json"

    env, oracle = assemble(source)
    env_text = _dump(env)
    oracle_text = _dump(oracle)

    if args.check:
        drift = False
        if not output.exists() or output.read_text() != env_text:
            print(f"DRIFT: {output} does not match a re-assembly", file=sys.stderr)
            drift = True
        if not oracle_path.exists() or oracle_path.read_text() != oracle_text:
            print(f"DRIFT: {oracle_path} does not match a re-assembly", file=sys.stderr)
            drift = True
        if drift:
            print("run: tools/assemble_world.py --source " + str(source),
                  file=sys.stderr)
            return 1
        print(f"ok: {output} matches its sources")
        return 0

    output.write_text(env_text)
    oracle_path.write_text(oracle_text)
    print(f"wrote {output} ({len(env['rooms'])} rooms, {len(env['toons'])} toons, "
          f"{len(env['things'])} things) + {oracle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
