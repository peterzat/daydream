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


def _is_loopback(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip in LOCALHOST_V4 or ip in LOCALHOST_V6


_ACCESS_TOKEN_HEADERS = frozenset({b"cf-access-client-id", b"cf-access-client-secret"})


class AccessMiddleware:
    """The network rule, layered under account sign-in: 'tailscale' admits
    tailnet + loopback peers, 'edge' admits loopback peers only (cloudflared),
    'public' admits everyone. No mode grants a session."""

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
        # Cloudflare Access may pass the Worker's service-token headers on to
        # the origin: the secret goes no further into the app (security
        # review 2026-09-29; nothing here reads them).
        hdrs = scope.get("headers") or []
        if any(k.lower() in _ACCESS_TOKEN_HEADERS for k, _ in hdrs):
            scope = {**scope, "headers": [(k, v) for k, v in hdrs
                                          if k.lower() not in _ACCESS_TOKEN_HEADERS]}

        mode = config.access_mode()
        if mode == "public":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        host = client[0] if client else ""
        if mode == "edge":
            # Prod behind the Cloudflare tunnel: cloudflared on loopback is the
            # only way in. Admitting only loopback peers is a transport rule
            # (it catches an accidental non-loopback bind), never a privilege:
            # every request still needs an account session (daydream/api/gate.py).
            if _is_loopback(host):
                await self.app(scope, receive, send)
                return
        elif is_tailscale_or_local(host):
            await self.app(scope, receive, send)
            return

        # Reject. Logger so operators see the rejection without cranking
        # the FastAPI access log.
        logger.info(
            "access denied for %s (DAYDREAM_ACCESS=%s)", host or "<unknown>", mode
        )
        if scope["type"] == "http":
            body = (
                f"forbidden: {host or 'unknown client'} is not on the tailnet. "
                "Reach the dev server over the tailnet, from the box itself, or "
                "through an SSH tunnel (ssh -L 54321:127.0.0.1:54321 <box>); "
                "hosting for friends goes through the edge (docs/CLOUDFLARE-SETUP.md).\n"
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
