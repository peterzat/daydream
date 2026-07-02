"""NPC dialogue voice + memory binding (playtest fix 2026-07-02).

The shared dispatcher system message forced SECOND-person narration ("address
the player as 'you'") onto NPC dialogue whose templates open "You are Mott..."
— so the model described the NPC's actions as "you", reading as the player's
own body ("A soft smile plays on your lips as you wave back"). Dialogue now
gets a third-person system message built around the NPC's name, selected by an
explicit npc binding threaded from the talk verb (or the legacy t-<skill>
convention), and that same binding fixes memory capture for envelope-installed
`dlg-*` dialogue skills, whose names never matched the convention (the live
memories table held zero dialogue rows)."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, verbs
from daydream.skills import data as data_skills

pytestmark = pytest.mark.tier_short

CANNED = {"effects": [{"kind": "narrate",
                       "text": "Mossling tilts their head. 'Evening, friend.'"}]}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path):
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _install_skill(name: str, ui_hint: str = "Talk") -> None:
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES (?, ?, 'data', '{\"room_slug\": \"__npc_dialogue__\"}', "
        "'You are Mossling. They say: {{ player_input }}', ?, 'Talk to them.', "
        "'{}', 1)",
        (f"skill-{name}", name, ui_hint),
    )


def _spawn_dlg_npc(name: str = "Mossling") -> "objects.Object":
    """An envelope-style NPC: uuid'd toon id + properties.dialogue = dlg-*,
    the shape the loader installs (which the t-<skill> convention never
    matched)."""
    _install_skill(f"dlg-{name.lower()}")
    return objects.spawn(
        "w-bunny", "toon", name, "r-meadow", prototype_id=objects.PROTO_NPC,
        properties={"seed": "a small moss spirit", "mood": "content",
                    "dialogue": f"dlg-{name.lower()}"},
    )


def _spy_llm(monkeypatch):
    spy = AsyncMock(return_value=dict(CANNED))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    return spy


# ---- system-message selection -------------------------------------------


@pytest.mark.asyncio
async def test_talk_uses_third_person_dialogue_system(monkeypatch):
    spy = _spy_llm(monkeypatch)
    npc = _spawn_dlg_npc()
    await verbs.execute_command("t-wren", "talk", dobj_id=npc.id, args="hello")
    system = spy.call_args.kwargs["system"]
    assert "THIRD PERSON" in system
    assert "Mossling" in system
    # The affordance rule ("player's own actions in the SECOND PERSON") must
    # NOT govern dialogue.
    assert "player's own actions in the SECOND PERSON" not in system
    # It advertises talk's own allowed kinds, not the data-skill default.
    for kind in sorted(verbs.VERBS["talk"].allowed_effects):
        assert kind in system
    assert "move_object" not in system  # not in talk's allowlist


@pytest.mark.asyncio
async def test_affordance_skill_keeps_second_person_dispatcher(monkeypatch):
    """A room affordance with no NPC binding (forge/wind/listen) narrates the
    PLAYER's actions and keeps the second-person dispatcher message."""
    spy = _spy_llm(monkeypatch)
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES ('skill-listen', 'listen', 'data', '{}', "
        "'{{ player_input }}', 'Listen', 'Listen closely.', '{}', 1)"
    )
    await data_skills.execute_by_name("listen", "t-wren", "r-meadow", "")
    system = spy.call_args.kwargs["system"]
    assert system == data_skills._DISPATCHER_SYSTEM
    assert "SECOND PERSON" in system


@pytest.mark.asyncio
async def test_legacy_convention_also_gets_dialogue_voice(monkeypatch):
    """The bunny-world binding (skill name -> t-<name>) selects the dialogue
    voice too, so `rook hi` and the voice-samples harness speak correctly."""
    spy = _spy_llm(monkeypatch)
    db.get_conn().execute(
        "INSERT INTO skills (id, name, kind, context_predicate_json, "
        "prompt_template, ui_hint, description, effects_schema_json, enabled) "
        "VALUES ('skill-rook', 'rook', 'data', '{}', "
        "'{{ player_input }}', 'Rook', 'Talk to Rook.', '{}', 1)"
    )
    await data_skills.execute_by_name("rook", "t-wren", "r-forge", "hello")
    system = spy.call_args.kwargs["system"]
    assert "THIRD PERSON" in system and "Rook" in system


# ---- memory binding -------------------------------------------------------


@pytest.mark.asyncio
async def test_talk_memory_binds_to_dlg_npc(monkeypatch):
    """Memory capture fires for an envelope-installed dlg-* dialogue skill,
    bound to the actual NPC toon id — the case the t-<skill-name> convention
    silently missed (live memories table at zero dialogue rows)."""
    _spy_llm(monkeypatch)
    captured: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "daydream.memories.capture",
        lambda npc_id, world_id, text, source_event_seq=None:
            captured.append((npc_id, world_id, text)),
    )
    npc = _spawn_dlg_npc()
    await verbs.execute_command("t-wren", "talk", dobj_id=npc.id, args="hello")
    assert [c[0] for c in captured] == [npc.id, npc.id]
    assert captured[0][2] == "the visitor said: hello"
    # The NPC's own name is the speaker, not the skill's ui_hint ("Talk").
    assert captured[1][2].startswith("Mossling said:")


@pytest.mark.asyncio
async def test_talk_memory_retrieves_for_dlg_npc(monkeypatch):
    _spy_llm(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(
        "daydream.memories.retrieve",
        lambda npc_id, world_id, query, k=3: (calls.append(npc_id), [])[1],
    )
    npc = _spawn_dlg_npc()
    await verbs.execute_command("t-wren", "talk", dobj_id=npc.id, args="hello")
    assert calls == [npc.id]
