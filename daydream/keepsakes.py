"""Keepsakes while the village sleeps (SPEC 2026-09-27 criterion 16;
docs/GOING-LIVE.md section 6).

This exports, for each enabled account, what is theirs to read when the box
is down:

- their name and their toon's name
- their journal
- their Book of Stray Minutes (found entries only)
- their portrait
- the village chronicle

It also exports the pass list: sha256(session token) mapped to {account,
expires} for every live session. The edge Worker hashes a friend's session
cookie with WebCrypto and looks it up, so it recognizes them without a
signing key, without password hashes ever leaving the box, and with
revocation taking effect at the next sync.

Run by `bin/game prod sleep` and hourly, always with the prod release's own
code against prod data:

    python -m daydream.keepsakes export --stdout   (what bin/game prod runs, as
        the service user; the operator only receives the bytes)
    python -m daydream.keepsakes export --out DIR  (DIR/keepsakes.json)

`daydream/edge.py` uploads the result to Workers KV, changed keys only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

JOURNAL_ENTRIES = 10
CHRONICLE_LINES = 12


def _book(world_id: str, toon_id: str) -> dict | None:
    """The satchel's book, reduced to what reads well on a static page: the
    title, the counts, and the found entries per page (blanks dropped)."""
    from daydream import collect

    b = collect.book(world_id, toon_id)
    if not b:
        return None
    pages = []
    for p in b.get("pages") or []:
        found = [{"name": e.get("name"), "text": e.get("text")}
                 for e in p.get("entries") or [] if e.get("found")]
        pages.append({"title": p.get("title"), "found": p.get("found"), "total": p.get("total"),
                      "complete": p.get("complete"), "reward_text": p.get("reward_text"),
                      "entries": found})
    return {"title": b.get("title"), "found": b.get("found"), "total": b.get("total"),
            "pages": pages}


def _journal(toon_id: str) -> list[dict]:
    from daydream import objects

    stored = objects.get_property(toon_id, "journal")
    if not isinstance(stored, list):
        return []
    return [{"text": e.get("text"), "at": e.get("at")}
            for e in stored if isinstance(e, dict) and e.get("text")][-JOURNAL_ENTRIES:]


def _portrait_bytes(world_id: str, toon) -> bytes | None:
    """The portrait's bytes, read without following a symlink anywhere under
    the cache root (SECURITY WARN 2026-09-27: a planted link must not turn
    some other file into a friend's published "portrait")."""
    import os

    from daydream.images import cache, client

    seed = (toon.appearance_seed or "").strip()
    if not seed:
        return None
    target = client.portrait_target(world_id, toon.id, seed)
    path = cache.cache_path(world_id, "toon", toon.id, seed, client.load_workflow_for(target))
    root = cache.cache_dir().resolve()
    if path.resolve() != path.absolute() or root not in path.resolve().parents:
        return None  # a link somewhere on the way
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as f:
        return f.read(4 * 1024 * 1024)


def build() -> dict:
    """The keepsakes document, portraits inline as base64 (`portraits`)."""
    import base64

    from daydream import accounts, db, story, toons

    accounts.init()
    db.init_live()
    world_id = toons.live_world_id()
    chronicle = [{"day": e.get("day"), "text": e.get("text")}
                 for e in story.chronicle(world_id)][-CHRONICLE_LINES:]
    people: dict[str, dict] = {}
    portraits: dict[str, str] = {}
    for acc in accounts.list_accounts():
        if acc["disabled_at"]:
            continue
        mine = toons.owned_toons(acc["id"])
        entry = {"display_name": acc["display_name"], "toons": [], "portrait": False}
        for t in mine:
            entry["toons"].append({"name": t.name, "journal": _journal(t.id),
                                   "book": _book(world_id, t.id)})
        if mine:
            png = _portrait_bytes(world_id, mine[0])
            if png:
                portraits[acc["id"]] = base64.b64encode(png).decode()
                entry["portrait"] = True
        people[acc["id"]] = entry
    passes = {r["token_hash"]: {"account": r["account_id"], "expires": r["expires_at"]}
              for r in accounts.live_passes() if r["account_id"] in people}
    return {"world": world_id, "chronicle": chronicle, "accounts": people, "passes": passes,
            "portraits": portraits}


def export(out: Path) -> dict:
    """Write keepsakes.json under `out` (portraits inline); return it."""
    doc = build()
    out.mkdir(parents=True, exist_ok=True)
    (out / "keepsakes.json").write_text(json.dumps(doc, indent=1))
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m daydream.keepsakes")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    g = e.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", type=Path)
    g.add_argument("--stdout", action="store_true",
                   help="print the document (how bin/game prod takes it: as bytes)")
    args = p.parse_args(argv)
    if args.stdout:
        print(json.dumps(build()))
        return 0
    doc = export(args.out)
    print(f"keepsakes: {len(doc['accounts'])} account(s), {len(doc['passes'])} pass(es), "
          f"{len(doc['chronicle'])} chronicle line(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
