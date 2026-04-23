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
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from daydream import events, items, rooms, toons
from daydream.api import auth
from daydream.gpu import arbiter
from daydream.images import cache as image_cache
from daydream.images import client as image_client
from daydream.skills import interpreter, registry

logger = logging.getLogger(__name__)
router = APIRouter()

HUMAN_TOON_ID = "t-wren"
HUMAN_ROOM_ID = "r-meadow"
SNAPSHOT_HISTORY_DEPTH = 50

# Prompt suffix appended to every room-background generation. The full
# string lives in WHIMSY.md (## Prompt suffix); kept here as a code
# constant for now and will move to daydream/llm/prompts.py in v1's
# safety-baseline-v1 increment.
WHIMSY_PROMPT_SUFFIX = (
    "soft watercolor, painterly, warm late-day light, cozy storybook "
    "illustration, gentle composition, no text, no logos, no people in "
    "modern dress, no machinery, no harsh edges, Spiritfarer-adjacent, "
    "A Short Hike-adjacent, low-saturation cream and sage palette"
)

# Per-room generation dedup. Keys are (world_id, room_id, seed_hash).
# Set membership check + add is atomic under asyncio's cooperative model
# as long as no `await` sits between them.
_generating: set[tuple[str, str, str]] = set()


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

    image_url: str | None = None
    if room is not None and image_cache.is_cached(room.world_id, room.id, room.seed):
        image_url = image_cache.cache_url(room.world_id, room.id, room.seed)

    return {
        "kind": "state_snapshot",
        "room": (
            {
                "id": room.id,
                "slug": room.slug,
                "title": room.title,
                "description": room.description_cached,
                "image_url": image_url,
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


def _maybe_enqueue_image_gen(world_id: str, room_id: str, room_seed: str) -> None:
    """If the room has no cached background and no in-flight job, spawn one.
    Idempotent across concurrent connections: dedup keyed on seed hash."""
    if image_cache.is_cached(world_id, room_id, room_seed):
        return
    key = (world_id, room_id, image_cache.seed_hash(room_seed))
    if key in _generating:
        return
    _generating.add(key)
    asyncio.create_task(_generate_and_emit(world_id, room_id, room_seed))


async def _generate_and_emit(world_id: str, room_id: str, room_seed: str) -> None:
    """Run image gen under the GPU arbiter, then append room_image_ready.
    On ComfyUI failure, emit room_image_ready with image_url=None and the
    error string so the SPA can fall back to the placeholder."""
    payload: dict = {}
    try:
        async with arbiter.acquire():
            await image_client.generate_room_background(
                world_id, room_id, room_seed, prompt_suffix=WHIMSY_PROMPT_SUFFIX
            )
        payload["image_url"] = image_cache.cache_url(world_id, room_id, room_seed)
    except image_client.ComfyUIError as e:
        logger.warning("room image gen failed for %s/%s: %s", world_id, room_id, e)
        payload["image_url"] = None
        payload["error"] = str(e)
    except Exception as e:  # broad catch: this runs as a fire-and-forget task
        logger.exception("unexpected error in room image gen for %s/%s", world_id, room_id)
        payload["image_url"] = None
        payload["error"] = f"unexpected error: {e}"
    finally:
        _generating.discard((world_id, room_id, image_cache.seed_hash(room_seed)))
    try:
        events.append("system", None, "room_image_ready", payload, room_id=room_id)
    except RuntimeError:
        # DB closed (server shutting down). Drop the event silently.
        pass


def reset_in_flight() -> None:
    """Test helper: clear the in-flight generation set."""
    _generating.clear()


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
        # Kick off image gen for the current room if the cache is cold.
        # Fire-and-forget; the resulting room_image_ready event reaches the
        # client through the broadcast loop below.
        room = rooms.get_room(HUMAN_ROOM_ID)
        if room is not None:
            _maybe_enqueue_image_gen(room.world_id, room.id, room.seed)
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
