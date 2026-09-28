"""Sign-in: accounts and server-side sessions (SPEC 2026-09-27 criteria 2-4,
7; docs/GOING-LIVE.md section 4). Replaces the shared DAYDREAM_PASSWORD and
the signed-cookie session.

- The session cookie (`config.cookie_name()`) carries a random token. It is
  HttpOnly and SameSite=Lax, scoped to the public base path, Secure when the
  public origin is https, and lives 30 days (refreshed on each page load;
  the server side slides on use).
- `GateMiddleware` (daydream/api/gate.py) resolves the cookie on every
  request and puts the `accounts.Principal` in `scope["state"]`; handlers
  read it with `principal(request)`.
- Every mode requires an account. The access mode only adds network rules
  (daydream/api/access.py).

Throttles (accounts.LOGIN_* / REDEEM_*) count failures per client address,
per username, and, for invite redemption, globally per hour and per day.
Failures never say whether a username exists.
"""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from daydream import accounts, config

router = APIRouter()

MAX_FIELD = 300


# ---- principal + client address --------------------------------------------


def principal(conn) -> accounts.Principal | None:
    """The signed-in person for a Request or WebSocket (set by the gate)."""
    state = conn.scope.get("state") or {}
    return state.get("principal")


def token_from_cookie_header(raw: str | None) -> str | None:
    if not raw:
        return None
    # Starlette's parser, not SimpleCookie: SimpleCookie drops every cookie
    # after a malformed neighbor (`prefs={"a":1}`), reading a signed-in person
    # as signed out (codereview NOTE 2026-09-28).
    from starlette.requests import cookie_parser

    return cookie_parser(raw).get(config.cookie_name()) or None


def throttle_address(addr: str) -> str:
    """The throttle key for an address: IPv6 by its /64 (one household or
    host), so rotating through a prefix does not reset the count."""
    import ipaddress

    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return addr
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def client_address(scope) -> str:
    """The requester's address for throttling. Behind the edge Worker the
    socket peer is always cloudflared on loopback, so edge mode trusts only
    the Worker's X-Daydream-Client-IP (the Worker overwrites any client-sent
    copy). Elsewhere it is the socket peer."""
    if config.access_mode() == "edge":
        for k, v in scope.get("headers") or []:
            if k == b"x-daydream-client-ip":
                return v.decode("latin-1").strip()[:64] or "unknown"
        return "unknown"
    client = scope.get("client")
    return client[0] if client else "unknown"


# ---- cookies -----------------------------------------------------------------


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        config.cookie_name(), token,
        max_age=accounts.SESSION_DAYS * 24 * 3600,
        path=config.public_base(),
        httponly=True,
        samesite="lax",
        secure=config.cookie_secure(),
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(config.cookie_name(), path=config.public_base(),
                           httponly=True, samesite="lax", secure=config.cookie_secure())


def _deny(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _body(request: Request) -> dict:
    """JSON or form body as a dict of short strings."""
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            data = await request.json()
        else:
            data = dict(await request.form())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # A JSON null is a missing field, not the string "None".
    return {k: ("" if v is None else str(v))[:MAX_FIELD] for k, v in data.items()
            if isinstance(k, str)}


def _signed_in(principal_row, request: Request, body: dict | None = None) -> JSONResponse:
    token, _ = accounts.create_session(principal_row["id"],
                                       request.headers.get("user-agent", ""))
    resp = JSONResponse({"ok": True, "next": config.public_base(),
                         "username": principal_row["username"]})
    set_session_cookie(resp, token)
    return resp


# ---- endpoints -----------------------------------------------------------------


LOGIN_REFUSED = "that username and password don't match"
# At most this many argon2 checks at once; a burst queues instead of each
# check taking its own slice of memory (SECURITY WARN 2026-09-28).
_HASH_SLOTS = threading.BoundedSemaphore(4)
SLOW_DOWN = "too many tries; wait a few minutes and try again"


@router.post("/api/login")
async def login(request: Request):
    body = await _body(request)
    username = accounts.normalize_username(body.get("username", ""))
    password = body.get("password", "")
    addr_key = "login-addr:" + throttle_address(client_address(request.scope))
    user_key = "login-user:" + username
    if (accounts.throttled(addr_key, accounts.LOGIN_PER_ADDRESS)
            or accounts.throttled(user_key, accounts.LOGIN_PER_USERNAME)):
        return _deny(429, SLOW_DOWN)
    # Count the attempt before the await: the check above and this record run
    # with no await between them, so a concurrent burst cannot all pass the
    # budget while the hashes run (SECURITY WARN 2026-09-28). A right password
    # takes it back.
    accounts.record_failure(addr_key, accounts.LOGIN_PER_ADDRESS)
    if username:
        accounts.record_failure(user_key, accounts.LOGIN_PER_USERNAME)
    # argon2 is ~30-60 ms of CPU: off the event loop, so a burst of logins
    # never stalls everyone's game (SECURITY NOTE 2026-09-27).
    row = await asyncio.to_thread(_hashing, accounts.authenticate, username, password)
    if row is None:
        return _deny(401, LOGIN_REFUSED)
    accounts.forgive_one(addr_key)
    accounts.clear_failures(user_key)
    return _signed_in(row, request)


def _hashing(fn, *args):
    """Run an argon2-bound call under the shared cap (in a worker thread)."""
    with _HASH_SLOTS:
        return fn(*args)


@router.post("/api/logout")
async def logout(request: Request):
    accounts.end_session(token_from_cookie_header(request.headers.get("cookie")))
    resp = JSONResponse({"ok": True, "next": config.public_base()})
    clear_session_cookie(resp)
    return resp


@router.get("/api/me")
async def me(request: Request):
    p = principal(request)
    if p is None:  # the gate already refused; belt and braces
        return _deny(401, "sign in first")
    return {"username": p.username, "display_name": p.display_name, "role": p.role,
            "is_admin": p.is_admin}


@router.post("/api/account/password")
async def change_password(request: Request):
    p = principal(request)
    if p is None:
        return _deny(401, "sign in first")
    body = await _body(request)
    key = "password-change:" + p.account_id
    if accounts.throttled(key, accounts.LOGIN_PER_USERNAME):
        return _deny(429, SLOW_DOWN)
    # Every attempt counts, and the two argon2 operations run off the event
    # loop under the login cap: a signed-in session changing its password in a
    # loop must not stall everyone's game (codereview NOTE 2026-09-28).
    accounts.record_failure(key, accounts.LOGIN_PER_USERNAME)
    try:
        new_hash = await asyncio.to_thread(_hashing, accounts.prepare_password_change,
                                           p.account_id, body.get("old", ""), body.get("new", ""))
    except accounts.AccountError as e:
        return _deny(400, str(e))
    accounts.commit_password_change(p.account_id, new_hash, keep_session_id=p.session_id)
    return {"ok": True}


def invites_resting() -> str:
    return (f"invitations are resting for a little while; try again later, or ask "
            f"{config.operator_name()}")


def _redeem_blocked(addr: str) -> bool:
    return (accounts.throttled("redeem-addr:" + addr, accounts.REDEEM_PER_ADDRESS)
            or accounts.throttled("redeem-hour", accounts.REDEEM_GLOBAL_HOUR)
            or accounts.throttled("redeem-day", accounts.REDEEM_GLOBAL_DAY))


def _redeem_failed(addr: str) -> None:
    accounts.record_failure("redeem-addr:" + addr, accounts.REDEEM_PER_ADDRESS)
    accounts.record_failure("redeem-hour", accounts.REDEEM_GLOBAL_HOUR)
    accounts.record_failure("redeem-day", accounts.REDEEM_GLOBAL_DAY)


@router.post("/api/invite/peek")
async def invite_peek(request: Request):
    """Who an open invitation is for, so the card can greet them. A used,
    expired, revoked or unknown slug all answer the same 404, and each
    counts against the redemption throttles."""
    body = await _body(request)
    addr = throttle_address(client_address(request.scope))
    if _redeem_blocked(addr):
        return _deny(429, invites_resting())
    inv = accounts.peek_invite(body.get("slug", ""))
    if inv is None:
        _redeem_failed(addr)
        return _deny(404, accounts.invite_refused())
    return {"for": inv["for_name"], "kind": inv["kind"],
            "operator": config.operator_name()}


@router.post("/api/invite/redeem")
async def invite_redeem(request: Request):
    """Redeem an invitation: a `join` creates the account and signs it in; a
    `reset` sets a new password (ending every old session) and signs in."""
    body = await _body(request)
    addr = throttle_address(client_address(request.scope))
    if _redeem_blocked(addr):
        return _deny(429, invites_resting())
    slug = body.get("slug", "")
    inv = accounts.peek_invite(slug)
    if inv is None:
        _redeem_failed(addr)
        return _deny(404, accounts.invite_refused())
    try:
        if inv["kind"] == "join":
            row = accounts.redeem_join(slug, body.get("username", ""), body.get("password", ""))
        else:
            row = accounts.redeem_reset(slug, body.get("password", ""))
    except accounts.AccountError as e:
        if str(e) == accounts.invite_refused():  # lost a race for the same slug
            _redeem_failed(addr)
            return _deny(404, str(e))
        # A taken username or a short password is the person's to fix, not a
        # guess at the slug: it does not count against the throttle.
        return _deny(400, str(e))
    return _signed_in(row, request)
