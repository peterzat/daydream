"""Backups and deploy preflight (SPEC 2026-09-27 criteria 10 and 13): the
online backup API copies a DB a server is still writing, rotation keeps the
newest N, and preflight reads versions and pending migrations without
running any."""

import json
import sqlite3

import pytest

from daydream import accounts, admin, config, db

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    yield
    db.close_db()


def _world_with_uncheckpointed_write():
    db.init_live()
    conn = db.get_conn()
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("INSERT INTO world_state(world_id, key, value_json) "
                 "SELECT id, 'probe', '\"still in the WAL\"' FROM worlds LIMIT 1")
    return conn


def test_backup_copies_live_writes_still_in_the_wal(tmp_path):
    _world_with_uncheckpointed_write()  # the "server" keeps its connection open
    accounts.init()
    accounts.create_account("wren", "correct horse battery")
    assert admin.cmd_backup(keep=14) == 0
    (out,) = list((tmp_path / "backups").iterdir())
    copy = sqlite3.connect(str(out / "live.db"))
    assert copy.execute("SELECT value_json FROM world_state WHERE key = 'probe'").fetchone()
    acc = sqlite3.connect(str(out / "accounts-dev.db"))
    assert acc.execute("SELECT username FROM accounts").fetchall() == [("wren",)]


def test_backup_rotation_keeps_the_newest(tmp_path, monkeypatch):
    db.init_live()
    root = tmp_path / "backups"
    for name in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (root / name).mkdir(parents=True)
    assert admin.cmd_backup(keep=2) == 0
    kept = sorted(d.name for d in root.iterdir())
    assert len(kept) == 2 and "20260101-000000" not in kept and "20260102-000000" not in kept


def test_backup_retention_is_days_with_a_count_floor(tmp_path):
    """Codereview WARN 2026-09-28: twenty deploy backups in one afternoon must
    not prune the nightly ones. A backup goes only when it is older than 14
    days AND not among the newest 14."""
    from datetime import datetime, timedelta

    db.init_live()
    root = tmp_path / "backups"
    now = datetime.now()
    recent = [(now - timedelta(minutes=10 * i)).strftime("%Y%m%d-%H%M%S") for i in range(1, 21)]
    nights = [(now - timedelta(days=d)).strftime("%Y%m%d-%H%M%S") for d in (3, 9, 13)]
    stale = [(now - timedelta(days=d)).strftime("%Y%m%d-%H%M%S") for d in (15, 30)]
    for name in recent + nights + stale:
        (root / name).mkdir(parents=True)
    assert admin.cmd_backup(keep=14) == 0
    kept = {d.name for d in root.iterdir()}
    assert set(recent + nights) <= kept and not set(stale) & kept


def test_backup_with_nothing_yet_is_a_quiet_no_op(tmp_path, capsys):
    assert admin.cmd_backup(keep=14) == 0
    assert "nothing to back up" in capsys.readouterr().out


def test_snapshot_uses_the_online_copy(tmp_path):
    conn = _world_with_uncheckpointed_write()
    world_id = conn.execute("SELECT id FROM worlds LIMIT 1").fetchone()["id"]
    assert admin.cmd_snapshot(world_id) == 0
    (snap,) = list((tmp_path / "snapshots").iterdir())
    copy = sqlite3.connect(str(snap))
    assert copy.execute("SELECT 1 FROM world_state WHERE key = 'probe'").fetchone()


def test_preflight_reports_versions_and_pending_migrations(tmp_path, capsys):
    db.init_live()
    db.close_db()
    assert admin.cmd_preflight() == 0
    out = capsys.readouterr().out
    assert "world_migrations_pending: 0" in out and "accounts: missing" in out


def test_preflight_refuses_a_major_world_mismatch(tmp_path, capsys):
    db.init_live()
    db.get_conn().execute("UPDATE worlds SET world_version = '0.9'")
    db.get_conn().execute("UPDATE worlds SET world_version = '9.0'")
    db.close_db()
    assert admin.cmd_preflight() == 3
    assert "refuse:" in capsys.readouterr().out


def test_preflight_on_a_brand_new_box(tmp_path, capsys):
    assert admin.cmd_preflight() == 0
    assert "live_world: missing" in capsys.readouterr().out
    assert not config.live_db_path().exists()  # read-only: created nothing



def test_restore_backup_refuses_a_symlink(tmp_path, capsys):
    backup = tmp_path / "b"
    backup.mkdir()
    (backup / "live.db").symlink_to(tmp_path / "elsewhere.db")
    (tmp_path / "elsewhere.db").write_bytes(b"x")
    assert admin.cmd_restore_backup(backup) == 2
    assert "not a regular file" in capsys.readouterr().err


def test_restore_backup_puts_the_dbs_back(tmp_path):
    db.init_live()
    db.close_db()
    backup = tmp_path / "b"
    backup.mkdir()
    (backup / "live.db").write_bytes(config.live_db_path().read_bytes())
    config.live_db_path().write_bytes(b"broken")
    assert admin.cmd_restore_backup(backup) == 0
    assert config.live_db_path().read_bytes() == (backup / "live.db").read_bytes()


def test_announce_cli_writes_the_file(tmp_path):
    from daydream import announce

    assert announce.main(["send", "The lamps are dimming."]) == 0
    assert json.loads(announce.path().read_text()) == {"text": "The lamps are dimming."}
    assert announce.main(["send", "  "]) == 2
