"""In-process world hot-swap endpoint.

`POST /api/world/swap` installs a target world DB (a `snapshot` output or a
`world bootstrap` DB) as the live DB of the RUNNING server, without a restart,
then signals connected WS clients to re-snapshot against the new world. It is
the online counterpart to the offline `bin/game world snapshot-restore` (which
requires the server down and refuses to overwrite a live DB).

The swap MUST run in the server process: the live DB connection (`daydream.db`)
and the drift task (`daydream.drift`) live in this process's memory, so the
offline admin CLI cannot perform a live swap. `bin/game world swap` is a thin
HTTP client to this endpoint.

Auth: gated by `auth.is_authed` (the same friend-scope gate as the slot
endpoints). In the default tailscale access mode that is tailnet membership;
in public mode it is the shared-password session cookie. There is no separate
admin role in v0.
"""

import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from daydream import config, db, drift, events
from daydream.api import auth

logger = logging.getLogger(__name__)
router = APIRouter()


class WorldSwapError(Exception):
    """A swap was refused (validation) or failed. `status` is the HTTP code
    the endpoint returns; `message` is the operator-facing reason."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _validate_target(target: Path) -> Path:
    """Refuse unsafe targets WITHOUT touching live state. Returns the
    resolved path on success. Raises WorldSwapError on: a path outside the
    data dir, a missing file, a file that is not a readable daydream SQLite
    DB, or a schema newer than this code knows.

    The data-dir confinement keeps an authed client from pointing the swap
    at an arbitrary file on disk; the read-only + immutable probe mirrors
    `cmd_snapshot_restore` so it never creates `-wal`/`-shm` next to the
    candidate."""
    data_root = config.data_dir().resolve()
    resolved = target.resolve()
    if not (resolved == data_root or data_root in resolved.parents):
        raise WorldSwapError(
            f"target must live under the data dir ({data_root})", status=400
        )
    if not resolved.is_file():
        raise WorldSwapError(f"target not found: {resolved}", status=404)
    try:
        probe = sqlite3.connect(f"file:{resolved}?mode=ro&immutable=1", uri=True)
        try:
            probe.row_factory = sqlite3.Row
            src_schema = db.applied_migration_max(probe)
        finally:
            probe.close()
    except sqlite3.DatabaseError as e:
        raise WorldSwapError(
            f"{resolved} is not a readable daydream DB: {e}", status=400
        ) from e
    cur_schema = db.max_known_migration()
    if src_schema > cur_schema:
        raise WorldSwapError(
            f"target schema_version {src_schema} is newer than this code's "
            f"max known migration {cur_schema}; refusing to swap",
            status=409,
        )
    return resolved


async def perform_world_swap(target: Path) -> dict:
    """Validate, then atomically swap the live DB to `target` in-process and
    notify connected clients.

    On a validation failure: raises WorldSwapError and changes nothing. On a
    swap failure: `db.swap_live_db` has already restored the original world,
    drift is restarted against it, and a 500 WorldSwapError is raised without
    notifying clients. On success: drift is restarted against the new world
    and every connected WS subscriber is told to re-snapshot."""
    resolved = _validate_target(target)
    # Stop drift so its periodic write cannot straddle the swap. The
    # swap_live_db call itself is synchronous (atomic w.r.t. the event loop);
    # stopping drift closes the one async writer that could resume mid-swap.
    await drift.stop_drift_loop()
    try:
        db.swap_live_db(resolved)
    except Exception as e:
        logger.exception("world swap failed; original world restored")
        drift.start_drift_loop()  # restart against the original world
        raise WorldSwapError(
            "swap failed; the original world was restored", status=500
        ) from e
    drift.start_drift_loop()
    events.broadcast_world_changed()
    conn = db.get_conn()
    row = conn.execute("SELECT id FROM worlds ORDER BY id LIMIT 1").fetchone()
    return {
        "ok": True,
        "world_id": row["id"] if row else None,
        "subscribers_notified": events.subscriber_count(),
    }


@router.post("/api/world/swap")
async def swap_world(request: Request):
    if not auth.is_authed(request.session):
        return JSONResponse({"error": "not authenticated"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    target = body.get("target") if isinstance(body, dict) else None
    if not isinstance(target, str) or not target:
        return JSONResponse(
            {"error": "missing 'target' (path to a world DB)"}, status_code=400
        )
    try:
        result = await perform_world_swap(Path(target))
    except WorldSwapError as e:
        return JSONResponse({"error": e.message}, status_code=e.status)
    return JSONResponse(result)
