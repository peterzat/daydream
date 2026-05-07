"""Password gate (DAYDREAM_PASSWORD from .env), session cookie via SessionMiddleware.

Two auth postures, selected by `DAYDREAM_ACCESS`:

- `tailscale` (default): tailnet membership IS the auth. The AccessMiddleware
  already rejects non-tailnet source IPs at the outer edge of the stack;
  layering a password on top is belt-and-suspenders that costs UX every time
  someone opens the game. In this mode, is_authed() returns True unconditionally,
  and POST /api/login short-circuits to a redirect so a cached login form still
  "works."
- `public`: there is no network boundary, so the shared password IS the gate.
  The friend-scope session cookie records "this browser may play"; wrong or
  empty passwords refuse access.

The shared password lives in .env at the project root (gitignored), sourced
by bin/game; if unset the server refuses all password-mode logins with a 503.
In tailscale mode the password is unused and can stay unset without effect."""

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from daydream import config

router = APIRouter()


def _ensure_session_id(session: dict) -> str:
    """Stamp a stable per-session UUID into the session dict on first
    auth. Used by the slot-picker (`daydream/api/slots.py`) to identify
    the controlling client and by `daydream/api/ws.py` to resolve the
    session's claimed toon. Idempotent: if `id` is already set the
    existing value is returned unchanged."""
    sid = session.get("id")
    if not isinstance(sid, str) or not sid:
        sid = str(uuid.uuid4())
        session["id"] = sid
    return sid


@router.post("/api/login")
async def login(request: Request):
    # Tailnet-trusted callers bypass the password check entirely. The
    # AccessMiddleware has already enforced CGNAT membership by the time
    # we get here, so the password check would be redundant ceremony.
    if config.access_mode() == "tailscale":
        request.session["authed"] = True
        _ensure_session_id(request.session)
        return RedirectResponse(url="/", status_code=303)

    data = await request.form()
    password = str(data.get("password", ""))
    expected = config.password()
    if not expected:
        # No password configured; refuse with a clear operator-facing message.
        # Empty would otherwise match an empty form field, granting access.
        return HTMLResponse(
            "no password configured. set DAYDREAM_PASSWORD in .env at the project root.",
            status_code=503,
        )
    if password != expected:
        # 401 with no session mutation. SessionMiddleware writes Set-Cookie only
        # when scope['session'] has been modified, so a wrong password leaves
        # the browser with no daydream_session cookie set to authed=True.
        return HTMLResponse(
            "wrong word. <a href='/login'>try again</a>",
            status_code=401,
        )
    request.session["authed"] = True
    _ensure_session_id(request.session)
    return RedirectResponse(url="/", status_code=303)


@router.post("/api/logout")
async def logout(request: Request):
    # In tailscale mode, logging out is meaningless (the next request
    # re-authes via is_authed()'s tailscale branch). Still clear the
    # session cookie so a later switch to public mode doesn't inherit
    # a stale authed=True, and redirect home rather than to a login
    # form the user wouldn't see anyway.
    request.session.pop("authed", None)
    if config.access_mode() == "tailscale":
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


def is_authed(scope_session: dict) -> bool:
    """Tailscale-mode clients are implicitly authed — the middleware
    already rejected any non-tailnet source IP, so getting this far IS
    the authorization. Public mode requires a valid session cookie set
    by a prior successful POST /api/login."""
    if config.access_mode() == "tailscale":
        return True
    return bool(scope_session.get("authed"))
