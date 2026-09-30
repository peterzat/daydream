"""Replay a play battery against the running server, through `bin/game play`
with the real local model (spec 2026-09-29 criterion 14).

A battery is JSON: {"groups": [{"name", "moves"?, "lines"}]}. Each group is
one fresh dreamer (`<prefix>-<group>`) that walks its moves from the start
room and types each line; the reply to each line is written, in order, to
the output file for reading. Nothing here judges a reply: the reader does,
and `--flag` only marks the known dead-end phrasings to read first.

    tools/play_battery.py docs/playtests/2026-09-29-creative-break.battery.json \\
        --prefix brk2 --out ~/data/daydream/playtests/brk2.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The answers that are dead ends, as the engine phrases them.
DEAD_END = re.compile(
    r"(?i)isn't sure what you mean|floats up and away|drifts? by|doesn't quite catch|"
    r"nothing in the dream takes up|don't understand|the dream is foggy")


def play(*args: str, timeout: int = 120) -> tuple[str, float]:
    t0 = time.monotonic()
    r = subprocess.run([str(ROOT / "bin/game"), "play", *args], capture_output=True,
                       text=True, timeout=timeout, cwd=ROOT)
    return (r.stdout + r.stderr).strip(), round(time.monotonic() - t0, 1)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("battery", type=Path)
    ap.add_argument("--prefix", default="brk", help="dreamer name prefix (fresh names, fresh dreamers)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--look", default="a curious dreamer in a patched coat")
    args = ap.parse_args(argv)
    battery = json.loads(args.battery.read_text())
    out = []
    for g in battery["groups"]:
        name = f"{args.prefix}-{g['name']}"
        play("start", name, "--look", args.look)
        for move in g.get("moves", []):
            play("do", name, move)
        for line in g["lines"]:
            text, secs = play("do", name, line)
            reply = text.split("\n== ")[0].strip()  # the room block a move prints
            row = {"group": g["name"], "line": line, "secs": secs, "reply": reply,
                   "dead_end": bool(DEAD_END.search(reply))}
            out.append(row)
            print(f"[{g['name']}] {line!r} ({secs}s){' DEAD END' if row['dead_end'] else ''}\n"
                  f"    {reply[:300]}", flush=True)
        play("leave", name)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {args.out}: {len(out)} lines, {sum(r['dead_end'] for r in out)} dead ends")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
