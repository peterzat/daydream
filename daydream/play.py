"""`bin/game play`: the agent play bridge (SPEC 2026-09-26 criterion 17).

Lets an agent (or a person at a shell) play a LIVE session through the very
WebSocket path a browser uses, one shell invocation at a time. A named
session persists between invocations (its cookie, toon, and the last event
it saw, under ~/data/daydream/play/<name>.json), so every call first prints
what happened in the room since the previous call ("meanwhile"), then sends
the new input and prints the narration it caused. Several named sessions
can play the same world at once from different shells.

    bin/game play start <name> [--slot N] [--look "appearance"]
    bin/game play do    <name> "take the lantern"       typed text
    bin/game play ask   <name> <npc> "<topic>"           the topic chip click
    bin/game play click <name> <verb> [<target>] [--with <iobj>] [--text ...]
    bin/game play look  <name>                           the scene, no input
    bin/game play book  <name>                           the Book of Stray Minutes
    bin/game play leave <name>                           rest the toon

Targets are resolved by name against the snapshot's entities. Output is
plain text meant to be read by an agent: the room, what is here, who is
here (with what you could ask them about), the ways out, the time of day.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
import websockets

DEFAULT_BASE = f"http://127.0.0.1:{os.environ.get('DAYDREAM_PORT', '54321')}"


def _state_dir() -> Path:
    base = Path(os.environ.get("DAYDREAM_DATA_DIR", Path.home() / "data" / "daydream"))
    d = base / "play"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(name: str) -> dict:
    p = _state_dir() / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"no play session {name!r}; run: bin/game play start {name}")
    return json.loads(p.read_text())


def _save(name: str, st: dict) -> None:
    # The state file holds a live account session cookie: owner-only.
    path = _state_dir() / f"{name}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(st, indent=2))
    os.chmod(path, 0o600)


# ---- rendering ---------------------------------------------------------------


def _scene(snap: dict) -> str:
    room = snap.get("room") or {}
    out = [f"== {room.get('title', '?')} =="]
    t = snap.get("time")
    if t and t.get("running"):
        out.append(f"(day {t['day']}, {t['label']})")
    elif t:
        out.append("(time stands still here)")
    if room.get("description"):
        out.append(room["description"])
    me = snap.get("self") or {}
    others = [x for x in snap.get("toons") or [] if x.get("id") != me.get("id")]
    if others:
        out.append("Here with you:")
        for o in others:
            line = f"  - {o['name']}"
            if o.get("away"):
                line += " (dozing)"  # a player with no one at their page
            elif o.get("mood"):
                line += f" ({o['mood']})"
            if o.get("topics"):
                line += "  | ask about: " + "; ".join(o["topics"])
            out.append(line)
    items = snap.get("items") or []
    if items:
        out.append("Around you: " + ", ".join(i["name"] for i in items))
    inv = snap.get("inventory") or []
    out.append("You carry: " + (", ".join(i["name"] for i in inv) if inv else "nothing"))
    exits = room.get("exits") or {}
    out.append("Ways: " + (", ".join(exits) if exits else "none"))
    verbs = [v["name"] for v in snap.get("verb_bar") or []]
    if verbs:
        out.append("Verbs: " + ", ".join(verbs))
    book = snap.get("book")
    if book:
        out.append(f"Book: {book['found']}/{book['total']} stray minutes")
    slept = snap.get("while_you_slept")
    if slept:
        out.append(f"** {slept.get('title', 'While you slept')} ** {slept.get('text', '')}")
    return "\n".join(out)


def _line(frame: dict, me: str | None = None) -> str | None:
    if frame.get("kind") == "event":
        e = frame.get("event") or {}
        p = e.get("payload") or {}
        if e.get("kind") == "narrate" and p.get("text"):
            return p["text"]
        if e.get("kind") in ("move", "arrive"):
            # Comings and goings, as the SPA tells them: your own move once
            # (its `you` line), anyone else's as the room saw it.
            if me and e.get("actor_id") == me:
                return p.get("you") if e.get("kind") == "move" else None
            return p.get("text")
        if e.get("kind") == "say" and p.get("text"):
            to = f" to {p['to']}" if p.get("to") else ""
            return f"{p.get('name', 'someone')} says{to}: \"{p['text']}\""
        if e.get("kind") == "game_won":
            return "[the dream reaches an ending]"
        return None
    if frame.get("kind") == "clarify":
        opts = ", ".join(o["name"] for o in frame.get("options", []))
        return f"[{frame.get('prompt')}] options: {opts}"
    if frame.get("kind") == "notice" and frame.get("text"):
        # A gentle limit (too long, too fast): the page shows it; so does this.
        return f"[{frame['text']}]"
    return None


# ---- the connection ------------------------------------------------------------


async def _session(st: dict, frame: dict | None, quiet: float = 1.2,
                   ack_timeout: float = 45.0) -> tuple[dict | None, list[str], list[str]]:
    """Connect (resuming from the last seen seq), collect the snapshot and
    the replayed 'meanwhile' lines, optionally send one frame and collect
    what it caused. Returns (latest snapshot, meanwhile lines, result lines)."""
    url = st["base"].replace("http", "ws", 1) + "/ws"
    if st.get("started"):
        # Every connection after the first resumes from the last event this
        # session saw, so the room's history since then replays ("meanwhile").
        url += f"?since={int(st.get('last_seq') or 0)}"
    meanwhile: list[str] = []
    result: list[str] = []
    snap = None
    async with websockets.connect(url, additional_headers={"Cookie": st["cookie"]},
                                  max_size=2**23) as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
        if first.get("kind") == "needs_toon":
            raise SystemExit("this session controls no toon (left or kicked); "
                             "run `bin/game play start` again")
        snap = first
        me = (first.get("self") or {}).get("id")
        for e in first.get("events") or []:
            line = _line({"kind": "event", "event": e}, me)
            if line:
                meanwhile.append(line)
        st["last_seq"] = first.get("last_seq", st.get("last_seq", 0))
        if frame is not None:
            sent_at = first.get("last_seq", 0)
            seen: set[int] = {e.get("seq") for e in first.get("events") or []}
            await ws.send(json.dumps(frame))
            # Until something addressed to this player arrives (their own
            # move or speech, a private line), keep waiting: an improvised
            # reply takes seconds, and an early frame (a refresh, a bystander
            # line) must not end the wait (playtest 2026-09-26: replies landed
            # a command late, under "meanwhile").
            answered = {"yes": False}
            deadline = time.monotonic() + min(ack_timeout, 25.0)

            def take(e: dict) -> None:
                # Events arrive live OR inside a re-snapshot's replayed
                # history (the SPA rehydrates from it): print each once.
                seq = e.get("seq", 0)
                if seq <= sent_at or seq in seen:
                    return
                seen.add(seq)
                # Your own words told back (a talk's private echo) are not
                # the reply: the reply is the line that follows, seconds
                # later (beta rehearsal 2026-09-28: replies landed a command
                # late, under "meanwhile").
                own_echo = (e.get("kind") in ("say", "echo") and e.get("actor_id") == me
                            and e.get("recipient_id") == me)
                if me and not own_echo and (e.get("recipient_id") == me or e.get("actor_id") == me):
                    answered["yes"] = True
                line = _line({"kind": "event", "event": e}, me)
                if line:
                    result.append(line)

            while True:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=budget)
                except asyncio.TimeoutError:
                    break
                f = json.loads(raw)
                if f.get("kind") == "state_snapshot":
                    snap = f
                    st["last_seq"] = max(st.get("last_seq", 0), f.get("last_seq", 0))
                    for e in sorted(f.get("events") or [], key=lambda x: x.get("seq", 0)):
                        take(e)
                elif f.get("kind") == "event":
                    st["last_seq"] = max(st.get("last_seq", 0), f["event"].get("seq", 0))
                    take(f["event"])
                elif f.get("kind") == "thinking":
                    # A reply is composing: wait for it.
                    deadline = time.monotonic() + 25.0
                    continue
                else:
                    line = _line(f)
                    if line:
                        result.append(line)
                        answered["yes"] = True
                if answered["yes"]:
                    deadline = time.monotonic() + quiet
    if snap is not None:
        st["room"] = (snap.get("room") or {}).get("id")
        st["entities"] = snap.get("entities") or []
        st["toons"] = [{"id": t["id"], "name": t["name"]} for t in snap.get("toons") or []]
    return snap, meanwhile, result


def _resolve(st: dict, name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().lower()
    for t in st.get("toons") or []:
        if t["name"].lower() == n:
            return t["id"]
    for e in st.get("entities") or []:
        if e.get("alias", "").lower() == n:
            return e["object_id"]
    return None


def agent_cookie(name: str) -> str:
    """A session cookie for the agent account behind play session `name`,
    minted in-process against this env's accounts DB (the shell is the admin
    console, so agents need no password). One `agent-<name>` player account
    per play name."""
    from daydream import accounts, config

    accounts.init()
    handle = re.sub(r"[^a-z0-9_-]", "", name.lower())[:18] or "player"
    token, _ = accounts.mint_session(f"agent-{handle}", display_name=f"agent {name}")
    return f"{config.cookie_name()}={token}"


async def enter_as(http, name: str, look: str | None = None, slot: int | None = None):
    """Enter the dream as this account's toon: its own if it has one ("your
    dreamer"), else a new one named `name` (in `slot` if given). Returns the
    claim/create response."""
    mine = (await http.get("/api/dreamer")).json().get("toons", [])
    if mine:
        return await http.post(f"/api/slots/{mine[0]['slot']}/claim")
    body = {"name": name,
            "appearance_seed": look or f"{name}, a traveler with a curious, kind face"}
    if slot is not None:
        return await http.post(f"/api/slots/{slot}/create", json=body)
    return await http.post("/api/dreamer/create", json=body)


async def _start(name: str, base: str, slot: int | None, look: str | None) -> int:
    cookie = agent_cookie(name)
    async with httpx.AsyncClient(base_url=base, timeout=30.0,
                                 headers={"Cookie": cookie}) as http:
        r = await enter_as(http, name, look, slot)
        if r.status_code != 200:
            print(f"claim/create failed: {r.status_code} {r.text[:200]}")
            return 2
    st = {"name": name, "base": base, "cookie": cookie, "last_seq": 0}
    snap, _, _ = await _session(st, None)
    st["started"] = True
    _save(name, st)
    print(_scene(snap))
    return 0


async def _act(name: str, frame: dict | None, show_scene: bool) -> int:
    st = _load(name)
    before_room = st.get("room")
    snap, meanwhile, result = await _session(st, frame)
    _save(name, st)
    if meanwhile and frame is not None:
        print("(meanwhile)")
        for line in meanwhile:
            print("  " + line)
    for line in result:
        print(line)
    if snap is not None and (show_scene or st.get("room") != before_room
                             or snap.get("while_you_slept")):
        print()
        print(_scene(snap))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bin/game play", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("name")
    s.add_argument("--slot", type=int)
    s.add_argument("--look", help="appearance for a new toon's portrait")
    d = sub.add_parser("do")
    d.add_argument("name")
    d.add_argument("text", nargs="+")
    a = sub.add_parser("ask")
    a.add_argument("name")
    a.add_argument("npc")
    a.add_argument("topic", nargs="*")
    c = sub.add_parser("click")
    c.add_argument("name")
    c.add_argument("verb")
    c.add_argument("target", nargs="?")
    c.add_argument("--with", dest="iobj")
    c.add_argument("--text", default="")
    for n in ("look", "book", "leave"):
        x = sub.add_parser(n)
        x.add_argument("name")
    args = ap.parse_args(argv)

    if args.cmd == "start":
        return asyncio.run(_start(args.name, args.base, args.slot, args.look))
    if args.cmd == "do":
        return asyncio.run(_act(args.name, {"kind": "input", "text": " ".join(args.text)}, False))
    if args.cmd == "look":
        return asyncio.run(_act(args.name, None, True))
    if args.cmd == "ask":
        st = _load(args.name)
        npc = _resolve(st, args.npc)
        if npc is None:
            asyncio.run(_act(args.name, None, False))
            st = _load(args.name)
            npc = _resolve(st, args.npc)
        if npc is None:
            print(f"no one called {args.npc!r} is here")
            return 1
        return asyncio.run(_act(args.name, {"kind": "command", "verb": "ask", "dobj_id": npc,
                                            "args": " ".join(args.topic)}, False))
    if args.cmd == "click":
        st = _load(args.name)
        frame = {"kind": "command", "verb": args.verb, "args": args.text}
        if args.target:
            frame["dobj_id"] = _resolve(st, args.target)
            if frame["dobj_id"] is None:
                print(f"no {args.target!r} in view; try `look` first")
                return 1
        if args.iobj:
            frame["iobj_id"] = _resolve(st, args.iobj)
        return asyncio.run(_act(args.name, frame, False))
    if args.cmd == "book":
        st = _load(args.name)
        snap, _, _ = asyncio.run(_session(st, None))
        _save(args.name, st)
        book = (snap or {}).get("book")
        if not book:
            print("no book yet")
            return 0
        print(f"{book['title']}: {book['found']}/{book['total']}")
        for pg in book["pages"]:
            mark = " (complete)" if pg["complete"] else ""
            print(f"- {pg['title']}: {pg['found']}/{pg['total']}{mark}")
            for e in pg["entries"]:
                if e["found"]:
                    print(f"    * {e['name']}: {e['text']}")
        return 0
    if args.cmd == "leave":
        st = _load(args.name)

        async def go():
            async with httpx.AsyncClient(base_url=st["base"], timeout=30.0,
                                         headers={"Cookie": st["cookie"]}) as http:
                r = await http.post("/api/session/leave")
                print(f"left the dream ({r.status_code})")
        asyncio.run(go())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
