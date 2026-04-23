"""Websocket endpoint and protocol.

Protocol:
- Server -> client on connect:  {kind: "state_snapshot", room, items, toons, skills, events, last_seq}
- Server -> client per change:  {kind: "event", event: {...}}
- Client -> server free-form:   {kind: "input", text: "..."}

Free-form input is routed by:
  1. Canonical bypass: if the first word is a known skill name (e.g., 'look'),
     dispatch directly. No LLM call. This is what the SPA's skill buttons send.
  2. Otherwise: pass through the LLM interpreter to pick a skill or 'none'.
     'none' produces a graceful narration fallback (SPEC criteria 6 and 7).

v0 hardcodes the human controller to the single seeded toon (Wren) in the
single seeded room (the meadow). Slot management lands in v1."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from daydream import events, items, rooms, toons
from daydream.api import auth
from daydream.skills import interpreter, registry

router = APIRouter()

HUMAN_TOON_ID = "t-wren"
HUMAN_ROOM_ID = "r-meadow"
SNAPSHOT_HISTORY_DEPTH = 50


def _state_snapshot(last_seq: int) -> dict:
    """Build a snapshot pinned to the given last_seq. Caller subscribes first
    (so concurrent appends fan out to this connection's queue), then captures
    last_seq, then calls this; any queued events with seq <= last_seq are
    drained as duplicates of what the snapshot already contains."""
    room = rooms.get_room(HUMAN_ROOM_ID)
    items_in = items.get_items_in_room(HUMAN_ROOM_ID)
    toons_in = toons.get_toons_in_room(HUMAN_ROOM_ID)
    recent = events.fetch_since(
        max(0, last_seq - SNAPSHOT_HISTORY_DEPTH), room_id=HUMAN_ROOM_ID
    )
    available = registry.list_available_for_room(HUMAN_ROOM_ID)
    return {
        "kind": "state_snapshot",
        "room": (
            {
                "id": room.id,
                "slug": room.slug,
                "title": room.title,
                "description": room.description_cached,
            }
            if room
            else None
        ),
        "items": [{"id": i.id, "name": i.name} for i in items_in],
        "toons": [{"id": t.id, "name": t.name, "mood": t.mood} for t in toons_in],
        "skills": [{"name": s.name, "ui_hint": s.ui_hint} for s in available],
        "events": [e.to_dict() for e in recent],
        "last_seq": last_seq,
    }


async def _handle_input(text: str) -> None:
    """Route player input. Canonical form (skill word + args) bypasses the LLM
    so button clicks and exact commands don't pay round-trip latency."""
    text = text.strip()
    if not text:
        return
    parts = text.split(None, 1)
    head = parts[0].lower()
    if registry.find(head) is not None:
        rest = parts[1] if len(parts) > 1 else ""
        registry.execute(head, HUMAN_TOON_ID, HUMAN_ROOM_ID, rest)
        return
    available = registry.list_available_for_room(HUMAN_ROOM_ID)
    decision = await interpreter.interpret(text, available)
    if decision.skill == "none":
        if decision.error:
            out = "The dream is foggy right now; that thought slips away."
        else:
            out = f"You think to yourself: \"{text}\". The daydream answers softly."
        events.append("system", None, "narrate", {"text": out}, room_id=HUMAN_ROOM_ID)
        return
    registry.execute(decision.skill, HUMAN_TOON_ID, HUMAN_ROOM_ID, decision.args)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if not auth.is_authed(ws.scope.get("session", {})):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await ws.accept()
    # Subscribe before snapshot so any events that land while we yield to send
    # the snapshot are captured in the queue; pin last_seq here, then drop any
    # queued events with seq <= last_seq before the broadcast loop starts.
    queue = events.subscribe()
    try:
        last_seq = events.max_seq()
        await ws.send_json(_state_snapshot(last_seq))
        receive_task = asyncio.create_task(_receive_loop(ws))
        broadcast_task = asyncio.create_task(_broadcast_loop(ws, queue, last_seq))
        done, pending = await asyncio.wait(
            [receive_task, broadcast_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        events.unsubscribe(queue)


async def _receive_loop(ws: WebSocket) -> None:
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("kind") == "input":
                await _handle_input(str(msg.get("text", "")))
    except WebSocketDisconnect:
        pass


async def _broadcast_loop(
    ws: WebSocket, queue: asyncio.Queue, snapshot_seq: int
) -> None:
    try:
        while True:
            event = await queue.get()
            # Drop events already covered by the snapshot to avoid duplicates
            # from the subscribe-before-snapshot ordering.
            if event.seq <= snapshot_seq:
                continue
            if event.room_id is not None and event.room_id != HUMAN_ROOM_ID:
                continue
            await ws.send_json({"kind": "event", "event": event.to_dict()})
    except (WebSocketDisconnect, RuntimeError):
        pass
