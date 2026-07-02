"""Drive the canonical walkthrough over a LIVE server's WebSocket (SPEC
2026-07-02 criterion 15): the swap rehearsal's solo playthrough, against
real engines, room art rendering lazily along the way.

Usage (server up, world swapped to zork1):

    .venv/bin/python tools/ws_playthrough.py [--base http://127.0.0.1:54321]
        [--slot 1] [--delay 0.15] [--transcript PATH]

The driver logs in (tailnet-trusted from loopback), claims the authored
slot-1 toon, opens /ws, replays every dataset command as a free-text
`{kind:"input"}` frame — the same producer a typing player is — and
tracks state snapshots. It exits 0 only if the final snapshot shows score
350 at the Stone Barrow. The transcript (every narration, keyed by the
command that produced it) is the findings record for the fix round.

Determinism note: the live world pins the same rng_seed, and the seeded
streams key on (seed, turn, purpose), so a fresh world replays the fights
and the thief exactly as tests/test_zork_walkthrough.py does."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
DATASET = json.loads((ROOT / "tests/data/zork1_walkthrough.json").read_text())


async def drive(base: str, slot: int, delay: float, transcript_path: Path,
                verify: bool = False) -> int:
    async with httpx.AsyncClient(base_url=base, timeout=30.0) as http:
        r = await http.post("/api/login", data={"password": ""})
        if r.status_code not in (200, 303):
            print(f"login failed: {r.status_code} {r.text[:200]}")
            return 2
        slots = (await http.get("/api/slots")).json()
        mine = next((s for s in slots.get("slots", []) if s.get("slot") == slot), None)
        if mine and mine.get("toon"):
            r = await http.post(f"/api/slots/{slot}/claim")
        else:
            r = await http.post(f"/api/slots/{slot}/create", json={
                "name": "Rehearsal",
                "appearance_seed": "a walkthrough made flesh, moving with unnatural certainty",
            })
        if r.status_code != 200:
            print(f"slot {slot} claim/create failed: {r.status_code} {r.text[:200]}")
            return 2
        cookies = "; ".join(f"{k}={v}" for k, v in http.cookies.items())

    ws_url = base.replace("http", "ws", 1) + "/ws"
    state = {"room": None, "room_id": None, "score": None, "rank": None,
             "moves": None}
    lines: list[str] = []
    t0 = time.monotonic()

    async with websockets.connect(
        ws_url, additional_headers={"Cookie": cookies}, max_size=2**22
    ) as ws:

        def absorb(frame: dict, cmd: str) -> None:
            kind = frame.get("kind")
            if kind == "state_snapshot":
                room = frame.get("room") or {}
                status = frame.get("status") or {}
                state.update(
                    room=room.get("title"), room_id=room.get("id"),
                    score=status.get("score"),
                    rank=status.get("rank"), moves=status.get("moves"),
                )
            elif kind == "event":
                ev = frame.get("event") or {}
                if ev.get("kind") == "narrate":
                    text = (ev.get("payload") or {}).get("text", "")
                    if text:
                        lines.append(f"[{cmd}] {text}")

        async def drain(cmd: str, quiet_for: float) -> None:
            deadline = time.monotonic() + quiet_for
            while True:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    return
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=budget)
                except asyncio.TimeoutError:
                    return
                absorb(json.loads(raw), cmd)

        async def await_ack(cmd: str, quiet_for: float, ack_timeout: float = 60.0) -> None:
            """Every executed command produces at least one frame for this
            client (private narrate, event, or snapshot). Block for the
            first one — retells can stall seconds behind the art queue on
            the GPU arbiter — then absorb a short quiet tail. Pacing by
            acknowledgment keeps the driver from outrunning the server's
            receive loop and dropping the tail on close."""
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=ack_timeout)
            except asyncio.TimeoutError:
                print(f"  !! no acknowledgment for {cmd!r} within {ack_timeout}s")
                return
            absorb(json.loads(raw), cmd)
            await drain(cmd, quiet_for)

        await drain("(connect)", 1.5)
        total = sum(len(s["commands"]) for s in DATASET["segments"])
        n = 0
        for seg in DATASET["segments"]:
            for step in seg["commands"]:
                n += 1
                cmd = step["cmd"]
                await ws.send(json.dumps({"kind": "input", "text": cmd}))
                await await_ack(cmd, delay)
                if verify and "expect" in step:
                    exp = step["expect"]
                    bad = []
                    if "room" in exp and state["room_id"] != exp["room"]:
                        bad.append(f"room {state['room_id']!r} != {exp['room']!r}")
                    if "score" in exp and state["score"] != exp["score"]:
                        bad.append(f"score {state['score']} != {exp['score']}")
                    if bad:
                        print(f"\nDIVERGED at [{n}] {cmd!r}: " + "; ".join(bad))
                        print("last narrations:")
                        for line in lines[-8:]:
                            print("   " + line)
                        return 3
            print(f"  [{n:3d}/{total}] {seg['name']:28s} room={state['room']!r} "
                  f"score={state['score']} moves={state['moves']}")
        await drain("(final)", 3.0)

    dt = time.monotonic() - t0
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(
        f"# ws_playthrough {datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}\n"
        f"# {dt:.0f}s, final: {state}\n\n" + "\n".join(lines) + "\n"
    )
    print(f"\nfinal state: {state}  ({dt:.0f}s)")
    print(f"transcript: {transcript_path}")
    ok = state["score"] == 350 and state["room"] == "Stone Barrow"
    print("PLAYTHROUGH " + ("COMPLETE: 350 at the Stone Barrow" if ok else "INCOMPLETE"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:54321")
    ap.add_argument("--slot", type=int, default=1)
    ap.add_argument("--delay", type=float, default=0.15,
                    help="quiet-period per command (seconds)")
    ap.add_argument("--verify", action="store_true",
                    help="check each step's expectations; stop at first divergence")
    ap.add_argument("--transcript", type=Path,
                    default=Path.home() / "data/daydream/rehearsals" /
                    f"zork1-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}.log")
    args = ap.parse_args()
    return asyncio.run(drive(args.base, args.slot, args.delay,
                             args.transcript, verify=args.verify))


if __name__ == "__main__":
    sys.exit(main())
