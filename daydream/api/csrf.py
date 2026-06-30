"""CSRF defense: reject cross-origin state-changing requests.

Pure ASGI middleware (mirrors `AccessMiddleware`) guarding unsafe HTTP methods
(POST/PUT/PATCH/DELETE) against the confused-deputy / CSRF vector. In the
default `tailscale` access mode, auth IS tailnet membership — `is_authed`
returns true unconditionally and the session cookie's `SameSite` is never
consulted — so a tailnet member who loads an attacker page could otherwise be
made to POST to a state-changing endpoint (toon delete, kick, leave) with their
own tailnet source IP, which `AccessMiddleware` then waves through.

This closes that vector: IF the browser sends an `Origin` (or, lacking it,
`Referer`) header, its `host[:port]` must equal the request's `Host`. Requests
with NO `Origin`/`Referer` pass through untouched, so non-browser clients (the
`bin/game world swap` CLI over urllib, the test suite, curl) are unaffected.

Safe methods (GET/HEAD/OPTIONS/TRACE) always pass, so the WebSocket upgrade (a
GET) and every read path are never gated here. `AccessMiddleware` (the IP gate)
still runs first; this is a second, orthogonal layer — defense in depth, not a
replacement for the v2 per-session-ownership work.

The comparison is against the request's own `Host`, not a hardcoded allowlist,
so it is correct for any hostname/IP a client legitimately uses to reach the
box (tailnet name, tailnet IP, localhost) without configuration.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Methods that never mutate state; never gated. (TRACE included for
# completeness; the app does not route it.)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    """First value of header `name` (lowercase bytes) from an ASGI header
    list, decoded latin-1, or None if absent."""
    for k, v in headers:
        if k == name:
            return v.decode("latin-1")
    return None


def origin_allows(headers: list[tuple[bytes, bytes]]) -> bool:
    """True when the request is safe to serve on CSRF grounds: either no
    Origin/Referer was sent (a non-browser client) or its netloc matches the
    request's Host. False only when a browser sent a cross-origin Origin (or
    Referer fallback)."""
    host = _header(headers, b"host") or ""
    source = _header(headers, b"origin")
    if source is None:
        source = _header(headers, b"referer")
        if source is None:
            return True  # non-browser client (CLI / tests / curl): allow
    return urlparse(source).netloc == host


class CsrfOriginMiddleware:
    """Reject cross-origin state-changing HTTP requests (see module docstring)."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            # WebSocket upgrades are GETs (safe); lifespan etc. pass through.
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET").upper()
        headers = scope.get("headers") or []
        if method in SAFE_METHODS or origin_allows(headers):
            await self.app(scope, receive, send)
            return

        host = _header(headers, b"host") or "<unknown>"
        logger.info("CSRF: rejected cross-origin %s (Host=%s)", method, host)
        body = (
            b"forbidden: cross-origin state-changing request rejected "
            b"(Origin does not match Host).\n"
        )
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
