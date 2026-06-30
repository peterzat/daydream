"""bin/game world {list,archive,restore,verify,delete} via the daydream.admin
CLI. Tests exercise admin.main() directly with a temp data dir; bash side
is a thin shell over `python -m daydream.admin`."""

import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from daydream import admin, assets, config, db
from daydream.images import cache as image_cache

pytestmark = pytest.mark.tier_medium


@pytest.fixture
def live_world(tmp_path: Path, monkeypatch):
    """Init a live DB at tmp_path with the seeded bunny-world + a recorded
    asset + a cache file on disk so all subcommands have something real
    to operate on."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    db.init_live(
        path=tmp_path / f"worlds-{config.env()}/live.db",
        migrations_dir=config.MIGRATIONS_DIR,
    )
    seed = "a small grassy meadow at dusk, fireflies just beginning, soft watercolor edges"
    h = image_cache.seed_hash(seed)
    cache_file = image_cache.cache_dir() / "w-bunny" / "room" / "r-meadow" / f"{h}.png"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * 1000
    cache_file.write_bytes(payload)
    assets.record_image_generation(
        world_id="w-bunny",
        target_kind="room",
        target_id="r-meadow",
        target_seed=seed,
        seed_hash=h,
        file_relpath=str(cache_file.relative_to(tmp_path)),
        model="sd_xl_base_1.0.safetensors",
        lora="watercolor_v1_sdxl.safetensors",
        prompt_text=seed + " soft watercolor",
        file_bytes=len(payload),
        workflow_hash="wfh-test",
    )
    yield tmp_path
    db.close_db()


# ---- list ---------------------------------------------------------------


def test_list_prints_seeded_world(live_world, capsys):
    rc = admin.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "w-bunny" in out
    assert "bunny-world" in out
    assert " 1 " in out or "  1  " in out


def test_list_prints_message_when_no_worlds(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    db.init_live(
        path=tmp_path / f"worlds-{config.env()}/live.db",
        migrations_dir=config.MIGRATIONS_DIR,
    )
    conn = db.get_conn()
    for tbl in ("objects", "worlds"):
        conn.execute(f"DELETE FROM {tbl}")
    try:
        rc = admin.main(["list"])
        assert rc == 0
        assert "no worlds" in capsys.readouterr().out
    finally:
        db.close_db()


# ---- archive ------------------------------------------------------------


def test_archive_creates_tarball_with_db_and_cache_and_manifest(live_world, capsys):
    rc = admin.main(["archive", "w-bunny"])
    assert rc == 0
    archives = list((live_world / "archives").iterdir())
    assert len(archives) == 1
    arc = archives[0]
    assert arc.name.startswith("w-bunny-")
    assert arc.name.endswith(".tar.gz")

    with tarfile.open(arc, "r:gz") as t:
        names = t.getnames()
        manifest_bytes = t.extractfile("MANIFEST.json").read()
    assert "MANIFEST.json" in names
    assert any(n.endswith("live.db") for n in names)
    assert any("images/cache/w-bunny/room/r-meadow/" in n for n in names)

    manifest = json.loads(manifest_bytes)
    assert manifest["archive_format_version"] == admin.ARCHIVE_FORMAT_VERSION
    assert manifest["world_id"] == "w-bunny"
    assert manifest["asset_count"] == 1
    assert manifest["schema_version"] >= 3  # 003 is applied


def test_archive_works_with_no_cache_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    db.init_live(
        path=tmp_path / f"worlds-{config.env()}/live.db",
        migrations_dir=config.MIGRATIONS_DIR,
    )
    try:
        rc = admin.main(["archive", "w-bunny"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "no cache dir" in captured.err
        archives = list((tmp_path / "archives").iterdir())
        assert len(archives) == 1
    finally:
        db.close_db()


# ---- restore ------------------------------------------------------------


def test_restore_round_trip(live_world, tmp_path, monkeypatch):
    """Archive a world, wipe the data dir, restore from the archive,
    confirm the DB rows + cache file came back."""
    rc = admin.main(["archive", "w-bunny"])
    assert rc == 0
    archive = next((live_world / "archives").iterdir())

    # Capture baseline state for comparison.
    baseline_assets = assets.list_assets()
    assert len(baseline_assets) == 1

    # Wipe state and re-init in a fresh data dir.
    db.close_db()
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(fresh))

    rc = admin.main(["restore", str(archive), "--yes"])
    assert rc == 0
    # The live DB now exists at the new data_dir's live path.
    assert config.live_db_path().exists()
    # Re-init against the restored DB and confirm rows survived.
    db.init_live()
    restored = assets.list_assets()
    assert len(restored) == 1
    assert restored[0].target_id == "r-meadow"
    # Cache file is back on disk too.
    assert (fresh / "images" / "cache" / "w-bunny").exists()
    db.close_db()


def test_restore_refuses_without_yes(live_world, tmp_path, monkeypatch, capsys):
    rc = admin.main(["archive", "w-bunny"])
    assert rc == 0
    archive = next((live_world / "archives").iterdir())
    rc = admin.main(["restore", str(archive)])
    assert rc == 2
    assert "refusing to restore" in capsys.readouterr().err


def test_restore_refuses_when_live_db_exists(live_world, capsys):
    """live_world has an existing DB at the data dir; restore must refuse."""
    rc = admin.main(["archive", "w-bunny"])
    assert rc == 0
    archive = next((live_world / "archives").iterdir())
    rc = admin.main(["restore", str(archive), "--yes"])
    assert rc == 2
    assert "live DB exists" in capsys.readouterr().err


def test_restore_rejects_unknown_archive(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    rc = admin.main(["restore", str(tmp_path / "no-such.tar.gz"), "--yes"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_restore_rejects_path_traversal_member(live_world, tmp_path, monkeypatch, capsys):
    """Regression for CVE-2007-4559: an archive containing a member whose
    name escapes the data dir (e.g. '../../../tmp/x') must be rejected
    before any payload bytes are written outside data_dir."""
    import io

    rc = admin.main(["archive", "w-bunny"])
    assert rc == 0
    archive = next((live_world / "archives").iterdir())

    # Build a tampered copy with an extra ../escape member alongside the
    # legitimate manifest.
    fresh = tmp_path / "tampered"
    fresh.mkdir()
    tampered = fresh / "evil.tar.gz"
    with tarfile.open(archive, "r:gz") as src, tarfile.open(tampered, "w:gz") as dst:
        for m in src.getmembers():
            f = src.extractfile(m)
            dst.addfile(m, f)
        evil_payload = b"escaped"
        info = tarfile.TarInfo("../../../tmp/daydream-restore-escape-test.txt")
        info.size = len(evil_payload)
        dst.addfile(info, io.BytesIO(evil_payload))

    db.close_db()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(elsewhere))
    rc = admin.main(["restore", str(tampered), "--yes"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unsafe" in err
    # And the payload was NOT written to /tmp.
    assert not Path("/tmp/daydream-restore-escape-test.txt").exists()


def test_restore_rejects_archive_with_newer_schema(live_world, tmp_path, monkeypatch, capsys):
    """If the archive's manifest claims a schema_version higher than what
    this code's migrations know, refuse."""
    rc = admin.main(["archive", "w-bunny"])
    assert rc == 0
    archive = next((live_world / "archives").iterdir())

    # Rewrite the manifest to claim a future schema version.
    fresh = tmp_path / "tampered"
    fresh.mkdir()
    tampered = fresh / "tampered.tar.gz"
    with tarfile.open(archive, "r:gz") as src, tarfile.open(tampered, "w:gz") as dst:
        for m in src.getmembers():
            if m.name == "MANIFEST.json":
                mf = json.loads(src.extractfile(m).read())
                mf["schema_version"] = 9999
                payload = json.dumps(mf).encode()
                import io
                info = tarfile.TarInfo("MANIFEST.json")
                info.size = len(payload)
                dst.addfile(info, io.BytesIO(payload))
            else:
                f = src.extractfile(m)
                dst.addfile(m, f)

    # Wipe and try to restore the tampered archive.
    db.close_db()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(elsewhere))
    rc = admin.main(["restore", str(tampered), "--yes"])
    assert rc == 2
    assert "newer than" in capsys.readouterr().err


# ---- snapshot -----------------------------------------------------------


def _snapshot_db_value(snap: Path, sql: str):
    """Open a snapshot .db read-only + immutable (so the probe creates no
    -wal/-shm sidecars) and return the first column of the first row."""
    probe = sqlite3.connect(f"file:{snap}?mode=ro&immutable=1", uri=True)
    try:
        return probe.execute(sql).fetchone()[0]
    finally:
        probe.close()


def test_snapshot_creates_db_only_file(live_world, capsys):
    """snapshot writes a single .db file under snapshots/ — no tarball, no
    manifest — that opens as a valid SQLite DB with the world's rows."""
    rc = admin.main(["snapshot", "w-bunny"])
    assert rc == 0
    snaps = list((live_world / "snapshots").iterdir())
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap.name.startswith("w-bunny-")
    assert snap.name.endswith(".db")
    assert "snapshot w-bunny ->" in capsys.readouterr().out
    # No tarball anywhere in the snapshots dir, and the file is real SQLite.
    assert not any(s.name.endswith(".tar.gz") for s in snaps)
    assert _snapshot_db_value(snap, "SELECT COUNT(*) FROM worlds WHERE id = 'w-bunny'") == 1


def test_snapshot_checkpoints_wal_before_copy(live_world):
    """A row committed to live just before the snapshot must appear in the
    independently-opened snapshot file, proving snapshot ran
    wal_checkpoint(TRUNCATE) before copying live.db (the row would otherwise
    sit only in live.db-wal and be missed by a bare-.db copy)."""
    db.get_conn().execute(
        "INSERT INTO worlds (id, name, slug, aesthetic_seed) VALUES "
        "('w-wal', 'wal', 'wal', 'x')"
    )
    rc = admin.main(["snapshot", "w-bunny"])
    assert rc == 0
    snap = next((live_world / "snapshots").iterdir())
    assert _snapshot_db_value(snap, "SELECT COUNT(*) FROM worlds WHERE id = 'w-wal'") == 1


def test_snapshot_refuses_unknown_world(live_world, capsys):
    rc = admin.main(["snapshot", "w-nope"])
    assert rc == 2
    assert "no world with id" in capsys.readouterr().err
    assert not (live_world / "snapshots").exists()


def test_snapshot_refuses_without_live_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    rc = admin.main(["snapshot", "w-bunny"])
    assert rc == 2
    assert "no live DB" in capsys.readouterr().err


def test_snapshot_refuses_on_collision(live_world, monkeypatch, capsys):
    """If the computed output path already exists, snapshot refuses rather
    than silently overwriting. Freeze the per-second timestamp so the second
    call collides deterministically."""
    import datetime as _dt

    class _FixedDatetime:
        @staticmethod
        def now():
            return _dt.datetime(2026, 5, 27, 12, 0, 0)

    monkeypatch.setattr(admin, "datetime", _FixedDatetime)
    assert admin.main(["snapshot", "w-bunny"]) == 0
    rc = admin.main(["snapshot", "w-bunny"])
    assert rc == 2
    assert "already exists" in capsys.readouterr().err
    # Only the first snapshot landed; the collision wrote nothing.
    assert len(list((live_world / "snapshots").iterdir())) == 1


def test_snapshot_restore_round_trip(live_world, tmp_path, monkeypatch):
    """The spec oracle: seed, snapshot, mutate, restore, assert restored ==
    snapshot-time state and != mutated state. The mutation is the control
    that proves restore reinstated the snapshot rather than live."""
    # F0: snapshot-time state — the seeded world has exactly one asset.
    assert len(assets.list_assets()) == 1

    assert admin.main(["snapshot", "w-bunny"]) == 0
    snap = next((live_world / "snapshots").iterdir())

    # Mutate live so it diverges from the snapshot (F1 != F0).
    db.get_conn().execute("DELETE FROM generated_assets WHERE world_id = 'w-bunny'")
    assert len(assets.list_assets()) == 0

    # The snapshot file, opened independently, still holds F0 (one asset).
    assert _snapshot_db_value(snap, "SELECT COUNT(*) FROM generated_assets") == 1

    # Restore into a fresh, empty data dir (no live DB to overwrite).
    db.close_db()
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(fresh))
    assert admin.main(["snapshot-restore", str(snap), "--yes"]) == 0
    assert config.live_db_path().exists()

    # Restored == F0 (one asset, r-meadow), != F1 (zero assets).
    db.init_live()
    restored = assets.list_assets()
    assert len(restored) == 1
    assert restored[0].target_id == "r-meadow"
    db.close_db()


def test_snapshot_restore_refuses_without_yes(live_world, tmp_path, monkeypatch, capsys):
    assert admin.main(["snapshot", "w-bunny"]) == 0
    snap = next((live_world / "snapshots").iterdir())
    db.close_db()
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(fresh))
    rc = admin.main(["snapshot-restore", str(snap)])
    assert rc == 2
    assert "refusing to restore" in capsys.readouterr().err
    assert not config.live_db_path().exists()


def test_snapshot_restore_refuses_when_live_db_exists(live_world, capsys):
    """live_world has an existing live DB; snapshot-restore must refuse to
    overwrite it (the data-loss guard)."""
    assert admin.main(["snapshot", "w-bunny"]) == 0
    snap = next((live_world / "snapshots").iterdir())
    rc = admin.main(["snapshot-restore", str(snap), "--yes"])
    assert rc == 2
    assert "live DB exists" in capsys.readouterr().err


def test_snapshot_restore_rejects_missing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    rc = admin.main(["snapshot-restore", str(tmp_path / "no-such.db"), "--yes"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_snapshot_restore_rejects_non_db_file(tmp_path, monkeypatch, capsys):
    """A file that is not a SQLite DB is refused before any copy to live."""
    db.close_db()
    junk = tmp_path / "junk.db"
    junk.write_text("this is plainly not a database")
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(fresh))
    rc = admin.main(["snapshot-restore", str(junk), "--yes"])
    assert rc == 2
    assert "not a readable daydream DB" in capsys.readouterr().err
    assert not config.live_db_path().exists()


def test_snapshot_restore_rejects_newer_schema(live_world, tmp_path, monkeypatch, capsys):
    """A snapshot whose _migrations claims a higher number than this code
    knows is refused (parity with archive restore)."""
    assert admin.main(["snapshot", "w-bunny"]) == 0
    snap = next((live_world / "snapshots").iterdir())

    # Tamper: bump the snapshot's applied-migration max to a future number,
    # then checkpoint so the row lands in the main file (an immutable-mode
    # reader ignores any -wal sidecar).
    tamper = sqlite3.connect(str(snap), isolation_level=None)
    try:
        tamper.execute("INSERT INTO _migrations(filename) VALUES ('9999_future.sql')")
        tamper.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        tamper.close()

    db.close_db()
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(fresh))
    rc = admin.main(["snapshot-restore", str(snap), "--yes"])
    assert rc == 2
    assert "newer than" in capsys.readouterr().err
    assert not config.live_db_path().exists()


# ---- verify -------------------------------------------------------------


def test_verify_clean_world(live_world, capsys):
    """live_world has one row + one matching file; both sides clean."""
    rc = admin.main(["verify"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "orphan rows: 0" in out
    assert "orphan files: 0" in out
    assert "0 orphan rows, 0 orphan files" in out


def test_verify_detects_orphan_file(live_world, capsys):
    """A PNG on disk with no DB row is reported as orphan-file."""
    extra = (
        live_world / "images" / "cache" / "w-bunny" / "room"
        / "r-meadow" / "ffffffffffffffff.png"
    )
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"\x89PNG\r\n\x1a\norphan")
    rc = admin.main(["verify"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "orphan files (1)" in out
    assert "ffffffffffffffff.png" in out


def test_verify_detects_orphan_row(live_world, capsys):
    """A DB row pointing at a missing file is reported as orphan-row."""
    # Add a row whose file_relpath does not exist.
    assets.record_image_generation(
        world_id="w-bunny",
        target_kind="room",
        target_id="r-ghost",
        target_seed="never generated",
        seed_hash="deadbeefdeadbeef",
        file_relpath="images/cache/w-bunny/room/r-ghost/missing.png",
        model="m", lora="l", prompt_text="p",
        file_bytes=999,
        workflow_hash="wh",
    )
    rc = admin.main(["verify"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "orphan rows (1)" in out
    assert "missing.png" in out


def test_verify_filtered_by_world(live_world, capsys):
    rc = admin.main(["verify", "w-bunny"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "world: w-bunny" in out


def test_verify_unknown_world_errors(live_world, capsys):
    rc = admin.main(["verify", "w-nope"])
    assert rc == 2
    assert "no world with id" in capsys.readouterr().err


# ---- delete -------------------------------------------------------------


def test_delete_without_yes_refuses(live_world, capsys):
    rc = admin.main(["delete", "w-bunny"])
    assert rc == 2
    assert "refusing to delete" in capsys.readouterr().err
    assert db.get_conn().execute(
        "SELECT COUNT(*) FROM worlds WHERE id = 'w-bunny'"
    ).fetchone()[0] == 1


def test_delete_with_yes_clears_db_and_cache(live_world):
    rc = admin.main(["delete", "w-bunny", "--yes"])
    assert rc == 0
    conn = db.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM worlds WHERE id = 'w-bunny'").fetchone()[0] == 0
    # rooms / toons / things / prototypes all live in `objects` now; the
    # cascade clears the whole world.
    assert conn.execute(
        "SELECT COUNT(*) FROM objects WHERE world_id = 'w-bunny'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM generated_assets WHERE world_id = 'w-bunny'"
    ).fetchone()[0] == 0
    assert not (live_world / "images" / "cache" / "w-bunny").exists()


def test_delete_unknown_world_returns_error(live_world, capsys):
    rc = admin.main(["delete", "w-does-not-exist", "--yes"])
    assert rc == 2
    assert "no world with id" in capsys.readouterr().err


def test_delete_only_clears_target_world(live_world):
    """With world_id now in generated_assets, delete must filter — a
    second world's assets in the same DB stay intact."""
    conn = db.get_conn()
    # Create a second world and a recorded asset for it.
    conn.execute(
        "INSERT INTO worlds (id, name, slug, aesthetic_seed) VALUES "
        "('w-other', 'other', 'other', 'unrelated')"
    )
    assets.record_image_generation(
        world_id="w-other",
        target_kind="room", target_id="r-other", target_seed="x",
        seed_hash="00000000abcdef00",
        file_relpath="images/cache/w-other/room/r-other/00.png",
        model=None, lora=None, prompt_text=None, file_bytes=10,
        workflow_hash="wh",
    )
    rc = admin.main(["delete", "w-bunny", "--yes"])
    assert rc == 0
    # Other world's assets survived the bunny delete.
    surviving = assets.list_assets(world_id="w-other")
    assert len(surviving) == 1


def test_delete_cascades_memories(live_world):
    """Migration 009 added a `memories` table with FK on world_id.
    The cascade must DELETE memory rows before the worlds row, otherwise
    `PRAGMA foreign_keys = ON` raises IntegrityError. Regression for
    CODEREVIEW BLOCK on admin.py:421-432."""
    conn = db.get_conn()
    # Insert a minimal memory row directly (bypass embedder) tied to
    # the seeded world.
    conn.execute(
        "INSERT INTO memories(world_id, npc_id, text, embedding) "
        "VALUES (?, ?, ?, ?)",
        ("w-bunny", "t-rook", "the visitor said: hello", b"\x00" * 4),
    )
    assert conn.execute(
        "SELECT COUNT(*) FROM memories WHERE world_id = 'w-bunny'"
    ).fetchone()[0] == 1
    rc = admin.main(["delete", "w-bunny", "--yes"])
    assert rc == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM worlds WHERE id = 'w-bunny'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM memories WHERE world_id = 'w-bunny'"
    ).fetchone()[0] == 0


# ---- guard: no live DB ---------------------------------------------------


def test_list_refuses_without_live_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    rc = admin.main(["list"])
    assert rc == 2
    assert "no live DB" in capsys.readouterr().err


def test_delete_refuses_without_live_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    rc = admin.main(["delete", "w-bunny", "--yes"])
    assert rc == 2
    assert "no live DB" in capsys.readouterr().err
    assert not (tmp_path / f"worlds-{config.env()}" / "live.db").exists()


def test_verify_refuses_without_live_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    rc = admin.main(["verify"])
    assert rc == 2
    assert "no live DB" in capsys.readouterr().err
