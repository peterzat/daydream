"""tools/ws_swarm.py — modest multiplayer load probe (plan 2026-07-02).

Spawns N bots that each log in, claim or create a human slot, open /ws, and
for M seconds walk in random compass directions and emit free text, pacing
by acknowledgment. Asserts every socket stays alive the whole time; prints
the server's arbiter + event-drop stats and per-bot latency.

This is the BACKLOG `multi-user-shared-world` 10-bot harness, modest
edition: a MANUAL instrument (not a pytest gate) to eyeball that arbiter v2
(shared LLM slots / exclusive renders / text priority) and the bounded
subscriber queues hold up when several players share the world and the GPU
at once. Movement verbs are deterministic (no LLM); free text goes through
the grounded parser (a real shared-slot LLM call), and stepping into a
fresh room kicks a lazy render — so the mix is exactly the text-vs-image
contention the arbiter arbitrates.

Run against a LIVE server (engines up for real latency; with them down the
game still runs — free text degrades to "foggy", art to a "painting"
overlay — so the socket-liveness assertion still means something):

    .venv/bin/python tools/ws_swarm.py [--base http://127.0.0.1:54321]
        [--bots 5] [--seconds 60] [--delay 0.2]

Password comes from DAYDREAM_PASSWORD (same as the server); loopback is
tailnet-trusted so an empty password works when the server has none set.
There are only 5 human slots, so --bots is clamped to 5.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time

import httpx
import websockets

MOVES = ["north", "south", "east", "west", "up", "down"]
CHATTER = [
    "look around",
    "hello there",
    "who is here",
    "examine the ground",
    "say hello to everyone",
    "what is this place",
    "sing a little song",
    "wave",
]
MAX_HUMAN_SLOTS = 5


async def _login_and_slot(http: httpx.AsyncClient, slot: int, password: str) -> bool:
    r = await http.post("/api/login", data={"password": password})
    if r.status_code not in (200, 303):
        print(f"  bot slot {slot}: login failed {r.status_code} {r.text[:120]}")
        return False
    slots = (await http.get("/api/slots")).json().get("slots", [])
    mine = next((s for s in slots if s.get("slot") == slot), None)
    if mine and mine.get("toon"):
        r = await http.post(f"/api/slots/{slot}/claim")
        # A live peer already holds it (409) — fall through to a different slot
        # is out of scope; just report and let this bot idle-fail loudly.
    else:
        r = await http.post(f"/api/slots/{slot}/create", json={
            "name": f"Swarm{slot}",
            "appearance_seed": "a curious wanderer, half-remembered",
        })
    if r.status_code != 200:
        print(f"  bot slot {slot}: claim/create failed {r.status_code} {r.text[:120]}")
        return False
    return True


async def _bot(base: str, slot: int, seconds: float, delay: float,
               password: str, rng: random.Random) -> dict:
    """One player: login → slot → /ws → random walk + chatter for `seconds`.
    Returns a per-bot result dict. `alive` is False if the socket ever
    dropped mid-run (the failure the swarm exists to catch)."""
    result = {"slot": slot, "alive": False, "actions": 0,
              "max_ack_ms": 0.0, "error": None}
    async with httpx.AsyncClient(base_url=base, timeout=30.0) as http:
        if not await _login_and_slot(http, slot, password):
            result["error"] = "login/slot"
            return result
        cookies = "; ".join(f"{k}={v}" for k, v in http.cookies.items())

    ws_url = base.replace("http", "ws", 1) + "/ws"
    try:
        async with websockets.connect(
            ws_url, additional_headers={"Cookie": cookies}, max_size=2**22
        ) as ws:
            # Absorb the initial snapshot burst.
            await _drain(ws, 1.0)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                text = (rng.choice(MOVES) if rng.random() < 0.6
                        else rng.choice(CHATTER))
                await ws.send(json.dumps({"kind": "input", "text": text}))
                t0 = time.monotonic()
                # Every executed command yields at least one frame for us.
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60.0)
                except asyncio.TimeoutError:
                    result["error"] = f"no ack for {text!r} in 60s"
                    return result
                ack_ms = (time.monotonic() - t0) * 1000
                result["max_ack_ms"] = max(result["max_ack_ms"], ack_ms)
                result["actions"] += 1
                _ = json.loads(raw)
                await _drain(ws, delay)
            result["alive"] = True
    except (websockets.exceptions.WebSocketException, OSError) as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


async def _drain(ws, quiet_for: float) -> None:
    """Absorb frames until `quiet_for` seconds pass with none."""
    deadline = time.monotonic() + quiet_for
    while True:
        budget = deadline - time.monotonic()
        if budget <= 0:
            return
        try:
            await asyncio.wait_for(ws.recv(), timeout=budget)
        except asyncio.TimeoutError:
            return
        except (websockets.exceptions.WebSocketException, OSError):
            raise


async def _monitor(base: str, stop: asyncio.Event, peaks: dict) -> None:
    """Poll /status/arbiter while the swarm runs; track peak waiting counts
    and the final line."""
    async with httpx.AsyncClient(base_url=base, timeout=5.0) as http:
        while not stop.is_set():
            try:
                line = (await http.get("/status/arbiter")).text.strip()
                peaks["last"] = line
                # Track the largest "+N waiting" seen on either gate.
                for tok in line.replace("+", " +").split():
                    if tok.startswith("+"):
                        peaks["max_waiting"] = max(peaks["max_waiting"], int(tok[1:]))
            except (httpx.HTTPError, ValueError):
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass


async def run(base: str, bots: int, seconds: float, delay: float,
              password: str) -> int:
    bots = max(1, min(bots, MAX_HUMAN_SLOTS))
    print(f"swarm: {bots} bots x {seconds:.0f}s against {base}")
    stop = asyncio.Event()
    peaks = {"max_waiting": 0, "last": "(no reading)"}
    monitor = asyncio.create_task(_monitor(base, stop, peaks))
    # Distinct per-bot RNGs seeded by index so a run is reproducible-ish
    # without argless Random() (index varies the stream; wall-clock does not
    # need to).
    results = await asyncio.gather(*[
        _bot(base, slot, seconds, delay, password, random.Random(1000 + slot))
        for slot in range(1, bots + 1)
    ])
    stop.set()
    await monitor

    print("\nper-bot:")
    all_alive = True
    total_actions = 0
    for r in results:
        total_actions += r["actions"]
        status = "alive" if r["alive"] else f"DEAD ({r['error']})"
        all_alive = all_alive and r["alive"]
        print(f"  slot {r['slot']}: {status}  actions={r['actions']}  "
              f"max_ack={r['max_ack_ms']:.0f}ms")
    print(f"\narbiter (final): {peaks['last']}")
    print(f"peak gate backlog during run: {peaks['max_waiting']} waiting")
    print(f"total actions: {total_actions}")
    ok = all_alive and total_actions > 0
    print("SWARM " + ("OK: all sockets survived" if ok
                      else "FAILED: a socket dropped or no actions ran"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:54321")
    ap.add_argument("--bots", type=int, default=5,
                    help=f"number of bots, clamped to {MAX_HUMAN_SLOTS} human slots")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--delay", type=float, default=0.2,
                    help="quiet-period drained after each command (seconds)")
    args = ap.parse_args()
    password = os.environ.get("DAYDREAM_PASSWORD", "")
    return asyncio.run(run(args.base, args.bots, args.seconds, args.delay, password))


if __name__ == "__main__":
    sys.exit(main())
