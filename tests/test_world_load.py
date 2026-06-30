"""Keyless world authoring (SPEC 2026-06-29, world-authoring-in-session).

A world is built from an Opus-authored JSON envelope with NO LLM call and NO
ANTHROPIC_API_KEY — the canonical keyless path under the generation policy."""

import json
import sqlite3
from pathlib import Path

import pytest

from daydream import admin

pytestmark = pytest.mark.tier_medium


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
        assert [r["slug"] for r in conn.execute("SELECT slug FROM rooms ORDER BY slug")] == [
            "a", "b", "c", "d", "e"
        ]
        assert [r["name"] for r in conn.execute("SELECT name FROM worlds")] == ["A Test World"]
        assert {r["name"] for r in conn.execute("SELECT name FROM toons")} == {
            "Wren", "Mara", "Pell", "Sorrel"
        }
        # Starting room designated from the human toon (Wren, slot 1, room 'a').
        assert conn.execute(
            "SELECT starting_room_id FROM worlds"
        ).fetchone()["starting_room_id"] == "r-a"
    finally:
        conn.close()


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
