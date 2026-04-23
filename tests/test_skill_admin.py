"""Tests for `bin/game world skill add` via daydream.admin.cmd_skill_add.

Covers SPEC criterion 1: upsert a data skill from a JSON author file,
malformed / missing-field files fail non-zero with a diagnostic and do
NOT write a partial row, and re-running with the same name is idempotent.
Also covers criterion 8's hot-reload promise: the installed skill is
immediately visible via the registry without a server restart.
"""

import json
from pathlib import Path

import pytest

from daydream import admin, config, db, events
from daydream.skills import registry

pytestmark = pytest.mark.tier_short


@pytest.fixture
def live_world(tmp_path: Path, monkeypatch):
    """Stand up a fresh live DB at tmp_path (matching config.live_db_path()
    layout) so admin commands that check _require_live_db() see a real
    file on disk."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    events.reset_subscribers()
    (tmp_path / f"worlds-{config.env()}").mkdir(parents=True, exist_ok=True)
    db.init_live(
        path=tmp_path / f"worlds-{config.env()}/live.db",
        migrations_dir=config.MIGRATIONS_DIR,
    )
    yield tmp_path
    db.close_db()
    events.reset_subscribers()


def _sample_payload(**overrides) -> dict:
    base = {
        "name": "forge",
        "ui_hint": "Forge",
        "description": "Work something at the forge.",
        "prompt_template": "At the forge. Player input: {{ player_input }}",
        "context_predicate": {"room_slug": "forge"},
        "effects_schema": {"effects": [{"kind": "add_item"}]},
    }
    base.update(overrides)
    return base


def _write(path: Path, payload) -> Path:
    """Write payload to path as JSON. If payload is not JSON-serializable,
    pass a string to write raw text."""
    if isinstance(payload, str):
        path.write_text(payload)
    else:
        path.write_text(json.dumps(payload))
    return path


# ---- happy path ----------------------------------------------------------


def test_skill_add_writes_row_and_registry_sees_it(live_world):
    p = _write(live_world / "forge.json", _sample_payload())
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 0
    # Registry sees the new skill immediately — no server restart (SPEC 8).
    spec = registry.find("forge")
    assert spec is not None
    assert spec.kind == "data"
    assert spec.ui_hint == "Forge"


def test_skill_add_stores_predicate_and_template_correctly(live_world):
    p = _write(live_world / "forge.json", _sample_payload())
    admin.main(["skill", "add", str(p)])
    row = db.get_conn().execute(
        "SELECT context_predicate_json, prompt_template, effects_schema_json, "
        "       ui_hint, kind, author, enabled FROM skills WHERE name = 'forge'"
    ).fetchone()
    assert row is not None
    assert row["kind"] == "data"
    assert row["enabled"] == 1
    assert json.loads(row["context_predicate_json"]) == {"room_slug": "forge"}
    assert "{{ player_input }}" in row["prompt_template"]
    assert row["author"] == "admin"


def test_skill_add_lowercases_name(live_world):
    p = _write(live_world / "forge.json", _sample_payload(name="FORGE"))
    admin.main(["skill", "add", str(p)])
    row = db.get_conn().execute(
        "SELECT name FROM skills WHERE id = 'skill-forge'"
    ).fetchone()
    assert row["name"] == "forge"


def test_skill_add_stores_authored_description(live_world):
    # The `description` field is REQUIRED by validation and must be
    # persisted so the interpreter sees the author's one-line summary
    # (not a generic "A data skill: <name>." fallback). Verified via
    # the registry read path so the DB write + loader + SkillSpec are
    # exercised end to end.
    authored = "Work something small at the quiet forge. Args: a short note."
    p = _write(live_world / "forge.json", _sample_payload(description=authored))
    admin.main(["skill", "add", str(p)])
    spec = registry.find("forge")
    assert spec is not None
    assert spec.description == authored


def test_skill_add_respects_custom_author(live_world):
    p = _write(live_world / "forge.json", _sample_payload(author="peter"))
    admin.main(["skill", "add", str(p)])
    row = db.get_conn().execute(
        "SELECT author FROM skills WHERE name = 'forge'"
    ).fetchone()
    assert row["author"] == "peter"


# ---- idempotent upsert ---------------------------------------------------


def test_skill_add_is_idempotent_on_rerun(live_world):
    p = _write(live_world / "forge.json", _sample_payload())
    admin.main(["skill", "add", str(p)])
    first_id = db.get_conn().execute(
        "SELECT id FROM skills WHERE name = 'forge'"
    ).fetchone()["id"]
    # Edit the file and re-run: row updates in place, same PK.
    _write(p, _sample_payload(
        ui_hint="Forge (v2)",
        prompt_template="At the forge v2: {{ player_input }}",
    ))
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 0
    count = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM skills WHERE name = 'forge'"
    ).fetchone()["n"]
    assert count == 1  # upsert, not insert
    row = db.get_conn().execute(
        "SELECT id, ui_hint, prompt_template FROM skills WHERE name = 'forge'"
    ).fetchone()
    assert row["id"] == first_id  # PK preserved
    assert row["ui_hint"] == "Forge (v2)"
    assert "v2" in row["prompt_template"]


# ---- malformed / missing-field failures ---------------------------------


def test_skill_add_rejects_missing_file(live_world, capsys):
    rc = admin.main(["skill", "add", str(live_world / "missing.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no such file" in err


def test_skill_add_rejects_malformed_json(live_world, capsys):
    p = _write(live_world / "bad.json", "{ not valid json")
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "invalid JSON" in err


def test_skill_add_rejects_non_object_top_level(live_world, capsys):
    p = _write(live_world / "arr.json", [1, 2, 3])
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 2
    assert "object" in capsys.readouterr().err


@pytest.mark.parametrize("field", ["name", "ui_hint", "description", "prompt_template"])
def test_skill_add_rejects_missing_string_field(live_world, capsys, field):
    payload = _sample_payload()
    del payload[field]
    p = _write(live_world / "bad.json", payload)
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 2
    err = capsys.readouterr().err
    assert field in err


@pytest.mark.parametrize("field", ["name", "ui_hint", "description", "prompt_template"])
def test_skill_add_rejects_empty_string_field(live_world, capsys, field):
    payload = _sample_payload()
    payload[field] = "   "
    p = _write(live_world / "bad.json", payload)
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 2
    assert field in capsys.readouterr().err


@pytest.mark.parametrize("field", ["context_predicate", "effects_schema"])
def test_skill_add_rejects_non_object_predicate_or_schema(live_world, capsys, field):
    payload = _sample_payload()
    payload[field] = "not-an-object"
    p = _write(live_world / "bad.json", payload)
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 2
    assert field in capsys.readouterr().err


def test_skill_add_writes_nothing_on_validation_failure(live_world):
    payload = _sample_payload()
    del payload["name"]
    p = _write(live_world / "bad.json", payload)
    before = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM skills WHERE kind = 'data'"
    ).fetchone()["n"]
    admin.main(["skill", "add", str(p)])
    after = db.get_conn().execute(
        "SELECT COUNT(*) AS n FROM skills WHERE kind = 'data'"
    ).fetchone()["n"]
    assert before == after  # no partial write


def test_skill_add_rejects_when_live_db_missing(tmp_path: Path, monkeypatch, capsys):
    # Point DAYDREAM_DATA_DIR at an empty dir so live_db_path() doesn't
    # exist; verify cmd refuses with the standard _require_live_db message.
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    p = _write(tmp_path / "forge.json", _sample_payload())
    rc = admin.main(["skill", "add", str(p)])
    assert rc == 2
    assert "no live DB" in capsys.readouterr().err
