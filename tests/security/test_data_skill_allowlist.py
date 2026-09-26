"""Data skills honor their declared effect allowlist (SPEC 2026-09-26
criterion 19; docs/PIVOT.md section 10).

A room data skill's `effects_schema.allowed_kinds` used to be documentation
only: the loft's `wind` and `listen` declared narrate-only yet dispatched
under the default set (including an unscoped `move_object`). The declaration
now narrows the caller's allowlist; it can never widen it."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects
from daydream.skills import data as data_skills
from daydream.skills import effects

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _install(name: str, allowed_kinds: list[str] | None) -> None:
    schema = {} if allowed_kinds is None else {"allowed_kinds": allowed_kinds}
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES (?, ?, 'data', '{}', '{{ player_input }}', 'Listen', 'Listen.', ?, 1)",
        (f"skill-{name}", name, json.dumps(schema)),
    )


async def test_narrate_only_skill_cannot_spawn_or_move(monkeypatch):
    lantern = objects.contents("r-meadow", kind="thing")[0]
    monkeypatch.setattr("daydream.llm.client.acompletion_json", AsyncMock(
        return_value={"effects": [
            {"kind": "narrate", "text": "You lean in and listen to the hush."},
            {"kind": "spawn_object", "name": "echo", "seed": "an echo",
             "generated_by": "listen"},
            {"kind": "move_object", "object_id": lantern.id, "dest_id": "t-wren"},
        ]}))
    _install("listen", ["narrate"])
    seq = events.max_seq()
    assert await data_skills.execute_by_name("listen", "t-wren", "r-meadow", "")
    assert not [o for o in objects.contents("r-meadow", kind="thing")
                if o.name == "echo"]
    assert objects.get(lantern.id).location_id == "r-meadow"
    texts = [e.payload.get("text", "") for e in events.fetch_since(seq)
             if e.kind == "narrate"]
    assert any("listen to the hush" in t for t in texts)


def test_declaration_narrows_never_widens():
    body = data_skills.DataSkillBody(
        context_predicate={}, prompt_template="",
        effects_schema={"allowed_kinds": ["narrate", "spawn_room", "win"]},
    )
    got = data_skills.effective_allowed(None, body)
    assert got == frozenset({"narrate"})
    talkish = frozenset({"narrate", "set_mood", "spawn_object"})
    body2 = data_skills.DataSkillBody(
        context_predicate={}, prompt_template="",
        effects_schema={"allowed_kinds": ["narrate", "set_mood"]},
    )
    assert data_skills.effective_allowed(talkish, body2) == frozenset(
        {"narrate", "set_mood"})


def test_undeclared_skill_keeps_the_default_set():
    body = data_skills.DataSkillBody(
        context_predicate={}, prompt_template="", effects_schema={})
    assert data_skills.effective_allowed(None, body) == effects.DEFAULT_KINDS
