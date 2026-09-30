#!/usr/bin/env python3
"""The egress gateway: prod's one way out of its sandbox (docs/EXTERNAL.md).

The game service reaches loopback only (its unit's IPAddressAllow; the root
helper refuses a unit that loosens it). The hosted services this project
allows as controlled, optional exceptions to its generation policy are
declared in ROUTES below, and this small server is the only process that
reaches them: its own unit, daydream-egress.service (a throwaway system
user, no writes anywhere, the data dir and /srv/daydream/etc hidden, the
public internet but not the tailnet or the LAN), listening on
127.0.0.1:54323. It forwards a request to its route's host only when:

- the route is declared here, and its key is set (/etc/daydream/egress.env,
  root-only, handed to this process by systemd; `bin/game prod root egress
  set <KEY>`). A route with no key answers 503, and the game runs local;
- the method and path are among the route's, with no query string;
- the body is within the route's limit.

It adds the key itself; any Authorization the caller sends is dropped, so
the game never holds one. `GET /routes` says which routes have a key (never
a key). One journal line per request: route, path, status, bytes, time;
never a body.

To add an exception (a second hosted service): a Route here with its host,
its key's name and the few requests the game makes, the key's name in the
root helper's EGRESS_KEYS, and a section in docs/EXTERNAL.md saying what it
buys and what leaves the box. Standard library only: the unit runs this file
with the system's python3, not the release's venv.
"""

from __future__ import annotations

import argparse
import http.client
import json
import logging
import os
import ssl
import sys
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger("daydream.egress")

PORT = 54323
LOOPBACK = ("127.0.0.1", "::1")


@dataclass(frozen=True)
class Route:
    host: str                      # the only host the route reaches (https, port 443)
    key_env: str                   # its key's name in /etc/daydream/egress.env
    requests: frozenset            # (method, path) pairs the game makes
    max_body: int = 256 * 1024
    max_reply: int = 2 * 1024 * 1024
    timeout: float = 10.0
    doc: str = ""


ROUTES: dict[str, Route] = {
    # Jev, TypeSafe's hosted decision model: the promise judge and topic
    # choice beside the local model (daydream/jev; docs/EXTERNAL.md#jev).
    "jev": Route(host="api.typesafe.ai", key_env="DAYDREAM_JEV_API_KEY",
                 requests=frozenset({("POST", "/v1/systemone"), ("GET", "/v1/models")}),
                 doc="docs/EXTERNAL.md#jev"),
}
# Upstream reply headers passed back (nothing that sets state or leaks more).
PASS_HEADERS = ("content-type", "retry-after", "retry-after-ms", "x-typesafe-request-id")


def key_for(route: Route) -> str | None:
    key = os.environ.get(route.key_env, "").strip()
    return key or None


def configured() -> dict[str, bool]:
    return {name: key_for(r) is not None for name, r in ROUTES.items()}


def _connect(route: Route) -> http.client.HTTPConnection:
    """The upstream connection (tests replace this)."""
    return http.client.HTTPSConnection(route.host, 443, timeout=route.timeout,
                                       context=ssl.create_default_context())


class Handler(BaseHTTPRequestHandler):
    server_version = "daydream-egress/1"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # the default logs every line to stderr raw
        pass

    def _reply(self, status: int, body: bytes, headers: dict | None = None) -> None:
        self.send_response(status)
        for k, v in (headers or {"Content-Type": "application/json"}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        # One request per connection: a refused body is never read, and must
        # never be parsed as the next request.
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: dict) -> None:
        self._reply(status, json.dumps(obj).encode())

    def do_GET(self):  # noqa: N802 - http.server's naming
        if self.path == "/routes":
            self._json(200, {"routes": configured()})
            return
        self._forward("GET")

    def do_POST(self):  # noqa: N802
        self._forward("POST")

    def _refuse(self):
        self._json(405, {"error": "method not allowed"})

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _refuse  # noqa: N815

    def _forward(self, method: str) -> None:
        t0 = time.monotonic()
        name, _, rest = self.path.lstrip("/").partition("/")
        path = "/" + rest
        route = ROUTES.get(name)
        status, sent = 0, 0
        try:
            if route is None:
                status = 404
                self._json(404, {"error": "no such route"})
                return
            if "?" in path or "#" in path or (method, path) not in route.requests:
                status = 404
                self._json(404, {"error": "not a request this route makes"})
                return
            key = key_for(route)
            if key is None:
                status = 503
                self._json(503, {"error": "this route has no key"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > route.max_body:
                status = 413
                self._json(413, {"error": "body too large"})
                return
            body = self.rfile.read(length) if length else None
            conn = _connect(route)
            try:
                conn.request(method, path, body=body, headers={
                    "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                    "Accept": "application/json", "User-Agent": "daydream-egress/1"})
                resp = conn.getresponse()
                data = resp.read(route.max_reply + 1)
                status = resp.status
                if len(data) > route.max_reply:
                    status = 502
                    self._json(502, {"error": "reply too large"})
                    return
                headers = {k: v for k, v in resp.getheaders() if k.lower() in PASS_HEADERS}
                headers.setdefault("Content-Type", "application/json")
                sent = len(data)
                self._reply(resp.status, data, headers)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001 - an upstream failure is a 502, never a crash
            status = 502
            try:
                self._json(502, {"error": f"upstream: {type(e).__name__}"})
            except Exception:  # noqa: BLE001 - the caller went away
                pass
        finally:
            logger.info("egress route=%s path=%s status=%s bytes=%s ms=%d", name, path, status,
                        sent, (time.monotonic() - t0) * 1000)


def serve(host: str, port: int) -> ThreadingHTTPServer:
    if host not in LOOPBACK:
        raise SystemExit(f"egress: refusing to listen on {host}: loopback only")
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="daydream-egress")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    srv = serve(args.host, args.port)
    logger.info("egress: listening on %s:%d; routes with a key: %s", args.host, args.port,
                ", ".join(n for n, ok in configured().items() if ok) or "none")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
