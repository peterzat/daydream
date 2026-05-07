"""World admin CLI: list, archive, restore, verify, delete worlds and their
generated assets.

Invoked by `bin/game world {list,archive,restore,verify,delete}`. Five
operations on the same (DB, cache-dir) pair:

  list                   - inventory: worlds in the live DB + per-world
                           asset count + per-world cache-dir size on disk.
  archive <world_id>     - tar bundle: live DB (post-WAL-checkpoint) +
                           per-world cache + a MANIFEST.json describing
                           the archive contents and source schema_version.
                           Written to ~/data/daydream/archives/. Read-only.
  restore <archive> --yes
                         - extract a previous archive into the current
                           data_dir. Refuses if the live DB already
                           exists; refuses if the archive's schema_version
                           is newer than the highest known migration.
  verify [world_id]      - walk DB rows checking each file_relpath exists,
                           walk the cache dir checking each PNG has a row.
                           Reports orphans on each side. Diagnostic only,
                           never destructive; exit 0 even if orphans found.
  delete <world_id> --yes
                         - destructive: DELETE the world's rows AND
                           rm -rf its cache dir. --yes is required.

Implementation notes:
- "world" today maps 1:1 to a slug in the worlds table. The DB technically
  supports many worlds per file; commands accept the world id (e.g.
  'w-bunny') so they remain stable across slug renames.
- Archive tarballs are rooted at data_dir() so untarring on a peer machine
  with the same layout drops files into the right relative paths.
- The cascade in delete is hand-rolled because the 001 schema's FKs do
  not declare ON DELETE CASCADE. Order matters: child rows first."""

import argparse
import json
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from daydream import assets, config, db
from daydream.images import cache as image_cache

# Bump when the manifest format changes incompatibly. Restore validates
# this matches what it knows how to read.
ARCHIVE_FORMAT_VERSION = 1


def _archives_dir() -> Path:
    return config.data_dir() / "archives"


def _world_cache_dir(world_id: str) -> Path:
    return image_cache.cache_dir() / world_id


def _format_bytes(n: int) -> str:
    """Human-readable byte count. Cheap, no extra deps."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _dir_size_bytes(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _max_known_migration() -> int:
    """Highest numeric prefix in migrations/. The schema_version baked into
    new archives matches the highest applied migration; restore refuses
    archives produced by a NEWER system than this one."""
    nums = []
    for f in config.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"):
        try:
            nums.append(int(f.name[:3]))
        except ValueError:
            continue
    return max(nums) if nums else 0


def _applied_migration_max(conn: sqlite3.Connection) -> int:
    """Highest migration number actually applied to a given DB. Used by
    archive to stamp the manifest."""
    rows = conn.execute("SELECT filename FROM _migrations").fetchall()
    nums = []
    for r in rows:
        try:
            nums.append(int(r["filename"][:3]))
        except (ValueError, KeyError):
            continue
    return max(nums) if nums else 0


def _require_live_db() -> int | None:
    """Refuse if the live DB doesn't exist yet — none of the world commands
    should create or seed the DB as a side effect. Returns an exit code on
    failure, None on success."""
    p = config.live_db_path()
    if not p.exists():
        print(
            f"error: no live DB at {p}\n"
            "run 'bin/game up' first (the FastAPI startup creates and seeds it)",
            file=sys.stderr,
        )
        return 2
    return None


# ---- list ---------------------------------------------------------------


def cmd_list() -> int:
    rc = _require_live_db()
    if rc is not None:
        return rc
    db.init_live()
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, name, slug FROM worlds ORDER BY id"
    ).fetchall()
    if not rows:
        print("(no worlds in live DB)")
        return 0
    print(f"{'world id':<16}  {'slug':<20}  {'assets':>6}  {'recorded':>10}  {'on disk':>10}")
    print(f"{'-' * 16}  {'-' * 20}  {'-' * 6}  {'-' * 10}  {'-' * 10}")
    for r in rows:
        wid = r["id"]
        slug = r["slug"]
        n = conn.execute(
            "SELECT COUNT(*) FROM generated_assets WHERE world_id = ?", (wid,)
        ).fetchone()[0]
        recorded = assets.total_bytes(world_id=wid, conn=conn)
        on_disk = _dir_size_bytes(_world_cache_dir(wid))
        print(
            f"{wid:<16}  {slug:<20}  {n:>6}  "
            f"{_format_bytes(int(recorded)):>10}  {_format_bytes(on_disk):>10}"
        )
    return 0


# ---- archive ------------------------------------------------------------


def _build_manifest(world_id: str, conn: sqlite3.Connection) -> dict:
    schema_version = _applied_migration_max(conn)
    n_assets = conn.execute(
        "SELECT COUNT(*) FROM generated_assets WHERE world_id = ?", (world_id,)
    ).fetchone()[0]
    total = assets.total_bytes(world_id=world_id, conn=conn)
    return {
        "archive_format_version": ARCHIVE_FORMAT_VERSION,
        "schema_version": schema_version,
        "world_id": world_id,
        "asset_count": int(n_assets),
        "asset_bytes": int(total),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def cmd_archive(world_id: str) -> int:
    db_path = config.live_db_path()
    if not db_path.exists():
        print(f"error: live DB not found at {db_path}", file=sys.stderr)
        return 2

    # Checkpoint the WAL so the on-disk live.db reflects all committed
    # writes. Without this, a hot DB's most recent transactions live in
    # live.db-wal and would be missed by a tar of just live.db.
    db.init_live()
    conn = db.get_conn()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    manifest = _build_manifest(world_id, conn)

    cache_dir = _world_cache_dir(world_id)
    if not cache_dir.exists():
        print(
            f"warning: no cache dir for {world_id} at {cache_dir} "
            "(archive will include the DB only)",
            file=sys.stderr,
        )

    out_dir = _archives_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"{world_id}-{ts}.tar.gz"

    # Write the manifest to a temp file we can include in the tar with a
    # stable name. tar -C anchors the archive at data_dir so untar drops
    # files back to the same relative locations on the destination.
    data_dir = config.data_dir()
    members = [str(db_path.relative_to(data_dir))]
    if cache_dir.exists():
        members.append(str(cache_dir.relative_to(data_dir)))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as mf:
        json.dump(manifest, mf, indent=2)
        manifest_temp = Path(mf.name)
    try:
        # Build the tarball with the manifest included as MANIFEST.json at
        # the archive root (not under data_dir's tree). Use Python's
        # tarfile module so we control the in-archive name precisely.
        with tarfile.open(out, "w:gz") as t:
            t.add(manifest_temp, arcname="MANIFEST.json")
            for m in members:
                t.add(data_dir / m, arcname=m)
    finally:
        manifest_temp.unlink(missing_ok=True)

    size = out.stat().st_size
    print(
        f"archived {world_id} -> {out} "
        f"({_format_bytes(size)}, schema_version={manifest['schema_version']}, "
        f"{manifest['asset_count']} assets)"
    )
    return 0


# ---- restore ------------------------------------------------------------


def cmd_restore(archive_path: Path, yes: bool) -> int:
    if not yes:
        print(
            f"refusing to restore {archive_path}: pass --yes to confirm.\n"
            "this writes to the data dir; the live DB must not exist yet "
            "(restore refuses to overwrite).",
            file=sys.stderr,
        )
        return 2
    if not archive_path.exists():
        print(f"error: archive not found at {archive_path}", file=sys.stderr)
        return 2

    live = config.live_db_path()
    if live.exists():
        print(
            f"error: live DB exists at {live}\n"
            "restore refuses to overwrite. archive or delete it first if "
            "you want to replace it.",
            file=sys.stderr,
        )
        return 2

    # Validate the manifest before extracting any payload files.
    try:
        with tarfile.open(archive_path, "r:gz") as t:
            try:
                mf_member = t.getmember("MANIFEST.json")
            except KeyError:
                print(
                    f"error: {archive_path} has no MANIFEST.json — not a "
                    "daydream archive, or produced by an older format",
                    file=sys.stderr,
                )
                return 2
            mf_bytes = t.extractfile(mf_member).read()
    except tarfile.ReadError as e:
        print(f"error: cannot read {archive_path}: {e}", file=sys.stderr)
        return 2

    manifest = json.loads(mf_bytes)
    fmt = manifest.get("archive_format_version")
    if fmt != ARCHIVE_FORMAT_VERSION:
        print(
            f"error: archive format version {fmt} not supported "
            f"(this code knows {ARCHIVE_FORMAT_VERSION})",
            file=sys.stderr,
        )
        return 2
    src_schema = int(manifest.get("schema_version", 0))
    cur_schema = _max_known_migration()
    if src_schema > cur_schema:
        print(
            f"error: archive schema_version {src_schema} is newer than "
            f"this code's max known migration {cur_schema}; refuse to "
            "restore (the archive expects columns we don't know about)",
            file=sys.stderr,
        )
        return 2

    data_dir = config.data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as t:
        for m in t.getmembers():
            if m.name == "MANIFEST.json":
                continue
            # Belt-and-suspenders against CVE-2007-4559: reject obvious
            # path-traversal entries before letting tarfile's data filter
            # do the authoritative check. Archives are an
            # operator-shipped-bundle workflow, so externally-produced
            # archives are in scope.
            if m.name.startswith("/") or ".." in Path(m.name).parts:
                print(
                    f"error: archive {archive_path.name} contains unsafe "
                    f"member path {m.name!r}; refusing to extract",
                    file=sys.stderr,
                )
                return 2
            t.extract(m, path=data_dir, filter="data")

    print(
        f"restored {archive_path.name} -> {data_dir} "
        f"(world_id={manifest.get('world_id')}, "
        f"schema_version={src_schema}, "
        f"{manifest.get('asset_count', 0)} assets)"
    )
    if src_schema < cur_schema:
        print(
            f"note: archive schema is older than current ({src_schema} < {cur_schema}); "
            "next 'bin/game up' will run the missing migrations forward."
        )
    return 0


# ---- verify -------------------------------------------------------------


def cmd_verify(world_id: str | None) -> int:
    rc = _require_live_db()
    if rc is not None:
        return rc
    db.init_live()
    conn = db.get_conn()
    data_dir = config.data_dir()

    if world_id is None:
        worlds_to_check = [
            r["id"]
            for r in conn.execute("SELECT id FROM worlds ORDER BY id").fetchall()
        ]
    else:
        if conn.execute(
            "SELECT id FROM worlds WHERE id = ?", (world_id,)
        ).fetchone() is None:
            print(f"error: no world with id {world_id} in live DB", file=sys.stderr)
            return 2
        worlds_to_check = [world_id]

    total_orphan_rows = 0
    total_orphan_files = 0

    for wid in worlds_to_check:
        print(f"world: {wid}")

        # Orphan rows: DB row points at a file that does not exist.
        rows = assets.assets_for_world(wid, conn=conn)
        orphan_rows = [a for a in rows if not (data_dir / a.file_relpath).exists()]
        if orphan_rows:
            total_orphan_rows += len(orphan_rows)
            print(f"  orphan rows ({len(orphan_rows)}): row exists, file missing")
            for a in orphan_rows:
                print(f"    {a.target_kind}/{a.target_id}  {a.file_relpath}")
        else:
            print("  orphan rows: 0")

        # Orphan files: PNG on disk with no matching DB row. Walk the
        # per-world cache dir and compare relative paths against the
        # recorded file_relpaths.
        recorded_relpaths = {a.file_relpath for a in rows}
        cache_dir = _world_cache_dir(wid)
        if cache_dir.exists():
            disk_files = [
                f for f in cache_dir.rglob("*.png") if f.is_file()
            ]
            orphan_files = [
                f for f in disk_files
                if str(f.relative_to(data_dir)) not in recorded_relpaths
            ]
        else:
            orphan_files = []

        if orphan_files:
            total_orphan_files += len(orphan_files)
            print(f"  orphan files ({len(orphan_files)}): file exists, no row")
            for f in orphan_files:
                print(f"    {f.relative_to(data_dir)}  ({_format_bytes(f.stat().st_size)})")
        else:
            print("  orphan files: 0")

    print()
    print(
        f"verify summary: {total_orphan_rows} orphan rows, "
        f"{total_orphan_files} orphan files"
    )
    return 0


# ---- delete -------------------------------------------------------------


def cmd_delete(world_id: str, yes: bool) -> int:
    if not yes:
        print(
            f"refusing to delete {world_id}: pass --yes to confirm.\n"
            "this removes DB rows AND the cache dir; archive first if you "
            "might want it back: bin/game world archive " + world_id,
            file=sys.stderr,
        )
        return 2
    rc = _require_live_db()
    if rc is not None:
        return rc
    db.init_live()
    conn = db.get_conn()
    world = conn.execute(
        "SELECT id FROM worlds WHERE id = ?", (world_id,)
    ).fetchone()
    if world is None:
        print(f"error: no world with id {world_id} in live DB", file=sys.stderr)
        return 2
    # Cascade by hand. Order: child rows first.
    conn.execute(
        "DELETE FROM events WHERE room_id IN (SELECT id FROM rooms WHERE world_id = ?)",
        (world_id,),
    )
    # Now that generated_assets has world_id (migration 003), filter cleanly
    # rather than blanket-deleting. Multi-world DBs no longer get clobbered.
    conn.execute("DELETE FROM generated_assets WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM memories WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM items WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM toons WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM rooms WHERE world_id = ?", (world_id,))
    conn.execute("DELETE FROM worlds WHERE id = ?", (world_id,))
    cache_dir = _world_cache_dir(world_id)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    print(f"deleted world {world_id} (DB rows + {cache_dir})")
    return 0


# ---- skill add ---------------------------------------------------------


# JSON author-file shape. Values are already parsed (dict for predicate
# and effects_schema, not JSON strings) — the CLI re-serializes them
# for the `_json` TEXT columns on write. This keeps the author file
# readable and diffable.
_SKILL_REQUIRED_STR = ("name", "ui_hint", "description", "prompt_template")
_SKILL_REQUIRED_DICT = ("context_predicate", "effects_schema")


def _skill_validate(payload: object) -> dict | str:
    """Return a normalized dict on success, an error message on failure.
    Validation is deliberately strict so a misauthored skill JSON fails
    at the CLI with a clear diagnostic rather than landing a bad row in
    the `skills` table that the executor would later skip silently."""
    if not isinstance(payload, dict):
        return "top-level JSON must be an object"
    for field in _SKILL_REQUIRED_STR:
        v = payload.get(field)
        if not isinstance(v, str) or not v.strip():
            return f"missing or empty required string field: {field!r}"
    for field in _SKILL_REQUIRED_DICT:
        v = payload.get(field)
        if not isinstance(v, dict):
            return f"missing or non-object required field: {field!r}"
    return {
        "name": payload["name"].strip().lower(),
        "ui_hint": payload["ui_hint"].strip(),
        "description": payload["description"].strip(),
        "prompt_template": payload["prompt_template"],
        "context_predicate": payload["context_predicate"],
        "effects_schema": payload["effects_schema"],
        "author": str(payload.get("author", "admin")).strip() or "admin",
    }


def cmd_skill_add(path: Path) -> int:
    """Install a data skill from a JSON author file.

    Author-file schema (validated):
        name              (str, non-empty; lowercased before storage)
        ui_hint           (str, non-empty; button label)
        description       (str, non-empty; one-line summary for the interpreter)
        prompt_template   (str, non-empty; Jinja template)
        context_predicate (object; e.g. {} or {"room_slug": "forge"})
        effects_schema    (object; documentation/provenance in v1)
        author            (str, optional; defaults to 'admin')

    Writes to the skills table with kind='data'. Upsert on name: re-running
    with an edited JSON file updates the row in place (idempotent) while
    preserving the row's id. Exit 0 on success, 2 on any failure; no
    partial writes.
    """
    if err := _require_live_db():
        return err
    if not path.exists():
        print(f"error: {path}: no such file", file=sys.stderr)
        return 2
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"error: {path}: invalid JSON: {e}", file=sys.stderr)
        return 2
    validated = _skill_validate(payload)
    if isinstance(validated, str):
        print(f"error: {path}: {validated}", file=sys.stderr)
        return 2
    conn = db.init_live()
    # Use ON CONFLICT(name) upsert so re-runs update the existing row in
    # place, preserving the PK and letting operators edit the JSON file
    # without the row's id churning.
    conn.execute(
        "INSERT INTO skills "
        "(id, name, kind, context_predicate_json, prompt_template, ui_hint, "
        " description, effects_schema_json, author, enabled) "
        "VALUES (?, ?, 'data', ?, ?, ?, ?, ?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET "
        " kind = 'data',"
        " context_predicate_json = excluded.context_predicate_json,"
        " prompt_template = excluded.prompt_template,"
        " ui_hint = excluded.ui_hint,"
        " description = excluded.description,"
        " effects_schema_json = excluded.effects_schema_json,"
        " author = excluded.author,"
        " enabled = 1",
        (
            f"skill-{validated['name']}",
            validated["name"],
            json.dumps(validated["context_predicate"]),
            validated["prompt_template"],
            validated["ui_hint"],
            validated["description"],
            json.dumps(validated["effects_schema"]),
            validated["author"],
        ),
    )
    print(f"installed skill {validated['name']!r} from {path}")
    return 0


def cmd_world_bootstrap(
    name: str,
    aesthetic: str,
    output: Path | None,
    model: str,
    force: bool,
) -> int:
    """Author a fresh daydream world via Claude Opus 4.7 (or another
    model named via --model). Writes a new SQLite file at the chosen
    output path. See ``daydream/llm/bootstrap.py`` for the full
    pipeline (LLM call → JSON validate → DB write).

    Exit codes:
    - 0 on success.
    - 2 if the LLM call fails (no ANTHROPIC_API_KEY, network error,
      rate limit, malformed model name).
    - 3 if the LLM's JSON envelope fails validation (wrong shape,
      duplicate slugs, broken exits, etc.).
    - 4 if the output path exists and --force was not given.
    """
    from daydream.llm import bootstrap as boot_mod

    if output is None:
        output = config.data_dir() / f"worlds-{config.env()}" / f"{name}.db"
    output = Path(output).expanduser()
    try:
        result = boot_mod.bootstrap_world(
            name=name,
            aesthetic=aesthetic,
            output_path=output,
            model=model,
            force=force,
        )
    except boot_mod.BootstrapOutputExistsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 4
    except boot_mod.BootstrapValidationError as e:
        print(f"error: bootstrap validation failed: {e}", file=sys.stderr)
        return 3
    except boot_mod.BootstrapLLMError as e:
        print(f"error: bootstrap LLM call failed: {e}", file=sys.stderr)
        return 2
    print(f"bootstrapped world {name!r} -> {result}")
    return 0


# ---- main ---------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="daydream.admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list worlds and asset counts")

    p_arch = sub.add_parser("archive", help="tar DB + cache + manifest to archives/")
    p_arch.add_argument("world_id")

    p_rest = sub.add_parser("restore", help="extract a previous archive into data_dir")
    p_rest.add_argument("archive_path", type=Path)
    p_rest.add_argument("--yes", action="store_true", help="confirm restore")

    p_ver = sub.add_parser(
        "verify", help="report orphan rows and orphan files (diagnostic)"
    )
    p_ver.add_argument(
        "world_id", nargs="?", default=None,
        help="restrict to one world (default: all worlds)",
    )

    p_del = sub.add_parser("delete", help="DELETE world rows + rm -rf cache dir")
    p_del.add_argument("world_id")
    p_del.add_argument("--yes", action="store_true", help="confirm destructive op")

    p_skill = sub.add_parser("skill", help="manage data skills")
    p_skill_sub = p_skill.add_subparsers(dest="skill_cmd", required=True)
    p_skill_add = p_skill_sub.add_parser("add", help="install/upsert a data skill from a JSON author file")
    p_skill_add.add_argument("path", type=Path, help="path to skill.json")

    p_boot = sub.add_parser(
        "bootstrap",
        help="author a fresh world via Claude Opus 4.7 (writes a new .db)",
    )
    p_boot.add_argument("name", help="kebab-case world identifier")
    p_boot.add_argument(
        "--aesthetic", required=True,
        help='free-text aesthetic description, e.g. "a foggy autumn forest village"',
    )
    p_boot.add_argument(
        "--output", type=Path, default=None,
        help="output path (default: ~/data/daydream/worlds-dev/<NAME>.db)",
    )
    p_boot.add_argument(
        "--model", default="anthropic/claude-opus-4-7",
        help="LiteLLM model identifier (default: anthropic/claude-opus-4-7)",
    )
    p_boot.add_argument(
        "--force", action="store_true",
        help="overwrite the output path if it already exists",
    )

    args = p.parse_args(argv)
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "archive":
        return cmd_archive(args.world_id)
    if args.cmd == "restore":
        return cmd_restore(args.archive_path, args.yes)
    if args.cmd == "verify":
        return cmd_verify(args.world_id)
    if args.cmd == "delete":
        return cmd_delete(args.world_id, args.yes)
    if args.cmd == "skill":
        if args.skill_cmd == "add":
            return cmd_skill_add(args.path)
    if args.cmd == "bootstrap":
        return cmd_world_bootstrap(
            args.name, args.aesthetic, args.output, args.model, args.force,
        )
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
