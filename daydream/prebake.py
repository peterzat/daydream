"""`bin/game prebake`: render a world's art at design time (SPEC 2026-09-26
criterion 20).

Every room background and every toon portrait (residents and guests alike,
offstage or not) is rendered through the PRODUCTION pipeline
(`images.client.generate_image` under the arbiter's exclusive slot, the same
workflows, prompt suffixes, and cache keys the live server uses), so the
first player to enter a room never waits on a render. Assets are recorded
in the DB's `generated_assets` like any lazy paint.

Run it with the game server DOWN (the arbiter is in-process: the server's
own renders would otherwise contend for the card) and ComfyUI up, against
the live DB right after `bin/game world reset` (which wipes the image cache
for the world it loads). Then grade: the agent Reads each PNG listed in the
contact sheet against WHIMSY.md, re-renders weak ones with a fresh sampler
seed (`--force <id> --reseed <id>=<n>`), and records verdicts in
docs/art/.

    bin/game prebake [--only rooms|toons] [--force id,...] [--reseed id=N,...]
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
import time
from pathlib import Path

from daydream import config, db, objects, toons


def _targets(world_id: str, only: str | None):
    from daydream.images import client

    out = []
    conn = db.get_conn()
    if only in (None, "rooms"):
        for r in conn.execute("SELECT * FROM objects WHERE world_id = ? AND kind = 'room' "
                              "ORDER BY id", (world_id,)):
            o = objects.Object.from_row(r)
            if not o.seed.strip():
                continue
            out.append(("room", o.id, o.properties.get("title") or o.name, client.PersistentTarget(
                world_id=world_id, target_kind="room", target_id=o.id, seed=o.seed,
                prompt_suffix=client.WHIMSY_PROMPT_SUFFIX)))
    if only in (None, "toons"):
        for r in conn.execute("SELECT * FROM objects WHERE world_id = ? AND kind = 'toon' "
                              "AND is_human_controlled = 0 ORDER BY slot", (world_id,)):
            o = objects.Object.from_row(r)
            seed = o.properties.get("appearance_seed")
            if not isinstance(seed, str) or not seed.strip():
                continue
            out.append(("toon", o.id, o.name, client.portrait_target(world_id, o.id, seed.strip())))
    return out


async def prebake(db_path: Path, only: str | None = None, force: set[str] | None = None,
                  reseed: dict[str, int] | None = None) -> list[dict]:
    from daydream.gpu import arbiter
    from daydream.images import cache, client

    force, reseed = force or set(), reseed or {}
    db.init_live(path=db_path, migrations_dir=config.MIGRATIONS_DIR)
    world_id = toons.live_world_id()
    results = []
    try:
        for kind, tid, label, target in _targets(world_id, only):
            workflow = client.load_workflow_for(target)
            path = cache.cache_path(world_id, target.target_kind, tid, target.seed, workflow)
            rec = {"kind": kind, "id": tid, "label": label, "path": str(path),
                   "prompt": client.canonical_prompt(target.seed, target.prompt_suffix)}
            if path.exists() and tid not in force:
                rec["status"] = "cached"
                results.append(rec)
                continue
            t0 = time.monotonic()
            try:
                async with arbiter.acquire():
                    out = await client.generate_image(target, force=tid in force,
                                                      seed=reseed.get(tid))
                rec.update(status="rendered", path=str(out),
                           seconds=round(time.monotonic() - t0, 1))
            except client.ComfyUIError as e:
                rec.update(status="failed", error=str(e)[:300])
            print(f"{rec['status']:8s} {kind:4s} {tid:24s} {rec.get('seconds', '')}",
                  flush=True)
            results.append(rec)
    finally:
        db.close_db()
    return results


def contact_sheet(results: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for r in results:
        img = (f'<img src="file://{html.escape(r["path"])}" loading="lazy">'
               if r["status"] != "failed" else f"<p>{html.escape(r.get('error', ''))}</p>")
        cards.append(f'<figure><figcaption><b>{html.escape(r["label"])}</b> '
                     f'({r["kind"]} {html.escape(r["id"])}, {r["status"]})</figcaption>'
                     f'{img}<p class="p">{html.escape(r["prompt"])}</p></figure>')
    page = ("<!doctype html><meta charset='utf-8'><title>prebake</title><style>"
            "body{font-family:Georgia;background:#f6f3ec;color:#3a4a44;margin:24px}"
            "figure{display:inline-block;width:420px;margin:10px;vertical-align:top}"
            "img{width:100%;border-radius:10px}.p{font-size:11px;opacity:.7}</style>"
            + "".join(cards))
    p = out_dir / "index.html"
    p.write_text(page)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))
    return p


def _server_up() -> bool:
    import httpx

    try:
        return httpx.get(f"http://127.0.0.1:{config.port()}/status/build", timeout=1.5).is_success
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bin/game prebake", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="DB to paint (default: the live DB)")
    ap.add_argument("--only", choices=("rooms", "toons"))
    ap.add_argument("--force", default="", help="comma list of ids to re-render")
    ap.add_argument("--reseed", default="", help="comma list of id=N sampler seeds")
    ap.add_argument("--allow-server-up", action="store_true")
    args = ap.parse_args(argv)
    if _server_up() and not args.allow_server_up:
        print("the game server is up; stop it first (bin/game down): its renders "
              "would contend with these for the card", file=sys.stderr)
        return 2
    reseed = {}
    for pair in filter(None, args.reseed.split(",")):
        k, v = pair.split("=", 1)
        reseed[k.strip()] = int(v)
    force = {x.strip() for x in args.force.split(",") if x.strip()} | set(reseed)
    db_path = Path(args.db or config.live_db_path()).expanduser()
    results = asyncio.run(prebake(db_path, args.only, force, reseed))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    sheet = contact_sheet(results, config.data_dir() / "prebake" / stamp)
    failed = [r for r in results if r["status"] == "failed"]
    print(f"{len(results)} targets ({len(failed)} failed); contact sheet: {sheet}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
