"""Middleware that stamps `Cache-Control: no-store` on asset responses.

Browsers (Safari in particular) aggressively cache the SPA's JS and CSS;
without this, every web/assets/* edit forces the operator to hard-refresh
before the change becomes visible. This middleware makes `Cmd+R` enough.

Scope is narrow on purpose:

- `/assets/*`            → no-store (this middleware). Small files, edited
                           often in dev, must always reflect latest disk.
- `/cache/*`             → default (no header stamped). Generated image
                           files are content-addressed by hash (filename
                           changes when content changes), so browsers can
                           cache them aggressively; that's correct.
- `/` (SPA shell)        → default. Re-fetched on every navigation and
                           pulls /assets/main.js etc. as child requests;
                           stamping no-store on /assets/ is sufficient to
                           defeat stale-JS problems.
- `/login`, `/api/*`     → default. Not cacheable by browsers in practice
                           (POSTs and dynamic responses).

Unconditional today because the project has no dev/live split — every
instance is the "dev" instance on this box. When a public deploy lands,
the cache posture should be re-evaluated (revision-stamped asset URLs
is the idiomatic upgrade)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class NoCacheAssetsMiddleware:
    """ASGI middleware. Adds `Cache-Control: no-store` to every HTTP
    response whose request path starts with `/assets/`. Non-HTTP scopes
    (lifespan, websocket) and non-asset paths pass through unchanged."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http" or not scope.get("path", "").startswith("/assets/"):
            await self.app(scope, receive, send)
            return

        async def send_with_no_cache(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                # Drop any pre-existing cache-control header so we don't
                # ship two values (StaticFiles may set one). Header names
                # are bytes and case-insensitive per ASGI; normalize on
                # compare, preserve on rewrite.
                headers = [
                    (k, v)
                    for (k, v) in message.get("headers", [])
                    if k.lower() != b"cache-control"
                ]
                headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_no_cache)
