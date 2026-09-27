"""Sign a TestClient in (SPEC 2026-09-27: accounts replaced the shared
password). The account is created on first use in the test's own data dir,
then the client logs in through the real HTTP endpoint so the session cookie
is set exactly as a browser's would be. Pass a distinct `username` for each
player in a multi-client test: ownership and liveness are per account."""

from daydream import accounts, config

PASSWORD = "test-password-long-enough"


def login(client, username: str = "tester", *, role: str = "player") -> accounts.Principal:
    accounts.init()
    if accounts.get_account(username) is None:
        accounts.create_account(username, PASSWORD, role=role)
    elif role == "admin":
        accounts.set_role(username, "admin")
    r = client.post("/api/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, (r.status_code, r.text)
    token = r.cookies.get(config.cookie_name())
    who = accounts.resolve(token)
    assert who is not None
    return who
