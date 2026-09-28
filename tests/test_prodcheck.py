"""`bin/game prod check` (daydream/prodcheck.py): the live invariants the
bring-up verified by hand, as pure checks over canned replies."""

import json

import pytest

from daydream import prodcheck
from daydream.prodcheck import Reply, Target

pytestmark = pytest.mark.tier_short

T = Target("https://www.example.org", "/daydream/", "daydream-origin.example.org")
ROOT = "https://www.example.org/daydream/"


def fake_edge(*, awake=True, leak=False, origin_open=False, door_base="/daydream/",
              unplanned=False):
    """A request() standing in for the network: the edge as it should behave,
    with one thing broken on demand."""
    def request(method, url, headers=None, body=None):
        headers = headers or {}
        if url == ROOT + "edge/status":
            state = "awake" if awake else "asleep"
            return Reply(200, [], json.dumps({"state": state, "note": "",
                                               "unplanned": unplanned}).encode())
        if url == ROOT and method == "GET":
            if not awake:
                return Reply(503, [], b"<h1>The village is asleep</h1>")
            return Reply(200, [], f'<base href="{door_base}">'.encode())
        if url == ROOT + "api/me":
            return (Reply(401, [], b'{"error":"sign in first"}') if awake
                    else Reply(503, [], b'{"asleep": true}'))
        if url == ROOT + "api/login":
            return Reply(403 if headers.get("Origin") == "https://example.invalid" else 401)
        if url == ROOT.rstrip("/") or url == "https://example.org/daydream/":
            return Reply(301, [("Location", ROOT)])
        if url == "https://daydream-origin.example.org/healthz":
            return Reply(200 if origin_open else 403)
        if url == ROOT + "ws":
            cookies = [("Set-Cookie", "CF_Authorization=jwt; Path=/")] if leak else []
            return Reply(403 if awake else 503, cookies)
        raise AssertionError(f"unexpected {method} {url}")
    return request


def session(frames=("needs_toon",), close=1000, status=101, cookies=()):
    return lambda url, cookie, origin: (status, list(cookies), list(frames), close)


def failed(checks):
    return sorted(c.name for c in checks if not c.ok)


def test_a_healthy_awake_village_passes_everything():
    checks = prodcheck.run(T, awake=True, flag="awake", cookie="dd_session_prod=t",
                           cookie_name="dd_session_prod", request=fake_edge(), session=session())
    assert failed(checks) == []
    assert {c.name for c in checks} >= {"edge status", "front door", "api signed out",
                                        "cross-origin login", "no-slash redirect", "apex redirect",
                                        "origin locked", "anonymous ws upgrade", "session ws"}


def test_an_asleep_village_expects_the_asleep_answers():
    checks = prodcheck.run(T, awake=False, flag="asleep", cookie=None,
                           cookie_name="dd_session_prod", request=fake_edge(awake=False))
    assert failed(checks) == []
    assert "session ws" not in {c.name for c in checks}


def test_the_access_cookie_leak_is_caught():
    """The 2026-09-28 BLOCK: the Worker passed CF_Authorization on upgrades."""
    checks = prodcheck.run(T, awake=True, flag="awake", cookie="dd_session_prod=t",
                           cookie_name="dd_session_prod", request=fake_edge(leak=True),
                           session=session(cookies=[("Set-Cookie", "CF_Authorization=x")]))
    assert failed(checks) == ["anonymous ws upgrade", "session ws"]


def test_an_open_origin_and_a_wrong_base_are_caught():
    checks = prodcheck.run(T, awake=True, flag="awake", cookie=None,
                           cookie_name="dd_session_prod",
                           request=fake_edge(origin_open=True, door_base="/"))
    assert failed(checks) == ["front door", "origin locked"]


def test_awake_prod_that_the_edge_calls_asleep_names_the_likely_cause():
    checks = prodcheck.run(T, awake=True, flag="awake", cookie=None,
                           cookie_name="dd_session_prod",
                           request=fake_edge(awake=False, unplanned=True))
    status = next(c for c in checks if c.name == "edge status")
    assert not status.ok and "tunnel or service" in status.detail


def test_a_socket_dropped_without_a_close_frame_fails():
    """The needs_toon frame was lost at the edge until the app closed with 1000."""
    c = prodcheck.check_ws_session(101, [], ["needs_toon"], None)
    assert not c.ok and "1000" in c.detail


def test_timer_results():
    assert prodcheck.check_timer("daydream-backup.service",
                                 {"Result": "success", "ExecMainExitTimestamp": "n/a"}).ok
    ok = prodcheck.check_timer("daydream-backup.service",
                               {"Result": "success", "ExecMainExitTimestamp": "Mon 04:30"})
    bad = prodcheck.check_timer("daydream-keepsakes.service",
                                {"Result": "exit-code", "ExecMainExitTimestamp": "Mon 02:03"})
    assert ok.ok and not bad.ok and "journalctl -u daydream-keepsakes.service" in bad.detail


def test_report_exit_status():
    lines = []
    assert prodcheck.report([prodcheck.Check("a", True, "fine")], lines.append) == 0
    assert prodcheck.report([prodcheck.Check("a", False, "broken")], lines.append) == 1
    assert any(line.startswith("FAIL a") for line in lines)


def test_the_target_comes_from_prod_env_and_wrangler_toml():
    t = prodcheck.target_from_config({"DAYDREAM_PUBLIC_ORIGIN": "https://www.eidolon.com/",
                                      "DAYDREAM_PUBLIC_BASE": "/daydream/"})
    assert (t.public, t.base, t.root) == ("https://www.eidolon.com", "/daydream/",
                                          "https://www.eidolon.com/daydream/")
    assert t.apex == "eidolon.com" and t.origin_host.startswith("daydream-origin.")
