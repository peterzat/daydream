"""Room-image repaint API: the dev-facing regen surface (plan 2026-07-02).

Two endpoints let a logged-in dev experiment with how prompts drive the
room background, without any prompt being remembered:

  GET  /api/rooms/{room_id}/image-prompt -> {"prompt": <canonical prompt>}
       The full positive prompt the render uses (seed text + tone suffix).
       Shown read-only in the repaint dialog so a dev can see, then edit it.

  POST /api/rooms/{room_id}/image  {"prompt"?: str}
       Force-repaint the room. With no body / no prompt: a same-prompt
       regen (fresh random seed, so it looks different). With a prompt: a
       one-off render using that exact positive prompt. Either way the cache
       file is overwritten IN PLACE (the cache key never moves) and a
       {hash}.png.prev is kept; the custom prompt is NEVER persisted (the
       generated_assets row records a fixed marker). 202 on start, 409 if a
       paint for that room is already in flight, 404 if the room is unknown.

This is a dev tool: per the plan we do minimal input hygiene (a length cap
to avoid an absurd prompt) and no content filtering. Auth mirrors the other
mutating endpoints (an authenticated session behind the tailnet gate); the
CSRF-origin middleware already covers POSTs. The off-switch is
DAYDREAM_REGEN_UI=0 (config.regen_ui_enabled): both endpoints 404 as if
they were never mounted, and the snapshot's features flag tells the SPA to
keep the plate tools unbound. Default ON in dev; flip it off on any shared
deployment where players shouldn't repaint shared art.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from daydream import config, rooms
from daydream.api import auth as auth_mod
from daydream.images import client as image_client

router = APIRouter()


def _require_regen_enabled() -> None:
    """404 (not 403) when the regen UI is switched off: the surface should
    look unmounted, not forbidden — there is nothing for a player to ask
    permission for."""
    if not config.regen_ui_enabled():
        raise HTTPException(status_code=404, detail="not found")

# Generous cap: a real seed + suffix is a few hundred chars. This only stops
# a pathological multi-megabyte body, not creativity.
MAX_PROMPT_CHARS = 2000


def _require_authed(request: Request) -> None:
    if not auth_mod.is_authed(request.session):
        raise HTTPException(status_code=401, detail="not authenticated")


@router.get("/api/rooms/{room_id}/image-prompt")
async def get_image_prompt(room_id: str, request: Request) -> dict:
    """Return the canonical positive prompt for the room's background so the
    repaint dialog can show it (read-only) and pre-fill the edit box."""
    _require_regen_enabled()
    _require_authed(request)
    room = rooms.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="no such room")
    return {
        "room_id": room.id,
        "prompt": image_client.canonical_prompt(
            room.seed, image_client.WHIMSY_PROMPT_SUFFIX
        ),
    }


@router.post("/api/rooms/{room_id}/image")
async def repaint_room(room_id: str, request: Request) -> dict:
    """Force-repaint the room background. Optional JSON body `{"prompt": str}`
    supplies a one-off positive prompt; omitted / blank means a same-prompt
    regen. The new art is broadcast to everyone in the room via the
    room_image_ready event; this endpoint returns as soon as the job is
    queued."""
    _require_regen_enabled()
    _require_authed(request)
    prompt: str | None = None
    # A body is optional; tolerate an empty/absent one (same-prompt regen).
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        raw = body.get("prompt")
        if raw is not None:
            if not isinstance(raw, str):
                raise HTTPException(status_code=400, detail="prompt must be a string")
            if len(raw) > MAX_PROMPT_CHARS:
                raise HTTPException(
                    status_code=400,
                    detail=f"prompt exceeds {MAX_PROMPT_CHARS} chars",
                )
            prompt = raw.strip() or None

    # Import lazily: ws pulls in the arbiter / image stack, and importing it
    # at module load would widen this router's import surface needlessly.
    from daydream.api import ws as ws_mod

    outcome = ws_mod.enqueue_room_regen(room_id, prompt_override=prompt)
    if outcome == "no_room":
        raise HTTPException(status_code=404, detail="no such room")
    if outcome == "in_flight":
        raise HTTPException(status_code=409, detail="a paint for this room is in flight")
    return {"ok": True, "status": "started", "custom_prompt": prompt is not None}
