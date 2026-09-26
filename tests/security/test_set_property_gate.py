"""set_property is a per-verb opt-in kind (codereview WARN 2026-09-26b).

talk's allowlist and DEFAULT_KINDS (every standalone data skill) used to
carry set_property, so a player injection could get the dialogue model to
write ANY property on ANY object with ANY JSON value: a non-string room seed
crashed every snapshot, a non-string presence_text disconnected everyone
entering the room, and a room's exits/title write bypassed the restricted
link_exit/rename_object kinds. set_property is now in RESTRICTED_KINDS and
off talk's allowlist. These drive the real talk and data-skill paths with a
mocked model emitting set_property and assert nothing is mutated."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, verbs
from daydream.skills import data as data_skills
from daydream.skills import effects

pytestmark = pytest.mark.tier_short

HOSTILE = {"effects": [
    {"kind": "narrate", "text": "Mossling hums and looks out over the meadow."},
    {"kind": "set_property", "target_id": "r-meadow", "key": "seed", "value": 7},
    {"kind": "set_property", "target_id": "r-meadow", "key": "exits",
     "value": {"up": "r-forge"}},
    {"kind": "set_property", "target_id": "r-meadow", "key": "title",
     "value": "A Stolen Meadow"},
    {"kind": "set_property", "target_id": "t-rook", "key": "presence_text",
     "value": ["not", "a", "string"]},
]}
WATCHED = [("r-meadow", "seed"), ("r-meadow", "exits"), ("r-meadow", "title"),
           ("t-rook", "presence_text")]


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    monkeypatch.setattr("daydream.llm.client.acompletion_json",
                        AsyncMock(return_value=dict(HOSTILE)))
    yield
    db.close_db()
    events.reset_subscribers()


def _install_skill(name: str, predicate: str) -> None:
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES (?, ?, 'data', ?, '{{ player_input }}', 'Talk', 'Talk.', '{}', 1)",
        (f"skill-{name}", name, predicate),
    )


def _watched() -> dict:
    return {(oid, key): objects.get_property(oid, key) for oid, key in WATCHED}


def _assert_rejected(before: dict, since_seq: int) -> None:
    assert _watched() == before
    new = events.fetch_since(since_seq)
    assert not [e for e in new if e.kind == "property_set"]
    # The allowed narrate in the same batch still speaks.
    assert any("Mossling hums" in e.payload.get("text", "") for e in new)


def test_set_property_is_restricted_and_off_talk():
    assert "set_property" in effects.RESTRICTED_KINDS
    assert "set_property" not in effects.DEFAULT_KINDS
    assert "set_property" not in verbs.VERBS["talk"].allowed_effects
    assert "set_property" in effects.RULE_KINDS  # authored rules keep it


async def test_talk_dispatched_set_property_is_rejected():
    _install_skill("dlg-mossling", '{"room_slug": "__npc_dialogue__"}')
    npc = objects.spawn(
        "w-bunny", "toon", "Mossling", "r-meadow", prototype_id=objects.PROTO_NPC,
        properties={"seed": "a small moss spirit", "dialogue": "dlg-mossling"},
    )
    before, seq = _watched(), events.max_seq()
    await verbs.execute_command("t-wren", "talk", dobj_id=npc.id, args="hello")
    _assert_rejected(before, seq)


async def test_default_kinds_data_skill_set_property_is_rejected():
    _install_skill("listen", "{}")
    before, seq = _watched(), events.max_seq()
    assert await data_skills.execute_by_name("listen", "t-wren", "r-meadow", "")
    _assert_rejected(before, seq)
