"""Build + world versioning: the deploy/staleness guardrails.

Two independent axes of "is this deployment current", each made visible and/or
enforced:

  build SHA      which commit the RUNNING server process started from. Captured
                 once at startup and surfaced via GET /status/build so
                 `bin/game status` can flag a server that is behind HEAD (the
                 "I thought we'd already redeployed" trap). Degrades to
                 "unknown" when git / .git is unavailable: the runtime never
                 hard-depends on git.

  WORLD_VERSION  a "MAJOR.MINOR" content/compat version stamped into each world
                 DB at `world load` time (the `worlds.world_version` column,
                 migration 012) and compared against this code's constant at
                 boot. A MAJOR mismatch means the live world cannot be carried
                 forward, so the server refuses to boot and names
                 `bin/game world reset`; a MINOR (or legacy NULL) mismatch only
                 warns. Bump MAJOR when a change makes existing worlds
                 unloadable (a non-additive migration, an objects-model change);
                 bump MINOR for authored content/behaviour changes an old world
                 won't reflect (a seed, an NPC prompt, worlds/bunny.json).
"""

import logging
import os
import sqlite3
import subprocess
from functools import lru_cache

from daydream import config

logger = logging.getLogger(__name__)

# Bump MAJOR when an existing world DB can no longer be loaded by this code;
# bump MINOR for authored content/behaviour changes an old world won't reflect.
# See the module docstring for the boot-gate semantics.
WORLD_VERSION = "1.1"


@lru_cache(maxsize=1)
def build_sha() -> str:
    """The git short SHA the running process started from, with a `-dirty`
    suffix when the working tree has uncommitted changes. Captured ONCE and
    cached for the process lifetime so it reflects the deployed commit, not a
    later checkout. `DAYDREAM_BUILD_SHA` overrides (containers / CI with no
    .git). Returns "unknown" when git is unavailable: the runtime must never
    hard-depend on git."""
    override = os.environ.get("DAYDREAM_BUILD_SHA")
    if override:
        return override.strip()
    try:
        rev = subprocess.run(
            ["git", "-C", str(config.PROJECT_ROOT), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if rev.returncode != 0:
            return "unknown"
        sha = rev.stdout.strip()
        if not sha:
            return "unknown"
        dirty = subprocess.run(
            ["git", "-C", str(config.PROJECT_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=2,
        )
        if dirty.returncode == 0 and dirty.stdout.strip():
            sha += "-dirty"
        return sha
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def parse_version(v: str | None) -> tuple[int, int]:
    """Parse a "MAJOR.MINOR" string into (major, minor). Unparseable / None ->
    (0, 0), a sentinel no real version MAJOR-matches, so a legacy or garbled
    stamp is treated as 'unknown' (warn, never block)."""
    if not v:
        return (0, 0)
    parts = str(v).split(".")
    try:
        major = int(parts[0])
    except (ValueError, IndexError):
        return (0, 0)
    try:
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        minor = 0
    return (major, minor)


def check_world_compat(conn: sqlite3.Connection) -> None:
    """Compare the live world DB's stamped `world_version` against this code's
    WORLD_VERSION and enforce the boot policy:

      MAJOR mismatch         raise SystemExit (refuse to boot) -- the world
                             cannot be carried forward; the operator must
                             `bin/game world reset` to rebuild from bunny.json.
      MINOR mismatch / NULL  log a WARNING -- the world still loads but may not
                             reflect current authored content.

    Fail OPEN on a missing worlds table or world_version column (a pre-012 or
    non-daydream DB): never block on the unknown. Call AFTER init_live (so
    migration 012 has added + back-filled the column)."""
    code_major, _ = parse_version(WORLD_VERSION)
    try:
        rows = conn.execute("SELECT id, world_version FROM worlds").fetchall()
    except sqlite3.Error:
        return  # no worlds table / no column: nothing to gate
    for row in rows:
        wid = row["id"]
        stamp = row["world_version"]
        if stamp is None:
            logger.warning(
                "world %s has no world_version (pre-1.0 / legacy); run "
                "'bin/game world reset' if its content looks stale",
                wid,
            )
            continue
        major, _ = parse_version(stamp)
        if major == 0:
            logger.warning("world %s has an unparseable world_version %r", wid, stamp)
            continue
        if major != code_major:
            msg = (
                f"live world {wid} is version {stamp}, but this server requires "
                f"major {code_major} (WORLD_VERSION={WORLD_VERSION}). The live "
                f"world is incompatible with this code -- run 'bin/game world "
                f"reset' to rebuild it from worlds/bunny.json."
            )
            logger.error(msg)
            raise SystemExit(msg)
        if stamp != WORLD_VERSION:
            logger.warning(
                "world %s is content version %s; this server is %s -- run "
                "'bin/game world reset' to see the latest content",
                wid, stamp, WORLD_VERSION,
            )
