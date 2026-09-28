"""Toons and who may hold them: "your dreamer" for players, the slot view for
admins (SPEC 2026-09-27 criterion 5; SPEC 2026-05-07 for the slot model).

A human toon belongs to one account (`owner_account`, migration 018):

- **Players.** A player account may create one toon per world and may enter,
  rest (kick) or delete only its own. It may adopt an unowned toon (a seeded
  or pre-accounts one) when it has none.
- **Admins.** An admin account may hold several toons. It acts on another
  account's toon only from the CLI (`bin/game world rest-toon|delete-toon`):
  a stolen admin cookie cannot touch a friend's dreamer (SECURITY WARN
  2026-09-27; SPEC criterion 4's "exactly three" admin extras).
- **Another tab.** Opening the game in a second tab or device of the same
  account takes control; the earlier socket is told quietly (daydream/api/ws.py).

Endpoints:

- `GET /api/dreamer`: the caller's own toons plus whether they may create
  one (the SPA's "your dreamer" panel).
- `POST /api/dreamer/create`: make the caller's toon in the next free slot.
- `GET /api/slots`: every populated human slot. Admins only.
- `POST /api/slots/{slot}/create|claim|kick|delete`: slot-addressed forms,
  kept for tools and tests. Same ownership rules.
- `POST /api/session/leave`: rest this session's toon and write its journal.

Errors are JSON `{"detail": "<reason>"}` with the documented status codes.
"""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException, Request

from daydream import accounts, instance, journal, toons
from daydream.api import auth as auth_mod
from daydream.images import client as image_client
from daydream.llm import safety

router = APIRouter()

# appearance_seed is rendered through SDXL into portraits shown to
# co-located players, so player input gets the same gates as the growth
# phrase (length cap + WHIMSY input banlist). Loader-authored NPC seeds are
# design-time and do not pass through here.
MAX_APPEARANCE_SEED_CHARS = 300

# Moderation names a toon by id, so a name must not pass for one (codereview
# WARN 2026-09-28b): no brackets, no id-shaped run, no player toon's id.
# Residents (slots 100+) are never moderated, and their short ids (`t-fen`)
# sit inside ordinary names ("Matt-Fenwick"), so they are not scanned.
_TOON_ID_SHAPE = re.compile(r"t-slot\d+-[0-9a-f]{8}", re.IGNORECASE)


def _mimics_a_toon_id(name: str) -> bool:
    if "[" in name or "]" in name or _TOON_ID_SHAPE.search(name):
        return True
    low = name.lower()
    players = toons._query("world_id = ? AND slot BETWEEN 1 AND 99", (toons.live_world_id(),))
    return any(t.id.lower() in low for t in players)


# How long after a controller's last WS drop an UNOWNED toon it holds stays
# protected from another account's delete. (Owned toons are protected by
# ownership outright.)
DELETE_GRACE_SECONDS = 120.0


def _require_authed(request: Request) -> accounts.Principal:
    """The signed-in person, or 401. The gate middleware already refuses an
    unauthenticated request; this keeps every endpoint explicit."""
    who = auth_mod.principal(request)
    if who is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return who


def _session_id(request: Request) -> str:
    return _require_authed(request).session_id


def _validate_slot(slot: int) -> None:
    if slot not in toons.HUMAN_SLOT_RANGE:
        raise HTTPException(status_code=404, detail="slot out of range")


def _portrait(t: toons.Toon) -> str | None:
    """Cached-only by contract: listing toons NEVER triggers a render."""
    return image_client.cached_portrait_url(toons.live_world_id(), t.id, t.appearance_seed)


def _may_hold_another(who: accounts.Principal) -> bool:
    return who.is_admin or not toons.owned_toons(who.account_id)


def _require_actionable(t: toons.Toon, who: accounts.Principal, *, for_delete: bool = False) -> None:
    """Ownership gate for kick/delete. A toon owned by another account is off
    limits to a player (403). An unowned toon keeps the old liveness rule:
    refuse only while another session is live on it (for delete, within
    DELETE_GRACE_SECONDS of its last drop, since deletion is irreversible)."""
    if t.owner_account == who.account_id:
        return
    if t.owner_account is not None:
        raise HTTPException(status_code=403, detail="that dreamer belongs to someone else")
    from daydream.api import ws as ws_mod

    controller = t.controller_session
    present = (ws_mod.is_session_recently_live(controller, DELETE_GRACE_SECONDS) if for_delete
               else ws_mod.is_session_live(controller))
    if (t.is_human_controlled and t.kicked_at is None and controller is not None
            and controller != who.session_id and present):
        raise HTTPException(status_code=403, detail="slot is held by another active player")


async def _toon_request(request: Request) -> tuple[str, str]:
    """Validate a create body; returns (name, appearance_seed)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="body must be JSON") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    name = body.get("name")
    appearance = body.get("appearance_seed")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="name must be a non-empty string")
    if len(name.strip()) > toons.MAX_NAME_CHARS or not name.strip().isprintable():
        raise HTTPException(status_code=400, detail=(
            f"name must be at most {toons.MAX_NAME_CHARS} characters on one line"))
    if safety.first_banned(name) is not None:
        raise HTTPException(status_code=400, detail="name doesn't fit the dream's tone")
    if _mimics_a_toon_id(name):
        raise HTTPException(status_code=400, detail="name can't use brackets or a dreamer's id")
    if not isinstance(appearance, str) or not appearance.strip():
        raise HTTPException(status_code=400, detail="appearance_seed must be a non-empty string")
    appearance = appearance.strip()
    if len(appearance) > MAX_APPEARANCE_SEED_CHARS:
        raise HTTPException(status_code=400, detail=(
            f"appearance_seed must be at most {MAX_APPEARANCE_SEED_CHARS} characters"))
    if safety.first_banned(appearance) is not None:
        raise HTTPException(status_code=400, detail="appearance_seed doesn't fit the dream's tone")
    return name.strip(), appearance


logger = logging.getLogger(__name__)

# Each new dreamer paints a portrait on the shared GPU, so making and letting
# go of dreamers in a loop could keep the card from everyone else. A player
# makes at most this many a day (the operator's admin accounts are exempt).
DREAMERS_PER_DAY = (6, 24 * 60 * 60)


def _create(slot: int, name: str, appearance: str, who: accounts.Principal) -> dict:
    if not _may_hold_another(who):
        raise HTTPException(status_code=409, detail="you already have a dreamer here")
    budget_key = f"dreamer-create:{who.account_id}"
    if not who.is_admin and accounts.throttled(budget_key, DREAMERS_PER_DAY):
        logger.warning("dreamer made too often: %s", who.username)
        raise HTTPException(status_code=429,
                            detail="you have made several dreamers today; try again tomorrow")
    new_toon = toons.create_toon_in_slot(slot, name, appearance, who.session_id,
                                         owner_account=who.account_id)
    if new_toon is None:
        raise HTTPException(status_code=409, detail="slot already populated")
    accounts.set_left(who.session_id, False)  # picking a toon re-enters the dream
    if not who.is_admin:
        accounts.record_failure(budget_key, DREAMERS_PER_DAY)  # counts makes, not failures
    logger.info("dreamer made: %s by %s", new_toon.name, who.username)
    return _toon_to_dict(new_toon, who.session_id)


# ---- your dreamer ---------------------------------------------------------------


@router.get("/api/dreamer")
async def my_dreamer(request: Request) -> dict:
    who = _require_authed(request)
    mine = []
    for t in toons.owned_toons(who.account_id):
        card = toons.toon_card(t, who.session_id)
        card["portrait_url"] = _portrait(t)
        mine.append(card)
    return {"toons": mine,
            "can_create": _may_hold_another(who) and toons.next_free_slot() is not None,
            "display_name": who.display_name, "is_admin": who.is_admin}


@router.post("/api/dreamer/create")
async def create_dreamer(request: Request) -> dict:
    who = _require_authed(request)
    name, appearance = await _toon_request(request)
    slot = toons.next_free_slot()
    if slot is None:
        raise HTTPException(status_code=409, detail=f"{instance.place()} is full just now")
    return _create(slot, name, appearance, who)


# ---- slot-addressed forms (tools, tests, admins) ---------------------------------


@router.get("/api/slots")
async def list_slots(request: Request) -> dict:
    """Every populated human slot, with cached-only portraits. Admins only;
    a player sees their own toons at /api/dreamer."""
    who = _require_authed(request)
    if not who.is_admin:
        raise HTTPException(status_code=403, detail="the slot list is for admins")
    slots = toons.get_human_slots(who.session_id)
    for entry in slots:
        t = toons.get_toon(entry["toon"]["id"])
        entry["toon"]["portrait_url"] = _portrait(t) if t else None
    return {"slots": slots}


@router.post("/api/slots/{slot}/create")
async def create_slot(slot: int, request: Request) -> dict:
    """Create the caller's toon in `slot`. 400 bad body; 404 slot out of
    range; 409 slot populated or the player already has a dreamer here."""
    who = _require_authed(request)
    _validate_slot(slot)
    name, appearance = await _toon_request(request)
    return _create(slot, name, appearance, who)


@router.post("/api/slots/{slot}/claim")
async def claim_slot(slot: int, request: Request) -> dict:
    """Enter as the toon in `slot`. Your own toon: always (a second tab or
    device takes over). An unowned toon: adopted, if you have none and no
    other live session holds it. Another account's toon: 403, admins
    included. 404 empty slot; 409 held by an active player or you already
    have a dreamer."""
    who = _require_authed(request)
    _validate_slot(slot)
    t = toons.get_toon_in_slot(slot)
    if t is None:
        raise HTTPException(status_code=404, detail="slot is empty")
    if t.owner_account not in (None, who.account_id):
        raise HTTPException(status_code=403, detail="that dreamer belongs to someone else")
    if t.owner_account is None and not _may_hold_another(who):
        raise HTTPException(status_code=409, detail="you already have a dreamer here")
    from daydream.api import ws as ws_mod

    own = t.owner_account == who.account_id
    toon, reason = toons.claim_slot(
        slot, who.session_id,
        can_take_over=lambda cs: own or not ws_mod.is_session_live(cs))
    if reason == "empty":
        raise HTTPException(status_code=404, detail="slot is empty")
    if reason == "controlled":
        raise HTTPException(status_code=409, detail="slot is held by an active player; kick first")
    assert toon is not None
    if toon.owner_account is None:
        toons.adopt(toon.id, who.account_id)
        toon = toons.get_toon(toon.id)
        logger.info("dreamer adopted: %s by %s", toon.name, who.username)
    accounts.set_left(who.session_id, False)  # picking a toon re-enters the dream
    logger.info("dreamer entered: %s by %s", toon.name, who.username)
    return _toon_to_dict(toon, who.session_id)


@router.post("/api/slots/{slot}/kick")
async def kick_slot(slot: int, request: Request) -> dict:
    """Rest the toon in `slot` (controller cleared, kicked_at stamped; it
    keeps its room, inventory and memories). Your own only. 404 empty; 403
    someone else's."""
    who = _require_authed(request)
    _validate_slot(slot)
    t = toons.get_toon_in_slot(slot)
    if t is None:
        raise HTTPException(status_code=404, detail="slot is empty")
    _require_actionable(t, who)
    held_here = t.controller_session == who.session_id
    toon = toons.kick_slot(slot)
    if toon is None:
        raise HTTPException(status_code=404, detail="slot is empty")
    if held_here:
        # Resting the toon you are playing is leaving the dream: otherwise the
        # next connect's auto-enter wakes it at once, in the start room.
        accounts.set_left(who.session_id, True)
        _departed(toon)
    logger.info("dreamer rested: %s by %s", toon.name, who.username)
    return _toon_to_dict(toon, who.session_id)


def _departed(t: toons.Toon) -> None:
    """A dreamer leaves: the room sees them go (playtest 2026-09-26: players
    vanished mid-conversation with no line at all), and their journal recap
    is written in the background (fail-closed, never awaited)."""
    if t.current_room_id:
        from daydream import events
        events.append("system", None, "narrate",
                      {"text": f"{t.name} drifts out of the dream for now.", "except": t.id},
                      room_id=t.current_room_id)
    asyncio.create_task(journal.write_entry(t.id))


@router.post("/api/session/leave")
async def leave_session(request: Request) -> dict:
    """Leave the dream: rest this session's controlled toon (if any) and mark
    the session 'left' so the next connect shows "your dreamer" instead of
    walking straight back in. Idempotent.

    Leaving also fires the dream-journal recap for the released toon as a
    fire-and-forget background task (SPEC 2026-07-07 criterion 3):
    journal.write_entry is fail-closed end-to-end, so this endpoint ALWAYS
    succeeds regardless of LLM state and never waits on the write. The WS
    disconnect is deliberately NOT a trigger: the reconnect overlay rides
    out transient drops all the time and would double-write."""
    sid = _session_id(request)
    released = toons.release_session_toon(sid)
    accounts.set_left(sid, True)
    if released is not None:
        who = auth_mod.principal(request)
        logger.info("left the dream: %s (%s)", released.name,
                    who.username if who else "unknown account")
        _departed(released)
    return {"ok": True, "released": released.id if released else None}


@router.post("/api/slots/{slot}/delete")
async def delete_toon(slot: int, request: Request) -> dict:
    """Permanently delete the toon in `slot` (distinct from kick, which rests
    a recoverable toon). Your own only; an unowned toon keeps the delete grace
    window. 404 empty; 403 someone else's."""
    who = _require_authed(request)
    _validate_slot(slot)
    t = toons.get_toon_in_slot(slot)
    if t is None:
        raise HTTPException(status_code=404, detail="slot is empty")
    _require_actionable(t, who, for_delete=True)
    deleted = toons.delete_slot(slot)
    if deleted is None:
        raise HTTPException(status_code=404, detail="slot is empty")
    logger.info("dreamer let go: %s by %s", deleted.name, who.username)
    return {"ok": True, "deleted": deleted.id}


def _toon_to_dict(t: toons.Toon, session_id: str) -> dict:
    return toons.toon_card(t, session_id)
