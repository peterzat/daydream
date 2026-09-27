"""Sign-in over HTTP (SPEC 2026-09-27 criteria 2, 3, 7, 8): the front door,
login/logout, the session cookie, throttles, and invite redemption.

Rewritten for accounts. The shared-password tests, and the tailscale-mode
"the tailnet is the login" tests, encoded the retired trust model; their
replacement is test_no_location_grants_a_session below. No network location
grants anything now; every mode needs an account."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from daydream import accounts, config
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium

PW = authhelp.PASSWORD


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


def _account(username="wren", role="player"):
    accounts.init()
    return accounts.create_account(username, PW, role=role)


def _cookie_header(r) -> str:
    return next(v for k, v in r.headers.multi_items()
                if k == "set-cookie" and v.startswith(config.cookie_name() + "="))


# ---- the front door -----------------------------------------------------------


def test_signed_out_root_is_the_front_door():
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert 'id="login-form"' in r.text and "assets/door.js" in r.text
    assert 'id="room-bg"' not in r.text  # not the game shell


def test_signed_in_root_is_the_game():
    with TestClient(app) as client:
        authhelp.login(client)
        r = client.get("/")
    assert r.status_code == 200 and 'id="room-bg"' in r.text


def test_invite_path_serves_the_same_door_for_any_slug():
    with TestClient(app) as client:
        a = client.get("/invite/amber-thimble")
        b = client.get("/invite/zzz")
    assert a.status_code == b.status_code == 200 and a.text == b.text
    assert 'id="door-invite"' in a.text


# ---- login / logout / me ------------------------------------------------------


def test_login_sets_a_hardened_session_cookie(monkeypatch):
    monkeypatch.setenv("DAYDREAM_PUBLIC_BASE", "/daydream/")
    monkeypatch.setenv("DAYDREAM_PUBLIC_ORIGIN", "https://www.eidolon.com")
    _account()
    with TestClient(app) as client:
        r = client.post("/api/login", json={"username": "Wren", "password": PW},
                        headers={"origin": "https://www.eidolon.com"})
    assert r.status_code == 200 and r.json()["next"] == "/daydream/"
    c = _cookie_header(r).lower()
    assert "httponly" in c and "samesite=lax" in c and "secure" in c
    assert "path=/daydream/" in c and f"max-age={30 * 24 * 3600}" in c
    token = _cookie_header(r).split(";")[0].split("=", 1)[1]
    stored = accounts.get_conn().execute("SELECT token_hash FROM sessions").fetchall()
    assert [s["token_hash"] for s in stored] == [accounts._sha(token)]


def test_dev_cookie_is_not_secure_and_named_per_env():
    _account()
    with TestClient(app) as client:
        r = client.post("/api/login", json={"username": "wren", "password": PW})
    c = _cookie_header(r)
    assert c.startswith("dd_session_dev=") and "secure" not in c.lower()


def test_login_accepts_a_plain_form_post_too():
    _account()
    with TestClient(app) as client:
        r = client.post("/api/login", data={"username": "wren", "password": PW})
        assert r.status_code == 200
        assert client.get("/api/me").json()["username"] == "wren"


def test_wrong_password_and_unknown_user_answer_identically():
    _account()
    with TestClient(app) as client:
        a = client.post("/api/login", json={"username": "wren", "password": "not the password"})
        b = client.post("/api/login", json={"username": "nobody", "password": PW})
        assert a.status_code == b.status_code == 401
        assert a.json() == b.json()
        assert config.cookie_name() not in client.cookies
        assert client.get("/api/me").status_code == 401


def test_me_and_logout():
    _account("keeper", role="admin")
    with TestClient(app) as client:
        authhelp.login(client, "keeper")
        me = client.get("/api/me").json()
        assert me == {"username": "keeper", "display_name": "keeper", "role": "admin",
                      "is_admin": True}
        r = client.post("/api/logout")
        assert r.status_code == 200
        assert client.get("/api/me").status_code == 401
    assert accounts.get_conn().execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_disabling_an_account_ends_access_on_the_next_request():
    _account()
    with TestClient(app) as client:
        authhelp.login(client, "wren")
        assert client.get("/api/me").status_code == 200
        accounts.set_disabled("wren", True)
        assert client.get("/api/me").status_code == 401
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect("/ws"):
                pass
        assert refused.value.code == 4401


def test_change_password():
    _account()
    with TestClient(app) as client:
        authhelp.login(client, "wren")
        bad = client.post("/api/account/password", json={"old": "nope nope nope", "new": "x" * 12})
        assert bad.status_code == 400
        ok = client.post("/api/account/password", json={"old": PW, "new": "a fresh new password"})
        assert ok.status_code == 200
        assert client.get("/api/me").status_code == 200  # this session survives
    assert accounts.authenticate("wren", "a fresh new password") is not None


# ---- throttles ----------------------------------------------------------------


def test_repeated_failures_for_one_username_are_throttled():
    _account()
    with TestClient(app) as client:
        for _ in range(accounts.LOGIN_PER_USERNAME[0]):
            assert client.post("/api/login", json={"username": "wren",
                                                  "password": "wrong wrong"}).status_code == 401
        r = client.post("/api/login", json={"username": "wren", "password": PW})
    assert r.status_code == 429  # even the right password waits out the window


def test_repeated_failures_from_one_address_are_throttled():
    with TestClient(app) as client:
        for i in range(accounts.LOGIN_PER_ADDRESS[0]):
            client.post("/api/login", json={"username": f"guess{i}", "password": "x" * 12})
        r = client.post("/api/login", json={"username": "another", "password": "x" * 12})
    assert r.status_code == 429


def test_edge_mode_throttles_by_the_workers_client_ip_header(monkeypatch):
    """Behind the Worker every request arrives from cloudflared on loopback;
    the throttle keys on X-Daydream-Client-IP, so one abuser does not lock
    out everyone else."""
    monkeypatch.setenv("DAYDREAM_ACCESS", "edge")
    monkeypatch.setenv("DAYDREAM_PUBLIC_ORIGIN", "https://www.eidolon.com")
    _account()
    with TestClient(app, client=("127.0.0.1", 5000)) as client:  # cloudflared's peer
        for i in range(accounts.LOGIN_PER_ADDRESS[0]):
            client.post("/api/login", json={"username": f"guess{i}", "password": "x" * 12},
                        headers={"x-daydream-client-ip": "203.0.113.9"})
        blocked = client.post("/api/login", json={"username": "wren", "password": PW},
                              headers={"x-daydream-client-ip": "203.0.113.9"})
        fine = client.post("/api/login", json={"username": "wren", "password": PW},
                           headers={"x-daydream-client-ip": "198.51.100.4"})
    assert blocked.status_code == 429 and fine.status_code == 200


# ---- invites over HTTP -------------------------------------------------------------


@pytest.fixture
def words(monkeypatch):
    monkeypatch.setattr(accounts, "_words_cache", {
        "adjectives": [f"adj{i:03d}" for i in range(300)],
        "nouns": [f"noun{i:03d}" for i in range(300)],
    })


def test_invite_peek_and_redeem_sign_the_invitee_in(words, monkeypatch):
    monkeypatch.setenv("DAYDREAM_OPERATOR_NAME", "Peter")
    accounts.init()
    slug, _ = accounts.create_invite("Robin Ash")
    with TestClient(app) as client:
        peek = client.post("/api/invite/peek", json={"slug": slug})
        assert peek.json() == {"for": "Robin Ash", "kind": "join", "operator": "Peter"}
        r = client.post("/api/invite/redeem",
                        json={"slug": slug, "username": "robin", "password": PW})
        assert r.status_code == 200
        assert client.get("/api/me").json()["display_name"] == "Robin Ash"
        again = client.post("/api/invite/redeem",
                            json={"slug": slug, "username": "robin2", "password": PW})
        assert again.status_code == 404 and "Peter" in again.json()["error"]


def test_a_taken_username_or_short_password_keeps_the_invite(words):
    accounts.init()
    accounts.create_account("robin", PW)
    slug, _ = accounts.create_invite("Robin Ash")
    with TestClient(app) as client:
        r = client.post("/api/invite/redeem", json={"slug": slug, "username": "robin",
                                                    "password": PW})
        assert r.status_code == 400 and "taken" in r.json()["error"]
        r = client.post("/api/invite/redeem", json={"slug": slug, "username": "robin-a",
                                                    "password": "short"})
        assert r.status_code == 400
        r = client.post("/api/invite/redeem", json={"slug": slug, "username": "robin-a",
                                                    "password": PW})
        assert r.status_code == 200


def test_reset_invite_over_http(words):
    _account()
    slug, _ = accounts.create_invite("", kind="reset", account="wren")
    with TestClient(app) as client:
        assert client.post("/api/invite/peek", json={"slug": slug}).json()["kind"] == "reset"
        r = client.post("/api/invite/redeem", json={"slug": slug, "password": "brand new password"})
        assert r.status_code == 200
        assert client.get("/api/me").json()["username"] == "wren"
    assert accounts.authenticate("wren", "brand new password") is not None


def test_failed_redemptions_hit_a_global_cap(words):
    with TestClient(app) as client:
        n = accounts.REDEEM_PER_ADDRESS[0]
        for i in range(n):
            assert client.post("/api/invite/peek", json={"slug": f"nope-{i}"}).status_code == 404
        assert client.post("/api/invite/peek", json={"slug": "nope-x"}).status_code == 429
    # The global hourly budget counts every address's failures.
    accounts.init()
    for _ in range(accounts.REDEEM_GLOBAL_HOUR[0]):
        accounts.record_failure("redeem-hour", accounts.REDEEM_GLOBAL_HOUR)
    slug, _ = accounts.create_invite("Robin Ash")
    with TestClient(app, client=("198.51.100.7", 4000)) as other:
        assert other.post("/api/invite/peek", json={"slug": slug}).status_code == 429


# ---- no network location grants a session ------------------------------------


@pytest.mark.parametrize("mode", ["tailscale", "public"])
@pytest.mark.parametrize("peer", ["127.0.0.1", "100.64.1.2"])
def test_no_location_grants_a_session(monkeypatch, mode, peer):
    """The retired model let the tailnet stand in for a login. Now loopback
    and tailnet peers without a session get the gate's 401, in every mode."""
    monkeypatch.setenv("DAYDREAM_ACCESS", mode)
    with TestClient(app, client=(peer, 5000)) as client:
        assert client.get("/api/slots").status_code == 401
        assert client.get("/api/me").status_code == 401
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect("/ws"):
                pass
        assert refused.value.code == 4401


# ---- review fixes (SECURITY 2026-09-27) ---------------------------------------------


def test_the_cli_identities_cannot_be_taken_through_an_invite(words):
    accounts.init()
    for name in ("cli-operator", "agent-probe", "admin", "Keeper"):
        slug, _ = accounts.create_invite("Squatter")
        with pytest.raises(accounts.AccountError, match="taken"):
            accounts.redeem_join(slug, name, PW)
        assert accounts.peek_invite(slug) is not None  # the invite survives


def test_a_global_pause_says_so_and_the_operator_can_reopen(words, monkeypatch):
    monkeypatch.setenv("DAYDREAM_OPERATOR_NAME", "Peter")
    accounts.init()
    for _ in range(accounts.REDEEM_GLOBAL_HOUR[0]):
        accounts.record_failure("redeem-hour", accounts.REDEEM_GLOBAL_HOUR)
    slug, _ = accounts.create_invite("Robin Ash")
    with TestClient(app) as client:
        r = client.post("/api/invite/peek", json={"slug": slug})
        assert r.status_code == 429 and "ask Peter" in r.json()["error"]
        from daydream import accounts_cli
        assert accounts_cli.main(["invite", "unblock"]) == 0
        accounts.init()
        assert client.post("/api/invite/peek", json={"slug": slug}).status_code == 200


def test_ipv6_throttles_key_on_the_64():
    from daydream.api import auth as auth_mod

    a = auth_mod.throttle_address("2001:db8:1:2:aaaa::1")
    b = auth_mod.throttle_address("2001:db8:1:2:ffff::9")
    assert a == b == "2001:db8:1:2::/64"
    assert auth_mod.throttle_address("203.0.113.9") == "203.0.113.9"


def test_edge_csrf_checks_the_scheme_too(monkeypatch):
    from daydream.api.csrf import origin_allows

    monkeypatch.setenv("DAYDREAM_PUBLIC_ORIGIN", "https://www.eidolon.com")
    assert origin_allows([(b"origin", b"https://www.eidolon.com")])
    assert not origin_allows([(b"origin", b"http://www.eidolon.com")])
    assert not origin_allows([(b"origin", b"https://eidolon.com")])
