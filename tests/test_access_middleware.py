"""AccessMiddleware contract: tailscale-only rejects non-tailnet clients;
public lets all through; non-request scopes always pass through.

Tested at the ASGI layer directly (constructing scope dicts and capturing
send() calls) so we don't have to forge tailnet source IPs through TestClient.
The middleware itself is a pure ASGI app that wraps another ASGI app."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from daydream.api.access import AccessMiddleware, is_tailscale_or_local


# ---- is_tailscale_or_local ---------------------------------------------


@pytest.mark.parametrize(
    "host,expected",
    [
        ("100.64.0.1", True),     # bottom of CGNAT
        ("100.127.255.254", True),  # top of CGNAT
        ("127.0.0.1", True),      # IPv4 loopback
        ("127.5.5.5", True),      # 127.0.0.0/8
        ("::1", True),            # IPv6 loopback
        ("100.63.255.255", False),  # one below CGNAT
        ("100.128.0.0", False),   # one above CGNAT
        ("8.8.8.8", False),       # public DNS
        ("192.168.1.1", False),   # private LAN, not tailnet
        ("10.0.0.1", False),      # private LAN, not tailnet
        ("", False),              # empty
        ("not-an-ip", False),     # garbage
    ],
)
def test_is_tailscale_or_local(host: str, expected: bool):
    assert is_tailscale_or_local(host) is expected


# ---- middleware behavior -----------------------------------------------


class _Recorder:
    """Captures the calls a downstream ASGI app would receive, plus the
    send() messages the middleware produces."""

    def __init__(self) -> None:
        self.app_called = False
        self.sent: list[dict[str, Any]] = []

    async def app(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.app_called = True

    async def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    async def receive(self) -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}


def _http_scope(client_host: str = "100.64.0.42") -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": (client_host, 50000),
    }


def _ws_scope(client_host: str = "100.64.0.42") -> dict[str, Any]:
    return {
        "type": "websocket",
        "path": "/ws",
        "headers": [],
        "client": (client_host, 50000),
    }


@pytest.mark.asyncio
async def test_tailscale_mode_passes_tailnet_http(monkeypatch):
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    await mw(_http_scope("100.64.0.42"), rec.receive, rec.send)
    assert rec.app_called
    assert rec.sent == []


@pytest.mark.asyncio
async def test_tailscale_mode_passes_localhost_http(monkeypatch):
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    await mw(_http_scope("127.0.0.1"), rec.receive, rec.send)
    assert rec.app_called


@pytest.mark.asyncio
async def test_tailscale_mode_rejects_public_http(monkeypatch):
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    await mw(_http_scope("8.8.8.8"), rec.receive, rec.send)
    assert not rec.app_called
    # 403 response with body
    starts = [m for m in rec.sent if m.get("type") == "http.response.start"]
    bodies = [m for m in rec.sent if m.get("type") == "http.response.body"]
    assert starts and starts[0]["status"] == 403
    assert bodies and b"forbidden" in bodies[0]["body"]


@pytest.mark.asyncio
async def test_tailscale_mode_rejects_public_websocket(monkeypatch):
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    await mw(_ws_scope("8.8.8.8"), rec.receive, rec.send)
    assert not rec.app_called
    closes = [m for m in rec.sent if m.get("type") == "websocket.close"]
    assert closes and closes[0]["code"] == 1008  # policy violation


@pytest.mark.asyncio
async def test_public_mode_passes_any_http(monkeypatch):
    monkeypatch.setenv("DAYDREAM_ACCESS", "public")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    await mw(_http_scope("8.8.8.8"), rec.receive, rec.send)
    assert rec.app_called


@pytest.mark.asyncio
async def test_public_mode_passes_any_websocket(monkeypatch):
    monkeypatch.setenv("DAYDREAM_ACCESS", "public")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    await mw(_ws_scope("8.8.8.8"), rec.receive, rec.send)
    assert rec.app_called


@pytest.mark.asyncio
async def test_lifespan_scope_always_passes(monkeypatch):
    """Lifespan and other non-request scopes must not be blocked even in
    tailscale mode (the server itself isn't a remote client)."""
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    await mw({"type": "lifespan"}, rec.receive, rec.send)
    assert rec.app_called


@pytest.mark.asyncio
async def test_missing_client_in_tailscale_mode_rejects(monkeypatch):
    """Defensive: if scope has no client info, default-deny under tailscale
    mode rather than letting it through."""
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    rec = _Recorder()
    mw = AccessMiddleware(rec.app)
    scope = _http_scope()
    del scope["client"]
    await mw(scope, rec.receive, rec.send)
    assert not rec.app_called
    starts = [m for m in rec.sent if m.get("type") == "http.response.start"]
    assert starts and starts[0]["status"] == 403
