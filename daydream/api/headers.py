"""Security headers on every HTTP response (SPEC 2026-09-27 criterion 7).

- **CSP.** The client has no inline script, no inline handler and no style
  attribute (tests/test_security_headers.py keeps it that way), so the policy
  is strict: scripts, styles, fonts and connections are all our own origin.
  Images may also be `data:` (the paper-noise SVGs in style.css) or `blob:`.
  WebSocket targets are listed explicitly for browsers whose `'self'` does
  not cover ws/wss.
- **Framing and sniffing.** The page cannot be framed, and content types are
  not sniffed.
- **Referrer and indexing.** Referrers stay on this origin, and nothing is
  indexed (friends-only; this repo is public, the village is not).

A header a handler set itself is left alone.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from daydream import config


def _ws_sources(scope) -> str:
    public = config.public_origin()
    if public:
        host = urlparse(public).netloc
        return f"wss://{host}"
    host = ""
    for k, v in scope.get("headers") or []:
        if k == b"host":
            host = v.decode("latin-1")
            break
    return f"ws://{host} wss://{host}" if host else ""


def csp(scope) -> str:
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        f"connect-src 'self' {_ws_sources(scope)}".rstrip(),
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


class SecurityHeadersMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        extra = [
            (b"content-security-policy", csp(scope).encode("latin-1")),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"same-origin"),
            (b"x-robots-tag", b"noindex, nofollow"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        ]

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {k.lower() for k, _ in headers}
                headers.extend((k, v) for k, v in extra if k not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
