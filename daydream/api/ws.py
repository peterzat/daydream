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

v1's toon-slot-management replaced the v0 hardcoded Wren-as-player
assumption with a session-resolved controlled toon (see
`daydream/api/slots.py`). When a session has claimed a slot, that
toon is the actor for input dispatch and the room-filter anchor for
the broadcast loop. Sessions that haven't claimed a slot fall through
to the legacy default `t-wren` so existing tests + the single-session
flow keep working."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from daydream import events, items, rooms, toons
from daydream.api import auth
from daydream.gpu import arbiter
from daydream.images import cache as image_cache
from daydream.images import client as image_client
from daydream.skills import data as data_skills
from daydream.skills import interpreter, registry

logger = logging.getLogger(__name__)
router = APIRouter()

# Legacy default actor when a session hasn't claimed a slot. Single-user
# v1 friend-scope: the seeded Wren toon at slot 1 catches every
# unclaimed session. Removed in v2 multi-user-shared-world (multiple
# sessions can't share one default toon).
LEGACY_TOON_ID = "t-wren"
# Event kinds emitted by `daydream.skills.effects` allowlist handlers
# that mutate observable room state. When one of these reaches the
# broadcast loop, the WS layer pushes a fresh state_snapshot so the
# SPA's items/toons panels reflect the change without the player
# having to navigate away and back. Keep in sync with effects.ALLOWED_KINDS
# minus the pure-narrative kinds (narrate changes no observable
# panel state beyond the event log itself).
_EFFECT_MUTATION_KINDS = frozenset({"item_added", "mood_set"})
# Starting room for the seeded toon; also the fallback used if the toon
# somehow has a NULL current_room_id. After multi-room-navigation lands
# the session's room is read dynamically via _current_room_id() per input
# so a player can walk around.
DEFAULT_ROOM_ID = "r-meadow"
SNAPSHOT_HISTORY_DEPTH = 50


def _resolve_controlled_toon_id(session_id: str | None) -> str:
    """Return the toon id this session controls. Looks up the toons
    table for a row with matching `controller_session` (set by the
    slot picker's create / claim endpoints); falls back to
    `LEGACY_TOON_ID` when no row matches. The fallback covers
    sessions that haven't claimed a slot (legacy single-user flow,
    test fixtures that don't go through the slot picker, the WS
    connection from a freshly-authed session before its first
    slot interaction)."""
    if session_id:
        t = toons.get_toon_by_session(session_id)
        if t is not None:
            return t.id
    return LEGACY_TOON_ID


def _current_room_id(toon_id: str) -> str:
    """Authoritative 'where is the controlled toon right now' for the
    given toon. Reads from DB on each call; the room flips as the
    player moves. Falls back to DEFAULT_ROOM_ID only if the toon has
    no current_room_id (programming bug, not a normal state)."""
    t = toons.get_toon(toon_id)
    if t is None or t.current_room_id is None:
        return DEFAULT_ROOM_ID
    return t.current_room_id

# Per-room generation dedup. Keys are returned by image_client.target_dedup_key
# (world_id, target_kind, target_id, combined_hash). Set membership check +
# add is atomic under asyncio's cooperative model as long as no `await`
# sits between them.
_generating: set[tuple[str, str, str, str]] = set()


def _room_target(world_id: str, room_id: str, room_seed: str) -> "image_client.PersistentTarget":
    """Build the canonical PersistentTarget for a room background. One
    helper so the prompt_suffix / target_kind never drift between the
    is_cached check, the dedup key, and the actual generate call."""
    return image_client.PersistentTarget(
        world_id=world_id,
        target_kind="room",
        target_id=room_id,
        seed=room_seed,
        prompt_suffix=image_client.WHIMSY_PROMPT_SUFFIX,
    )


def _state_snapshot(last_seq: int, toon_id: str) -> dict:
    """Build a snapshot pinned to the given last_seq. Caller subscribes first
    (so concurrent appends fan out to this connection's queue), then captures
    last_seq, then calls this; any queued events with seq <= last_seq are
    drained as duplicates of what the snapshot already contains.

    Room is resolved dynamically from the controlled toon's
    current_room_id so that post-move snapshots reflect the new room
    without the caller having to pass the id in."""
    room_id = _current_room_id(toon_id)
    room = rooms.get_room(room_id)
    items_in = items.get_items_in_room(room_id)
    toons_in = toons.get_toons_in_room(room_id)
    recent = events.fetch_since(
        max(0, last_seq - SNAPSHOT_HISTORY_DEPTH), room_id=room_id
    )
    available = registry.list_available_for_room(room_id)

    image_url: str | None = None
    if room is not None:
        target = _room_target(room.world_id, room.id, room.seed)
        if image_client.is_persistent_cached(target):
            workflow = image_client.load_workflow()
            image_url = image_cache.cache_url(
                room.world_id, "room", room.id, room.seed, workflow
            )

    return {
        "kind": "state_snapshot",
        "room": (
            {
                "id": room.id,
                "slug": room.slug,
                "title": room.title,
                "description": room.description_cached,
                # exits is the SPA's source of truth for nav buttons;
                # room.exits is the parsed dict shape of exits_json
                # (migration 004 populates it bidirectionally).
                "exits": room.exits,
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
    Idempotent across concurrent connections: dedup keyed on the cache
    combined_hash (which factors in seed + workflow JSON)."""
    target = _room_target(world_id, room_id, room_seed)
    if image_client.is_persistent_cached(target):
        return
    key = image_client.target_dedup_key(target)
    if key in _generating:
        return
    _generating.add(key)
    asyncio.create_task(_generate_and_emit(target, key))


async def _generate_and_emit(
    target: "image_client.PersistentTarget",
    dedup_key: tuple[str, str, str, str],
) -> None:
    """Run image gen under the GPU arbiter, then append room_image_ready.
    On ComfyUI failure, emit room_image_ready with image_url=None and the
    error string so the SPA can fall back to the placeholder."""
    payload: dict = {}
    try:
        async with arbiter.acquire():
            path = await image_client.generate_image(target)
        payload["image_url"] = image_cache.url_for_cache_path(path)
    except image_client.ComfyUIError as e:
        logger.warning(
            "room image gen failed for %s/%s: %s",
            target.world_id, target.target_id, e,
        )
        payload["image_url"] = None
        payload["error"] = str(e)
    except Exception as e:  # broad catch: this runs as a fire-and-forget task
        logger.exception(
            "unexpected error in room image gen for %s/%s",
            target.world_id, target.target_id,
        )
        payload["image_url"] = None
        payload["error"] = f"unexpected error: {e}"
    finally:
        _generating.discard(dedup_key)
    try:
        events.append(
            "system", None, "room_image_ready", payload, room_id=target.target_id,
        )
    except RuntimeError:
        # DB closed (server shutting down). Drop the event silently.
        pass


def reset_in_flight() -> None:
    """Test helper: clear the in-flight generation set."""
    _generating.clear()


def _emit_npc_presence_narrates(controlled_toon_id: str, room_id: str) -> None:
    """Emit one narrate per co-located NPC with non-empty presence_text.

    Called from the broadcast loop's controlled-move branch after the
    post-move state_snapshot has been sent, so the narrates land in
    chat-log order AFTER the move event + snapshot pair. Three filters:
    the controlled toon is skipped (self-greeting is meaningless);
    toons with NULL / empty / whitespace-only `presence_text` are
    skipped silently (authoring a greeting is optional per toon);
    kicked toons are already excluded by `get_toons_in_room`.

    Events are appended via events.append; they flow back through the
    same broadcast loop's queue and reach the client as normal
    `narrate` event frames. Not called on initial connect (the
    snapshot's events field already carries prior narrates on
    reconnect, so firing fresh would duplicate on the chat log) nor
    on effect-mutation snapshot refreshes (which would spam the log
    during data-skill dispatch in a populated room). See SPEC
    2026-04-24 criterion 3."""
    for t in toons.get_toons_in_room(room_id):
        if t.id == controlled_toon_id:
            continue
        greeting = (t.presence_text or "").strip()
        if not greeting:
            continue
        events.append(
            "system", None, "narrate",
            {"text": greeting},
            room_id=room_id,
        )


async def _handle_input(text: str, toon_id: str) -> None:
    """Route player input. Canonical form (skill word + args) bypasses the LLM
    so button clicks and exact commands don't pay round-trip latency.

    Each invocation re-reads the toon's current room so the routing
    applies to where the player is NOW, not where they were when the
    connection opened. `toon_id` is resolved once at connect time
    (`_resolve_controlled_toon_id`) and threaded through here."""
    text = text.strip()
    if not text:
        return
    parts = text.split(None, 1)
    head = parts[0].lower()
    room_id = _current_room_id(toon_id)
    # Use the room-filtered candidate list for BOTH the canonical bypass
    # and the interpreter fallback, so a data skill whose context
    # predicate hides it in the current room does not dispatch when the
    # player types its name. Core skills always pass the filter (they
    # have no predicate); this only affects data skills.
    available = registry.list_available_for_room(room_id)
    available_by_name = {s.name: s for s in available}
    spec = available_by_name.get(head)
    if spec is not None:
        rest = parts[1] if len(parts) > 1 else ""
        await _dispatch_spec(spec, toon_id, room_id, rest)
        return
    decision = await interpreter.interpret(text, available)
    if decision.skill == "none":
        if decision.error:
            out = "The dream is foggy right now; that thought slips away."
        else:
            out = f"You think to yourself: \"{text}\". The daydream answers softly."
        events.append("system", None, "narrate", {"text": out}, room_id=room_id)
        return
    spec = available_by_name.get(decision.skill)
    if spec is None:
        return  # race: skill was disabled between interpret and dispatch
    await _dispatch_spec(spec, toon_id, room_id, decision.args)


async def _dispatch_spec(
    spec: "registry.SkillSpec", actor_id: str, room_id: str, args: str
) -> None:
    """Dispatch a resolved SkillSpec. Core skills run synchronously
    through the registry; data skills run through the async
    safety + LLM + effects pipeline in daydream.skills.data."""
    if spec.kind == "core":
        registry.execute(spec.name, actor_id, room_id, args)
        return
    await data_skills.execute_by_name(spec.name, actor_id, room_id, args)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    session = ws.scope.get("session", {})
    if not auth.is_authed(session):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    # Resolve the controlled toon for this connection. Slot picker's
    # create / claim endpoints set controller_session = <session id>;
    # an unclaimed session falls through to LEGACY_TOON_ID.
    session_id = session.get("id") if isinstance(session, dict) else None
    toon_id = _resolve_controlled_toon_id(session_id)
    await ws.accept()
    # Subscribe before snapshot so any events that land while we yield to send
    # the snapshot are captured in the queue; pin last_seq here, then drop any
    # queued events with seq <= last_seq before the broadcast loop starts.
    queue = events.subscribe()
    try:
        last_seq = events.max_seq()
        await ws.send_json(_state_snapshot(last_seq, toon_id))
        # Kick off image gen for the current room if the cache is cold.
        # Fire-and-forget; the resulting room_image_ready event reaches the
        # client through the broadcast loop below.
        room = rooms.get_room(_current_room_id(toon_id))
        if room is not None:
            _maybe_enqueue_image_gen(room.world_id, room.id, room.seed)
        receive_task = asyncio.create_task(_receive_loop(ws, toon_id))
        broadcast_task = asyncio.create_task(
            _broadcast_loop(ws, queue, last_seq, toon_id)
        )
        done, pending = await asyncio.wait(
            [receive_task, broadcast_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        events.unsubscribe(queue)


async def _receive_loop(ws: WebSocket, toon_id: str) -> None:
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("kind") == "input":
                await _handle_input(str(msg.get("text", "")), toon_id)
    except WebSocketDisconnect:
        pass


async def _broadcast_loop(
    ws: WebSocket, queue: asyncio.Queue, snapshot_seq: int, toon_id: str
) -> None:
    try:
        while True:
            event = await queue.get()
            # Out-of-band control signal: an in-process world hot-swap
            # replaced the live DB. Re-snapshot this connection against the
            # now-live world and tell the client. Identity check runs before
            # any `.seq` access (the sentinel is not an Event).
            if event is events.WORLD_CHANGED:
                snapshot_seq = events.max_seq()
                await ws.send_json({"kind": "world_changed"})
                await ws.send_json(_state_snapshot(snapshot_seq, toon_id))
                continue
            # Drop events already covered by the snapshot to avoid duplicates
            # from the subscribe-before-snapshot ordering.
            if event.seq <= snapshot_seq:
                continue
            # Room filter follows the player: events in rooms the toon is
            # NOT currently in get dropped. The toon's own events always
            # pass — a move event has room_id=<departure>, which wouldn't
            # match current_room after the move otherwise, and the client
            # would never learn it moved.
            own_event = event.actor_id == toon_id
            if not own_event and event.room_id is not None:
                if event.room_id != _current_room_id(toon_id):
                    continue
            await ws.send_json({"kind": "event", "event": event.to_dict()})
            # After a mutation of observable room state, push a fresh
            # snapshot so the client's items / toons / exits / image
            # panel reflect the new truth. `move` covers controlled-toon
            # navigation; `item_added` and `mood_set` cover data-skill
            # effects (emitted by daydream.skills.effects). Without this,
            # an authored skill that adds an item leaves the items panel
            # stale until the next manual snapshot trigger. Advance
            # snapshot_seq so any events already queued for the new state
            # aren't dropped as "covered by snapshot" when they weren't.
            is_controlled_move = event.kind == "move" and event.actor_id == toon_id
            is_effect_mutation = event.kind in _EFFECT_MUTATION_KINDS
            if is_controlled_move or is_effect_mutation:
                snapshot_seq = events.max_seq()
                await ws.send_json(_state_snapshot(snapshot_seq, toon_id))
                if is_controlled_move:
                    # Kick image gen for the new room if the cache is cold;
                    # the room_image_ready event flows back through this
                    # same loop.
                    new_room = rooms.get_room(_current_room_id(toon_id))
                    if new_room is not None:
                        _maybe_enqueue_image_gen(
                            new_room.world_id, new_room.id, new_room.seed
                        )
                    # Greet any co-located NPCs (SPEC 2026-04-24). This
                    # is inside the controlled-move branch only, not
                    # the effect-mutation branch, so dispatching a
                    # data skill at r-forge doesn't re-greet Rook on
                    # every snapshot refresh.
                    _emit_npc_presence_narrates(toon_id, _current_room_id(toon_id))
    except (WebSocketDisconnect, RuntimeError):
        pass
