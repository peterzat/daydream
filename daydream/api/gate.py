"""The sign-in gate: every HTTP request, WebSocket and mount needs an account
session except a short public allowlist (SPEC 2026-09-27 criterion 1).

Pure ASGI, so it covers both HTTP and WebSocket scopes. It sits just inside
AccessMiddleware (the network rule) and outside everything else. It resolves
the session cookie once per request, stores the `accounts.Principal` (or
None) in `scope["state"]["principal"]`, and refuses what the allowlist does
not name:

- **HTTP:** an HTML navigation gets a 303 to the public base (the front
  door); anything else gets 401 JSON.
- **WebSocket:** the handshake is refused before accept.

No network location grants anything here. Loopback, the tailnet and
cloudflared all need a session like everyone else. tests/test_edge_access.py
walks every registered route to prove it.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from daydream import accounts, config

# Origin paths (the edge Worker strips /daydream before proxying).
PUBLIC_EXACT = frozenset({
    "/",                   # the front door when signed out, the game when signed in
    "/login",              # alias of the front door
    "/healthz",            # liveness for the Worker and `bin/game prod status`
    "/api/login",
    "/api/logout",
    "/api/invite/peek",
    "/api/invite/redeem",
})
PUBLIC_PREFIXES = (
    "/assets/",            # the SPA's own static files (no player data)
    "/invite/",            # the redeem card; the slug is only checked by the POSTs
)


def is_public(path: str) -> bool:
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES)


def _token(scope) -> str | None:
    from daydream.api.auth import token_from_cookie_header

    for k, v in scope.get("headers") or []:
        if k == b"cookie":
            return token_from_cookie_header(v.decode("latin-1"))
    return None


def _wants_html(scope) -> bool:
    for k, v in scope.get("headers") or []:
        if k == b"accept":
            return b"text/html" in v
    return False


# No request this app serves carries more than a few KB; the public
# endpoints parse bodies before anyone is signed in (SECURITY NOTE 2026-09-27).
MAX_BODY_BYTES = 64 * 1024


def _content_length(scope) -> int | None:
    for k, v in scope.get("headers") or []:
        if k == b"content-length":
            try:
                return int(v)
            except ValueError:
                return None
    return None


def _capped(receive):
    """A receive that stops a streamed body at MAX_BODY_BYTES: what arrives
    beyond it is dropped and the body ends, so a handler sees a truncated
    (unparseable) body instead of holding megabytes."""
    seen = 0
    done = False

    async def wrapped():
        nonlocal seen, done
        if done:
            return {"type": "http.request", "body": b"", "more_body": False}
        message = await receive()
        if message["type"] == "http.request":
            body = message.get("body", b"")
            seen += len(body)
            if seen > MAX_BODY_BYTES:
                done = True
                keep = max(0, MAX_BODY_BYTES - (seen - len(body)))
                return {"type": "http.request", "body": body[:keep], "more_body": False}
        return message

    return wrapped


async def _send_simple(send, status: int, body: bytes, ctype: bytes = b"application/json"):
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", ctype),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class GateMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http":
            length = _content_length(scope)
            if length is not None and length > MAX_BODY_BYTES:
                await _send_simple(send, 413, json.dumps({"error": "too large"}).encode())
                return
            receive = _capped(receive)
        try:
            who = accounts.resolve(_token(scope))
        except Exception:  # an unreadable accounts DB fails closed
            who = None
        scope.setdefault("state", {})["principal"] = who
        path = scope.get("path") or "/"
        if who is not None or is_public(path):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # Refused before accept: the browser sees the handshake fail
            # (close 1006); the SPA then probes api/me to tell a lapsed
            # session from a sleeping village.
            await send({"type": "websocket.close", "code": 4401})
            return
        if scope.get("method") == "GET" and _wants_html(scope):
            await send({"type": "http.response.start", "status": 303,
                        "headers": [(b"location", config.public_base().encode()),
                                    (b"content-length", b"0")]})
            await send({"type": "http.response.body", "body": b""})
            return
        body = json.dumps({"error": "sign in first"}).encode()
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
