"""Websocket endpoint and protocol.

Protocol:
- Server -> client on connect:  {kind: "state_snapshot", room, items, toons,
  inventory, skills, verb_bar, entities, events, last_seq}
- Server -> client per change:  {kind: "event", event: {...}}
- Client -> server, two producers (objects + verbs, 2026-06-30):
  - {kind: "command", verb, dobj_id?, iobj_id?, args?} — the CLICK path; goes
    straight to `verbs.execute_command` with NO parser/LLM call.
  - {kind: "input", text} — free text, routed through the grounded command
    parser (`daydream.parser`): a deterministic fast-path (exit directions,
    bare verbs, "verb <name>", legacy data-skill names) makes no LLM call;
    otherwise one local-LLM call grounds the text to a closed verb + in-scope
    object id, then `execute_command` runs it. A room-affordance data skill
    runs the data pipeline; `none` / LLM-outage degrade to a gentle narration.

Toon-slot-management resolves the controlled toon per session (see
`daydream/api/slots.py`); a session that controls no toon (fresh connect,
after "leave the dream", or a kicked/deleted toon) is routed to the character
picker via a `needs_toon` frame — picker-first entry (SPEC 2026-06-30). There
is no default-toon fallback: an unresolved session never silently controls an
arbitrary toon."""

import asyncio
import logging
from collections import Counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from daydream import events, objects, parser, rooms, toons, verbs, version
from daydream.api import auth
from daydream.gpu import arbiter
from daydream.images import cache as image_cache
from daydream.images import client as image_client
from daydream.skills import data as data_skills
from daydream.skills import registry

logger = logging.getLogger(__name__)
router = APIRouter()

# Event kinds emitted by `daydream.skills.effects` allowlist handlers
# that mutate observable room state. When one of these reaches the
# broadcast loop, the WS layer pushes a fresh state_snapshot so the
# SPA's scene/inventory panels reflect the change without the player
# having to navigate away and back. `object_moved` covers take/drop,
# `object_spawned` covers generative spawns; `item_added`/`mood_set`
# are the legacy add_item/set_mood aliases. `property_set` is omitted:
# its dominant use (lazy-cache examine text) changes no visible panel.
_EFFECT_MUTATION_KINDS = frozenset(
    {"item_added", "mood_set", "object_moved", "object_spawned"}
)
# Starting room for the seeded toon; also the fallback used if the toon
# somehow has a NULL current_room_id. After multi-room-navigation lands
# the session's room is read dynamically via _current_room_id() per input
# so a player can walk around.
DEFAULT_ROOM_ID = "r-meadow"
SNAPSHOT_HISTORY_DEPTH = 50

# Sentinel for _state_snapshot's resume_since: replay the room's recent history
# (the default, used by move/effect re-snapshots). None = a fresh session
# (empty log); an int = resume from that seq (a reconnect).
_REPLAY_RECENT = object()


def _resolve_controlled_toon_id(session_id: str | None) -> str | None:
    """Return the toon id this session controls, or None if it controls none.

    A match requires a toons row whose `controller_session` equals
    `session_id` (set by the slot picker's create / claim endpoints) that is
    not kicked and is human-controlled (`toons.get_toon_by_session`). A None
    return routes the connection to the character picker (a `needs_toon`
    frame) rather than auto-controlling a default toon: picker-first entry
    (SPEC 2026-06-30) removed the legacy `t-wren` fallback, which silently
    resolved every unclaimed session to a single seeded toon and, in a
    `world load`ed world (uuid'd ids, no literal `t-wren`), to a phantom
    that no-op'd every input."""
    if session_id:
        t = toons.get_toon_by_session(session_id)
        if t is not None:
            return t.id
    return None


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


def _room_description(room: "rooms.Room", view: dict | None) -> str:
    """Description text for a snapshot's room view. With no per-connection
    `view` (e.g. a direct call) it is the full stored description, as before.
    With a view it is the FULL stored description the first time the session
    enters the room, and a short "you return to ..." line on re-entry —
    decided at entry and sticky for the duration of the visit so effect
    re-snapshots don't shrink it. The first-look text is pre-baked stored
    content (`rooms.description_cached`), never a live LLM call (per the
    generation policy)."""
    full = room.description_cached or f"You are in {room.title}."
    if view is None:
        return full
    if view.get("room_id") != room.id:
        view["room_id"] = room.id
        view["first_visit"] = room.id not in view["visited"]
        view["visited"].add(room.id)
    return full if view["first_visit"] else f"You return to {room.title}."


def _state_snapshot(
    last_seq: int, toon_id: str, view: dict | None = None, resume_since=_REPLAY_RECENT
) -> dict:
    """Build a snapshot pinned to the given last_seq. Caller subscribes first
    (so concurrent appends fan out to this connection's queue), then captures
    last_seq, then calls this; any queued events with seq <= last_seq are
    drained as duplicates of what the snapshot already contains.

    Room is resolved dynamically from the controlled toon's
    current_room_id so that post-move snapshots reflect the new room
    without the caller having to pass the id in."""
    room_id = _current_room_id(toon_id)
    room = rooms.get_room(room_id)
    things_in = objects.contents(room_id, kind="thing")
    inventory_in = objects.contents(toon_id, kind="thing")
    toons_in = toons.get_toons_in_room(room_id)
    # The controlled toon's own identity, so the SPA can render WHO YOU ARE
    # distinctly and separate it from WHO ELSE IS HERE. It is also in `toons`
    # (all co-located toons) for back-compat; the client filters it out there.
    self_toon = next((t for t in toons_in if t.id == toon_id), None) or toons.get_toon(toon_id)
    if resume_since is _REPLAY_RECENT:
        # Move / effect re-snapshots: the room's recent history.
        recent = events.fetch_since(
            max(0, last_seq - SNAPSHOT_HISTORY_DEPTH), room_id=room_id
        )
    elif resume_since is None:
        recent = []  # fresh session: empty log, only new events stream in
    else:
        recent = events.fetch_since(resume_since, room_id=room_id)  # reconnect resume
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
                "description": _room_description(room, view),
                # exits is the SPA's source of truth for nav buttons;
                # room.exits is the parsed dict shape of exits_json
                # (migration 004 populates it bidirectionally).
                "exits": room.exits,
                "image_url": image_url,
            }
            if room
            else None
        ),
        # Scene objects carry their verb affordances so the SPA can render
        # them as distinct, clickable elements (id + kind + verbs). `items`
        # (room things) were previously sent but never rendered; `inventory`
        # is the actor's carried things.
        "items": [_object_card(o) for o in things_in],
        "toons": [_toon_card(t) for t in toons_in],
        # WHO YOU ARE: the controlled toon, named explicitly so the SPA never
        # has to guess which co-located toon is the player.
        "self": _toon_card(self_toon) if self_toon is not None else None,
        "inventory": [_object_card(o) for o in inventory_in],
        "skills": [{"name": s.name, "ui_hint": s.ui_hint, "kind": s.kind} for s in available],
        # The verb bar (Examine / Take / Drop / Talk) — verb-then-object.
        "verb_bar": [{"name": v.name, "ui_hint": v.ui_hint} for v in verbs.bar_verbs()],
        # Entity sidecar: in-scope names/aliases -> object ids, so the client
        # can wrap object mentions in narration as clickable spans.
        "entities": _entity_sidecar(toon_id),
        "events": [e.to_dict() for e in recent],
        "last_seq": last_seq,
        # Build + world version so the client can detect a redeploy (a stale
        # open tab still running the OLD main.js — a WS reconnect never reloads
        # page JS) and reload itself. The snapshot already re-flows on every
        # move / effect / swap, so this rides it; no separate control frame.
        "build": version.build_sha(),
        "world_version": version.WORLD_VERSION,
    }


def _object_card(o: "objects.Object") -> dict:
    """A scene object as the SPA needs it: id + kind + name + verb affordances
    (and aliases, for client-side narration linking)."""
    return {
        "id": o.id,
        "name": o.name,
        "kind": o.kind,
        "aliases": o.aliases,
        "verbs": objects.verbs_for(o),
    }


def _toon_card(t: "toons.Toon") -> dict:
    obj = objects.get(t.id)
    return {
        "id": t.id,
        "name": t.name,
        "mood": t.mood,
        "kind": "toon",
        "verbs": objects.verbs_for(obj) if obj is not None else [],
    }


def _entity_sidecar(actor_id: str) -> list[dict]:
    """In-scope objects' names + aliases mapped to their ids, for wrapping
    object mentions in narration as clickable spans. The actor, rooms, and
    prototypes are excluded (you don't click-to-act on yourself or the room)."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for o in objects.in_scope(actor_id):
        if o.id == actor_id or o.kind in ("prototype", "room"):
            continue
        for alias in [o.name, *o.aliases]:
            if not isinstance(alias, str) or not alias.strip():
                continue
            key = (alias.lower(), o.id)
            if key in seen:
                continue
            seen.add(key)
            out.append({"alias": alias, "object_id": o.id, "kind": o.kind})
    return out


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
    """Route free-text player input through the grounded command parser.

    The parser's deterministic fast-path (exit directions, bare verbs, "verb
    <name>", legacy data-skill names) resolves without an LLM call; natural
    phrasings ("say hi to rook") are grounded by one local-LLM call. A grounded
    closed verb dispatches through the verb command bus; a room-affordance data
    skill runs the data pipeline; `none` / LLM-outage degrade gracefully.

    Each invocation re-reads the toon's current room (via the parser/scope) so
    routing applies to where the player is NOW. `toon_id` is resolved once at
    connect time and threaded through."""
    text = text.strip()
    if not text:
        return
    room_id = _current_room_id(toon_id)
    p = await parser.parse(toon_id, text)
    if p.error:
        # LLM unavailable: natural-language free text can't be parsed. The
        # deterministic click/exit verbs still work (the command frame + the
        # parser fast-path), but this open-text input degrades to "foggy".
        events.append(
            "system", None, "narrate",
            {"text": "The dream is foggy right now; that thought slips away."},
            room_id=room_id,
        )
        return
    if p.verb == "none":
        events.append(
            "system", None, "narrate",
            {"text": f"You think to yourself: \"{text}\". The daydream answers softly."},
            room_id=room_id,
        )
        return
    if p.verb in verbs.VERBS:
        await verbs.execute_command(
            toon_id, p.verb, p.dobj_id, p.iobj_id, p.args, dobj_name=p.dobj_name
        )
        return
    # A room-affordance data skill (e.g. forge) selected as a verb: run the
    # existing safety + LLM + effects pipeline.
    spec = registry.find(p.verb)
    if spec is not None and spec.kind == "data":
        await data_skills.execute_by_name(p.verb, toon_id, room_id, p.args)
        return
    events.append(
        "system", None, "narrate",
        {"text": f"You think to yourself: \"{text}\". The daydream answers softly."},
        room_id=room_id,
    )


# Per-session COUNT of live WS connections controlling a toon, maintained by the
# handler (incremented on connect, decremented on disconnect). The slot-claim
# path reads this so a player can adopt a toon whose controlling session is gone
# (an abandoned claim) while a toon an ACTIVE player holds stays protected. A
# count (not a set) so a session with two tabs stays live until BOTH close.
_live_session_counts: "Counter[str]" = Counter()


def _mark_session_live(session_id: str | None) -> None:
    if session_id:
        _live_session_counts[session_id] += 1


def _unmark_session_live(session_id: str | None) -> None:
    if not session_id:
        return
    remaining = _live_session_counts.get(session_id, 0) - 1
    if remaining > 0:
        _live_session_counts[session_id] = remaining
    else:
        _live_session_counts.pop(session_id, None)  # drop zero-count keys


def is_session_live(session_id: str | None) -> bool:
    """True if `session_id` currently has at least one live WS connection
    controlling a toon. Used by the slot-claim takeover logic
    (daydream/api/slots.py)."""
    return bool(session_id) and _live_session_counts.get(session_id, 0) > 0


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    session = ws.scope.get("session", {})
    if not auth.is_authed(session):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    # Resolve the controlled toon for this connection. Slot picker's
    # create / claim endpoints set controller_session = <session id>.
    session_id = session.get("id") if isinstance(session, dict) else None
    toon_id = _resolve_controlled_toon_id(session_id)
    if toon_id is None:
        # No claimed/controllable toon (a fresh connect, a session that left
        # the dream, or one whose toon was kicked/deleted): route to the
        # character picker instead of auto-controlling a default toon
        # (picker-first entry, SPEC 2026-06-30). This subsumes the prior
        # `left`-flag branch — leaving the dream rests the toon, so it
        # resolves to None here.
        await ws.accept()
        await ws.send_json({"kind": "needs_toon"})
        return
    await ws.accept()
    # Subscribe before snapshot so any events that land while we yield to send
    # the snapshot are captured in the queue; pin last_seq here, then drop any
    # queued events with seq <= last_seq before the broadcast loop starts.
    queue = events.subscribe()
    # Per-connection room-view memory: which rooms this session has entered
    # (drives full-vs-abbreviated room descriptions) plus the current room and
    # its first-visit verdict (sticky so mid-visit re-snapshots don't shrink).
    view = {"visited": set(), "room_id": None, "first_visit": True}
    # A fresh page load omits `since` and starts with an empty event log; a
    # reconnect sends its last-rendered seq and resumes from there.
    since_raw = ws.query_params.get("since")
    resume_since: int | None = None
    if since_raw is not None:
        try:
            resume_since = int(since_raw)
        except ValueError:
            resume_since = None
    try:
        _mark_session_live(session_id)
        last_seq = events.max_seq()
        await ws.send_json(_state_snapshot(last_seq, toon_id, view, resume_since))
        # Kick off image gen for the current room if the cache is cold.
        # Fire-and-forget; the resulting room_image_ready event reaches the
        # client through the broadcast loop below.
        room = rooms.get_room(_current_room_id(toon_id))
        if room is not None:
            _maybe_enqueue_image_gen(room.world_id, room.id, room.seed)
        receive_task = asyncio.create_task(_receive_loop(ws, toon_id))
        broadcast_task = asyncio.create_task(
            _broadcast_loop(ws, queue, last_seq, toon_id, view)
        )
        done, pending = await asyncio.wait(
            [receive_task, broadcast_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        _unmark_session_live(session_id)
        events.unsubscribe(queue)


async def _handle_command(msg: dict, toon_id: str) -> None:
    """Execute a structured UI command frame `{kind:"command", verb, dobj_id?,
    iobj_id?, args?}`. This is the click path: it bypasses the parser entirely,
    so it makes NO LLM call (the verb's own handler may, e.g. `talk`). The same
    `execute_command` serves the parsed-free-text path."""
    verb = str(msg.get("verb", "")).strip()
    if not verb:
        return
    dobj_id = msg.get("dobj_id")
    iobj_id = msg.get("iobj_id")
    await verbs.execute_command(
        toon_id,
        verb,
        dobj_id=dobj_id if isinstance(dobj_id, str) else None,
        iobj_id=iobj_id if isinstance(iobj_id, str) else None,
        args=str(msg.get("args", "")),
    )


async def _receive_loop(ws: WebSocket, toon_id: str) -> None:
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("kind")
            if kind == "input":
                await _handle_input(str(msg.get("text", "")), toon_id)
            elif kind == "command":
                await _handle_command(msg, toon_id)
    except WebSocketDisconnect:
        pass


async def _broadcast_loop(
    ws: WebSocket, queue: asyncio.Queue, snapshot_seq: int, toon_id: str, view: dict
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
                await ws.send_json(_state_snapshot(snapshot_seq, toon_id, view))
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
                await ws.send_json(_state_snapshot(snapshot_seq, toon_id, view))
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
