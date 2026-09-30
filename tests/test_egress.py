"""The egress gateway (daydream/egress.py; docs/EXTERNAL.md): prod's one way
out of its sandbox forwards only a declared route's own requests, adds the
route's key itself (dropping any the caller sends), says which routes have
a key without saying the key, and listens on loopback only. The upstream is
a fake connection: no network."""

import http.client
import json
import threading

import pytest

from daydream import egress

pytestmark = pytest.mark.tier_short


class FakeResp:
    def __init__(self, status, body, headers):
        self.status, self._body, self._headers = status, body, headers

    def read(self, n):
        return self._body[:n]

    def getheaders(self):
        return self._headers


class FakeConn:
    sent: list = []
    reply = (200, b'{"answers": {}}', [("Content-Type", "application/json"),
                                        ("x-typesafe-request-id", "req_9"),
                                        ("set-cookie", "no=1")])

    def __init__(self, route):
        self.route = route

    def request(self, method, path, body=None, headers=None):
        FakeConn.sent.append({"host": self.route.host, "method": method, "path": path,
                              "body": body, "headers": headers})

    def getresponse(self):
        return FakeResp(*FakeConn.reply)

    def close(self):
        pass


@pytest.fixture()
def gateway(monkeypatch):
    monkeypatch.setenv("DAYDREAM_JEV_API_KEY", "gw-key")
    monkeypatch.setattr(egress, "_connect", FakeConn)
    FakeConn.sent = []
    srv = egress.serve("127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    port = srv.server_address[1]

    def call(method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, r.read(), dict(r.getheaders())

    yield call
    srv.shutdown()
    srv.server_close()


def test_it_forwards_a_declared_request_with_the_routes_own_key(gateway):
    status, body, headers = gateway("POST", "/jev/v1/systemone", body=b'{"state": 1}',
                                    headers={"Authorization": "Bearer caller-key",
                                             "Content-Type": "application/json"})
    assert status == 200 and json.loads(body) == {"answers": {}}
    [sent] = FakeConn.sent
    assert sent["host"] == "api.typesafe.ai" and sent["path"] == "/v1/systemone"
    assert sent["headers"]["Authorization"] == "Bearer gw-key"  # the caller's is dropped
    assert sent["body"] == b'{"state": 1}'
    assert headers.get("x-typesafe-request-id") == "req_9"
    assert "set-cookie" not in {k.lower() for k in headers}


def test_it_says_which_routes_have_a_key_and_never_the_key(gateway, monkeypatch):
    status, body, _ = gateway("GET", "/routes")
    assert status == 200 and json.loads(body) == {"routes": {"jev": True}}
    assert b"gw-key" not in body
    monkeypatch.delenv("DAYDREAM_JEV_API_KEY")
    assert json.loads(gateway("GET", "/routes")[1]) == {"routes": {"jev": False}}
    status, _, _ = gateway("POST", "/jev/v1/systemone", body=b"{}")
    assert status == 503 and FakeConn.sent == []  # no key: nothing leaves


@pytest.mark.parametrize("method,path,status", [
    ("POST", "/nope/v1/systemone", 404),       # no such route
    ("POST", "/jev/v1/other", 404),            # not a request the route makes
    ("GET", "/jev/v1/systemone", 404),         # the wrong method for it
    ("POST", "/jev/v1/systemone?x=1", 404),    # no query strings
    ("PUT", "/jev/v1/systemone", 405),
    ("DELETE", "/jev/v1/models", 405),
])
def test_it_refuses_everything_else(gateway, method, path, status):
    assert gateway(method, path, body=b"{}")[0] == status
    assert FakeConn.sent == []


def test_a_body_over_the_limit_is_refused(gateway):
    big = b"x" * (egress.ROUTES["jev"].max_body + 1)
    assert gateway("POST", "/jev/v1/systemone", body=big)[0] == 413
    assert FakeConn.sent == []


def test_an_upstream_failure_is_a_502(gateway, monkeypatch):
    class Boom(FakeConn):
        def getresponse(self):
            raise OSError("reset")

    monkeypatch.setattr(egress, "_connect", Boom)
    status, body, _ = gateway("POST", "/jev/v1/systemone", body=b"{}")
    assert status == 502 and b"upstream" in body


def test_it_listens_on_loopback_only():
    with pytest.raises(SystemExit):
        egress.serve("0.0.0.0", 0)


def test_it_is_standard_library_only():
    """The unit runs it with the system's python3, outside the release venv."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(egress.__file__).read_text())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
            for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"__future__", "argparse", "http", "json", "logging", "os", "ssl", "sys",
                    "time", "dataclasses"}, mods
