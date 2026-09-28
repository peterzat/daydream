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
