"""Keyless world authoring (SPEC 2026-06-29, world-authoring-in-session).

A world is built from an Opus-authored JSON envelope with NO LLM call and NO
ANTHROPIC_API_KEY — the canonical keyless path under the generation policy."""

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import admin, config, db, events, objects, verbs, version

pytestmark = pytest.mark.tier_medium

REPO = Path(__file__).resolve().parent.parent


def _envelope() -> dict:
    """A minimal valid envelope (same schema bootstrap's LLM produces): 5
    rooms in a line with bidirectional exits, 4 toons, an item, 2 skills."""
    rooms = [
        {"slug": "a", "title": "Room A", "seed": "A soft room.", "exits": {"east": "b"}},
        {"slug": "b", "title": "Room B", "seed": "A warm room.",
         "exits": {"west": "a", "east": "c"}},
        {"slug": "c", "title": "Room C", "seed": "A quiet room.",
         "exits": {"west": "b", "east": "d"}},
        {"slug": "d", "title": "Room D", "seed": "A dim room.",
         "exits": {"west": "c", "east": "e"}},
        {"slug": "e", "title": "Room E", "seed": "A still room.", "exits": {"west": "d"}},
    ]
    toons = [
        {"slot": 1, "name": "Wren", "seed": "a wanderer", "appearance_seed": "a wisp",
         "current_room_slug": "a", "is_human_controlled": 1, "mood": "curious",
         "presence_text": None},
        {"slot": 100, "name": "Mara", "seed": "a keeper", "appearance_seed": "weathered",
         "current_room_slug": "b", "is_human_controlled": 0, "mood": "content",
         "presence_text": "Mara nods."},
        {"slot": 101, "name": "Pell", "seed": "a reader", "appearance_seed": "ink-stained",
         "current_room_slug": "c", "is_human_controlled": 0, "mood": "thoughtful",
         "presence_text": None},
        {"slot": 102, "name": "Sorrel", "seed": "a tender", "appearance_seed": "green",
         "current_room_slug": "d", "is_human_controlled": 0, "mood": "content",
         "presence_text": None},
    ]
    items = [{"room_slug": "a", "name": "a lantern", "seed": "a warm lantern"}]
    skills = [
        {"name": "greet-mara", "ui_hint": "Greet", "description": "Say hello to Mara.",
         "context_predicate": {"room_slug": "b"}, "prompt_template": "{{ player_input }}",
         "effects_schema": {"allowed_kinds": ["narrate"]}},
        {"name": "read-with-pell", "ui_hint": "Read", "description": "Read with Pell.",
         "context_predicate": {"room_slug": "c"}, "prompt_template": "{{ player_input }}",
         "effects_schema": {"allowed_kinds": ["narrate"]}},
    ]
    return {
        "world": {"name": "A Test World", "aesthetic_seed": "soft and small"},
        "rooms": rooms, "toons": toons, "items": items, "skills": skills,
    }


def test_world_load_writes_db_keyless(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # prove no key needed
    env_path = tmp_path / "world.json"
    env_path.write_text(json.dumps(_envelope()))
    out = tmp_path / "out.db"

    assert admin.main(["load", str(env_path), "--output", str(out)]) == 0
    assert out.exists()

    conn = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # The world is written onto the unified `objects` schema: rooms /
        # toons are rows discriminated by `kind`, room slug in properties.
        assert [
            r["slug"] for r in conn.execute(
                "SELECT json_extract(properties_json, '$.slug') AS slug "
                "FROM objects WHERE kind = 'room' "
                "ORDER BY json_extract(properties_json, '$.slug')"
            )
        ] == ["a", "b", "c", "d", "e"]
        assert [r["name"] for r in conn.execute("SELECT name FROM worlds")] == ["A Test World"]
        assert {
            r["name"] for r in conn.execute("SELECT name FROM objects WHERE kind = 'toon'")
        } == {"Wren", "Mara", "Pell", "Sorrel"}
        # Prototypes are seeded so concrete objects can inherit verbs.
        assert {
            r["name"] for r in conn.execute(
                "SELECT name FROM objects WHERE kind = 'prototype'"
            )
        } == {"room", "npc", "thing", "readable", "fixture"}
        # Starting room designated from the human toon (Wren, slot 1, room 'a').
        assert conn.execute(
            "SELECT starting_room_id FROM worlds"
        ).fetchone()["starting_room_id"] == "r-a"
        # Stamped with the code's WORLD_VERSION so the loaded world matches the
        # running server and boots without a version block (migration 012).
        assert conn.execute(
            "SELECT world_version FROM worlds"
        ).fetchone()["world_version"] == version.WORLD_VERSION
    finally:
        conn.close()


def test_world_load_object_schema_with_aliases_and_dialogue(tmp_path: Path, monkeypatch):
    """Keyless object-schema authoring: an envelope carrying toon aliases, a
    per-NPC `talk` dialogue binding, and a readable thing with aliases loads
    onto the objects schema with NO LLM call / NO key (SPEC 2026-06-30)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env = _envelope()
    # Give Mara (an NPC) aliases + a bound dialogue, and a readable thing.
    mara = next(t for t in env["toons"] if t["name"] == "Mara")
    mara["aliases"] = ["keeper", "the keeper"]
    mara["dialogue"] = {
        "ui_hint": "Talk", "description": "Talk to Mara.",
        "prompt_template": "{{ player_input }}",
        "effects_schema": {"allowed_kinds": ["narrate", "spawn_object"]},
    }
    env["items"].append(
        {"room_slug": "b", "name": "a sheaf of papers", "seed": "loose pages",
         "aliases": ["papers", "sheaf"], "readable": True}
    )
    env_path = tmp_path / "world.json"
    env_path.write_text(json.dumps(env))
    out = tmp_path / "out.db"
    assert admin.main(["load", str(env_path), "--output", str(out)]) == 0

    conn = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # Prototypes seeded.
        assert {r["name"] for r in conn.execute(
            "SELECT name FROM objects WHERE kind = 'prototype'"
        )} == {"room", "npc", "thing", "readable", "fixture"}
        # Mara carries aliases + a dialogue binding referencing a data skill.
        mara_row = conn.execute(
            "SELECT aliases_json, json_extract(properties_json, '$.dialogue') AS dialogue "
            "FROM objects WHERE kind = 'toon' AND name = 'Mara'"
        ).fetchone()
        assert json.loads(mara_row["aliases_json"]) == ["keeper", "the keeper"]
        assert mara_row["dialogue"] == "dlg-mara"
        # The bound dialogue skill is installed (hidden from room affordances).
        skill = conn.execute(
            "SELECT context_predicate_json FROM skills WHERE name = 'dlg-mara'"
        ).fetchone()
        assert skill is not None
        assert "__npc_dialogue__" in skill["context_predicate_json"]
        # The readable thing carries aliases + the readable prototype.
        papers = conn.execute(
            "SELECT aliases_json, prototype_id FROM objects "
            "WHERE kind = 'thing' AND name = 'a sheaf of papers'"
        ).fetchone()
        assert json.loads(papers["aliases_json"]) == ["papers", "sheaf"]
        assert papers["prototype_id"] == "proto-readable"
    finally:
        conn.close()


def test_authored_bunny_world_loads_and_rook_spawns_papers(tmp_path: Path, monkeypatch):
    """Integration for the committed reset world (worlds/bunny.json): it loads
    keyless onto the object schema, and talking to its Rook (via the per-NPC
    dialogue binding) spawns the canonical 'sheaf of papers'. The server boot +
    browser check remain the flagged one-time manual steps (SPEC 2026-06-30)."""
    out = tmp_path / "live.db"
    assert admin.main(["load", str(REPO / "worlds" / "bunny.json"), "--output", str(out)]) == 0
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=out, migrations_dir=config.MIGRATIONS_DIR)
    try:
        conn = db.get_conn()
        rook_id = conn.execute(
            "SELECT id FROM objects WHERE kind = 'toon' AND name = 'Rook'"
        ).fetchone()["id"]
        # Wren (slot 1) is the claimable human toon (is_human_controlled=0 until
        # claimed, matching the seed convention); use it as the acting player.
        human_id = conn.execute(
            "SELECT id FROM objects WHERE kind = 'toon' AND slot = 1"
        ).fetchone()["id"]
        rook = objects.get(rook_id)
        objects.move(human_id, rook.location_id)  # co-locate to bring Rook in scope
        # The dialogue binding resolves to the loaded dlg-rook skill; mock its
        # LLM output to emit the papers (as the authored prompt instructs).
        monkeypatch.setattr(
            "daydream.llm.client.acompletion_json",
            AsyncMock(return_value={"effects": [
                {"kind": "narrate", "text": "Rook spreads a sheaf of papers across the bench."},
                {"kind": "spawn_object", "name": "a sheaf of papers",
                 "seed": "loose pages, soft at the edges", "readable": True,
                 "aliases": ["papers", "sheaf"], "generated_by": "talk:rook"},
            ]}),
        )
        asyncio.run(
            verbs.execute_command(human_id, "talk", dobj_id=rook_id, args="show me your papers")
        )
        papers = [
            o for o in objects.contents(rook.location_id, "thing")
            if o.name == "a sheaf of papers"
        ]
        assert len(papers) == 1
        # Readable prototype now grants give + read alongside examine/take/drop.
        assert objects.verbs_for(papers[0]) == ["examine", "take", "drop", "give", "read"]
    finally:
        db.close_db()
        events.reset_subscribers()


def test_world_load_refuses_invalid_envelope(tmp_path: Path):
    bad = _envelope()
    bad["rooms"] = bad["rooms"][:3]  # only 3 rooms -> validation error
    env_path = tmp_path / "bad.json"
    env_path.write_text(json.dumps(bad))
    out = tmp_path / "out.db"
    assert admin.main(["load", str(env_path), "--output", str(out)]) == 3
    assert not out.exists()


def test_world_load_refuses_existing_output(tmp_path: Path):
    env_path = tmp_path / "world.json"
    env_path.write_text(json.dumps(_envelope()))
    out = tmp_path / "out.db"
    out.write_text("preexisting")
    assert admin.main(["load", str(env_path), "--output", str(out)]) == 4
