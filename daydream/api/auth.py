"""Password gate ('REDACTED' by default), session cookie via SessionMiddleware.

Friend-scope security only: a single shared password, no per-user identity.
The session cookie just records "this browser may play"; the real gate is
network access to the box (Tailscale, not Tailscale Funnel)."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from daydream import config

router = APIRouter()


@router.post("/api/login")
async def login(request: Request):
    data = await request.form()
    password = str(data.get("password", ""))
    if password != config.password():
        # 401 with no session mutation. SessionMiddleware writes Set-Cookie only
        # when scope['session'] has been modified, so a wrong password leaves
        # the browser with no daydream_session cookie set to authed=True.
        return HTMLResponse(
            "wrong word. <a href='/login'>try again</a>",
            status_code=401,
        )
    request.session["authed"] = True
    return RedirectResponse(url="/", status_code=303)


@router.post("/api/logout")
async def logout(request: Request):
    request.session.pop("authed", None)
    return RedirectResponse(url="/login", status_code=303)


def is_authed(scope_session: dict) -> bool:
    return bool(scope_session.get("authed"))
