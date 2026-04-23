"""Generated-asset provenance: read/write the generated_assets table.

Mirrors the per-entity module pattern (rooms.py, toons.py, items.py) so the
top-level package stays flat. The schema is defined in migrations 002
(initial table) and 003 (world_id, pinned, workflow_hash); see those
files' headers for the column rationale.

What lives here:
- record_image_generation(): called by daydream.images.client right after a
  PNG is written to the cache, on the persistent path only. Idempotent on
  (target_kind, target_id, seed_hash) so a re-run doesn't multiply rows.
- list_assets() / assets_for_world() / total_bytes(): observability helpers
  for `bin/game world list`, `bin/game world verify`, future admin UI.
- pin_asset() / unpin_asset(): mark/unmark an asset as "do not GC". Used by
  zero code today; ready for the first gardening pass.

What does NOT live here:
- Cache file deletion. `bin/game world delete` does that at the shell level.
- The cache-hit fast path. Recording happens on miss only.
- The ephemeral path. Ephemeral image-gen never records by design.
"""

import sqlite3
from dataclasses import dataclass

from daydream import db


@dataclass(frozen=True)
class Asset:
    id: int
    asset_kind: str
    target_kind: str
    target_id: str
    target_seed: str
    seed_hash: str
    file_relpath: str
    model: str | None
    lora: str | None
    prompt_text: str | None
    generated_at: str
    file_bytes: int | None
    world_id: str | None
    pinned: bool
    workflow_hash: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Asset":
        return cls(
            id=row["id"],
            asset_kind=row["asset_kind"],
            target_kind=row["target_kind"],
            target_id=row["target_id"],
            target_seed=row["target_seed"],
            seed_hash=row["seed_hash"],
            file_relpath=row["file_relpath"],
            model=row["model"],
            lora=row["lora"],
            prompt_text=row["prompt_text"],
            generated_at=row["generated_at"],
            file_bytes=row["file_bytes"],
            world_id=row["world_id"],
            pinned=bool(row["pinned"]),
            workflow_hash=row["workflow_hash"],
        )


def record_image_generation(
    *,
    world_id: str,
    target_kind: str,
    target_id: str,
    target_seed: str,
    seed_hash: str,
    file_relpath: str,
    model: str | None,
    lora: str | None,
    prompt_text: str | None,
    file_bytes: int | None,
    workflow_hash: str,
    pinned: bool = False,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Idempotent on (target_kind, target_id, seed_hash). A repeat call with
    the same triple replaces the row's metadata.

    This is the persistent path's recorder; the ephemeral path never calls
    it. If `conn` is not passed and `db.get_conn()` raises, the exception
    propagates — recording on the persistent path is REQUIRED, not best-
    effort. Production WS path always has DB initialized."""
    c = conn or db.get_conn()
    c.execute(
        "INSERT INTO generated_assets ("
        "  asset_kind, target_kind, target_id, target_seed, seed_hash,"
        "  file_relpath, model, lora, prompt_text, file_bytes,"
        "  world_id, pinned, workflow_hash"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(target_kind, target_id, seed_hash) DO UPDATE SET"
        "   asset_kind    = excluded.asset_kind,"
        "   target_seed   = excluded.target_seed,"
        "   file_relpath  = excluded.file_relpath,"
        "   model         = excluded.model,"
        "   lora          = excluded.lora,"
        "   prompt_text   = excluded.prompt_text,"
        "   file_bytes    = excluded.file_bytes,"
        "   world_id      = excluded.world_id,"
        "   workflow_hash = excluded.workflow_hash,"
        "   generated_at  = CURRENT_TIMESTAMP",
        (
            "image",
            target_kind,
            target_id,
            target_seed,
            seed_hash,
            file_relpath,
            model,
            lora,
            prompt_text,
            file_bytes,
            world_id,
            int(pinned),
            workflow_hash,
        ),
    )


def list_assets(
    *,
    target_kind: str | None = None,
    world_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[Asset]:
    """Return assets, optionally filtered by target_kind and/or world_id.
    Ordered by generated_at ascending so the result reads chronologically."""
    c = conn or db.get_conn()
    where: list[str] = []
    params: list = []
    if target_kind is not None:
        where.append("target_kind = ?")
        params.append(target_kind)
    if world_id is not None:
        where.append("world_id = ?")
        params.append(world_id)
    sql = "SELECT * FROM generated_assets"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY generated_at ASC, id ASC"
    rows = c.execute(sql, params).fetchall()
    return [Asset.from_row(r) for r in rows]


def assets_for_world(
    world_id: str, conn: sqlite3.Connection | None = None
) -> list[Asset]:
    """Convenience wrapper around list_assets() for the most common query."""
    return list_assets(world_id=world_id, conn=conn)


def total_bytes(
    *,
    world_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Sum of recorded file_bytes, optionally filtered by world. NULL bytes
    count as 0 (the row exists but its size wasn't captured)."""
    c = conn or db.get_conn()
    if world_id is None:
        row = c.execute(
            "SELECT COALESCE(SUM(file_bytes), 0) AS total FROM generated_assets"
        ).fetchone()
    else:
        row = c.execute(
            "SELECT COALESCE(SUM(file_bytes), 0) AS total FROM generated_assets"
            " WHERE world_id = ?",
            (world_id,),
        ).fetchone()
    return int(row["total"])


def pin_asset(asset_id: int, conn: sqlite3.Connection | None = None) -> None:
    """Mark an asset as pinned (excluded from future GC). Idempotent."""
    c = conn or db.get_conn()
    c.execute("UPDATE generated_assets SET pinned = 1 WHERE id = ?", (asset_id,))


def unpin_asset(asset_id: int, conn: sqlite3.Connection | None = None) -> None:
    """Unpin a previously-pinned asset. Idempotent."""
    c = conn or db.get_conn()
    c.execute("UPDATE generated_assets SET pinned = 0 WHERE id = ?", (asset_id,))
