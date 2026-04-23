"""Access control middleware: Tailscale-only by default, public if opted in.

Pure ASGI middleware so it covers both HTTP and WebSocket scopes (Starlette's
BaseHTTPMiddleware would only cover HTTP). Sits at the outer edge of the
middleware stack — added LAST in server.py so it runs FIRST per request.

Honest tradeoff: this is HTTP/WS-layer enforcement, not network-layer. An
attacker who can reach the bind address can still send packets; the
middleware just refuses to serve them. Combine with UFW (deny public
ingress) for the actual network isolation. The toggle here is the
"agree to be public" flag; flipping it does NOT also open UFW."""

import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from daydream import config

logger = logging.getLogger(__name__)

# Tailscale's CGNAT-reserved range. Hardcoded because Tailscale itself
# hardcodes it; a self-hosted Headscale with a custom range would need
# this updated.
TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")
LOCALHOST_V4 = ipaddress.ip_network("127.0.0.0/8")
LOCALHOST_V6 = ipaddress.ip_network("::1/128")


def is_tailscale_or_local(host: str) -> bool:
    """True if the host string is a tailnet IP (100.64.0.0/10) or loopback."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.version == 4:
        return ip in TAILSCALE_CGNAT or ip in LOCALHOST_V4
    return ip in LOCALHOST_V6


class AccessMiddleware:
    """Reject HTTP/WS requests from clients outside the tailnet when
    config.access_mode() == 'tailscale'. Pass-through when 'public'."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        # lifespan and other non-request scopes always pass through.
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if config.access_mode() == "public":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        host = client[0] if client else ""
        if is_tailscale_or_local(host):
            await self.app(scope, receive, send)
            return

        # Reject. Logger so operators see the rejection without cranking
        # the FastAPI access log.
        logger.info(
            "access denied for %s (DAYDREAM_ACCESS=tailscale; not on tailnet)", host or "<unknown>"
        )
        if scope["type"] == "http":
            body = (
                f"forbidden: {host or 'unknown client'} is not on the tailnet. "
                "Set DAYDREAM_ACCESS=public in .env (and open UFW for the port) "
                "to allow non-tailnet clients.\n"
            ).encode()
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
        else:  # websocket
            # Per RFC 6455 / WebSocket close codes, 1008 = policy violation.
            await send({"type": "websocket.close", "code": 1008})
