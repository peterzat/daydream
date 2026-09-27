"""Prod fails closed (SPEC 2026-09-27 criteria 1 and 4): every registered
route, WebSocket and mount refuses a request without an account session,
except the public allowlist, from any network location and with spoofed
forwarding headers. The walk reads the app's own route table, so a route
added later without thought fails here automatically."""

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount, WebSocketRoute
from starlette.websockets import WebSocketDisconnect

from daydream import config
from daydream.api import gate
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium

SPOOF = {
    "x-forwarded-for": "127.0.0.1",
    "x-real-ip": "127.0.0.1",
    "x-daydream-client-ip": "127.0.0.1",
    "forwarded": "for=127.0.0.1",
}
EDGE = {
    "DAYDREAM_ACCESS": "edge",
    "DAYDREAM_PUBLIC_ORIGIN": "https://www.eidolon.com",
    "DAYDREAM_PUBLIC_BASE": "/daydream/",
}


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


def _http_routes():
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD"}):
                yield m, _concrete(r.path)
        elif isinstance(r, Mount):
            yield "GET", r.path.rstrip("/") + "/x"


def _ws_routes():
    return [_concrete(r.path) for r in app.routes if isinstance(r, WebSocketRoute)]


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


def test_the_walk_sees_the_app():
    guarded = [(m, p) for m, p in _http_routes() if not gate.is_public(p)]
    assert len(guarded) >= 12
    assert ("POST", "/api/slots/x/create") in guarded
    assert ("GET", "/cache/x/x/x/x") in guarded
    assert "/ws" in _ws_routes()


def test_the_public_allowlist_is_exactly_this():
    """Growing the allowlist is a reviewed change: edit this test with it."""
    assert gate.PUBLIC_EXACT == {"/", "/login", "/healthz", "/api/login", "/api/logout",
                                 "/api/invite/peek", "/api/invite/redeem"}
    assert gate.PUBLIC_PREFIXES == ("/assets/", "/invite/")


@pytest.mark.parametrize("mode,peer", [
    ("edge", "127.0.0.1"),        # cloudflared's peer in prod
    ("tailscale", "127.0.0.1"),   # dev, on the box
    ("tailscale", "100.64.0.1"),  # dev, a tailnet friend
])
def test_every_guarded_route_refuses_without_a_session(monkeypatch, mode, peer):
    if mode == "edge":
        for k, v in EDGE.items():
            monkeypatch.setenv(k, v)
    else:
        monkeypatch.setenv("DAYDREAM_ACCESS", mode)
    leaks = []
    with TestClient(app, client=(peer, 5000)) as client:
        for method, path in _http_routes():
            if gate.is_public(path):
                continue
            for accept in ("application/json", "text/html"):
                r = client.request(method, path, headers={**SPOOF, "accept": accept},
                                   follow_redirects=False)
                ok = r.status_code == 401 or (
                    r.status_code == 303 and method == "GET" and accept == "text/html")
                if not ok:
                    leaks.append(f"{method} {path} ({accept}) -> {r.status_code}")
        for path in _ws_routes():
            try:
                with client.websocket_connect(path, headers=SPOOF):
                    leaks.append(f"WS {path} accepted")
            except WebSocketDisconnect as e:
                if e.code != 4401:
                    leaks.append(f"WS {path} closed {e.code}")
    assert not leaks, "\n".join(leaks)


def test_edge_mode_refuses_non_loopback_peers_outright(monkeypatch):
    for k, v in EDGE.items():
        monkeypatch.setenv(k, v)
    with TestClient(app, client=("100.64.0.1", 5000)) as client:
        assert client.get("/healthz").status_code == 403


def test_public_routes_say_nothing_private(monkeypatch):
    for k, v in EDGE.items():
        monkeypatch.setenv(k, v)
    with TestClient(app, client=("127.0.0.1", 5000)) as client:
        assert client.get("/healthz").json() == {"ok": True}
        door = client.get("/")
        assert door.status_code == 200 and 'id="login-form"' in door.text
        assert client.get("/assets/main.js").status_code == 200


def test_a_player_cannot_reach_admin_surfaces():
    with TestClient(app, client=("127.0.0.1", 5000)) as client:
        authhelp.login(client, "wren")
        for path in ("/status/build", "/status/drift", "/status/arbiter"):
            assert client.get(path).status_code == 403, path
        assert client.post("/api/world/swap", json={"target": "x"}).status_code == 403


def test_an_admin_can(monkeypatch):
    with TestClient(app, client=("127.0.0.1", 5000)) as client:
        authhelp.login(client, "keeper", role="admin")
        assert client.get("/status/build").status_code == 200


def test_world_swap_does_not_exist_in_edge_mode(monkeypatch):
    for k, v in EDGE.items():
        monkeypatch.setenv(k, v)
    # https: the prod cookie is Secure, so a plain-http client would drop it.
    with TestClient(app, client=("127.0.0.1", 5000), base_url="https://testserver") as client:
        authhelp.login(client, "keeper", role="admin")
        # The cookie is scoped to /daydream/, which the Worker strips before the
        # origin sees the request; the browser still sends it. Send it here.
        name = config.cookie_name()
        token = next(c.value for c in client.cookies.jar if c.name == name)
        h = {"cookie": f"{name}={token}", "origin": "https://www.eidolon.com"}
        assert client.get("/api/me", headers=h).status_code == 200
        r = client.post("/api/world/swap", json={"target": "x"}, headers=h)
    assert r.status_code == 404


def test_cached_images_are_private(monkeypatch, tmp_path):
    from daydream.images import cache as image_cache

    p = image_cache.cache_dir() / "w-x" / "room" / "r-x" / "abc.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    with TestClient(app) as client:
        assert client.get("/cache/w-x/room/r-x/abc.png").status_code == 401
        authhelp.login(client)
        r = client.get("/cache/w-x/room/r-x/abc.png")
    assert r.status_code == 200 and r.headers["cache-control"].startswith("private")
