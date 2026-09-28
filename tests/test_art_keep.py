"""The art keep (daydream/images/keep.py; docs/DATA-LIFECYCLE.md): every
painting outlives the worlds and caches that use it, with what it was for.

First prod reset, 2026-09-28: `world reset` wiped prod's image cache, and
with it the only copies of two player portraits and every provenance row
(the village's own art came back only because dev held graded copies). The
keep takes every render, keeps a world's art before any wipe, and gives a
new world its art back."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from daydream import admin, assets, config, db
from daydream.images import cache, keep
from daydream.images import client as image_client

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def live_world(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    db.init_live()
    yield
    db.close_db()


def _room_target(seed: str = "a meadow at dusk") -> image_client.PersistentTarget:
    world_id = db.get_conn().execute("SELECT id FROM worlds LIMIT 1").fetchone()["id"]
    room = db.get_conn().execute(
        "SELECT id FROM objects WHERE kind = 'room' AND world_id = ? LIMIT 1", (world_id,)
    ).fetchone()["id"]
    return image_client.PersistentTarget(world_id=world_id, target_kind="room",
                                         target_id=room, seed=seed,
                                         prompt_suffix=image_client.WHIMSY_PROMPT_SUFFIX)


async def _render(target, *byte_runs, force=False):
    with patch.object(image_client, "_execute_workflow",
                      new=AsyncMock(side_effect=list(byte_runs))):
        return await image_client.generate_image(target, force=force)


def test_put_stores_the_bytes_once_by_content_and_appends_provenance(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG one painting")
    rec = {"event": "rendered", "world_id": "w", "target_kind": "room", "target_id": "r-a"}
    sha = keep.put(f, dict(rec))
    art = keep.art_path(sha)
    assert art.read_bytes() == f.read_bytes()
    assert os.stat(art).st_ino == os.stat(f).st_ino  # a hard link: no extra disk
    keep.put(f, dict(rec), once=True)  # already kept for this target: no new line
    keep.put(f, dict(rec, target_id="r-b"), once=True)  # the same bytes for another target
    lines = [json.loads(x) for x in keep.provenance_path().read_text().splitlines()]
    assert [x["target_id"] for x in lines] == ["r-a", "r-b"]
    assert {"at", "env", "build", "sha256", "bytes"} <= set(lines[0])
    with pytest.raises(ValueError):
        keep.put(f, {"event": "invented"})


@pytest.mark.asyncio
async def test_a_render_is_kept_with_what_it_was_for_and_a_repaint_keeps_both():
    target = _room_target()
    out = await _render(target, b"\x89PNG first")
    first = keep.records()[-1]
    assert first["event"] == "rendered"
    assert first["target_id"] == target.target_id
    assert first["target_name"]  # the room's title, in words
    assert first["source_text"] == "a meadow at dusk" and "watercolor" in first["prompt"]
    assert first["cache_key"] == out.stem and first["model"] and first["workflow_hash"]

    await _render(target, b"\x89PNG second", force=True)
    second = keep.records()[-1]
    assert second["event"] == "repainted" and second["sha256"] != first["sha256"]
    assert keep.art_path(first["sha256"]).read_bytes() == b"\x89PNG first"  # not overwritten
    assert out.read_bytes() == b"\x89PNG second"


def test_sync_backfills_records_and_orphans_and_is_idempotent():
    target = _room_target()
    wf = image_client.load_workflow()
    path = cache.cache_path(target.world_id, "room", target.target_id, target.seed, wf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG from before the keep")
    image_client._record_persistent(target, "a prompt", wf, path)
    orphan = cache.cache_dir() / target.world_id / "toon" / "t-gone" / "abc123.png"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"\x89PNG a face with no record")

    counts = keep.sync()
    assert (counts["kept"], counts["found"]) == (1, 1)
    events = sorted(r["event"] for r in keep.records())
    assert events == ["backfilled", "found"]
    assert keep.sync()["already"] == 2
    assert len(keep.records()) == 2


@pytest.mark.asyncio
async def test_deleting_a_world_keeps_its_art_first(capsys):
    target = _room_target()
    out = await _render(target, b"\x89PNG a room that will be deleted")
    sha = keep.file_sha256(out)
    db.close_db()
    assert admin.cmd_delete(target.world_id, yes=True) == 0
    assert "its art is in the keep" in capsys.readouterr().out
    assert not out.exists()
    assert keep.art_path(sha).read_bytes() == b"\x89PNG a room that will be deleted"
    assert any(r["sha256"] == sha and r["world_id"] == target.world_id for r in keep.records())


@pytest.mark.asyncio
async def test_a_wiped_cache_gets_its_art_back_from_the_keep():
    from daydream import prebake

    target = _room_target()
    out = await _render(target, b"\x89PNG the graded painting")
    db.get_conn().execute("DELETE FROM generated_assets")
    out.unlink()
    wf = image_client.load_workflow()
    assert prebake._adopt_from_keep(target, wf, out) is True
    assert out.read_bytes() == b"\x89PNG the graded painting"
    assert [a.target_id for a in assets.list_assets()] == [target.target_id]
    assert keep.records()[-1]["event"] == "restored"


def test_a_backup_carries_the_keeps_provenance(tmp_path):
    f = tmp_path / "x.png"
    f.write_bytes(b"\x89PNG")
    keep.put(f, {"event": "rendered", "world_id": "w", "target_kind": "room", "target_id": "r"})
    assert admin.cmd_backup(keep=14) == 0
    (backup,) = (config.data_dir() / "backups").iterdir()
    assert (backup / "provenance.jsonl").read_text() == keep.provenance_path().read_text()


def test_world_reset_keeps_the_art_before_wiping_and_restores_it_after():
    script = (ROOT / "bin" / "game").read_text()
    body = script[script.index("cmd_world_reset() {"):]
    body = body[:body.index("\n}\n")]
    keep_at = body.index("daydream.admin keep-sync")
    wipe_at = body.index('rm -rf "${data_dir}/images/cache/"w-*')
    load_at = body.index("daydream.admin load")
    restore_at = body.index("daydream.prebake --from-keep")
    assert keep_at < wipe_at < load_at < restore_at
    assert "nothing was reset" in body[keep_at:wipe_at]  # a failed keep wipes nothing


@pytest.mark.asyncio
async def test_a_restore_over_a_kept_painting_leaves_the_keep_intact():
    """Codereview WARN 2026-09-28e: `world restore` wrote an older painting
    into a cache file in place, and so, through the hard link, into the kept
    newer one (the file named for one sha then held the other's bytes)."""
    target = _room_target()
    out = await _render(target, b"\x89PNG the older painting")
    assert admin.cmd_archive(target.world_id) == 0
    (archive,) = (config.data_dir() / "archives").iterdir()
    await _render(target, b"\x89PNG the newer painting", force=True)
    newer = keep.file_sha256(out)
    assert os.stat(out).st_ino == os.stat(keep.art_path(newer)).st_ino
    db.close_db()
    for p in config.worlds_dir().glob("live.db*"):
        p.unlink()
    assert admin.cmd_restore(archive, yes=True) == 0
    assert out.read_bytes() == b"\x89PNG the older painting"
    assert keep.art_path(newer).read_bytes() == b"\x89PNG the newer painting"
    assert keep.file_sha256(keep.art_path(newer)) == newer


@pytest.mark.asyncio
async def test_kept_paintings_are_read_only_and_repaints_still_keep_a_revert_copy():
    target = _room_target()
    out = await _render(target, b"\x89PNG one")
    art = keep.art_path(keep.file_sha256(out))
    assert art.stat().st_mode & 0o777 == 0o444
    with pytest.raises(PermissionError):  # an in-place write fails loudly
        out.open("r+b")
    await _render(target, b"\x89PNG two", force=True)
    await _render(target, b"\x89PNG three", force=True)  # the .prev is replaced, not written into
    assert out.with_name(out.name + ".prev").read_bytes() == b"\x89PNG two"
    assert out.read_bytes() == b"\x89PNG three" and art.read_bytes() == b"\x89PNG one"


@pytest.mark.asyncio
async def test_a_cache_miss_takes_the_kept_painting_instead_of_the_gpu():
    """Codereview WARN 2026-09-28e: after a restore, a face the reset's
    from-keep pass did not cover was painted again on the GPU although the
    keep held it."""
    target = _room_target()
    out = await _render(target, b"\x89PNG the graded painting")
    db.get_conn().execute("DELETE FROM generated_assets")
    out.unlink()
    with patch.object(image_client, "_execute_workflow",
                      new=AsyncMock(side_effect=AssertionError("rendered on the GPU"))):
        again = await image_client.generate_image(target)
    assert again == out and out.read_bytes() == b"\x89PNG the graded painting"
    assert [a.target_id for a in assets.list_assets()] == [target.target_id]
    assert keep.records()[-1]["event"] == "restored"


@pytest.mark.asyncio
async def test_a_restored_experimental_repaint_keeps_its_own_provenance():
    """Codereview WARN 2026-09-28e: the restore recorded the canonical prompt
    for a painting made from an experimental one."""
    from daydream import prebake

    target = _room_target()
    with patch.object(image_client, "_execute_workflow",
                      new=AsyncMock(return_value=b"\x89PNG a sketch")):
        out = await image_client.generate_image(target, force=True,
                                                prompt_override="a charcoal sketch of a meadow")
    painted = keep.records()[-1]
    assert painted["prompt"] == "(experimental prompt, not retained)"
    db.get_conn().execute("DELETE FROM generated_assets")
    out.unlink()
    assert prebake._adopt_from_keep(target, image_client.load_workflow(), out) is True
    restored = keep.records()[-1]
    assert restored["event"] == "restored" and restored["prompt"] == painted["prompt"]
    assert restored["restored_from"] == painted["sha256"]
    (row,) = assets.list_assets()
    assert row.prompt_text == painted["prompt"]


def test_from_keep_mode_includes_a_player_still_in_a_session():
    """Codereview WARN 2026-09-28e: a player who closed a tab without resting
    is still human-controlled, and the reset's from-keep pass skipped them."""
    from daydream import prebake, toons

    t = toons.create_toon_in_slot(2, "Robin", "a small wren with a red scarf", "s-robin")
    world_id = t.world_id
    assert t.id not in [tid for _, tid, _, _ in prebake._targets(world_id, "toons")]
    assert t.id in [tid for _, tid, _, _ in prebake._targets(world_id, "toons", every_toon=True)]


def test_a_line_torn_mid_character_is_skipped_not_fatal():
    """Codereview WARN 2026-09-28e: a full disk mid-append can tear a
    multi-byte character; the read raised, so keep-sync failed and `world
    reset` refused."""
    p = keep.provenance_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    good = json.dumps({"sha256": "a" * 64, "target_name": "Café"}, ensure_ascii=False)
    p.write_bytes(good.encode() + b"\n" + b'{"sha256": "b", "target_name": "Caf'
                  + "é".encode()[:1] + b"\n" + good.encode() + b"\n")
    assert [r["target_name"] for r in keep.records()] == ["Café", "Café"]
    assert keep.sync()["found"] == 0  # and keep-sync carries on


def test_keep_sync_keeps_the_art_of_a_world_whose_db_is_broken(capsys):
    """Codereview WARN 2026-09-28e: a corrupt live DB failed keep-sync, so
    `world reset` (the escape hatch) refused with "the art keep could not be
    written". The files are kept as found, and the DB error said plainly."""
    target = _room_target()
    wf = image_client.load_workflow()
    path = cache.cache_path(target.world_id, "room", target.target_id, target.seed, wf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG a painting of a broken world")
    db.close_db()
    for p in config.worlds_dir().glob("live.db*"):
        p.unlink()
    config.live_db_path().write_bytes(b"this is not a database" * 100)
    assert admin.cmd_keep_sync() == 0
    assert "the live DB could not be opened" in capsys.readouterr().err
    (rec,) = keep.records()
    assert rec["event"] == "found" and rec["target_id"] == target.target_id
    assert keep.art_path(rec["sha256"]).read_bytes() == b"\x89PNG a painting of a broken world"


@pytest.mark.asyncio
async def test_a_leftover_restore_temp_is_replaced_not_written_into():
    """A crash between the link and the rename leaves `.<key>.png.restore`
    behind, linked to some kept painting: the next restore replaces it."""
    target = _room_target()
    out = await _render(target, b"\x89PNG the graded painting")
    other = keep.art_path(keep.put(_scratch_png(b"\x89PNG another painting"),
                                   {"event": "rendered", "world_id": "w", "target_kind": "room",
                                    "target_id": "r-other"}))
    out.unlink()
    os.link(other, out.with_name(f".{out.name}.restore"))
    with patch.object(image_client, "_execute_workflow",
                      new=AsyncMock(side_effect=AssertionError("rendered on the GPU"))):
        await image_client.generate_image(target)
    assert out.read_bytes() == b"\x89PNG the graded painting"
    assert other.read_bytes() == b"\x89PNG another painting"


def _scratch_png(data: bytes) -> Path:
    p = config.data_dir() / "scratch" / f"{len(data)}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p
