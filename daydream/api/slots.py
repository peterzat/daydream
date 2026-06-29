"""Slot-picker API: GET /api/slots, POST /api/slots/{slot}/{create|claim|kick}.

Implements the v1 toon-slot-management surface (SPEC 2026-05-07). The
slot system is for HUMAN-controllable toons in slots 1..5 only;
hand-authored NPCs in slots 100+ are excluded from every endpoint.

Auth: AccessMiddleware (loopback / tailnet) is the outer gate; the
endpoints additionally require an authenticated session via the
existing SessionMiddleware machinery (mirrors `/api/login` and
`/api/logout`'s implicit posture). v1 friend-scope: any authed
session can create / claim / kick any slot — multi-user differentiation
lands with v2.

Errors are JSON `{"error": "<reason>"}` bodies with the documented
status codes. The four endpoints share a small `_session_id` helper
that pulls the per-session UUID stamped by `daydream.api.auth.login`."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from daydream import toons
from daydream.api import auth as auth_mod

router = APIRouter()


def _session_id(request: Request) -> str:
    """Return the requester's session UUID, stamping a fresh one if
    missing. The slot endpoints all require a session-bound caller —
    the create endpoint records the session as the controller, claim
    rebinds the toon to the caller, and kick clears whatever session
    held the slot. Stamping on read keeps the client coherent across
    legitimate-but-cookie-less first hits (e.g., a TestClient that
    didn't go through /api/login)."""
    return auth_mod._ensure_session_id(request.session)


def _require_authed(request: Request) -> None:
    """Reject if the caller's session isn't authed. Mirrors the bar
    `/api/logout` and the WS endpoint use; centralized here so all
    four slot endpoints share one gate."""
    if not auth_mod.is_authed(request.session):
        raise HTTPException(status_code=401, detail="not authenticated")


def _validate_slot(slot: int) -> None:
    if slot not in toons.HUMAN_SLOT_RANGE:
        raise HTTPException(status_code=404, detail="slot out of range (1-5)")


@router.get("/api/slots")
async def list_slots(request: Request) -> dict:
    """List the 5 human slots and their current state. Empty slots
    return `{"slot": N, "toon": null}`. Populated slots return the
    toon's id/name/appearance + a `claimed_by_me` boolean derived
    against the requester's session id. Hand-authored NPCs in slots
    100+ are excluded."""
    _require_authed(request)
    sid = _session_id(request)
    return {"slots": toons.get_human_slots(sid)}


@router.post("/api/slots/{slot}/create")
async def create_slot(slot: int, request: Request) -> dict:
    """Create a new human-controlled toon in `slot` for this session.
    Body JSON: `{"name": str, "appearance_seed": str}`. Returns the
    created toon. Errors:
    - 400 missing / non-string / whitespace-only `name` or
      `appearance_seed`.
    - 404 slot not in 1..5.
    - 409 slot already populated by an existing toon (claim or kick
      first if you want a fresh one)."""
    _require_authed(request)
    _validate_slot(slot)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="body must be JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    name = body.get("name")
    appearance = body.get("appearance_seed")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail="name must be a non-empty string")
    if not isinstance(appearance, str) or not appearance.strip():
        raise HTTPException(
            status_code=400, detail="appearance_seed must be a non-empty string"
        )
    sid = _session_id(request)
    new_toon = toons.create_toon_in_slot(slot, name.strip(), appearance.strip(), sid)
    if new_toon is None:
        raise HTTPException(status_code=409, detail="slot already populated")
    request.session.pop("left", None)  # picking a toon re-enters the dream
    return _toon_to_dict(new_toon, sid)


@router.post("/api/slots/{slot}/claim")
async def claim_slot(slot: int, request: Request) -> dict:
    """Adopt a kicked-NPC toon as the requester's controlled toon.
    Errors:
    - 404 slot empty or not in 1..5.
    - 409 slot's toon is currently controlled (kick it first)."""
    _require_authed(request)
    _validate_slot(slot)
    sid = _session_id(request)
    toon, reason = toons.claim_slot(slot, sid)
    if reason == "empty":
        raise HTTPException(status_code=404, detail="slot is empty")
    if reason == "controlled":
        raise HTTPException(
            status_code=409, detail="slot is currently controlled; kick first"
        )
    assert toon is not None
    request.session.pop("left", None)  # picking a toon re-enters the dream
    return _toon_to_dict(toon, sid)


@router.post("/api/slots/{slot}/kick")
async def kick_slot(slot: int, request: Request) -> dict:
    """Release `slot` to a non-drifting NPC. Sets controller_session
    NULL, is_human_controlled 0, kicked_at <UTC ISO>. The toon stays
    in its current room carrying its inventory + memories.
    Errors: 404 slot empty or not in 1..5."""
    _require_authed(request)
    _validate_slot(slot)
    sid = _session_id(request)
    toon = toons.kick_slot(slot)
    if toon is None:
        raise HTTPException(status_code=404, detail="slot is empty")
    return _toon_to_dict(toon, sid)


@router.post("/api/session/leave")
async def leave_session(request: Request) -> dict:
    """Leave the dream: rest this session's controlled toon (if any) and mark
    the session 'left' so the next WS connect routes to the character picker
    instead of silently auto-controlling a toon. Idempotent (a session with no
    toon just gets marked)."""
    _require_authed(request)
    sid = _session_id(request)
    released = toons.release_session_toon(sid)
    request.session["left"] = True
    return {"ok": True, "released": released.id if released else None}


@router.post("/api/slots/{slot}/delete")
async def delete_toon(slot: int, request: Request) -> dict:
    """Permanently delete the toon in `slot`, freeing it — distinct from kick,
    which rests a recoverable toon. Errors: 404 slot empty or out of range.
    Friend-scope: any authed session may delete any slot (v2 tightens)."""
    _require_authed(request)
    _validate_slot(slot)
    deleted = toons.delete_slot(slot)
    if deleted is None:
        raise HTTPException(status_code=404, detail="slot is empty")
    return {"ok": True, "deleted": deleted.id}


def _toon_to_dict(t: "toons.Toon", session_id: str) -> dict:
    """Serialize a Toon for the JSON response. Mirrors the shape used by
    `get_human_slots` so a client can stitch list+create responses
    without two parsers."""
    return {
        "id": t.id,
        "slot": t.slot,
        "name": t.name,
        "appearance_seed": t.appearance_seed,
        "current_room_id": t.current_room_id,
        "is_human_controlled": t.is_human_controlled,
        "kicked_at": t.kicked_at,
        "mood": t.mood,
        "claimed_by_me": (
            t.controller_session == session_id
            and t.kicked_at is None
            and t.is_human_controlled
        ),
    }
