"""The art keep (docs/DATA-LIFECYCLE.md): every painting daydream makes, with
what it was for, outliving the worlds and caches that use it.

The image cache (images/cache/<world>/<kind>/<id>/<key>.png) is a working
copy keyed by seed and workflow, and world verbs rebuild or wipe it. The keep
is the durable record, one per data dir (dev's and prod's are separate):

    keep/art/<sha256[:2]>/<sha256>.png   the bytes, content-addressed, stored once
    keep/provenance.jsonl                one line per event, append-only

The bytes are hard-linked from the cache when they can be (no extra disk).
That is safe because nothing writes a cache file in place: a repaint writes a
temp file and renames it over the old name, so the keep's link still holds
the old bytes (images/client.py `_atomic_write_with_prev`), and a restore
replaces files rather than writing into them. Each kept file is read-only,
so anything that tried to write through a link would fail loudly.

A provenance line says what an image is FOR, in words as well as ids: the
world, the target (a room or a resident) and its name, the prompt and the
text it came from, the model, LoRA and workflow, the cache key, when, in
which env and build, and what happened:

    rendered    painted for this target
    repainted   painted again over an earlier painting (the admin repaint)
    adopted     copied from another env's graded cache (prod from dev)
    restored    put back into a new world's cache from the keep (a reset)
    backfilled  kept from a world's records after the fact (keep-sync)
    found       a cache file with no record (keep-sync; provenance is thin)

Nothing in daydream deletes from the keep. Pruning is a deliberate, recorded
operator act that does not exist yet (docs/DATA-LIFECYCLE.md "Pruning")."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from daydream import config

logger = logging.getLogger(__name__)

EVENTS = ("rendered", "repainted", "adopted", "restored", "backfilled", "found")


def keep_dir() -> Path:
    return config.data_dir() / "keep"


def provenance_path() -> Path:
    return keep_dir() / "provenance.jsonl"


def art_path(sha256: str) -> Path:
    return keep_dir() / "art" / sha256[:2] / f"{sha256}.png"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _store(path: Path, sha256: str) -> Path:
    dest = art_path(sha256)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f".{dest.name}.tmp")
        try:
            os.link(path, tmp)
        except OSError:  # another filesystem, or links not allowed: copy
            shutil.copyfile(path, tmp)
        os.replace(tmp, dest)
    try:
        # Read-only, as defense in depth: a cache file may share this inode,
        # so a write into it in place fails loudly (renames still work).
        os.chmod(dest, 0o444)
    except OSError:  # (another user's file): the store itself still holds
        pass
    return dest


def records() -> list[dict]:
    """Every provenance line, oldest first; a torn or foreign line is skipped."""
    p = provenance_path()
    if not p.exists():
        return []
    out = []
    with open(p, "rb") as f:  # bytes: a line torn mid-character must not stop the read
        for line in f:
            try:
                rec = json.loads(line.decode("utf-8"))
            except ValueError:  # (UnicodeDecodeError included)
                continue
            if isinstance(rec, dict) and rec.get("sha256"):
                out.append(rec)
    return out


def _kept(sha256: str, rec: dict, existing: list[dict]) -> bool:
    key = (sha256, rec.get("world_id"), rec.get("target_kind"), rec.get("target_id"))
    return any((r.get("sha256"), r.get("world_id"), r.get("target_kind"),
                r.get("target_id")) == key for r in existing)


def put(path: Path, record: dict, *, once: bool = False,
        existing: list[dict] | None = None) -> str:
    """Keep the image at `path` with its provenance `record` (which carries an
    `event` from EVENTS). Returns the image's sha256. With `once`, a line is
    written only if this image is not already kept for this target (a
    backfill run twice adds nothing)."""
    if record.get("event") not in EVENTS:
        raise ValueError(f"unknown keep event {record.get('event')!r}")
    sha256 = file_sha256(path)
    _store(path, sha256)
    if once and _kept(sha256, record, records() if existing is None else existing):
        return sha256
    from daydream import version

    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "env": config.env(), "build": version.build_sha(), **record,
            "sha256": sha256, "bytes": path.stat().st_size}
    provenance_path().parent.mkdir(parents=True, exist_ok=True)
    with open(provenance_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    if existing is not None:
        existing.append(line)
    return sha256


def find(cache_key: str) -> tuple[Path, dict] | None:
    """The kept image for a cache key (seed text + workflow), newest first."""
    for rec in reversed(records()):
        if rec.get("cache_key") == cache_key:
            art = art_path(rec["sha256"])
            if art.is_file():
                return art, rec
    return None


def target_name(target_id: str) -> str | None:
    """A room's title or a resident's name, from the live world (None if the
    world is not open or the target is gone)."""
    try:
        from daydream import objects

        o = objects.get(target_id)
    except Exception:
        return None
    if o is None:
        return None
    return (o.properties or {}).get("title") or o.name


def provenance(*, world_id: str, target_kind: str, target_id: str, source_text: str | None,
               prompt: str | None, model: str | None, lora: str | None,
               workflow_hash: str | None, cache_key: str | None, file: str | None,
               event: str, **extra) -> dict:
    return {"event": event, "world_id": world_id, "target_kind": target_kind,
            "target_id": target_id, "target_name": target_name(target_id),
            "source_text": source_text, "prompt": prompt, "model": model, "lora": lora,
            "workflow_hash": workflow_hash, "cache_key": cache_key, "file": file, **extra}


def sync(world_id: str | None = None, *, with_db: bool = True) -> dict:
    """Keep every image the live world knows of (backfill): each
    generated_assets row whose file exists, with the row's provenance, and
    each cache file with no row ("found"). Idempotent. Raises if the keep
    cannot be written: callers that wipe art must not wipe after a failure.
    `with_db=False` (a live DB that cannot be opened) keeps every cache file
    as "found"."""
    from daydream import db
    from daydream.images import cache

    counts = {"kept": 0, "already": 0, "found": 0, "missing_file": 0}
    existing = records()
    sql = "SELECT * FROM generated_assets"
    params: tuple = ()
    if world_id is not None:
        sql += " WHERE world_id = ?"
        params = (world_id,)
    known: set[Path] = set()
    for row in db.get_conn().execute(sql, params).fetchall() if with_db else []:
        f = config.data_dir() / row["file_relpath"]
        known.add(f.resolve())
        if not f.is_file():
            counts["missing_file"] += 1
            continue
        rec = provenance(
            world_id=row["world_id"], target_kind=row["target_kind"], target_id=row["target_id"],
            source_text=row["target_seed"], prompt=row["prompt_text"], model=row["model"],
            lora=row["lora"], workflow_hash=row["workflow_hash"], cache_key=f.stem,
            file=row["file_relpath"], event="backfilled", generated_at=row["generated_at"])
        before = len(existing)
        put(f, rec, once=True, existing=existing)
        counts["kept" if len(existing) > before else "already"] += 1
    root = cache.cache_dir()
    worlds = [root / world_id] if world_id is not None else (
        [d for d in root.iterdir() if d.is_dir()] if root.exists() else [])
    for wdir in worlds:
        for f in sorted(wdir.rglob("*.png")) if wdir.exists() else []:
            if f.resolve() in known or not f.is_file() or f.is_symlink():
                continue
            parts = f.relative_to(root).parts  # world/kind/id/key.png
            if len(parts) != 4:
                continue
            rec = provenance(world_id=parts[0], target_kind=parts[1], target_id=parts[2],
                             source_text=None, prompt=None, model=None, lora=None,
                             workflow_hash=None, cache_key=f.stem,
                             file=str(f.relative_to(config.data_dir())), event="found")
            before = len(existing)
            put(f, rec, once=True, existing=existing)
            counts["found" if len(existing) > before else "already"] += 1
    return counts
