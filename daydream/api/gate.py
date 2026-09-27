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


class GateMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
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
