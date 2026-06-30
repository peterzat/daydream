"""world-bootstrap-opus: hermetic tests for the bootstrap pipeline.

Mocks ``litellm.acompletion`` at the module boundary so no real
Anthropic call ever fires; tests cover the validation + DB-insertion
path end-to-end.

Spec: 2026-05-07 world-bootstrap-opus, criterion 6.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from daydream.llm import bootstrap as boot

pytestmark = pytest.mark.tier_medium


# ---- a valid envelope --------------------------------------------------


def _valid_envelope() -> dict:
    """Return a minimal but valid LLM envelope. Five rooms with
    bidirectional exits, four toons (one human in slot 1, three NPCs
    in slots 100/101/102), three items, two skills."""
    return {
        "world": {
            "name": "Foggy Forest",
            "aesthetic_seed": "a damp autumn forest village at the edge of a slow river, watercolor edges",
        },
        "rooms": [
            {
                "slug": "lantern",
                "title": "Lantern Square",
                "seed": "a small square strung with paper lanterns; the pavement is damp.",
                "exits": {"north": "alder", "east": "river"},
            },
            {
                "slug": "alder",
                "title": "Old Alder Grove",
                "seed": "an alder grove where the leaves fall slowly into a low pool.",
                "exits": {"south": "lantern", "up": "loft"},
            },
            {
                "slug": "river",
                "title": "Slow River Bend",
                "seed": "the river bends past a moss-furred bridge; mist hangs in patches.",
                "exits": {"west": "lantern", "east": "shed"},
            },
            {
                "slug": "loft",
                "title": "Boatkeeper's Loft",
                "seed": "a wooden loft full of folded sails and clay teacups.",
                "exits": {"down": "alder"},
            },
            {
                "slug": "shed",
                "title": "Tinker's Shed",
                "seed": "a low shed where small brass things rest in shallow trays.",
                "exits": {"west": "river"},
            },
        ],
        "toons": [
            {
                "slot": 1,
                "name": "Wren",
                "seed": "a quiet wandering toon who hums when alone",
                "appearance_seed": "a soft watercolor toon, dusty cloak, freckles",
                "current_room_slug": "lantern",
                "is_human_controlled": 0,
                "mood": "curious",
                "presence_text": None,
            },
            {
                "slot": 100,
                "name": "Linden",
                "seed": "the lantern-lighter; small voice, careful hands",
                "appearance_seed": "a slim person with a long taper and patched mittens",
                "current_room_slug": "lantern",
                "is_human_controlled": 0,
                "mood": "content",
                "presence_text": "Linden tips the taper to a fresh wick and looks up with a small smile.",
            },
            {
                "slot": 101,
                "name": "Marsh",
                "seed": "the boatkeeper; weathered, slow with stories",
                "appearance_seed": "an older person with a fisherman's cap and ink-stained fingers",
                "current_room_slug": "loft",
                "is_human_controlled": 0,
                "mood": "thoughtful",
                "presence_text": "Marsh sets down a folded sail and nods without rising.",
            },
            {
                "slot": 102,
                "name": "Tinker",
                "seed": "the tinker; quick-fingered, sometimes whistles a half-tune",
                "appearance_seed": "a small person in an apron sleeve full of tiny tools",
                "current_room_slug": "shed",
                "is_human_controlled": 0,
                "mood": "curious",
                "presence_text": None,
            },
        ],
        "items": [
            {"room_slug": "lantern", "name": "a paper lantern", "seed": "rice paper, ink-blotted moon"},
            {"room_slug": "loft", "name": "a folded sail", "seed": "soft linen, smelling of cedar"},
            {"room_slug": "shed", "name": "a brass dial", "seed": "weathered, half-marked"},
        ],
        "skills": [
            {
                "name": "linden",
                "ui_hint": "Linden",
                "description": "Speak with Linden, the lantern-lighter.",
                "context_predicate": {"room_slug": "lantern"},
                "prompt_template": "Linden is the lantern-lighter. {{ player_input }} Compose a single narrate effect.",
                "effects_schema": {"allowed_kinds": ["narrate"]},
            },
            {
                "name": "marsh",
                "ui_hint": "Marsh",
                "description": "Speak with Marsh, the boatkeeper.",
                "context_predicate": {"room_slug": "loft"},
                "prompt_template": "Marsh is the boatkeeper. {{ player_input }} Compose a single narrate effect.",
                "effects_schema": {"allowed_kinds": ["narrate"]},
            },
        ],
    }


def _patch_llm_returning(envelope: dict) -> AsyncMock:
    """Build an AsyncMock that mimics litellm's acompletion shape and
    returns the given envelope (or its serialized form, optionally
    wrapped in a code fence)."""
    text = json.dumps(envelope) if isinstance(envelope, dict) else envelope
    mock_response = type(
        "MockResp", (),
        {"choices": [type("MockChoice", (), {"message": type("MockMsg", (), {"content": text})()})()]},
    )()
    return AsyncMock(return_value=mock_response)


# ---- happy path -------------------------------------------------------


def test_bootstrap_writes_db_with_expected_content(tmp_path: Path):
    out = tmp_path / "foggy.db"
    with patch("litellm.acompletion", _patch_llm_returning(_valid_envelope())):
        result = boot.bootstrap_world(
            name="foggy-forest",
            aesthetic="a damp autumn forest village",
            output_path=out,
        )
    assert result == out.resolve()
    assert out.exists()

    conn = sqlite3.connect(str(out))
    conn.row_factory = sqlite3.Row
    try:
        # Single world, named per the LLM envelope.
        rows = conn.execute("SELECT * FROM worlds").fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == "w-bunny"
        assert rows[0]["name"] == "Foggy Forest"

        # Five rooms in w-bunny (objects schema: kind='room', slug + exits
        # in properties_json).
        rooms = conn.execute(
            "SELECT json_extract(properties_json, '$.slug') AS slug, "
            "json_extract(properties_json, '$.exits') AS exits_json "
            "FROM objects WHERE kind = 'room' AND world_id = 'w-bunny'"
        ).fetchall()
        assert len(rooms) == 5
        slugs = {r["slug"] for r in rooms}
        assert slugs == {"lantern", "alder", "river", "loft", "shed"}
        # exits keys reference room IDs (r-<slug>), not slugs.
        lantern = next(r for r in rooms if r["slug"] == "lantern")
        exits = json.loads(lantern["exits_json"])
        assert exits == {"north": "r-alder", "east": "r-river"}

        # Four toons; seeded Wren / Rook / Iris are gone (they were
        # deleted before bootstrap inserted its own).
        toons = conn.execute(
            "SELECT slot, name FROM objects WHERE kind = 'toon' "
            "AND world_id = 'w-bunny' ORDER BY slot"
        ).fetchall()
        assert [(t["slot"], t["name"]) for t in toons] == [
            (1, "Wren"), (100, "Linden"), (101, "Marsh"), (102, "Tinker"),
        ]
        # The seeded Rook (slot 100) and Iris (slot 101) are NOT in
        # the bootstrapped DB — the wipe deleted them and the new
        # toons took those slots.
        rook_iris = conn.execute(
            "SELECT name FROM objects WHERE kind = 'toon' AND name IN ('Rook', 'Iris')"
        ).fetchall()
        assert rook_iris == []

        # Three things.
        items = conn.execute(
            "SELECT name FROM objects WHERE kind = 'thing' AND world_id = 'w-bunny'"
        ).fetchall()
        assert {it["name"] for it in items} == {
            "a paper lantern", "a folded sail", "a brass dial",
        }

        # Two data skills.
        skills = conn.execute(
            "SELECT name, kind FROM skills WHERE kind = 'data'"
        ).fetchall()
        assert {s["name"] for s in skills} == {"linden", "marsh"}
    finally:
        conn.close()


# ---- validation rejects ------------------------------------------------


def test_bootstrap_rejects_non_json(tmp_path: Path):
    out = tmp_path / "bad.db"
    with patch("litellm.acompletion", _patch_llm_returning("this is not JSON")):
        with pytest.raises(boot.BootstrapValidationError, match="non-JSON"):
            boot.bootstrap_world(
                name="x", aesthetic="y", output_path=out,
            )
    assert not out.exists()


def test_bootstrap_rejects_wrong_room_count(tmp_path: Path):
    env = _valid_envelope()
    env["rooms"] = env["rooms"][:3]  # only 3
    with patch("litellm.acompletion", _patch_llm_returning(env)):
        with pytest.raises(boot.BootstrapValidationError, match="rooms.*5 entries"):
            boot.bootstrap_world(
                name="x", aesthetic="y", output_path=tmp_path / "bad.db",
            )


def test_bootstrap_rejects_orphan_exit(tmp_path: Path):
    """Room A → north → B but B has no return path back to A."""
    env = _valid_envelope()
    # Remove the loft → alder return path.
    for r in env["rooms"]:
        if r["slug"] == "loft":
            r["exits"] = {}  # no exits; alder → up → loft is now orphan
    with patch("litellm.acompletion", _patch_llm_returning(env)):
        with pytest.raises(boot.BootstrapValidationError, match="no return path"):
            boot.bootstrap_world(
                name="x", aesthetic="y", output_path=tmp_path / "bad.db",
            )


def test_bootstrap_rejects_duplicate_slot(tmp_path: Path):
    env = _valid_envelope()
    env["toons"][1]["slot"] = env["toons"][0]["slot"]  # both slot 1
    with patch("litellm.acompletion", _patch_llm_returning(env)):
        with pytest.raises(boot.BootstrapValidationError, match="slot duplicate"):
            boot.bootstrap_world(
                name="x", aesthetic="y", output_path=tmp_path / "bad.db",
            )


def test_bootstrap_rejects_unknown_room_in_toon(tmp_path: Path):
    env = _valid_envelope()
    env["toons"][0]["current_room_slug"] = "nowhere"
    with patch("litellm.acompletion", _patch_llm_returning(env)):
        with pytest.raises(boot.BootstrapValidationError, match="not in rooms"):
            boot.bootstrap_world(
                name="x", aesthetic="y", output_path=tmp_path / "bad.db",
            )


# ---- output-path handling ----------------------------------------------


def test_bootstrap_refuses_overwrite_without_force(tmp_path: Path):
    out = tmp_path / "exists.db"
    out.write_text("dummy")
    with patch("litellm.acompletion", _patch_llm_returning(_valid_envelope())):
        with pytest.raises(boot.BootstrapOutputExistsError):
            boot.bootstrap_world(
                name="x", aesthetic="y", output_path=out,
            )
    # File contents preserved (no overwrite).
    assert out.read_text() == "dummy"


def test_bootstrap_overwrites_with_force(tmp_path: Path):
    out = tmp_path / "exists.db"
    out.write_text("dummy")
    with patch("litellm.acompletion", _patch_llm_returning(_valid_envelope())):
        boot.bootstrap_world(
            name="x", aesthetic="y", output_path=out, force=True,
        )
    # Now a real SQLite file: opening and querying succeeds.
    conn = sqlite3.connect(str(out))
    try:
        rows = conn.execute("SELECT name FROM worlds").fetchall()
        assert rows == [("Foggy Forest",)]
    finally:
        conn.close()


# ---- code-fence stripping ---------------------------------------------


def test_bootstrap_strips_markdown_code_fence(tmp_path: Path):
    """Anthropic occasionally wraps JSON in ```json...``` fences despite
    instructions; the parser strips the fence before json.loads."""
    fenced = "```json\n" + json.dumps(_valid_envelope()) + "\n```"
    out = tmp_path / "fenced.db"
    with patch("litellm.acompletion", _patch_llm_returning(fenced)):
        result = boot.bootstrap_world(
            name="x", aesthetic="y", output_path=out,
        )
    assert result.exists()


# ---- LLM error mapping -------------------------------------------------


def test_bootstrap_wraps_llm_failure(tmp_path: Path):
    """A litellm exception is mapped to BootstrapLLMError so the CLI
    can return exit code 2."""
    with patch("litellm.acompletion", AsyncMock(side_effect=RuntimeError("api down"))):
        with pytest.raises(boot.BootstrapLLMError, match="api down"):
            boot.bootstrap_world(
                name="x", aesthetic="y", output_path=tmp_path / "bad.db",
            )
