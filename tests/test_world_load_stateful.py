"""Loader/validator extension for stateful interactive objects (SPEC 2026-07-01).

The keyless world envelope can now author stateful things: an item `properties`
passthrough (state / state_text / use rule / contains / locked_text / open_text),
per-object `verbs` (open / use), readable `text`, an immovable `fixture` flag,
and NPC `properties` (wants / gives / gives_text). This exercises the loader
writers + validator directly against a synthetic envelope, so it stays
independent of the shipped world (that gets its own integrity test). tier_short:
`load_world` is a handful of SQLite inserts, no LLM, no server."""

import json
import sqlite3
from pathlib import Path

import pytest

from daydream.llm import bootstrap

pytestmark = pytest.mark.tier_short


def _base_envelope() -> dict:
    """A minimal valid envelope (5 rooms in a line, 4 toons, 2 skills)."""
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
        {"slot": 100, "name": "Tace", "seed": "a clockmaker", "appearance_seed": "aproned",
         "current_room_slug": "b", "is_human_controlled": 0, "mood": "wistful",
         "presence_text": None},
        {"slot": 101, "name": "Bell", "seed": "a lamplighter", "appearance_seed": "bright",
         "current_room_slug": "c", "is_human_controlled": 0, "mood": "content",
         "presence_text": None},
        {"slot": 102, "name": "Mott", "seed": "a sweeper", "appearance_seed": "dusty",
         "current_room_slug": "d", "is_human_controlled": 0, "mood": "content",
         "presence_text": None},
    ]
    skills = [
        {"name": "wind", "ui_hint": "Wind", "description": "Wind a spring.",
         "context_predicate": {"room_slug": "b"}, "prompt_template": "{{ player_input }}",
         "effects_schema": {"allowed_kinds": ["narrate"]}},
        {"name": "listen", "ui_hint": "Listen", "description": "Listen at the well.",
         "context_predicate": {"room_slug": "e"}, "prompt_template": "{{ player_input }}",
         "effects_schema": {"allowed_kinds": ["narrate"]}},
    ]
    return {
        "world": {"name": "A Stateful World", "aesthetic_seed": "soft and small"},
        "rooms": rooms, "toons": toons, "items": [], "skills": skills,
    }


def _load(env: dict, tmp_path: Path) -> sqlite3.Connection:
    out = tmp_path / "out.db"
    bootstrap.load_world(env["world"]["name"], env, out, force=True)
    conn = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _props(conn: sqlite3.Connection, name: str) -> dict:
    row = conn.execute(
        "SELECT properties_json FROM objects WHERE name = ?", (name,)
    ).fetchone()
    return json.loads(row["properties_json"])


# ---- new prototypes carry the new default verbs ------------------------


def test_prototypes_include_fixture_and_new_default_verbs(tmp_path: Path):
    conn = _load(_base_envelope(), tmp_path)
    try:
        protos = {
            r["name"]: json.loads(r["properties_json"])["verbs"]
            for r in conn.execute(
                "SELECT name, properties_json FROM objects WHERE kind = 'prototype'"
            )
        }
        assert set(protos) == {"room", "npc", "thing", "readable", "fixture"}
        assert "give" in protos["thing"]
        assert "give" in protos["readable"] and "read" in protos["readable"]
        assert protos["fixture"] == ["examine"]  # immovable: no take/drop
    finally:
        conn.close()


# ---- item: properties / verbs / text / fixture land -------------------


def test_stateful_item_properties_and_verbs_persist(tmp_path: Path):
    env = _base_envelope()
    env["items"].append({
        "room_slug": "a", "name": "clock case", "fixture": True, "verbs": ["open"],
        "seed": "a tall glass-fronted case",
        "properties": {
            "state": "locked",
            "state_text": {"locked": "a small lock holds it", "open": "it stands open"},
            "locked_text": "The case is locked.",
            "open_text": "The case swings wide.",
            "use": {"with": "case key", "from_state": "locked",
                    "to_state": "unlocked", "text": "The lock gives."},
            "contains": {"name": "warm brass cog", "seed": "a small cog"},
        },
    })
    conn = _load(env, tmp_path)
    try:
        # Fixture prototype selected (immovable), per-object verb layered on.
        row = conn.execute(
            "SELECT prototype_id, properties_json FROM objects WHERE name = 'clock case'"
        ).fetchone()
        assert row["prototype_id"] == "proto-fixture"
        props = json.loads(row["properties_json"])
        assert props["state"] == "locked"
        assert props["verbs"] == ["open"]
        assert props["use"]["with"] == "case key"
        assert props["contains"]["name"] == "warm brass cog"
        assert props["seed"] == "a tall glass-fronted case"  # top-level seed preserved
    finally:
        conn.close()


def test_readable_item_text_persists_on_readable_prototype(tmp_path: Path):
    env = _base_envelope()
    env["items"].append({
        "room_slug": "a", "name": "repair ledger", "readable": True,
        "seed": "a worn leather ledger", "aliases": ["ledger"],
        "text": "The escapement gear is lost; return it to Tace.",
    })
    conn = _load(env, tmp_path)
    try:
        row = conn.execute(
            "SELECT prototype_id, properties_json FROM objects WHERE name = 'repair ledger'"
        ).fetchone()
        assert row["prototype_id"] == "proto-readable"
        assert "escapement gear" in json.loads(row["properties_json"])["text"]
    finally:
        conn.close()


# ---- toon: quest properties (wants / gives) land ----------------------


def test_toon_quest_properties_persist(tmp_path: Path):
    env = _base_envelope()
    tace = next(t for t in env["toons"] if t["name"] == "Tace")
    tace["properties"] = {
        "wants": "escapement gear",
        "gives": {"name": "case key", "seed": "a small warm key",
                  "aliases": ["key"], "verbs": ["use"]},
        "gives_text": "Tace presses the case-key into your palm.",
        "gives_mood": "delighted",
    }
    conn = _load(env, tmp_path)
    try:
        props = _props(conn, "Tace")
        assert props["wants"] == "escapement gear"
        assert props["gives"]["name"] == "case key"
        assert props["gives"]["verbs"] == ["use"]
        assert props["gives_mood"] == "delighted"
        # Core persona fields survive the merge.
        assert props["seed"] == "a clockmaker" and props["mood"] == "wistful"
    finally:
        conn.close()


# ---- malformed new fields fail loudly ---------------------------------


@pytest.mark.parametrize("mutate", [
    lambda env: env["items"].append(
        {"room_slug": "a", "name": "x", "seed": "s", "properties": "notadict"}),
    lambda env: env["items"].append(
        {"room_slug": "a", "name": "x", "seed": "s", "verbs": [1, 2]}),
    lambda env: env["items"].append(
        {"room_slug": "a", "name": "x", "seed": "s", "text": 42}),
    lambda env: env["items"].append(
        {"room_slug": "a", "name": "x", "seed": "s", "fixture": "yes"}),
])
def test_malformed_item_fields_rejected(tmp_path: Path, mutate):
    env = _base_envelope()
    mutate(env)
    with pytest.raises(bootstrap.BootstrapValidationError):
        bootstrap.load_world("bad", env, tmp_path / "bad.db", force=True)


def test_malformed_toon_properties_rejected(tmp_path: Path):
    env = _base_envelope()
    env["toons"][1]["properties"] = "notadict"
    with pytest.raises(bootstrap.BootstrapValidationError):
        bootstrap.load_world("bad", env, tmp_path / "bad.db", force=True)
